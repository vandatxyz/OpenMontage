"""First Frame Controller — semantic image roles + Mode A/B/C.

Hard rules (Zahna lessons):
- Image 1 MUST be role first_frame when a start image is required.
- character_sheet / prop_sheet NEVER Image 1.
- Mode A: first_frame = last frame of previous PASS take.
- Mode B/C: first_frame must be a NEW generated/locked frame; prev last = continuity_frame.
- Missing first_frame for B/C → error before Muse call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

IMAGE_ROLES = (
    "first_frame",
    "continuity_frame",
    "character_sheet",
    "prop_sheet",
    "environment_reference",
)

Mode = str  # "first" | "A" | "B" | "C"


SHEET_ROLES = frozenset({"character_sheet", "prop_sheet"})


@dataclass
class ImageRef:
    url: str
    role: str
    name: str = ""

    def as_dict(self) -> dict[str, Any]:
        d = {"url": self.url, "role": self.role}
        if self.name:
            d["name"] = self.name
        return d


@dataclass
class FirstFramePlan:
    mode: Mode
    reason: str
    images: list[ImageRef] = field(default_factory=list)
    error: Optional[str] = None
    warning: Optional[str] = None

    @property
    def ok(self) -> bool:
        return not self.error

    def ordered_urls(self) -> list[str]:
        return [im.url for im in self.images if im.url]

    def role_map(self) -> list[dict[str, Any]]:
        out = []
        for i, im in enumerate(self.images, 1):
            out.append({"n": i, **im.as_dict()})
        return out


def select_mode(prev: dict | None, curr: dict) -> tuple[Mode, str, Optional[str], Optional[str]]:
    """Pure mode selection (mirrors muse-batch first_frame_mode, with clearer names)."""
    if not prev:
        return ("first", "no previous clip", None, None)
    cont = bool(curr.get("continue"))
    prev_loc = (prev.get("location") or "").strip()
    curr_loc = (curr.get("location") or "").strip()
    prev_time = (prev.get("time") or "").strip()
    curr_time = (curr.get("time") or "").strip()
    prev_shot = (prev.get("shot") or "").strip()
    curr_shot = (curr.get("shot") or "").strip()
    loc_changed = bool(prev_loc and curr_loc and prev_loc != curr_loc)
    time_changed = bool(prev_time and curr_time and prev_time != curr_time)
    shot_changed = bool(prev_shot and curr_shot and prev_shot != curr_shot)
    scene_changed = bool(
        curr.get("scene_boundary")
        or (prev.get("scene") and curr.get("scene") and prev.get("scene") != curr.get("scene"))
    )
    warning = None
    prev_end = (prev.get("end") or "").strip()
    curr_start = (curr.get("start") or "").strip()
    if prev_end and curr_start and prev_end.lower() != curr_start.lower():
        warning = "start/end text differs from previous end (soft)"

    if cont:
        if loc_changed:
            return (None, "", "continue=true but location changed", warning)  # type: ignore[return-value]
        if time_changed:
            return (None, "", "continue=true but time changed", warning)  # type: ignore[return-value]
        if shot_changed:
            return (None, "", "continue=true but shot changed — use Mode B", warning)  # type: ignore[return-value]
        if scene_changed:
            return (None, "", "continue=true but scene changed", warning)  # type: ignore[return-value]
        return ("A", "direct continuation same place/time/shot", None, warning)
    if loc_changed or time_changed or scene_changed:
        return ("C", "scene/time transition", None, warning)
    return ("B", "camera cut same scene", None, warning)


def build_image_plan(
    *,
    mode: Mode,
    first_frame_url: str | None = None,
    prev_pass_last_frame: str | None = None,
    character_sheets: list[dict] | None = None,
    prop_sheets: list[dict] | None = None,
    environment_refs: list[dict] | None = None,
) -> FirstFramePlan:
    """Build ordered images with semantic roles. Never puts sheets at Image 1."""
    images: list[ImageRef] = []
    warning = None

    if mode == "A":
        ff = (prev_pass_last_frame or first_frame_url or "").strip()
        if not ff:
            return FirstFramePlan(
                mode=mode,
                reason="Mode A requires last frame of previous PASS take",
                error="missing first_frame for Mode A",
            )
        images.append(ImageRef(url=ff, role="first_frame"))
    elif mode in ("B", "C"):
        ff = (first_frame_url or "").strip()
        if not ff:
            return FirstFramePlan(
                mode=mode,
                reason=f"Mode {mode} requires a NEW first frame",
                error=f"missing first_frame for Mode {mode} — refuse sheet-as-Image1",
            )
        images.append(ImageRef(url=ff, role="first_frame"))
        cont = (prev_pass_last_frame or "").strip()
        # continuity appended later (after sheets) so it is never Image 1
        continuity_url = cont if cont and cont != ff else None
    elif mode == "first":
        ff = (first_frame_url or "").strip()
        if ff:
            images.append(ImageRef(url=ff, role="first_frame"))
        continuity_url = None
    else:
        return FirstFramePlan(mode=mode or "?", reason="unknown mode", error=f"invalid mode {mode}")

    for sheet in character_sheets or []:
        u = (sheet.get("url") or "").strip()
        if u:
            images.append(ImageRef(url=u, role="character_sheet", name=str(sheet.get("name") or "")))
    for sheet in prop_sheets or []:
        u = (sheet.get("url") or "").strip()
        if u:
            images.append(ImageRef(url=u, role="prop_sheet", name=str(sheet.get("name") or "")))
    for env in environment_refs or []:
        u = (env.get("url") or "").strip()
        if u:
            images.append(
                ImageRef(url=u, role="environment_reference", name=str(env.get("name") or ""))
            )

    if mode in ("B", "C"):
        cont = (prev_pass_last_frame or "").strip()
        if cont and cont != (first_frame_url or "").strip():
            images.append(ImageRef(url=cont, role="continuity_frame"))

    plan = FirstFramePlan(mode=mode, reason=f"mode {mode}", images=images, warning=warning)
    err = validate_image_plan(plan, require_first_frame=(mode in ("A", "B", "C")))
    if err:
        plan.error = err
    return plan


def validate_image_plan(plan: FirstFramePlan, require_first_frame: bool = True) -> Optional[str]:
    if require_first_frame:
        if not plan.images:
            return "no images and first_frame required"
        if plan.images[0].role != "first_frame":
            return f"Image 1 role must be first_frame, got {plan.images[0].role}"
        if plan.images[0].role in SHEET_ROLES:
            return "sheet must never be Image 1"
    for im in plan.images:
        if im.role not in IMAGE_ROLES:
            return f"unknown role {im.role}"
    # Any sheet appearing before a first_frame is illegal
    seen_ff = False
    for im in plan.images:
        if im.role == "first_frame":
            seen_ff = True
        elif im.role in SHEET_ROLES and not seen_ff and require_first_frame:
            return "sheet before first_frame"
    return None
