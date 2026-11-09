"""Series Manager — bible + episode index + state carryover across episodes."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from lib.film_factory.state_ledger import StateLedger


@dataclass
class SeriesState:
    series_id: str
    title: str = ""
    category_id: str = ""
    project_id: str = ""
    bible_path: str = ""
    episode_index: int = 0
    cast_lock: list[str] = field(default_factory=list)
    world_lock: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SeriesManager:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.root / "series.json"
        self.ledger_path = self.root / "state_ledger.json"
        self.state = self._load()
        self.ledger = StateLedger(self.ledger_path)

    def _load(self) -> SeriesState:
        if self.meta_path.exists():
            return SeriesState(**json.loads(self.meta_path.read_text(encoding="utf-8")))
        return SeriesState(series_id=self.root.name)

    def save(self) -> None:
        self.state.updated_at = time.time()
        self.meta_path.write_text(
            json.dumps(self.state.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self.ledger.save()

    def init_series(
        self,
        *,
        series_id: str,
        title: str,
        category_id: str,
        project_id: str,
        bible_path: str = "",
        cast_lock: list[str] | None = None,
        world_lock: dict | None = None,
    ) -> SeriesState:
        self.state = SeriesState(
            series_id=series_id,
            title=title,
            category_id=category_id,
            project_id=project_id,
            bible_path=bible_path,
            cast_lock=list(cast_lock or []),
            world_lock=dict(world_lock or {}),
        )
        self.save()
        return self.state

    def begin_episode(self) -> dict[str, Any]:
        self.state.episode_index += 1
        self.save()
        return {
            "episode_index": self.state.episode_index,
            "series_id": self.state.series_id,
            "category_id": self.state.category_id,
            "project_id": self.state.project_id,
            "seed_state": self.ledger.seed_for_next_clip(),
            "cast_lock": list(self.state.cast_lock),
            "world_lock": dict(self.state.world_lock),
        }

    def attach_bible(self, text: str, filename: str = "SERIES_BIBLE.md") -> Path:
        path = self.root / filename
        path.write_text(text, encoding="utf-8")
        self.state.bible_path = str(path)
        self.save()
        return path
