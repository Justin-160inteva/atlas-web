#!/usr/bin/env python3
"""Pure helpers for Atlas' signed Bilibili metadata and CDN transport path.

The helpers deliberately contain no HTTP client.  This keeps signing, source identity,
format selection, CDN candidate ordering, and diagnostic redaction independently
testable without downloading creator media.
"""
from __future__ import annotations

import base64
import hashlib
import json
import random
import re
import time
import urllib.parse
from typing import Any


MIXIN_KEY_ENC_TAB = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
)
WBI_FORBIDDEN = "!'()*"
DEFAULT_MAX_VIDEO_HEIGHT = 480


def _wbi_container(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("wbi_img"), dict):
        return payload
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def extract_mixin_key(nav_payload: dict[str, Any]) -> str:
    """Derive the 32-character WBI mixin key from an anonymous nav response."""
    wbi = _wbi_container(nav_payload).get("wbi_img") or {}
    lookup = "".join(
        str(wbi.get(name) or "").rsplit("/", 1)[-1].split(".", 1)[0]
        for name in ("img_url", "sub_url")
    )
    if len(lookup) < 64:
        raise ValueError("Bilibili nav API returned an incomplete WBI key")
    return "".join(lookup[index] for index in MIXIN_KEY_ENC_TAB)[:32]


def sign_wbi_params(
    params: dict[str, Any],
    mixin_key: str,
    *,
    timestamp: int | None = None,
) -> dict[str, str | int]:
    """Return a new, sorted and WBI-signed parameter mapping."""
    if len(mixin_key) < 32:
        raise ValueError("WBI mixin key is incomplete")
    prepared: dict[str, str | int] = dict(params)
    prepared["wts"] = int(time.time() if timestamp is None else timestamp)
    normalized = {
        str(key): "".join(char for char in str(value) if char not in WBI_FORBIDDEN)
        for key, value in sorted(prepared.items())
        if value is not None
    }
    query = urllib.parse.urlencode(normalized)
    normalized["w_rid"] = hashlib.md5(f"{query}{mixin_key}".encode()).hexdigest()
    return normalized


def signed_url(base_url: str, params: dict[str, Any], mixin_key: str) -> str:
    return f"{base_url}?{urllib.parse.urlencode(sign_wbi_params(params, mixin_key))}"


def fingerprint_params(seed: str | int | None = None) -> dict[str, str]:
    """Build a bounded anonymous web-player fingerprint for the signed play request."""
    rng = random.Random(seed)
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    def encoded(length: int) -> str:
        raw = "".join(rng.choice(alphabet) for _ in range(length)).encode()
        return base64.b64encode(raw).decode().rstrip("=")

    width, height = rng.choice(((1920, 1080), (1366, 768), (1536, 864), (1280, 720)))
    movement = rng.randrange(0, 114)
    offset = rng.randrange(0, 514)
    interaction = {
        "ds": [],
        "wh": [2 * width + 2 * height + 3 * movement, 4 * width - height + movement, movement],
        "of": [50 + offset, 2 * offset, offset],
    }
    return {
        "dm_img_list": "[]",
        "dm_img_str": encoded(32),
        "dm_cover_img_str": encoded(64),
        "dm_img_inter": json.dumps(interaction, separators=(",", ":")),
    }


