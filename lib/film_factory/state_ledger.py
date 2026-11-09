"""Minimal / Full State Ledger — planned → observed → validated / unknown.

Never auto-promote planned→observed or observed→validated.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class Confirmation(str, Enum):
    PLANNED = "planned"
    OBSERVED = "observed"
    VALIDATED = "validated"
    UNKNOWN = "unknown"
    UNCONFIRMED = "unconfirmed"


@dataclass
class StateRecord:
    key: str
    value: Any
    confirmation: str = Confirmation.UNKNOWN.value
    source_clip: str = ""
    source_take: str = ""
    evidence: str = ""  # frame path / timestamp note
    confidence: float = 0.0
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StateLedger:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self._states: dict[str, StateRecord] = {}
        if self.path and self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for k, v in (raw.get("states") or {}).items():
                self._states[k] = StateRecord(**v)

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"states": {k: v.to_dict() for k, v in self._states.items()}}
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def set_planned(self, key: str, value: Any, *, source_clip: str = "") -> StateRecord:
        rec = StateRecord(
            key=key,
            value=value,
            confirmation=Confirmation.PLANNED.value,
            source_clip=source_clip,
            confidence=0.0,
        )
        self._states[key] = rec
        self.save()
        return rec

    def set_observed(
        self,
        key: str,
        value: Any,
        *,
        source_clip: str,
        evidence: str,
        confidence: float,
        source_take: str = "",
    ) -> StateRecord:
        if confidence < 0 or confidence > 1:
            raise ValueError("confidence must be 0..1")
        rec = StateRecord(
            key=key,
            value=value,
            confirmation=Confirmation.OBSERVED.value,
            source_clip=source_clip,
            source_take=source_take,
            evidence=evidence,
            confidence=confidence,
        )
        self._states[key] = rec
        self.save()
        return rec

    def validate(self, key: str, *, evidence: str, confidence: float = 1.0) -> StateRecord:
        """Human/QA validation — only from observed/unconfirmed, never from planned alone."""
        cur = self._states.get(key)
        if not cur:
            raise KeyError(f"no state {key}")
        if cur.confirmation == Confirmation.PLANNED.value:
            raise ValueError("cannot validate planned state without observation")
        cur.confirmation = Confirmation.VALIDATED.value
        cur.evidence = evidence or cur.evidence
        cur.confidence = confidence
        cur.updated_at = time.time()
        self.save()
        return cur

    def mark_unknown(self, key: str, *, reason: str = "") -> StateRecord:
        cur = self._states.get(key) or StateRecord(key=key, value=None)
        cur.confirmation = Confirmation.UNKNOWN.value
        cur.evidence = reason or cur.evidence
        cur.confidence = 0.0
        cur.updated_at = time.time()
        self._states[key] = cur
        self.save()
        return cur

    def seed_for_next_clip(self) -> dict[str, Any]:
        """Only validated (or explicit unknown) values may seed the next clip."""
        out = {}
        for k, v in self._states.items():
            if v.confirmation in (Confirmation.VALIDATED.value, Confirmation.UNKNOWN.value):
                out[k] = {
                    "value": v.value,
                    "confirmation": v.confirmation,
                    "source_clip": v.source_clip,
                    "confidence": v.confidence,
                }
        return out

    def get(self, key: str) -> Optional[StateRecord]:
        return self._states.get(key)
