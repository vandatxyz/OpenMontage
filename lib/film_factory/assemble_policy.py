"""Assemble policy — PASS only into final; REVIEW waits; FAIL never final."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional


@dataclass
class AssembleDecision:
    include: bool
    tier: str  # PASS | REVIEW | FAIL
    reason: str


def decide_assemble(clip: dict[str, Any], *, require_human_review: bool = True) -> AssembleDecision:
    """Decide whether a clip may enter final assembly.

    Hard rules:
    - FAIL → never include
    - REVIEW → never auto-include (unless require_human_review=False and approved=True)
    - PASS → include
    - Missing qa tier treated as FAIL if status failed, else REVIEW
    """
    tier = str(clip.get("qa_tier") or clip.get("tier") or "").upper()
    qa = clip.get("qa") or {}
    if not tier:
        if qa.get("pass") is True:
            tier = "PASS"
        elif qa.get("pass") is False:
            tier = "FAIL"
        elif clip.get("status") in ("failed", "error"):
            tier = "FAIL"
        else:
            tier = "REVIEW"

    if tier == "FAIL":
        return AssembleDecision(False, "FAIL", "FAIL clips must not enter final")
    if tier == "REVIEW":
        if require_human_review and not clip.get("approved"):
            return AssembleDecision(False, "REVIEW", "REVIEW awaiting human approval")
        if clip.get("approved"):
            return AssembleDecision(True, "REVIEW", "REVIEW approved by human")
        return AssembleDecision(False, "REVIEW", "REVIEW not approved")
    if tier == "PASS":
        return AssembleDecision(True, "PASS", "PASS eligible for final")
    return AssembleDecision(False, tier or "UNKNOWN", f"unknown tier {tier}")


def filter_pass_clips(
    clips: Iterable[dict[str, Any]], *, require_human_review: bool = True
) -> tuple[list[dict[str, Any]], list[AssembleDecision]]:
    kept: list[dict[str, Any]] = []
    decisions: list[AssembleDecision] = []
    for c in clips:
        d = decide_assemble(c, require_human_review=require_human_review)
        decisions.append(d)
        if d.include:
            kept.append(c)
    return kept, decisions


def assert_no_fail_in_final(clips: Iterable[dict[str, Any]]) -> Optional[str]:
    for c in clips:
        d = decide_assemble(c)
        if d.tier == "FAIL" and d.include:
            return "FAIL clip slipped into final"
        if (c.get("qa") or {}).get("pass") is False and d.include and not c.get("approved"):
            return "qa.pass=false included without approval"
    return None
