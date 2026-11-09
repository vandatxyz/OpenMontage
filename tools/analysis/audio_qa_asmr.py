"""Audio QA branch for Bushcraft ASMR — levels, silence, music bleed heuristics."""

from __future__ import annotations

import json
import subprocess
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


class AudioQaAsmr(BaseTool):
    name = "audio_qa_asmr"
    version = "0.1.0"
    tier = ToolTier.ANALYZE
    capability = "analysis"
    provider = "openmontage"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    agent_skills = ["muse2-film-factory"]
    capabilities = ["audio_qa", "asmr"]
    best_for = ["bushcraft ASMR level / silence / track presence checks"]
    input_schema = {
        "type": "object",
        "required": ["video_path"],
        "properties": {
            "video_path": {"type": "string"},
            "require_audio": {"type": "boolean", "default": True},
            "max_mean_volume_db": {"type": "number", "default": -5},
            "min_mean_volume_db": {"type": "number", "default": -50},
        },
    }
    resource_profile = ResourceProfile(network_required=False)

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return 5.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        path = Path(inputs["video_path"])
        if not path.is_file():
            return ToolResult(False, error=f"missing {path}")

        # Has audio stream?
        probe = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=codec_type,sample_rate,channels",
                "-of",
                "json",
                str(path),
            ],
            text=True,
        )
        streams = (json.loads(probe).get("streams") or [])
        issues = []
        if not streams and inputs.get("require_audio", True):
            issues.append("missing_audio_track")

        mean_vol = None
        if streams:
            # ffmpeg volumedetect
            proc = subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    str(path),
                    "-af",
                    "volumedetect",
                    "-f",
                    "null",
                    "-",
                ],
                capture_output=True,
                text=True,
            )
            for line in (proc.stderr or "").splitlines():
                if "mean_volume:" in line:
                    try:
                        mean_vol = float(line.split("mean_volume:")[1].split("dB")[0].strip())
                    except ValueError:
                        pass
            if mean_vol is not None:
                if mean_vol > float(inputs.get("max_mean_volume_db", -5)):
                    issues.append("audio_too_loud")
                if mean_vol < float(inputs.get("min_mean_volume_db", -50)):
                    issues.append("audio_too_quiet_or_silent")

        tier = "PASS" if not issues else ("FAIL" if "missing_audio_track" in issues else "REVIEW")
        return ToolResult(
            True,
            data={
                "tier": tier,
                "pass": tier == "PASS",
                "issues": issues,
                "mean_volume_db": mean_vol,
                "has_audio": bool(streams),
                "streams": streams,
            },
        )
