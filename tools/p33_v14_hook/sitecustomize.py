#!/usr/bin/env python3
"""Conditional HTTP/1.1 and resumable chunk transport for Atlas scans.

The hook is active only when ``ATLAS_FORCE_HTTP11=1``. It provides two bounded
paths: a sequential exact-tail repair and a parallel 2 MiB range downloader.
Parallel range parts survive a failed CDN candidate and are reused by the next
candidate. Original media remains transient and authorization, queue order,
analysis, and retention behavior are unchanged.
"""
from __future__ import annotations

import hashlib
import math
import os
import pathlib
import re
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

ATLAS_HTTP11_PATCHED = False
ATLAS_TAIL_REPAIR_PATCHED = False
ATLAS_PARALLEL_CHUNK_PATCHED = False
_CONTENT_RANGE = re.compile(r"^bytes\s+(\d+)-(\d+)/(\d+|\*)$", re.IGNORECASE)
_TAIL_REQUEST_BYTES = max(
    1024,
    min(8 * 1024 * 1024, int(os.environ.get("ATLAS_TAIL_REQUEST_BYTES", 2 * 1024 * 1024))),
)
_PARALLEL_THRESHOLD_BYTES = max(
    _TAIL_REQUEST_BYTES,
    int(os.environ.get("ATLAS_PARALLEL_THRESHOLD_BYTES", 8 * 1024 * 1024)),
)


def _candidate_digest(candidate: str) -> str:
    return hashlib.sha256(candidate.encode("utf-8", "replace")).hexdigest()


def _parallel_marker(target: pathlib.Path) -> pathlib.Path:
    return target.with_name(f"{target.name}.atlas-parallel-candidate")


def _parallel_part(target: pathlib.Path, index: int) -> pathlib.Path:
    return target.with_name(f"{target.name}.atlas-range-{index:05d}.part")


def _parse_content_range(value: Any) -> tuple[int, int, str]:
    match = _CONTENT_RANGE.fullmatch(str(value or "").strip())
    if not match:
        raise RuntimeError("range response omitted a valid Content-Range")
    return int(match.group(1)), int(match.group(2)), match.group(3)


