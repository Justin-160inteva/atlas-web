#!/usr/bin/env python3
"""Conditional HTTP/1.1 and exact-tail repair for the bounded P33 retry.

Python imports ``sitecustomize`` automatically when this directory is placed on
``PYTHONPATH``. The hook is inert unless ``ATLAS_FORCE_HTTP11=1`` is present.
It keeps every verified partial byte, rejects servers that ignore ``Range``, and
requests only the missing tail. Authorization, queue order, retention, and
analysis behavior are not changed.
"""
from __future__ import annotations

import os
import pathlib
import re
import sys
import time
from typing import Any

ATLAS_HTTP11_PATCHED = False
ATLAS_TAIL_REPAIR_PATCHED = False
_CONTENT_RANGE = re.compile(r"^bytes\s+(\d+)-(\d+)/(\d+|\*)$", re.IGNORECASE)


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
    """Resume without ever deleting a valid partial target.

    A response to a resumed request must be HTTP 206 and its Content-Range must
    begin at the current file size. HTTP 200 is rejected without opening the
    target, so a CDN that ignores Range cannot erase previously downloaded data.
    If a transfer ends early, received bytes remain appended and the next bounded
    attempt requests only the new missing tail.
    """
    from analyze_authorized_video_v11 import runner

    attempts = max(1, int(retries))
    last_error: Exception = RuntimeError("single-stream retry limit reached")

    for attempt in range(attempts):
        existing = target.stat().st_size if target.exists() else 0
        if expected_size and existing == expected_size and existing >= 1024:
            return
        if expected_size and existing > expected_size:
            raise RuntimeError("partial target exceeds expected media size")

        headers = dict(runner.HEADERS)
        headers["Accept-Encoding"] = "identity"
        if existing:
            end = expected_size - 1 if expected_size else ""
            headers["Range"] = f"bytes={existing}-{end}"

        try:
            with runner.requests.get(
                candidate,
                headers=headers,
                impersonate="chrome",
                stream=True,
                timeout=90,
            ) as response:
                status = int(getattr(response, "status_code", 0) or 0)
                if existing:
                    if status != 206:
                        raise RuntimeError(
                            f"range request was not honored; partial preserved (status={status})"
                        )
                    content_range = str(response.headers.get("content-range") or "").strip()
                    match = _CONTENT_RANGE.fullmatch(content_range)
                    if not match or int(match.group(1)) != existing:
                        raise RuntimeError("range response start does not match partial size")
                    returned_end = int(match.group(2))
                    returned_total = match.group(3)
                    if returned_end < existing:
                        raise RuntimeError("range response end precedes requested start")
                    if (
                        expected_size
                        and returned_total != "*"
                        and int(returned_total) != expected_size
                    ):
                        raise RuntimeError("range response total does not match expected size")
                response.raise_for_status()

                header_size = int(response.headers.get("content-length") or 0)
                total = expected_size or (existing + header_size if header_size else 0)
                written = existing
                mode = "ab" if existing else "wb"
                with target.open(mode) as handle:
                    for chunk in response.iter_content(chunk_size=max(1024, int(chunk_size))):
                        if not chunk:
                            continue
                        if expected_size:
                            remaining = expected_size - written
                            if remaining <= 0:
                                break
                            chunk = chunk[:remaining]
                        handle.write(chunk)
                        written += len(chunk)
                        heartbeat.update(
                            downloaded_bytes=downloaded_before + written,
                            segment_downloaded_bytes=written,
                            segment_total_bytes=total,
                            segment_index=segment_index,
                        )

            current = target.stat().st_size if target.exists() else 0
            if expected_size:
                if current == expected_size and current >= 1024:
                    return
                raise RuntimeError(
                    f"exact tail incomplete: {max(0, expected_size - current)} bytes missing"
                )
            if current >= 1024:
                return
            raise RuntimeError("downloaded media stream is unexpectedly small")
        except Exception as exc:
            last_error = exc
            current = target.stat().st_size if target.exists() else 0
            if expected_size and current == expected_size and current >= 1024:
                return
            if current < existing:
                raise RuntimeError("partial target unexpectedly shrank during tail repair") from exc
            if attempt + 1 < attempts:
                time.sleep(min(6, 1 + attempt * 2))

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
