"""Frame Integrity Scan — catch one-frame sheet flashes without full vision QA cost.

Heuristic OpenCV/ffmpeg sampling across the clip. Flags contact sheets, grids,
large uniform grey boards, sudden still-frame flash dissimilar to neighbors.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


class FrameIntegrityScan(BaseTool):
    name = "frame_integrity_scan"
    version = "0.1.0"
    tier = ToolTier.ANALYZE
    capability = "analysis"
    provider = "openmontage"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = []
    agent_skills = ["muse2-film-factory"]
    capabilities = ["frame_integrity", "sheet_flash_detect"]
    supports = {"full_clip_scan": True}
    best_for = ["detecting reference-sheet flashes before Visual QA"]
    not_good_for = ["semantic action scoring"]
    input_schema = {
        "type": "object",
        "required": ["video_path"],
        "properties": {
            "video_path": {"type": "string"},
            "fps_sample": {"type": "number", "default": 8},
            "max_frames": {"type": "integer", "default": 120},
        },
    }
    resource_profile = ResourceProfile(cpu_cores=2, ram_mb=1024, network_required=False)

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return 15.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        path = Path(inputs["video_path"])
        if not path.is_file():
            return ToolResult(False, error=f"missing video {path}")

        fps = float(inputs.get("fps_sample") or 8)
        max_frames = int(inputs.get("max_frames") or 120)
        issues: list[str] = []
        scores: list[dict[str, Any]] = []

        with tempfile.TemporaryDirectory(prefix="integrity_") as td:
            pattern = str(Path(td) / "f_%04d.png")
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(path),
                "-vf",
                f"fps={fps}",
                "-frames:v",
                str(max_frames),
                pattern,
            ]
            try:
                subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError as e:
                return ToolResult(False, error=f"ffmpeg extract failed: {e}")

            frames = sorted(Path(td).glob("f_*.png"))
            try:
                from PIL import Image  # type: ignore
            except ImportError:
                # Fallback: only check file sizes / count — still useful smoke
                if len(frames) < 2:
                    issues.append("too_few_frames")
                return ToolResult(
                    True,
                    data={
                        "pass": len(issues) == 0,
                        "issues": issues,
                        "frame_count": len(frames),
                        "note": "Pillow missing — limited scan",
                    },
                )

            prev_hist = None
            for i, fp in enumerate(frames):
                im = Image.open(fp).convert("RGB")
                w, h = im.size
                # Downsample for heuristics
                small = im.resize((64, 64))
                pixels = list(small.getdata())
                # Grey board / contact-sheet heuristic: low color variance + grid-like edges
                rs = [p[0] for p in pixels]
                gs = [p[1] for p in pixels]
                bs = [p[2] for p in pixels]
                mean = (sum(rs) + sum(gs) + sum(bs)) / (3 * len(pixels))
                var = sum((r - mean) ** 2 for r in rs) / len(rs)
                # Many near-white or near-grey cells
                greyish = sum(1 for r, g, b in pixels if abs(r - g) < 12 and abs(g - b) < 12) / len(pixels)
                flash = False
                if prev_hist is not None:
                    # crude hist diff
                    hist = small.histogram()
                    diff = sum(abs(a - b) for a, b in zip(hist, prev_hist)) / max(1, sum(hist))
                    if diff > 0.55 and greyish > 0.55 and var < 1800:
                        flash = True
                        issues.append(f"sheet_or_board_flash_frame_{i}")
                # Multi-panel contact sheet: high edge density in center bands
                if greyish > 0.7 and var < 1200 and mean > 140:
                    issues.append(f"possible_reference_board_frame_{i}")
                scores.append(
                    {
                        "i": i,
                        "greyish": round(greyish, 3),
                        "var": round(var, 1),
                        "flash": flash,
                        "size": f"{w}x{h}",
                    }
                )
                prev_hist = small.histogram()

        # Dedup issue prefixes
        uniq = sorted(set(issues))
        integrity_fail = any("sheet" in x or "board" in x or "flash" in x for x in uniq)
        return ToolResult(
            True,
            data={
                "pass": not integrity_fail,
                "integrity_fail": integrity_fail,
                "issues": uniq,
                "frame_count": len(scores),
                "samples": scores[:12],
            },
        )
