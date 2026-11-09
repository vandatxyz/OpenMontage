"""Muse thread_key rotation — after 2 fails on one key, mint a new thread immediately."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Optional

_lock = threading.Lock()
_fail_counts: dict[str, int] = {}
_active: dict[str, str] = {}  # series_base -> current thread_key

FAIL_LIMIT = 2


def series_base(thread_key: str) -> str:
    """Strip rotation suffix: 'zahna-v1__t3_ab12' -> 'zahna-v1'."""
    key = (thread_key or "").strip() or "muse"
    if "__t" in key:
        return key.split("__t", 1)[0]
    return key


def current_thread(base: str) -> str:
    b = series_base(base)
    with _lock:
        return _active.get(b) or b


def mint_thread(base: str) -> str:
    b = series_base(base)
    new_key = f"{b}__t{int(time.time())}_{uuid.uuid4().hex[:6]}"
    with _lock:
        _active[b] = new_key
        _fail_counts[new_key] = 0
        # drop old counters for this series
        for k in list(_fail_counts):
            if k != new_key and series_base(k) == b:
                _fail_counts.pop(k, None)
    return new_key


def note_success(thread_key: str) -> None:
    key = (thread_key or "").strip()
    if not key:
        return
    with _lock:
        _fail_counts[key] = 0


def note_failure(thread_key: str) -> tuple[str, bool]:
    """Record a failure. Returns (thread_to_use_next, rotated).

    After FAIL_LIMIT consecutive fails on the same key, rotates immediately.
    """
    key = (thread_key or "").strip() or "muse"
    b = series_base(key)
    with _lock:
        # map to active key for this series
        active = _active.get(b) or key
        n = int(_fail_counts.get(active, 0)) + 1
        _fail_counts[active] = n
        if n >= FAIL_LIMIT:
            new_key = f"{b}__t{int(time.time())}_{uuid.uuid4().hex[:6]}"
            _active[b] = new_key
            _fail_counts[new_key] = 0
            _fail_counts.pop(active, None)
            return new_key, True
        _active[b] = active
        return active, False


def resolve_thread(preferred: Optional[str]) -> str:
    """Return the thread_key callers should send (honors prior rotations)."""
    if not preferred:
        return mint_thread("muse")
    b = series_base(preferred)
    with _lock:
        return _active.get(b) or preferred
