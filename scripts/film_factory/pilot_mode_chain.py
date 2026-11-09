#!/usr/bin/env python3
"""Pilot Mode A/B/C dry-run chain + minimal state ledger (no Muse quota)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.film_factory.assemble_policy import filter_pass_clips
from lib.film_factory.continuity import classify_continuity
from lib.film_factory.first_frame import build_image_plan
from lib.film_factory.prompt_pack import get_pack, load_project_overlay
from lib.film_factory.qa_tiers import score_to_tier
from lib.film_factory.series_manager import SeriesManager
from lib.film_factory.take_storage import TakeRecord, TakeStore
from tools.video.muse2_video import Muse2Video


def main() -> int:
    out = Path("/tmp/film_factory_pilot")
    out.mkdir(parents=True, exist_ok=True)
    pack = get_pack("bushcraft_asmr", "v1")
    overlay = load_project_overlay("solo_survival")
    sm = SeriesManager(out / "series")
    sm.init_series(
        series_id="solo_survival_pilot",
        title="Pilot",
        category_id=pack.id,
        project_id="solo_survival",
        cast_lock=["Protagonist"],
    )
    ep = sm.begin_episode()
    store = TakeStore(out / "takes.json")
    tool = Muse2Video()

    clips = [
        {"id": "C1", "continue": False, "location": "forest", "time": "dawn", "shot": "wide", "mode": "first"},
        {"id": "C2", "continue": True, "location": "forest", "time": "dawn", "shot": "wide", "mode": "A"},
        {"id": "C3", "continue": False, "location": "forest", "time": "dawn", "shot": "close", "mode": "B"},
        {"id": "C4", "continue": False, "location": "creek", "time": "morning", "shot": "wide", "mode": "C"},
    ]
    prev = None
    prev_ff = "file:///tmp/fake_prev.png"
    results = []
    for i, c in enumerate(clips):
        mode = c["mode"]
        kind = classify_continuity(prev, c, mode)
        if mode == "B":
            plan = build_image_plan(
                mode="B",
                first_frame_url="file:///tmp/fake_new_angle.png",
                prev_pass_last_frame=prev_ff,
                character_sheets=[{"url": "file:///tmp/char_sheet.png", "name": "Protagonist"}],
            )
        elif mode == "C":
            plan = build_image_plan(
                mode="C",
                first_frame_url="file:///tmp/fake_new_scene.png",
                prev_pass_last_frame=prev_ff,
            )
        elif mode == "A":
            plan = build_image_plan(mode="A", prev_pass_last_frame=prev_ff)
        else:
            plan = build_image_plan(mode="first", first_frame_url=None)

        assert plan.ok, plan.error
        dry = tool.execute(
            {
                "prompt": pack.prompt("draft")[:200] + f"\nBEAT {c['id']}",
                "mode": mode,
                "first_frame_url": plan.images[0].url if plan.images else None,
                "prev_pass_last_frame": prev_ff if mode in ("A", "B", "C") else None,
                "character_sheets": [{"url": "file:///tmp/char_sheet.png", "name": "Protagonist"}]
                if mode == "B"
                else [],
                "dry_run": True,
                "clip_id": c["id"],
                "pack_id": pack.id,
                "pack_version": pack.version,
                "take_store_path": str(out / "takes.json"),
                "aspect_ratio": pack.defaults.get("aspect", "16:9"),
            }
        )
        # dry_run with sheets for B goes through build_image_plan inside tool
        assert dry.success, dry.error
        qa = score_to_tier(
            scores={"beat": 2, "cast": 2, "continuity": 2, "realism": 2, "trash": 2},
            issues=[],
            profile=pack.qa_profile,
        )
        c["qa_tier"] = qa.tier
        c["qa"] = qa.to_dict()
        c["continuity_kind"] = kind.value
        tid = TakeStore.new_take_id()
        store.add(
            TakeRecord(
                take_id=tid,
                clip_id=c["id"],
                status="selected",
                prompt="pilot",
                pack_id=pack.id,
                pack_version=pack.version,
                image_roles=plan.role_map(),
                qa=qa.to_dict(),
                first_frame_mode=mode,
            )
        )
        if i == 0:
            sm.ledger.set_observed("at_camp", True, source_clip="C1", evidence="pilot", confidence=0.8)
            sm.ledger.validate("at_camp", evidence="pilot")
        results.append({"clip": c["id"], "mode": mode, "kind": kind.value, "tier": qa.tier})
        prev = c
        prev_ff = f"file:///tmp/last_{c['id']}.png"

    # Inject a FAIL and ensure assemble drops it
    clips.append({"id": "CBAD", "qa_tier": "FAIL", "qa": {"pass": False}})
    kept, _ = filter_pass_clips(clips)
    assert all(c["id"] != "CBAD" for c in kept)
    summary = {
        "episode": ep,
        "pack": pack.to_dict(),
        "overlay_project": overlay["project_id"],
        "results": results,
        "compose_count": len(kept),
    }
    (out / "pilot_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
