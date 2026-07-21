#!/usr/bin/env python3
"""Atlas v14 analyzer with bounded fastest-CDN selection.

v14 preserves v13's verified BVID/page/CID identity, WBI-signed metadata,
resumable API-provided CDN failover, transient-media policy, and numeric-only
analysis output. Before a new stream starts, it performs a small concurrent
speed probe across the API-provided candidates and tries the fastest route
first. This removes conservative project-side routing without bypassing source
authorization, access controls, or platform safety limits.
"""
from __future__ import annotations

import pathlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import analyze_authorized_video_v13 as v13

runner = v13.runner
MIB = v13.MIB


def _probe_speed(candidate: str, probe_bytes: int, timeout_seconds: int) -> float:
    """Return measured bytes/second for a small bounded range probe."""
    headers = dict(runner.HEADERS)
    headers.update({
        "Range": f"bytes=0-{probe_bytes - 1}",
        "Accept-Encoding": "identity",
    })
    started = time.monotonic()
    received = 0
    with runner.requests.get(
        candidate,
        headers=headers,
        impersonate="chrome",
        stream=True,
        timeout=timeout_seconds,
    ) as response:
        response.raise_for_status()
        status = int(getattr(response, "status_code", 0) or 0)
        if status not in {200, 206}:
            return 0.0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            received += len(chunk)
            if received >= probe_bytes:
                break
    elapsed = max(0.001, time.monotonic() - started)
    return received / elapsed if received else 0.0


def _ordered_candidates(
    candidates: list[str],
    target: pathlib.Path,
    settings: dict[str, Any],
) -> list[str]:
    """Order fresh transfers by bounded measured throughput.

    Existing partial files retain the original API failover order so resume
    semantics remain deterministic.
    """
    if len(candidates) < 2 or not settings.get("cdnSpeedProbeEnabled", True):
        return candidates
    if target.exists() and target.stat().st_size > 0:
        return candidates

    maximum = max(2, min(6, int(settings.get("cdnSpeedProbeCandidates", 4))))
    probe_bytes = max(128 * 1024, min(MIB, int(settings.get("cdnSpeedProbeBytes", 256 * 1024))))
    timeout_seconds = max(3, min(12, int(settings.get("cdnSpeedProbeTimeoutSeconds", 6))))
    sampled = candidates[:maximum]
    scores: dict[str, float] = {}

    with ThreadPoolExecutor(max_workers=len(sampled), thread_name_prefix="atlas-cdn-probe") as pool:
        futures = {
            pool.submit(_probe_speed, candidate, probe_bytes, timeout_seconds): candidate
            for candidate in sampled
        }
        for future in as_completed(futures):
            candidate = futures[future]
            try:
                scores[candidate] = max(0.0, float(future.result()))
            except Exception:
                scores[candidate] = 0.0

    original_index = {candidate: index for index, candidate in enumerate(candidates)}
    return sorted(
        candidates,
        key=lambda candidate: (-scores.get(candidate, 0.0), original_index[candidate]),
    )


_original_download_stream = v13._download_stream


def _download_stream(
    stream: dict[str, Any],
    target: pathlib.Path,
    *,
    heartbeat: Any,
    downloaded_before: int,
    segment_index: int,
    settings: dict[str, Any],
) -> tuple[int, list[str]]:
    tuned = dict(stream)
    tuned["candidates"] = _ordered_candidates(
        [str(candidate) for candidate in (stream.get("candidates") or [])],
        target,
        settings,
    )
    return _original_download_stream(
        tuned,
        target,
        heartbeat=heartbeat,
        downloaded_before=downloaded_before,
        segment_index=segment_index,
        settings=settings,
    )


v13._download_stream = _download_stream
runner.direct_bilibili_download = v13.direct_bilibili_download
runner.download_with_fallbacks = v13.download_with_fallbacks


if __name__ == "__main__":
    raise SystemExit(v13.v9.v6.main())
