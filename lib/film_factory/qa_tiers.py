"""QA tiers PASS / REVIEW / FAIL + hard-fail + rubric calibration hooks.

Thresholds are NOT hard-coded to min-9 forever — calibrate on Zahna regression set.
Default profile is conservative starter; override via PromptPack.qa_profile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


DEFAULT_PROFILE = {
    "pass_min_total": 9,
    "review_min_total": 7,
    "require_critical_axes_full": True,
    "critical_axes": ["beat", "cast", "realism", "trash"],
    "hard_fail_issues": [
        "reference_sheet",
        "contact_sheet",
        "character_sheet_in_frame",
        "prop_sheet_in_frame",
        "wrong_dar",
        "wrong_identity",
        "teleport_prop",
        "missing_main_action",
        "extra_person",
        "cartoon_look",
    ],
}


@dataclass
class QaTierResult:
    tier: str
    total: int
    scores: dict[str, int] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    hard_fail: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "qa_tier": self.tier,
            "pass": self.tier == "PASS",
            "total": self.total,
            "scores": self.scores,
            "issues": self.issues,
            "hard_fail": self.hard_fail,
            "reason": self.reason,
        }


def _issue_blob(issues: list[str]) -> str:
    return " | ".join(issues).lower()


def has_hard_fail(issues: list[str], profile: dict[str, Any] | None = None) -> Optional[str]:
    prof = {**DEFAULT_PROFILE, **(profile or {})}
    blob = _issue_blob(issues)
    for token in prof["hard_fail_issues"]:
        if token.replace("_", " ") in blob or token in blob:
            return token
    return None


def score_to_tier(
    *,
    scores: dict[str, int],
    issues: list[str] | None = None,
    profile: dict[str, Any] | None = None,
    aspect_fail: bool = False,
    integrity_fail: bool = False,
) -> QaTierResult:
    prof = {**DEFAULT_PROFILE, **(profile or {})}
    issues = list(issues or [])
    total = int(sum(int(scores.get(k, 0)) for k in ("beat", "cast", "continuity", "realism", "trash")))
    if aspect_fail:
        issues.append("wrong_dar")
    if integrity_fail:
        issues.append("reference_sheet_or_integrity")

    hf = has_hard_fail(issues, prof)
    if hf or aspect_fail or integrity_fail or any(int(scores.get(a, 0)) == 0 for a in ("beat", "cast", "trash")):
        return QaTierResult(
            tier="FAIL",
            total=total,
            scores=scores,
            issues=issues,
            hard_fail=True,
            reason=f"hard_fail:{hf or 'zero_critical_or_gate'}",
        )

    critical_ok = True
    if prof.get("require_critical_axes_full"):
        for ax in prof.get("critical_axes") or []:
            if int(scores.get(ax, 0)) < 2:
                critical_ok = False
                break

    if total >= int(prof["pass_min_total"]) and critical_ok:
        return QaTierResult("PASS", total, scores, issues, False, "meets pass profile")
    if total >= int(prof["review_min_total"]):
        return QaTierResult("REVIEW", total, scores, issues, False, "below pass / critical axis=1")
    return QaTierResult("FAIL", total, scores, issues, False, "below review floor")


# Zahna regression anchors for rubric calibration (ids only — no media).
ZAHNA_REGRESSION = {
    "sheet_flash": ["C17", "C28"],
    "action_fail": ["C77", "C83"],
    "wrong_dar": ["C99"],
    "axis_one_candidates": "clips with beat=1 or realism=1 from episode 20261104-175549-a9dfe8",
}
