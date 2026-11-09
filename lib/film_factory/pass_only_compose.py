"""Helper: filter clips then hand off to stitch/compose inputs."""

from __future__ import annotations

from typing import Any

from lib.film_factory.assemble_policy import filter_pass_clips


def build_compose_clip_list(
    clips: list[dict[str, Any]], *, require_human_review: bool = True
) -> dict[str, Any]:
    kept, decisions = filter_pass_clips(clips, require_human_review=require_human_review)
    rejected = [
        {"clip_id": c.get("id"), "decision": d.__dict__}
        for c, d in zip(clips, decisions)
        if not d.include
    ]
    return {
        "clips": kept,
        "rejected": rejected,
        "count_in": len(list(clips)),
        "count_out": len(kept),
    }
