"""Typed continuity — continuous | angle_change | scene_cut | time_jump."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional


class ContinuityKind(str, Enum):
    CONTINUOUS = "continuous"
    ANGLE_CHANGE = "angle_change"
    SCENE_CUT = "scene_cut"
    TIME_JUMP = "time_jump"


def classify_continuity(prev: dict | None, curr: dict, mode: str | None = None) -> ContinuityKind:
    if not prev:
        return ContinuityKind.SCENE_CUT
    if mode == "A" or bool(curr.get("continue")):
        return ContinuityKind.CONTINUOUS
    prev_time = (prev.get("time") or "").strip()
    curr_time = (curr.get("time") or "").strip()
    prev_loc = (prev.get("location") or "").strip()
    curr_loc = (curr.get("location") or "").strip()
    if prev_time and curr_time and prev_time != curr_time:
        return ContinuityKind.TIME_JUMP
    if prev_loc and curr_loc and prev_loc != curr_loc:
        return ContinuityKind.SCENE_CUT
    if mode == "C":
        return ContinuityKind.SCENE_CUT
    if mode == "B":
        return ContinuityKind.ANGLE_CHANGE
    return ContinuityKind.ANGLE_CHANGE


def continuity_check_required(kind: ContinuityKind) -> dict[str, Any]:
    """What Visual QA must verify for this continuity kind."""
    if kind == ContinuityKind.CONTINUOUS:
        return {
            "match_framing": True,
            "match_state": True,
            "compare_prev_last_to_curr_first": True,
        }
    if kind == ContinuityKind.ANGLE_CHANGE:
        return {
            "match_framing": False,
            "match_state": True,  # same place/time/props/identity
            "compare_prev_last_to_curr_first": True,
        }
    if kind == ContinuityKind.SCENE_CUT:
        return {
            "match_framing": False,
            "match_state": False,
            "story_world_consistent": True,
            "compare_prev_last_to_curr_first": False,
        }
    # TIME_JUMP
    return {
        "match_framing": False,
        "match_state": False,
        "planned_state_delta_allowed": True,
        "compare_prev_last_to_curr_first": False,
    }
