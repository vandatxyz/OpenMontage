from __future__ import annotations

from lib.film_factory.continuity import ContinuityKind, classify_continuity
from lib.film_factory.series_manager import SeriesManager
from tools.video.muse2_video import Muse2Video


def test_continuity_kinds():
    prev = {"location": "camp", "time": "dawn", "shot": "wide"}
    assert classify_continuity(prev, {"continue": True, "location": "camp", "time": "dawn", "shot": "wide"}, "A") == ContinuityKind.CONTINUOUS
    assert classify_continuity(prev, {"continue": False, "location": "camp", "time": "dawn", "shot": "close"}, "B") == ContinuityKind.ANGLE_CHANGE
    assert classify_continuity(prev, {"continue": False, "location": "river", "time": "dawn"}, "C") == ContinuityKind.SCENE_CUT
    assert classify_continuity(prev, {"continue": False, "location": "camp", "time": "dusk"}, "C") == ContinuityKind.TIME_JUMP


def test_series_manager(tmp_path):
    sm = SeriesManager(tmp_path / "solo_survival")
    sm.init_series(
        series_id="solo_survival",
        title="Solo Bushcraft",
        category_id="bushcraft_asmr",
        project_id="solo_survival",
        cast_lock=["Protagonist"],
    )
    sm.ledger.set_planned("shelter", "frame", source_clip="E1C1")
    sm.ledger.set_observed("shelter", "frame", source_clip="E1C1", evidence="f", confidence=0.7)
    sm.ledger.validate("shelter", evidence="ok")
    ep = sm.begin_episode()
    assert ep["episode_index"] == 1
    assert "shelter" in ep["seed_state"]


def test_muse2_dry_run_and_role_enforcement(monkeypatch):
    tool = Muse2Video()
    # Even without key, dry_run path still validates roles first — inject key for dry_run path
    monkeypatch.setenv("MUSE2API_KEY", "test-only")
    res = tool.execute(
        {
            "prompt": "test",
            "mode": "C",
            "prop_sheets": [{"url": "https://x/sheet.png", "name": "axe"}],
            "dry_run": True,
        }
    )
    assert res.success is False
    assert "missing first_frame" in (res.error or "")

    ok = tool.execute(
        {
            "prompt": "Wide empty forest, photoreal, no people",
            "mode": "first",
            "duration": 5,
            "aspect_ratio": "16:9",
            "dry_run": True,
        }
    )
    assert ok.success
    assert ok.data.get("dry_run") is True


def test_registry_discovers_muse2_despite_optional_import_failures():
    from tools.tool_registry import ToolRegistry

    r = ToolRegistry()
    r.clear()
    r.ensure_discovered()
    names = set(r.list_all())
    assert "muse2_video" in names
    assert "frame_integrity_scan" in names
    assert "visual_qa_film" in names
    assert "audio_qa_asmr" in names
    assert "pass_only_assemble" in names
