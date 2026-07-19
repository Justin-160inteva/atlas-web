#!/usr/bin/env python3
"""Publish sanitized Atlas scan heartbeats without retaining media details.

The publisher writes a local JSON snapshot and, when GitHub Actions credentials are
available, updates one public runtime-progress file through the GitHub Contents API.
Concurrent heartbeat writes are reconciled by refetching the current blob SHA before a
bounded retry. Publishing failure never stops the underlying scan.
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_PATH = "data/runtime-progress/eleven-pilot-progress.json"
_LAST_PUBLISHED_AT = 0.0
_LAST_STAGE = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_text(value: Any, limit: int = 280) -> str:
    text = str(value or "").replace("\n", " ").strip()
    lowered = text.lower()
    for marker in ("cookie", "http://", "https://", "/tmp/", "segment-"):
        if marker in lowered:
            return "Progress detail withheld by privacy filter."
    return text[:limit]


def _safe_metrics(metrics: dict[str, Any] | None) -> dict[str, Any]:
    metrics = metrics or {}
    allowed = {
        "downloadedBytes": int,
        "totalBytes": int,
        "segmentDownloadedBytes": int,
        "segmentTotalBytes": int,
        "segmentIndex": int,
        "segmentCount": int,
        "speedBytesPerSecond": float,
        "averageSpeedBytesPerSecond": float,
        "etaSeconds": float,
        "downloadElapsedSeconds": float,
        "speedWindowSeconds": float,
        "stalledSeconds": float,
        "heartbeatSequence": int,
    }
    clean: dict[str, Any] = {}
    for key, caster in allowed.items():
        value = metrics.get(key)
        if value is None:
            continue
        try:
            number = caster(value)
        except (TypeError, ValueError):
            continue
        clean[key] = max(0, number)
    return clean


def _payload(job: dict[str, Any], *, stage: str, progress_percent: float, message: str,
             processed_seconds: float = 0, sampled_frames: int = 0,
             target_frames: int | None = None, state: str = "running",
             metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    batch = job.get("batch") or {}
    payload = {
        "schemaVersion": 4,
        "author": job.get("author"),
        "authorizationId": job.get("authorizationId"),
        "pilotRegion": batch.get("regionGuess"),
        "externalSourceId": job.get("externalSourceId"),
        "page": batch.get("page"),
        "state": state,
        "stage": stage,
        "progressPercent": round(max(0.0, min(100.0, float(progress_percent))), 2),
        "processedSeconds": round(max(0.0, float(processed_seconds)), 3),
        "durationSeconds": float(job.get("durationHintSeconds") or 0),
        "sampledFrames": max(0, int(sampled_frames)),
        "targetFrames": max(1, int(target_frames or job.get("maxSamples") or 1)),
        "message": _safe_text(message),
        "updatedAt": utc_now(),
        "privacy": "Only public, sanitized task progress is stored. No media URLs, cookies, video files, local paths, or frame pixels are included.",
    }
    payload.update(_safe_metrics(metrics))
    return payload


def _local_path() -> pathlib.Path:
    configured = os.getenv("ATLAS_PROGRESS_LOCAL_PATH", "/tmp/atlas-runtime-progress.json")
    return pathlib.Path(configured)


def _write_local(payload: dict[str, Any]) -> None:
    path = _local_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _github_request(url: str, token: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AtlasRuntimeProgress/1.3",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def _current_sha(base_url: str, branch: str, token: str) -> str | None:
    try:
        current = _github_request(f"{base_url}?ref={urllib.parse.quote(branch)}", token)
        return current.get("sha")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def _publish_github(payload: dict[str, Any]) -> bool:
    token = os.getenv("ATLAS_PROGRESS_TOKEN", "").strip()
    repository = os.getenv("ATLAS_PROGRESS_REPOSITORY", "").strip()
    branch = os.getenv("ATLAS_PROGRESS_BRANCH", "main").strip() or "main"
    path = os.getenv("ATLAS_PROGRESS_PATH", DEFAULT_PATH).strip() or DEFAULT_PATH
    if not token or not repository:
        return False

    encoded_path = urllib.parse.quote(path, safe="/")
    base_url = f"https://api.github.com/repos/{repository}/contents/{encoded_path}"
    encoded_content = base64.b64encode(
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode("ascii")
    maximum = max(1, min(8, int(os.getenv("ATLAS_PROGRESS_CONFLICT_RETRIES", "5"))))

    for attempt in range(1, maximum + 1):
        sha = _current_sha(base_url, branch, token)
        body = {
            "message": f"Update Atlas runtime progress: {payload.get('stage')} {payload.get('progressPercent')}% [skip ci]",
            "content": encoded_content,
            "branch": branch,
        }
        if sha:
            body["sha"] = sha
        try:
            _github_request(base_url, token, method="PUT", body=body)
            return True
        except urllib.error.HTTPError as error:
            if error.code not in {409, 422} or attempt >= maximum:
                raise
            delay = min(8.0, 0.5 * (2 ** (attempt - 1))) + random.uniform(0.05, 0.45)
            print(f"runtime progress conflict; refetching SHA and retrying in {delay:.2f}s", flush=True)
            time.sleep(delay)
    return False


def emit(job: dict[str, Any], *, stage: str, progress_percent: float, message: str,
         processed_seconds: float = 0, sampled_frames: int = 0,
         target_frames: int | None = None, state: str = "running",
         metrics: dict[str, Any] | None = None, force: bool = False) -> dict[str, Any]:
    """Write and optionally publish a throttled sanitized heartbeat."""
    global _LAST_PUBLISHED_AT, _LAST_STAGE
    payload = _payload(
        job,
        stage=stage,
        progress_percent=progress_percent,
        message=message,
        processed_seconds=processed_seconds,
        sampled_frames=sampled_frames,
        target_frames=target_frames,
        state=state,
        metrics=metrics,
    )
    _write_local(payload)

    minimum_interval = max(30, int(os.getenv("ATLAS_PROGRESS_MIN_INTERVAL_SECONDS", "60")))
    current = time.monotonic()
    should_publish = force or stage != _LAST_STAGE or current - _LAST_PUBLISHED_AT >= minimum_interval
    if should_publish:
        try:
            published = _publish_github(payload)
            if published:
                _LAST_PUBLISHED_AT = current
                _LAST_STAGE = stage
        except Exception as error:
            print(f"runtime progress publish warning: {type(error).__name__}: {_safe_text(error)}", flush=True)
    return payload


if __name__ == "__main__":
    raise SystemExit("This module is imported by the authorized-video pipeline.")
