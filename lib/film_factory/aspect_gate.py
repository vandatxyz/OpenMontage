"""Aspect Gate — distinguish wrong DAR (FAIL) vs same DAR different resolution (normalize)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Optional


@dataclass
class AspectDecision:
    ok: bool
    action: str  # "pass" | "normalize" | "fail"
    reason: str
    expected_dar: Optional[str] = None
    actual_dar: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    sar: Optional[str] = None
    rotation: Optional[float] = None
    fps: Optional[float] = None
    duration: Optional[float] = None


def parse_aspect(aspect: str) -> Fraction:
    a = str(aspect or "").strip().lower().replace(" ", "").replace("/", ":")
    if a in ("landscape", "16:9", "16x9"):
        return Fraction(16, 9)
    if a in ("portrait", "9:16", "9x16"):
        return Fraction(9, 16)
    if a in ("1:1", "square"):
        return Fraction(1, 1)
    if ":" in a:
        w, h = a.split(":", 1)
        return Fraction(int(w), int(h))
    raise ValueError(f"unsupported aspect {aspect}")


def aspect_target_wh(aspect: str) -> tuple[int, int]:
    dar = parse_aspect(aspect)
    if dar == Fraction(16, 9):
        return (1280, 720)
    if dar == Fraction(9, 16):
        return (720, 1280)
    if dar == Fraction(1, 1):
        return (720, 720)
    # fallback from fraction
    return (int(dar.numerator * 80), int(dar.denominator * 80))


def _approx_equal(a: Fraction, b: Fraction, tol: float = 0.02) -> bool:
    if a == 0 or b == 0:
        return a == b
    return abs(float(a) - float(b)) / max(float(a), float(b)) <= tol


def dar_from_wh(width: int, height: int, sar: Fraction | None = None) -> Fraction:
    if height <= 0:
        raise ValueError("height must be > 0")
    pixel = Fraction(width, height)
    if sar and sar != 0:
        return pixel * sar
    return pixel


def probe_media(path: str) -> dict[str, Any]:
    """ffprobe stream/format facts. Raises on failure."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,avg_frame_rate,sample_aspect_ratio,display_aspect_ratio,side_data_list:stream_tags=rotate:format=duration",
        "-of",
        "json",
        path,
    ]
    raw = subprocess.check_output(cmd, text=True)
    data = json.loads(raw)
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    sar_s = stream.get("sample_aspect_ratio") or "1:1"
    dar_s = stream.get("display_aspect_ratio")
    rotate = 0.0
    tags = stream.get("tags") or {}
    if tags.get("rotate"):
        try:
            rotate = float(tags["rotate"])
        except ValueError:
            rotate = 0.0
    # side_data rotation
    for sd in stream.get("side_data_list") or []:
        if "rotation" in sd:
            try:
                rotate = float(sd["rotation"])
            except (TypeError, ValueError):
                pass
    fps = None
    afr = stream.get("avg_frame_rate") or "0/0"
    if "/" in afr:
        n, d = afr.split("/", 1)
        if float(d) != 0:
            fps = float(n) / float(d)
    duration = float(fmt.get("duration") or 0) or None
    sar = Fraction(1, 1)
    if sar_s and sar_s not in ("N/A", "0:1"):
        try:
            sw, sh = sar_s.split(":")
            sar = Fraction(int(sw), int(sh)) if int(sh) else Fraction(1, 1)
        except Exception:
            sar = Fraction(1, 1)
    if dar_s and dar_s not in ("N/A", "0:1"):
        try:
            dw, dh = dar_s.split(":")
            dar = Fraction(int(dw), int(dh))
        except Exception:
            dar = dar_from_wh(width, height, sar)
    else:
        dar = dar_from_wh(width, height, sar)
    # 90/270 rotation swaps display orientation
    if abs(rotate) % 180 == 90:
        width, height = height, width
        dar = Fraction(dar.denominator, dar.numerator) if dar != 0 else dar
    return {
        "width": width,
        "height": height,
        "sar": str(sar),
        "dar": str(dar),
        "dar_frac": dar,
        "rotation": rotate,
        "fps": fps,
        "duration": duration,
    }


def check_aspect(
    *,
    expected_aspect: str,
    width: int | None = None,
    height: int | None = None,
    path: str | None = None,
    actual_dar: Fraction | None = None,
) -> AspectDecision:
    expected = parse_aspect(expected_aspect)
    meta: dict[str, Any] = {}
    if path:
        meta = probe_media(path)
        width = meta["width"]
        height = meta["height"]
        actual = meta["dar_frac"]
    elif actual_dar is not None:
        actual = actual_dar
    elif width and height:
        actual = dar_from_wh(width, height)
    else:
        return AspectDecision(False, "fail", "no dimensions or path to check", str(expected))

    tw, th = aspect_target_wh(expected_aspect)
    if not _approx_equal(actual, expected):
        return AspectDecision(
            ok=False,
            action="fail",
            reason=f"DAR mismatch expected {expected} got {actual}",
            expected_dar=str(expected),
            actual_dar=str(actual),
            width=width,
            height=height,
            sar=meta.get("sar"),
            rotation=meta.get("rotation"),
            fps=meta.get("fps"),
            duration=meta.get("duration"),
        )
    if width == tw and height == th:
        return AspectDecision(
            ok=True,
            action="pass",
            reason="DAR and resolution match",
            expected_dar=str(expected),
            actual_dar=str(actual),
            width=width,
            height=height,
            sar=meta.get("sar"),
            rotation=meta.get("rotation"),
            fps=meta.get("fps"),
            duration=meta.get("duration"),
        )
    return AspectDecision(
        ok=True,
        action="normalize",
        reason=f"DAR ok; normalize {width}x{height} -> {tw}x{th}",
        expected_dar=str(expected),
        actual_dar=str(actual),
        width=width,
        height=height,
        sar=meta.get("sar"),
        rotation=meta.get("rotation"),
        fps=meta.get("fps"),
        duration=meta.get("duration"),
    )


def normalize_to_target(src: str, dst: str, aspect: str, fps: float = 24.0) -> None:
    """Scale+pad to target without changing DAR (letterbox only when DAR already correct)."""
    tw, th = aspect_target_wh(aspect)
    decision = check_aspect(expected_aspect=aspect, path=src)
    if decision.action == "fail":
        raise ValueError(decision.reason)
    vf = (
        f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"
        f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        src,
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        dst,
    ]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