def _urls(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    result: list[str] = []
    for candidate in values:
        if not isinstance(candidate, str):
            continue
        parsed = urllib.parse.urlsplit(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            result.append(candidate)
    return result


def stream_candidates(stream: dict[str, Any], *, prefer_backups: bool = True) -> list[str]:
    """Return de-duplicated API-provided CDN URLs in the preferred failover order."""
    primary: list[str] = []
    for key in ("baseUrl", "base_url", "url"):
        primary.extend(_urls(stream.get(key)))
    backups: list[str] = []
    for key in ("backupUrl", "backup_url"):
        backups.extend(_urls(stream.get(key)))
    ordered = [*backups, *primary] if prefer_backups else [*primary, *backups]
    unique: list[str] = []
    seen: set[str] = set()
    for candidate in ordered:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique.append(candidate)
    return unique


def _codec_rank(stream: dict[str, Any]) -> int:
    codec = str(stream.get("codecs") or stream.get("codec") or "").lower()
    if codec.startswith("avc") or "h264" in codec:
        return 3
    if codec.startswith("hev") or "h265" in codec:
        return 2
    if codec.startswith("av01") or "av1" in codec:
        return 1
    return 0


def select_dash_video(
    play_payload: dict[str, Any],
    *,
    max_height: int = DEFAULT_MAX_VIDEO_HEIGHT,
) -> dict[str, Any] | None:
    """Prefer an OpenCV-friendly AVC stream at or below the analysis height ceiling."""
    dash = play_payload.get("dash") or {}
    streams = [
        stream for stream in (dash.get("video") or [])
        if isinstance(stream, dict) and stream_candidates(stream)
    ]
    if not streams:
        return None
    ceiling = max(144, int(max_height))
    within = [stream for stream in streams if 0 < int(stream.get("height") or 0) <= ceiling]
    pool = within or streams
    if within:
        return max(
            pool,
            key=lambda stream: (
                _codec_rank(stream),
                int(stream.get("height") or 0),
                int(stream.get("bandwidth") or 0),
            ),
        )
    return min(
        pool,
        key=lambda stream: (
            int(stream.get("height") or 10**9),
            -_codec_rank(stream),
            -int(stream.get("bandwidth") or 0),
        ),
    )


def build_media_plan(
    play_payload: dict[str, Any],
    *,
    max_height: int = DEFAULT_MAX_VIDEO_HEIGHT,
    prefer_backups: bool = True,
) -> dict[str, Any]:
    """Build one video-only DASH stream or a legacy progressive segment plan."""
    video = select_dash_video(play_payload, max_height=max_height)
    if video:
        return {
            "kind": "wbi-dash-video",
            "streams": [{
                "extension": "m4s",
                "declaredSize": max(0, int(video.get("size") or 0)),
                "height": max(0, int(video.get("height") or 0)),
                "codec": str(video.get("codecs") or "unknown"),
                "candidates": stream_candidates(video, prefer_backups=prefer_backups),
            }],
        }

    progressive = []
    for segment in play_payload.get("durl") or []:
        if not isinstance(segment, dict):
            continue
        candidates = stream_candidates(segment, prefer_backups=prefer_backups)
        if candidates:
            progressive.append({
                "extension": "flv",
                "declaredSize": max(0, int(segment.get("size") or 0)),
                "candidates": candidates,
            })
    if progressive:
        return {"kind": "legacy-progressive", "streams": progressive}
    raise ValueError("Bilibili play metadata returned no usable video stream")


def validate_job_identity(job: dict[str, Any], url: str) -> tuple[str, int, int]:
    """Resolve and verify BVID, multipart page and catalog CID before HTTP transfer."""
    match = re.search(r"(BV[0-9A-Za-z]+)", url)
    if not match:
        raise ValueError("No BV identifier found in Bilibili URL")
    bvid = match.group(1)
    batch = job.get("batch") or {}
    source_key = str(batch.get("sourceKey") or "")
    expected_bvid = source_key.split(":", 1)[0] if ":" in source_key else ""
    if expected_bvid and expected_bvid != bvid:
        raise ValueError("BVID page identity mismatch")

    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    batch_page = int(batch.get("page") or 0)
    url_page = int((query.get("p") or [batch_page or 1])[0])
    page = batch_page or url_page
    if page < 1 or (batch_page and url_page != batch_page):
        raise ValueError("multipart page identity mismatch")

    cid = int(batch.get("cid") or 0)
    if cid <= 0:
        raise ValueError("verified catalog CID is missing")
    return bvid, page, cid


def redact_diagnostic(value: Any, *, limit: int = 1800) -> str:
    """Keep error class/status while removing media URLs, credentials and temp paths."""
    text = str(value or "").replace("\x00", "")
    text = re.sub(r"https?://\S+", "[url-redacted]", text, flags=re.IGNORECASE)
    text = re.sub(
        r"(?i)(authorization|cookie|token|sessdata)\s*[:=]\s*\S+",
        r"\1=[redacted]",
        text,
    )
    text = re.sub(r"/tmp/\S+", "[temporary-path-redacted]", text)
    return text[-max(200, int(limit)):]
