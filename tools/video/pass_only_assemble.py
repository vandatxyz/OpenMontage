"""PASS-only assemble gate for film-factory pipelines.

Filters clip lists before FFmpeg/Remotion compose. FAIL never enters final;
REVIEW requires approved=true.
"""

from __future__ import annotations

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

from lib.film_factory.pass_only_compose import build_compose_clip_list


class PassOnlyAssemble(BaseTool):
    name = "pass_only_assemble"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "video_editing"
    provider = "openmontage"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    agent_skills = ["muse2-film-factory"]
    capabilities = ["pass_only_assemble", "qa_gate"]
    best_for = ["blocking FAIL/REVIEW clips from final episode assemble"]
    not_good_for = ["bypassing QA for speed"]
    input_schema = {
        "type": "object",
        "required": ["clips"],
        "properties": {
            "clips": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Clip dicts with id, qa_tier|qa, optional approved",
            },
            "require_human_review": {"type": "boolean", "default": True},
        },
    }
    resource_profile = ResourceProfile(network_required=False)

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return 0.05

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        clips = list(inputs.get("clips") or [])
        if not clips:
            return ToolResult(False, error="clips required")
        payload = build_compose_clip_list(
            clips, require_human_review=bool(inputs.get("require_human_review", True))
        )
        return ToolResult(True, data=payload)
