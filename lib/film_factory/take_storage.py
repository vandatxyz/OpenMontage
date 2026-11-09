"""Take Storage — full provenance for every Muse take."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class TakeRecord:
    take_id: str
    clip_id: str
    status: str  # selected | rejected | pending
    reason: str = ""
    prompt: str = ""
    prompt_hash: str = ""
    pack_id: str = ""
    pack_version: str = ""
    model: str = "muse-video"
    provider: str = "muse2"
    config: dict[str, Any] = field(default_factory=dict)
    image_roles: list[dict[str, Any]] = field(default_factory=list)
    qa: dict[str, Any] = field(default_factory=dict)
    qa_rubric_version: str = ""
    ffprobe: dict[str, Any] = field(default_factory=dict)
    video_url: str = ""
    video_path: str = ""
    thread_key: str = ""
    task_id: str = ""
    account_id: str = ""
    created_at: float = field(default_factory=time.time)
    first_frame_mode: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TakeRecord":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


class TakeStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = {"takes": []}
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")

    def add(self, take: TakeRecord) -> TakeRecord:
        self._data.setdefault("takes", []).append(take.to_dict())
        self.save()
        return take

    def list_for_clip(self, clip_id: str) -> list[TakeRecord]:
        return [TakeRecord.from_dict(t) for t in self._data.get("takes", []) if t.get("clip_id") == clip_id]

    def select(self, take_id: str, reason: str = "selected") -> None:
        for t in self._data.get("takes", []):
            if t.get("clip_id") == self._clip_of(take_id):
                if t.get("take_id") == take_id:
                    t["status"] = "selected"
                    t["reason"] = reason
                elif t.get("status") == "selected":
                    t["status"] = "rejected"
                    t["reason"] = t.get("reason") or "superseded"
        self.save()

    def _clip_of(self, take_id: str) -> str:
        for t in self._data.get("takes", []):
            if t.get("take_id") == take_id:
                return t.get("clip_id") or ""
        return ""

    def selected(self, clip_id: str) -> Optional[TakeRecord]:
        for t in self.list_for_clip(clip_id):
            if t.status == "selected":
                return t
        return None

    @staticmethod
    def new_take_id() -> str:
        return "take-" + uuid.uuid4().hex[:10]
