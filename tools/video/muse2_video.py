"""Muse2 video generation via local muse2api (OpenAI-compatible /v1/videos).

Enforces semantic image roles from lib.film_factory.first_frame before calling Muse.
Never places character/prop sheets at Image 1.
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)

from lib.film_factory.first_frame import IMAGE_ROLES, build_image_plan, validate_image_plan
from lib.film_factory.muse_thread import note_failure, note_success, resolve_thread
from lib.film_factory.take_storage import TakeRecord, TakeStore


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _file_to_data_url(path: str) -> str:
    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _resolve_image_url(url_or_path: str) -> str:
    s = (url_or_path or "").strip()
    if not s:
        return s
    if s.startswith("data:") or s.startswith("http://") or s.startswith("https://"):
        return s
    if s.startswith("/media/"):
        base = _env("MUSE2API_BASE_URL", "http://127.0.0.1:18610").rstrip("/")
        # muse2api serves media at /v1/media/{name} — pass through absolute if local file exists
        return s
    path = Path(s)
    if path.is_file():
        return _file_to_data_url(str(path))
    return s


class Muse2Video(BaseTool):
    name = "muse2_video"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "muse2"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env:MUSE2API_KEY"]
    install_instructions = (
        "Set MUSE2API_BASE_URL (default http://127.0.0.1:18610) and MUSE2API_KEY.\n"
        "  Local muse2api must be running with valid Muse accounts."
    )
    agent_skills = ["ai-video-gen", "muse2-film-factory"]

    capabilities = ["text_to_video", "image_to_video", "reference_to_video"]
    supports = {
        "text_to_video": True,
        "image_to_video": True,
        "reference_image": True,
        "reference_to_video": True,
        "first_frame_roles": True,
        "thread_key": True,
        "photoreal_documentary": True,
        "bushcraft": True,
    }
    best_for = [
        "photoreal documentary and bushcraft clips via Muse",
        "image-to-video with semantic first_frame / sheet roles",
        "series production pinned to muse2api on this VPS",
    ]
    not_good_for = ["offline generation", "stock montage without Muse"]
    fallback_tools = []  # do not silently fall over to cartoon/other providers in film factory

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string"},
            "operation": {
                "type": "string",
                "enum": ["text_to_video", "image_to_video", "reference_to_video"],
                "default": "image_to_video",
            },
            "duration": {"type": ["integer", "string"], "default": 5},
            "aspect_ratio": {
                "type": "string",
                "enum": ["16:9", "9:16", "1:1"],
                "default": "16:9",
            },
            "mode": {
                "type": "string",
                "enum": ["first", "A", "B", "C"],
                "default": "first",
                "description": "First-frame Mode A/B/C",
            },
            "first_frame_url": {"type": "string"},
            "first_frame_path": {"type": "string"},
            "prev_pass_last_frame": {"type": "string"},
            "images": {
                "type": "array",
                "description": "Optional list of {url|path, role, name?}",
                "items": {"type": "object"},
            },
            "character_sheets": {"type": "array", "items": {"type": "object"}},
            "prop_sheets": {"type": "array", "items": {"type": "object"}},
            "environment_refs": {"type": "array", "items": {"type": "object"}},
            "thread_key": {"type": "string"},
            "clip_id": {"type": "string"},
            "pack_id": {"type": "string"},
            "pack_version": {"type": "string"},
            "take_store_path": {"type": "string"},
            "output_path": {"type": "string"},
            "poll_seconds": {"type": "integer", "default": 15},
            "timeout_seconds": {"type": "integer", "default": 900},
            "dry_run": {"type": "boolean", "default": False},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=500, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=["timeout", "rate_limit"])
    idempotency_key_fields = ["prompt", "duration", "aspect_ratio", "mode", "thread_key"]
    side_effects = ["calls muse2api", "writes take record", "may write output video"]
    user_visible_verification = [
        "Check first frame is not a contact/character sheet",
        "ffprobe DAR matches aspect_ratio",
    ]

    def _base(self) -> str:
        return _env("MUSE2API_BASE_URL", "http://127.0.0.1:18610").rstrip("/")

    def _key(self) -> str:
        return _env("MUSE2API_KEY")

    def get_status(self) -> ToolStatus:
        if self._key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0  # quota on Muse accounts, not USD here

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return 120.0

    def _http_json(self, method: str, path: str, body: dict | None = None, timeout: int = 180) -> dict:
        url = self._base() + path
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self._key())
        if body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"muse2api HTTP {e.code}: {detail}") from e

    def _build_plan(self, inputs: dict[str, Any]):
        mode = inputs.get("mode") or "first"
        ff = inputs.get("first_frame_url") or inputs.get("first_frame_path") or ""
        # Allow explicit images[] with roles
        explicit = inputs.get("images") or []
        if explicit:
            from lib.film_factory.first_frame import FirstFramePlan, ImageRef

            imgs = []
            for item in explicit:
                role = (item.get("role") or "").strip()
                url = item.get("url") or item.get("path") or ""
                if not url or not role:
                    continue
                imgs.append(ImageRef(url=url, role=role, name=str(item.get("name") or "")))
            plan = FirstFramePlan(mode=mode, reason="explicit images[]", images=imgs)
            require = mode in ("A", "B", "C") or any(i.role == "first_frame" for i in imgs)
            err = validate_image_plan(plan, require_first_frame=require and mode != "first")
            if mode in ("A", "B", "C"):
                err = validate_image_plan(plan, require_first_frame=True)
            if err:
                plan.error = err
            return plan

        return build_image_plan(
            mode=mode,
            first_frame_url=ff or None,
            prev_pass_last_frame=inputs.get("prev_pass_last_frame"),
            character_sheets=inputs.get("character_sheets"),
            prop_sheets=inputs.get("prop_sheets"),
            environment_refs=inputs.get("environment_refs"),
        )

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        t0 = time.time()
        if not self._key():
            return ToolResult(False, error="MUSE2API_KEY not set")

        prompt = (inputs.get("prompt") or "").strip()
        if not prompt:
            return ToolResult(False, error="prompt required")

        plan = self._build_plan(inputs)
        if not plan.ok:
            return ToolResult(False, error=plan.error, data={"first_frame_plan": plan.role_map()})

        # Build muse2api images list (url only, order preserved)
        muse_images = []
        for im in plan.images:
            muse_images.append({"url": _resolve_image_url(im.url)})

        duration = int(inputs.get("duration") or 5)
        aspect = inputs.get("aspect_ratio") or "16:9"
        preferred_thread = str(inputs.get("thread_key") or "").strip()
        thread_key = resolve_thread(preferred_thread) if preferred_thread else resolve_thread("muse-default")

        take_meta = {
            "mode": plan.mode,
            "image_roles": plan.role_map(),
            "aspect_ratio": aspect,
            "duration": duration,
            "dry_run": bool(inputs.get("dry_run")),
        }

        if inputs.get("dry_run"):
            body_preview = {
                "prompt": prompt,
                "model": "muse-video",
                "duration": duration,
                "aspect_ratio": aspect,
                "thread_key": thread_key,
            }
            return ToolResult(
                True,
                data={
                    "dry_run": True,
                    "would_post": body_preview,
                    "image_count": len(muse_images),
                    "image_roles": plan.role_map(),
                    "first_role": plan.images[0].role if plan.images else None,
                },
                duration_seconds=time.time() - t0,
                model="muse-video",
            )

        poll = int(inputs.get("poll_seconds") or 15)
        timeout = int(inputs.get("timeout_seconds") or 900)
        # Up to 2 fails on one thread, then immediate new-thread retry (max 4 posts).
        max_posts = 4
        last_error = ""
        last_data: dict[str, Any] = {}
        rotated_once = False

        for _post_i in range(max_posts):
            body: dict[str, Any] = {
                "prompt": prompt,
                "model": "muse-video",
                "duration": duration,
                "aspect_ratio": aspect,
                "thread_key": thread_key,
            }
            if muse_images:
                body["images"] = muse_images

            try:
                created = self._http_json("POST", "/v1/videos", body)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                last_data = {"thread_key": thread_key}
                thread_key, rotated = note_failure(thread_key)
                if rotated:
                    rotated_once = True
                    continue
                if _post_i + 1 >= max_posts:
                    break
                continue

            task_id = created.get("task_id") or created.get("id")
            if not task_id:
                last_error = f"no task id: {created}"
                last_data = {"thread_key": thread_key, "raw": created}
                thread_key, rotated = note_failure(thread_key)
                if rotated:
                    rotated_once = True
                continue

            deadline = time.time() + timeout
            last: dict[str, Any] = {}
            failed = False
            while time.time() < deadline:
                time.sleep(poll)
                last = self._http_json("GET", f"/v1/videos/{task_id}", None, timeout=60)
                status = (last.get("status") or "").lower()
                if last.get("url") or status in ("completed", "succeeded", "success", "done"):
                    break
                if status in ("failed", "error") or last.get("error"):
                    failed = True
                    last_error = str(last.get("error") or status)
                    last_data = {"task_id": task_id, "raw": last, "thread_key": thread_key, **take_meta}
                    break
            else:
                failed = True
                last_error = "timeout or missing url"
                last_data = {"task_id": task_id, "raw": last, "thread_key": thread_key, **take_meta}

            if failed:
                thread_key, rotated = note_failure(thread_key)
                if rotated:
                    rotated_once = True
                    # Immediate retry on the fresh thread.
                    continue
                # First fail on this thread — retry same thread once more.
                continue

            url = last.get("url") or (last.get("video") or {}).get("url") or ""
            if not url:
                last_error = "timeout or missing url"
                last_data = {"task_id": task_id, "raw": last, "thread_key": thread_key, **take_meta}
                thread_key, rotated = note_failure(thread_key)
                if rotated:
                    rotated_once = True
                continue

            note_success(thread_key)
            out_path = inputs.get("output_path")
            artifacts = []
            if out_path and url.startswith("http"):
                Path(out_path).parent.mkdir(parents=True, exist_ok=True)
                urllib.request.urlretrieve(url, out_path)
                artifacts.append(out_path)
            elif out_path and url.startswith("/"):
                artifacts.append(url)

            store_path = inputs.get("take_store_path")
            take_id = TakeStore.new_take_id()
            if store_path:
                store = TakeStore(store_path)
                rec = TakeRecord(
                    take_id=take_id,
                    clip_id=str(inputs.get("clip_id") or "C?"),
                    status="pending",
                    prompt=prompt,
                    prompt_hash=hashlib.sha256(prompt.encode()).hexdigest()[:16],
                    pack_id=str(inputs.get("pack_id") or ""),
                    pack_version=str(inputs.get("pack_version") or ""),
                    model="muse-video",
                    provider="muse2",
                    config={
                        "aspect_ratio": aspect,
                        "duration": duration,
                        "mode": plan.mode,
                        "thread_rotated": rotated_once,
                    },
                    image_roles=plan.role_map(),
                    video_url=url if isinstance(url, str) else "",
                    video_path=str(out_path or ""),
                    thread_key=str(thread_key),
                    task_id=str(task_id),
                    account_id=str(last.get("account") or ""),
                    first_frame_mode=plan.mode,
                )
                store.add(rec)

            return ToolResult(
                True,
                data={
                    "task_id": task_id,
                    "url": url,
                    "take_id": take_id,
                    "account": last.get("account"),
                    "thread_key": thread_key,
                    "thread_rotated": rotated_once,
                    **take_meta,
                },
                artifacts=artifacts,
                duration_seconds=time.time() - t0,
                model="muse-video",
            )

        return ToolResult(
            False,
            error=last_error or "muse2 failed after thread rotation",
            data=last_data or {"thread_key": thread_key, "thread_rotated": rotated_once, **take_meta},
            duration_seconds=time.time() - t0,
        )
