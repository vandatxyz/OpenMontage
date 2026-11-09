"""Visual QA for film-factory — wraps score_to_tier; optional LLM vision later.

Without an external vision model configured, accepts precomputed scores/issues
(from agent or offline judge) and applies PASS/REVIEW/FAIL policy + continuity kind.
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

from lib.film_factory.continuity import ContinuityKind, continuity_check_required
from lib.film_factory.qa_tiers import score_to_tier


class VisualQaFilm(BaseTool):
    name = "visual_qa_film"
    version = "0.1.0"
    tier = ToolTier.ANALYZE
    capability = "analysis"
    provider = "openmontage"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    agent_skills = ["muse2-film-factory"]
    capabilities = ["visual_qa", "qa_tiers"]
    input_schema = {
        "type": "object",
        "required": ["scores"],
        "properties": {
            "scores": {"type": "object"},
            "issues": {"type": "array", "items": {"type": "string"}},
            "continuity_kind": {
                "type": "string",
                "enum": [e.value for e in ContinuityKind],
            },
            "qa_profile": {"type": "object"},
            "aspect_fail": {"type": "boolean"},
            "integrity_fail": {"type": "boolean"},
        },
    }
    resource_profile = ResourceProfile(network_required=False)

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return 0.1

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        scores = {k: int(v) for k, v in (inputs.get("scores") or {}).items()}
        kind = inputs.get("continuity_kind") or ContinuityKind.ANGLE_CHANGE.value
        req = continuity_check_required(ContinuityKind(kind))
        # If continuous required but continuity score missing, treat as 0
        if req.get("compare_prev_last_to_curr_first") and "continuity" not in scores:
            scores.setdefault("continuity", 0)
        if not req.get("compare_prev_last_to_curr_first"):
            # do not demand continuity axis — default 2 when N/A
            scores.setdefault("continuity", 2)

        result = score_to_tier(
            scores=scores,
            issues=list(inputs.get("issues") or []),
            profile=inputs.get("qa_profile"),
            aspect_fail=bool(inputs.get("aspect_fail")),
            integrity_fail=bool(inputs.get("integrity_fail")),
        )
        data = result.to_dict()
        data["continuity_kind"] = kind
        data["continuity_requirements"] = req
        return ToolResult(True, data=data)
