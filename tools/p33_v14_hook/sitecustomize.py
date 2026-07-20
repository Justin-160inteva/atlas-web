#!/usr/bin/env python3
"""Conditional HTTP/1.1 and incremental range repair for the P33 transport.

Python imports ``sitecustomize`` automatically when this directory is placed on
``PYTHONPATH``. The hook is inert unless ``ATLAS_FORCE_HTTP11=1`` is present.
It keeps every verified partial byte, rejects servers that ignore ``Range``, and
can append multiple independently verified HTTP 206 fragments when one response
is still truncated. Authorization, queue order, retention, and analysis behavior
are not changed.
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import time
from typing import Any

MIB = 1024 * 1024
ATLAS_HTTP11_PATCHED = False
ATLAS_TAIL_REPAIR_PATCHED = False
_CONTENT_RANGE = re.compile(r"^bytes\s+(\d+)-(\d+)/(\d+|\*)$", re.IGNORECASE)


def _curl_repair_limit() -> int:
    try:
        configured = int(os.environ.get("ATLAS_INCREMENTAL_RANGE_MAX_BYTES", str(192 * MIB)))
    except (TypeError, ValueError):
        configured = 192 * MIB
    return max(4 * MIB, min(512 * MIB, configured))


def _curl_repair_rounds() -> int:
    try:
        configured = int(os.environ.get("ATLAS_INCREMENTAL_RANGE_ROUNDS", "6"))
    except (TypeError, ValueError):
        configured = 6
    return max(1, min(10, configured))


def _curl_header_args(runner: Any) -> list[str]:
    headers = getattr(runner, "HEADERS", {}) or {}
    result: list[str] = []
    for name in ("Referer", "User-Agent", "Origin"):
        value = headers.get(name)
        if value:
            result.extend(["--header", f"{name}: {value}"])
    return result


def _last_curl_response(header_path: pathlib.Path) -> tuple[int, dict[str, str]]:
    try:
        text = header_path.read_text(encoding="latin-1", errors="replace")
    except OSError:
        return 0, {}
    blocks = re.split(r"\r?\n\r?\n", text)
    for block in reversed(blocks):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines or not lines[0].lower().startswith("http/"):
            continue
        parts = lines[0].split()
        try:
            status = int(parts[1])
        except (IndexError, ValueError):
            status = 0
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
        return status, headers
    return 0, {}


def _verified_incremental_curl_repair(
    candidate: str,
    target: pathlib.Path,
    *,
    expected_size: int,
    heartbeat: Any,
    downloaded_before: int,
    segment_index: int,
) -> bool:
    """Append one or more verified 206 fragments without exposing the media URL."""
    if expected_size <= 0 or not target.exists():
        return False
    initial_size = target.stat().st_size
    initial_gap = expected_size - initial_size
    if initial_gap <= 0 or initial_gap > _curl_repair_limit():
        return False

    from analyze_authorized_video_v11 import runner

    part_path = target.with_name(f"{target.name}.incremental-range.part")
    header_path = target.with_name(f"{target.name}.incremental-range.headers")
    try:
        for _round in range(_curl_repair_rounds()):
            existing = target.stat().st_size if target.exists() else 0
            gap = expected_size - existing
            if gap == 0 and existing >= 1024:
                return True
            if gap <= 0 or gap > _curl_repair_limit():
                return False

            part_path.unlink(missing_ok=True)
            header_path.unlink(missing_ok=True)
            command = [
                "curl",
                "--http1.1",
                "--fail",
                "--location",
                "--silent",
                "--show-error",
                "--retry",
                "2",
                "--retry-delay",
                "1",
                "--retry-all-errors",
                "--connect-timeout",
                "20",
                "--max-time",
                "150",
                "--range",
                f"{existing}-{expected_size - 1}",
                "--header",
                "Accept-Encoding: identity",
                "--max-filesize",
                str(gap),
                "--dump-header",
                str(header_path),
                "--output",
                str(part_path),
                *_curl_header_args(runner),
                str(candidate),
            ]
            subprocess.run(command, capture_output=True, text=True, check=False)
            status, headers = _last_curl_response(header_path)
            if status != 206:
                return False
            match = _CONTENT_RANGE.fullmatch(headers.get("content-range", ""))
            if not match or int(match.group(1)) != existing:
                return False
            returned_total = match.group(3)
            if returned_total != "*" and int(returned_total) != expected_size:
                return False
            if not part_path.exists():
                return False
            received = part_path.stat().st_size
            if received <= 0 or received > gap:
                return False

            with target.open("ab") as output, part_path.open("rb") as source:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
            current = target.stat().st_size
            if current != existing + received or current > expected_size:
                return False
            heartbeat.update(
                downloaded_bytes=downloaded_before + current,
                segment_downloaded_bytes=current,
                segment_total_bytes=expected_size,
                segment_index=segment_index,
            )
            if current == expected_size and current >= 1024:
                return True
        return target.exists() and target.stat().st_size == expected_size and expected_size >= 1024
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        part_path.unlink(missing_ok=True)
        header_path.unlink(missing_ok=True)


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
    """Resume without deleting valid bytes, then use bounded curl range fragments."""
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

    if _verified_incremental_curl_repair(
        candidate,
        target,
        expected_size=expected_size,
        heartbeat=heartbeat,
        downloaded_before=downloaded_before,
        segment_index=segment_index,
    ):
        return
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