def _preserving_parallel_range_download(
    candidate: str,
    target: pathlib.Path,
    *,
    total_size: int,
    heartbeat: Any,
    downloaded_before: int,
    segment_index: int,
    workers: int,
    chunk_size: int,
    retries: int,
) -> None:
    """Download fixed ranges concurrently while preserving completed parts.

    Each part is at most ``_TAIL_REQUEST_BYTES``. Failed candidates leave part
    files intact. A later CDN candidate resumes every incomplete part from its
    exact local size. The final target appears only after all parts pass exact
    size checks and are assembled atomically.
    """
    import analyze_authorized_video_v11 as v11

    if total_size <= 0:
        return v11._atlas_original_parallel_range_download(
            candidate,
            target,
            total_size=total_size,
            heartbeat=heartbeat,
            downloaded_before=downloaded_before,
            segment_index=segment_index,
            workers=workers,
            chunk_size=chunk_size,
            retries=retries,
        )

    runner = v11.runner
    worker_count = max(1, min(8, int(os.environ.get("ATLAS_PARALLEL_RANGE_WORKERS", workers))))
    ranges = [
        (index, start, min(total_size - 1, start + _TAIL_REQUEST_BYTES - 1))
        for index, start in enumerate(range(0, total_size, _TAIL_REQUEST_BYTES))
    ]
    part_paths = [_parallel_part(target, index) for index, _, _ in ranges]
    counts: list[int] = []
    for part, (_, start, end) in zip(part_paths, ranges):
        expected = end - start + 1
        existing = part.stat().st_size if part.exists() else 0
        if existing > expected:
            raise RuntimeError("preserved range part exceeds its verified boundary")
        counts.append(existing)

    marker = _parallel_marker(target)
    marker.write_text(_candidate_digest(candidate), encoding="ascii")
    lock = threading.Lock()

    def publish(index: int, value: int) -> None:
        with lock:
            counts[index] = value
            current = sum(counts)
        heartbeat.update(
            downloaded_bytes=downloaded_before + current,
            segment_downloaded_bytes=current,
            segment_total_bytes=total_size,
            segment_index=segment_index,
        )

    def worker(position: int, start: int, end: int) -> None:
        part = part_paths[position]
        expected = end - start + 1
        no_progress_budget = max(2, min(10, int(retries) * 3))
        maximum_requests = max(8, no_progress_budget * 3)
        consecutive_no_progress = 0
        last_error: Exception = RuntimeError("parallel range retry limit reached")

        for _ in range(maximum_requests):
            existing = part.stat().st_size if part.exists() else 0
            if existing == expected:
                publish(position, expected)
                return
            if existing > expected:
                raise RuntimeError("parallel part exceeds expected size")

            request_start = start + existing
            headers = dict(runner.HEADERS)
            headers.update({
                "Accept-Encoding": "identity",
                "Range": f"bytes={request_start}-{end}",
            })
            try:
                with runner.requests.get(
                    candidate,
                    headers=headers,
                    impersonate="chrome",
                    stream=True,
                    timeout=30,
                ) as response:
                    status = int(getattr(response, "status_code", 0) or 0)
                    if status != 206:
                        raise RuntimeError(
                            f"range request was not honored; chunks preserved (status={status})"
                        )
                    returned_start, returned_end, returned_total = _parse_content_range(
                        response.headers.get("content-range")
                    )
                    if returned_start != request_start:
                        raise RuntimeError("parallel range start does not match local part size")
                    if returned_end < returned_start or returned_end > end:
                        raise RuntimeError("parallel range end exceeds requested boundary")
                    if returned_total != "*" and int(returned_total) != total_size:
                        raise RuntimeError("parallel range total does not match media size")
                    response.raise_for_status()

                    written = existing
                    mode = "ab" if existing else "wb"
                    with part.open(mode) as handle:
                        for data in response.iter_content(
                            chunk_size=max(1024, min(int(chunk_size), _TAIL_REQUEST_BYTES))
                        ):
                            if not data:
                                continue
                            remaining = expected - written
                            if remaining <= 0:
                                break
                            data = data[:remaining]
                            handle.write(data)
                            written += len(data)
                            publish(position, written)

                current = part.stat().st_size if part.exists() else 0
                if current < existing:
                    raise RuntimeError("parallel part unexpectedly shrank")
                if current == expected:
                    publish(position, expected)
                    return
                if current > existing:
                    consecutive_no_progress = 0
                    continue
                raise RuntimeError("verified parallel range returned no bytes")
            except Exception as exc:
                last_error = exc
                current = part.stat().st_size if part.exists() else 0
                if current < existing:
                    raise RuntimeError("parallel part unexpectedly shrank") from exc
                if current == expected:
                    publish(position, expected)
                    return
                if current > existing:
                    publish(position, current)
                    consecutive_no_progress = 0
                    continue
                consecutive_no_progress += 1
                if consecutive_no_progress >= no_progress_budget:
                    raise last_error
                time.sleep(min(3, consecutive_no_progress))
        raise last_error

    try:
        with ThreadPoolExecutor(
            max_workers=min(worker_count, len(ranges)),
            thread_name_prefix="atlas-preserved-range",
        ) as pool:
            futures = [
                pool.submit(worker, position, start, end)
                for position, (_, start, end) in enumerate(ranges)
            ]
            for future in as_completed(futures):
                future.result()

        assembling = target.with_name(f"{target.name}.atlas-assembling")
        assembling.unlink(missing_ok=True)
        with assembling.open("wb") as output:
            for part, (_, start, end) in zip(part_paths, ranges):
                expected = end - start + 1
                if not part.exists() or part.stat().st_size != expected:
                    raise RuntimeError("parallel range assembly found an incomplete part")
                with part.open("rb") as source:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
        if assembling.stat().st_size != total_size:
            raise RuntimeError("parallel range assembly size mismatch")
        assembling.replace(target)
        for part in part_paths:
            part.unlink(missing_ok=True)
        marker.unlink(missing_ok=True)
    except Exception:
        # Intentionally retain verified part files and the candidate marker.
        raise


