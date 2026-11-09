#!/usr/bin/env python3
"""Smoke Muse2 adapter (dry-run by default). Use --live to call muse2api once."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.video.muse2_video import Muse2Video  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--prompt", default="Photorealistic wide shot of a quiet snowy forest clearing at dawn, empty, no people, steady camera, 5 seconds.")
    args = ap.parse_args()
    tool = Muse2Video()
    print("status", tool.get_status().value)
    inputs = {
        "prompt": args.prompt,
        "duration": 5,
        "aspect_ratio": "16:9",
        "mode": "first",
        "dry_run": not args.live,
        "clip_id": "SMOKE1",
        "pack_id": "bushcraft_asmr",
        "pack_version": "v1",
    }
    # Mode B regression: sheets must not become Image 1 when FF missing
    bad = tool.execute(
        {
            **inputs,
            "mode": "B",
            "character_sheets": [{"url": "https://example.com/sheet.png", "name": "Hero"}],
            "dry_run": True,
        }
    )
    print("mode_B_missing_ff", bad.success, bad.error)
    assert not bad.success, "Mode B without first_frame must fail"

    ok = tool.execute(inputs)
    print("result", ok.success, ok.error or ok.data)
    return 0 if ok.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
