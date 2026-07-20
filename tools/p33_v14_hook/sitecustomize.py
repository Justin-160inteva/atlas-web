#!/usr/bin/env python3
"""Conditional HTTP/1.1 and chunked-tail repair for the bounded P33 retry.

Python imports ``sitecustomize`` automatically when this directory is placed on
``PYTHONPATH``. The hook is inert unless ``ATLAS_FORCE_HTTP11=1`` is present.
It keeps every verified partial byte, rejects servers that ignore ``Range``, and
requests the missing tail in small independently verified ranges. Authorization,
queue order, retention, and analysis behavior are not changed.
"""
from __future__ import annotations

import math
import os
import pathlib
import re
import sys
import time
from typing import Any

ATLAS_HTTP11_PATCHED = False
ATLAS_TAIL_REPAIR_PATCHED = False
_CONTENT_RANGE = re.compile(r"^bytes\s+(\d+)-(\d+)/(\d+|\*)$", re.IGNORECASE)
_TAIL_REQUEST_BYTES = max(
    1024,
    min(8 * 1024 * 1024, int(os.environ.get("ATLAS_TAIL_REQUEST_BYTES", 2 * 1024 * 1024))),
)


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
    """Fetch only missing bytes, in bounded ranges, without shrinking the target.

    Every request is capped to ``_TAIL_REQUEST_BYTES``. A response must be HTTP
    206 and begin exactly at the current file size. If a connection breaks after
    delivering some bytes, those bytes remain durable and the next request starts
    from the new file size. A CDN returning HTTP 200/5xx cannot open or truncate
    the target and is abandoned after a bounded no-progress budget.
    """
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

    runner = v11.runner
    initial = target.stat().st_size if target.exists() else 0
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

    for request_index in range(maximum_requests):
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

                content_range = str(response.headers.get("content-range") or "").strip()
                match = _CONTENT_RANGE.fullmatch(content_range)
                if not match:
                    raise RuntimeError("range response omitted a valid Content-Range")
                returned_start = int(match.group(1))
                returned_end = int(match.group(2))
                returned_total = match.group(3)
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
                    for chunk in response.iter_content(chunk_size=max(1024, min(int(chunk_size), _TAIL_REQUEST_BYTES))):
                        if not chunk:
                            continue
                        remaining_in_request = allowed - (written - existing)
                        if remaining_in_request <= 0:
                            break
                        chunk = chunk[:remaining_in_request]
                        handle.write(chunk)
                        written += len(chunk)
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
    global ATLAS_TAIL_REPAIR_PATCHED

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

    ATLAS_TAIL_REPAIR_PATCHED = True
    return True


ATLAS_HTTP11_PATCHED = _install()