def _preserving_single_stream_resume(
    candidate: str,
    target: pathlib.Path,
    *,
    expected_size: int,
    heartbeat: Any,
    downloaded_before: int,
    segment_index: int,
    chunk_size: int,
    retries: int,
) -> None:
    """Resume a sequential target or hand large files to preserved parallel parts."""
    import analyze_authorized_video_v11 as v11

    if expected_size <= 0:
        return v11._atlas_original_single_stream_resume(
            candidate,
            target,
            expected_size=expected_size,
            heartbeat=heartbeat,
            downloaded_before=downloaded_before,
            segment_index=segment_index,
            chunk_size=chunk_size,
            retries=retries,
        )

    marker = _parallel_marker(target)
    parts = list(target.parent.glob(f"{target.name}.atlas-range-*.part"))
    target_size = target.stat().st_size if target.exists() else 0
    if expected_size >= _PARALLEL_THRESHOLD_BYTES and (target_size == 0 or parts):
        digest = _candidate_digest(candidate)
        if marker.exists() and marker.read_text(encoding="ascii").strip() == digest:
            raise RuntimeError("current CDN exhausted; preserved chunks await another candidate")
        return _preserving_parallel_range_download(
            candidate,
            target,
            total_size=expected_size,
            heartbeat=heartbeat,
            downloaded_before=downloaded_before,
            segment_index=segment_index,
            workers=int(os.environ.get("ATLAS_PARALLEL_RANGE_WORKERS", 4)),
            chunk_size=chunk_size,
            retries=retries,
        )

    runner = v11.runner
    initial = target_size
    if initial > expected_size:
        raise RuntimeError("partial target exceeds expected media size")
    if initial == expected_size and initial >= 1024:
        return

    remaining_at_start = max(0, expected_size - initial)
    required_chunks = max(1, math.ceil(remaining_at_start / _TAIL_REQUEST_BYTES))
    no_progress_budget = max(2, min(12, int(retries) * 3))
    maximum_requests = required_chunks * 3 + no_progress_budget
    consecutive_no_progress = 0
    last_error: Exception = RuntimeError("chunked tail retry limit reached")

    for _ in range(maximum_requests):
        existing = target.stat().st_size if target.exists() else 0
        if existing == expected_size and existing >= 1024:
            return
        if existing > expected_size:
            raise RuntimeError("partial target exceeds expected media size")

        requested_end = min(expected_size - 1, existing + _TAIL_REQUEST_BYTES - 1)
        headers = dict(runner.HEADERS)
        headers.update({
            "Accept-Encoding": "identity",
            "Range": f"bytes={existing}-{requested_end}",
        })
        try:
            with runner.requests.get(
                candidate,
                headers=headers,
                impersonate="chrome",
                stream=True,
                timeout=45,
            ) as response:
                status = int(getattr(response, "status_code", 0) or 0)
                if status != 206:
                    raise RuntimeError(
                        f"range request was not honored; partial preserved (status={status})"
                    )
                returned_start, returned_end, returned_total = _parse_content_range(
                    response.headers.get("content-range")
                )
                if returned_start != existing:
                    raise RuntimeError("range response start does not match partial size")
                if returned_end < returned_start or returned_end > requested_end:
                    raise RuntimeError("range response end exceeds the requested chunk")
                if returned_total != "*" and int(returned_total) != expected_size:
                    raise RuntimeError("range response total does not match expected size")
                response.raise_for_status()

                allowed = requested_end + 1 - existing
                written = existing
                mode = "ab" if existing else "wb"
                with target.open(mode) as handle:
                    for data in response.iter_content(
                        chunk_size=max(1024, min(int(chunk_size), _TAIL_REQUEST_BYTES))
                    ):
                        if not data:
                            continue
                        remaining = allowed - (written - existing)
                        if remaining <= 0:
                            break
                        data = data[:remaining]
                        handle.write(data)
                        written += len(data)
                        heartbeat.update(
                            downloaded_bytes=downloaded_before + written,
                            segment_downloaded_bytes=written,
                            segment_total_bytes=expected_size,
                            segment_index=segment_index,
                        )

            current = target.stat().st_size if target.exists() else 0
            if current < existing:
                raise RuntimeError("partial target unexpectedly shrank during tail repair")
            if current > requested_end + 1:
                raise RuntimeError("tail request appended beyond its verified boundary")
            if current == expected_size and current >= 1024:
                return
            if current > existing:
                consecutive_no_progress = 0
                continue
            raise RuntimeError("verified range returned no new bytes")
        except Exception as exc:
            last_error = exc
            current = target.stat().st_size if target.exists() else 0
            if current < existing:
                raise RuntimeError("partial target unexpectedly shrank during tail repair") from exc
            if current == expected_size and current >= 1024:
                return
            if current > existing:
                consecutive_no_progress = 0
                continue
            consecutive_no_progress += 1
            if consecutive_no_progress >= no_progress_budget:
                raise last_error
            time.sleep(min(4, 1 + consecutive_no_progress))
    raise last_error


def _install() -> bool:
    global ATLAS_TAIL_REPAIR_PATCHED, ATLAS_PARALLEL_CHUNK_PATCHED

    if os.environ.get("ATLAS_FORCE_HTTP11") != "1":
        return False

    from curl_cffi import CurlHttpVersion, requests

    if not getattr(requests, "_atlas_http11_patched", False):
        original_request = requests.request
        original_get = requests.get

        def request(method: str, url: str, **kwargs: Any):
            kwargs.setdefault("http_version", CurlHttpVersion.V1_1)
            return original_request(method, url, **kwargs)

        def get(url: str, **kwargs: Any):
            kwargs.setdefault("http_version", CurlHttpVersion.V1_1)
            return original_get(url, **kwargs)

        requests.request = request
        requests.get = get
        requests._atlas_http11_patched = True
        requests._atlas_http11_original_request = original_request
        requests._atlas_http11_original_get = original_get

    tools_dir = pathlib.Path(__file__).resolve().parents[1]
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))

    import analyze_authorized_video_v11 as v11

    if not getattr(v11, "_atlas_tail_repair_patched", False):
        v11._atlas_original_single_stream_resume = v11._single_stream_resume
        v11._single_stream_resume = _preserving_single_stream_resume
        v11._atlas_tail_repair_patched = True
    if not getattr(v11, "_atlas_parallel_chunk_patched", False):
        v11._atlas_original_parallel_range_download = v11._parallel_range_download
        v11._parallel_range_download = _preserving_parallel_range_download
        v11._atlas_parallel_chunk_patched = True

    ATLAS_TAIL_REPAIR_PATCHED = True
    ATLAS_PARALLEL_CHUNK_PATCHED = True
    return True


ATLAS_HTTP11_PATCHED = _install()
