"""Regression gates from Zahna lessons — intentional failure cases must be blocked."""

from __future__ import annotations

from fractions import Fraction

import pytest

from lib.film_factory.aspect_gate import check_aspect
from lib.film_factory.assemble_policy import decide_assemble, filter_pass_clips
from lib.film_factory.first_frame import build_image_plan
from lib.film_factory.prompt_pack import get_pack, list_packs, load_project_overlay
from lib.film_factory.qa_tiers import ZAHNA_REGRESSION, score_to_tier
from lib.film_factory.state_ledger import StateLedger
from lib.film_factory.take_storage import TakeRecord, TakeStore


def test_mode_b_missing_first_frame_rejects_sheet_as_image1():
    plan = build_image_plan(
        mode="B",
        first_frame_url=None,
        prev_pass_last_frame="https://example.com/prev.png",
        character_sheets=[{"url": "https://example.com/char.png", "name": "Zahna"}],
    )
    assert not plan.ok
    assert "missing first_frame" in (plan.error or "")


def test_mode_b_with_first_frame_puts_sheet_after():
    plan = build_image_plan(
        mode="B",
        first_frame_url="https://example.com/new_ff.png",
        prev_pass_last_frame="https://example.com/prev.png",
        character_sheets=[{"url": "https://example.com/char.png", "name": "Zahna"}],
        prop_sheets=[{"url": "https://example.com/prop.png", "name": "wood"}],
    )
    assert plan.ok
    assert plan.images[0].role == "first_frame"
    roles = [i.role for i in plan.images]
    assert "character_sheet" in roles
    assert roles.index("character_sheet") > 0
    assert roles[-1] == "continuity_frame"


def test_mode_a_requires_prev_pass_frame():
    plan = build_image_plan(mode="A", first_frame_url=None, prev_pass_last_frame=None)
    assert not plan.ok


def test_aspect_wrong_dar_fails_right_dar_normalizes():
    # 9:16 into 16:9 episode
    d = check_aspect(expected_aspect="16:9", width=720, height=1280)
    assert d.action == "fail"
    # 1920x1080 is 16:9 → normalize
    d2 = check_aspect(expected_aspect="16:9", width=1920, height=1080)
    assert d2.action == "normalize"
    # exact
    d3 = check_aspect(expected_aspect="16:9", width=1280, height=720)
    assert d3.action == "pass"
    # C99-like
    d4 = check_aspect(expected_aspect="16:9", actual_dar=Fraction(9, 16))
    assert d4.action == "fail"


def test_fail_clip_not_assembled_review_blocked():
    clips = [
        {"id": "C77", "qa_tier": "FAIL", "qa": {"pass": False, "total": 7}},
        {"id": "C83", "qa": {"pass": False, "total": 7}},
        {"id": "C10", "qa_tier": "PASS", "qa": {"pass": True, "total": 10}},
        {"id": "C11", "qa_tier": "REVIEW", "qa": {"pass": True, "total": 8}},
    ]
    kept, decisions = filter_pass_clips(clips)
    ids = [c["id"] for c in kept]
    assert ids == ["C10"]
    assert decide_assemble(clips[0]).include is False
    assert decide_assemble(clips[3]).include is False
    # approved review may enter
    clips[3]["approved"] = True
    assert decide_assemble(clips[3]).include is True


def test_qa_hard_fail_sheet_and_axis_one_is_review():
    r = score_to_tier(
        scores={"beat": 2, "cast": 2, "continuity": 2, "realism": 2, "trash": 2},
        issues=["character_sheet_in_frame at 0.0s"],
    )
    assert r.tier == "FAIL"
    r2 = score_to_tier(
        scores={"beat": 1, "cast": 2, "continuity": 2, "realism": 2, "trash": 2},
        issues=[],
    )
    assert r2.tier == "REVIEW"
    assert "C17" in ZAHNA_REGRESSION["sheet_flash"]


def test_state_ledger_no_auto_validate_from_planned(tmp_path):
    led = StateLedger(tmp_path / "ledger.json")
    led.set_planned("fire", "stable", source_clip="C1")
    with pytest.raises(ValueError):
        led.validate("fire", evidence="nope")
    led.set_observed("fire", "ember", source_clip="C1", evidence="frame@2s", confidence=0.6)
    led.validate("fire", evidence="qa confirmed", confidence=0.95)
    seed = led.seed_for_next_clip()
    assert seed["fire"]["confirmation"] == "validated"


def test_take_storage_roundtrip(tmp_path):
    store = TakeStore(tmp_path / "takes.json")
    tid = TakeStore.new_take_id()
    store.add(
        TakeRecord(
            take_id=tid,
            clip_id="C1",
            status="pending",
            prompt="test",
            pack_id="bushcraft_asmr",
            pack_version="v1",
            image_roles=[{"n": 1, "role": "first_frame"}],
        )
    )
    store.select(tid, reason="best")
    assert store.selected("C1").take_id == tid


def test_packs_load():
    ids = {p["id"] for p in list_packs()}
    assert {"animation_cartoon", "doc_observational", "bushcraft_asmr"} <= ids
    for cid in ("animation_cartoon", "doc_observational", "bushcraft_asmr"):
        pack = get_pack(cid, "v1")
        assert pack.prompt("draft")
        assert pack.prompt("director")
    ov = load_project_overlay("zahna")
    assert "Photorealistic" in ov["hardcode"]
