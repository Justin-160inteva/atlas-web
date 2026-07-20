#!/usr/bin/env python3
"""Byte-accurate HTTP resume planning for Atlas source transport v14.

This module is deliberately HTTP-client agnostic so Content-Range handling, safe
restart decisions and completion accounting can be validated deterministically.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

_CONTENT_RANGE = re.compile(r"^bytes\s+(\d+)-(\d+)/(\d+|\*)$", re.IGNORECASE)


@dataclass(frozen=True)
class ResponseWritePlan:
    mode: str
    base_offset: int
    total_size: int
    expected_payload_bytes: int
    restarted: bool


def _header(headers: Mapping[str, object], name: str) -> str:
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).lower() == wanted:
            return str(value or "").strip()
    return ""


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def parse_content_range(value: str) -> tuple[int, int, int]:
    """Return (start, end, total), with total=0 when the server reports '*'."""
    match = _CONTENT_RANGE.fullmatch(str(value or "").strip())
    if not match:
        raise ValueError("invalid Content-Range")
    start = int(match.group(1))
    end = int(match.group(2))
    total = 0 if match.group(3) == "*" else int(match.group(3))
    if end < start or (total and end >= total):
        raise ValueError("incoherent Content-Range")
    return start, end, total


def plan_response_write(
    status_code: int,
    headers: Mapping[str, object],
    *,
    requested_offset: int,
    expected_size: int = 0,
) -> ResponseWritePlan:
    """Choose append/restart semantics and authoritative byte counts.

    A resumed request may append only when a valid 206 response starts exactly at
    the requested offset. A full 200 response, or a 206 response starting at zero,
    safely replaces the partial target instead of being appended to it.
    """
    status = int(status_code or 0)
    offset = max(0, int(requested_offset or 0))
    expected = max(0, int(expected_size or 0))
    content_length = _positive_int(_header(headers, "content-length"))
    content_range = _header(headers, "content-range")

    range_start = range_end = range_total = 0
    has_range = False
    if content_range:
        range_start, range_end, range_total = parse_content_range(content_range)
        has_range = True

    if status == 200:
        mode = "wb"
        base = 0
        restarted = offset > 0
    elif status == 206:
        if not has_range:
            if offset:
                raise RuntimeError("resumed response missing Content-Range")
            mode = "wb"
            base = 0
            restarted = False
        elif range_start == offset:
            mode = "ab" if offset else "wb"
            base = offset
            restarted = False
        elif range_start == 0:
            mode = "wb"
            base = 0
            restarted = offset > 0
        else:
            raise RuntimeError("resumed response starts at unexpected offset")
    else:
        raise RuntimeError(f"unexpected transfer status {status}")

    if has_range:
        payload_bytes = range_end - range_start + 1
    else:
        payload_bytes = content_length

    total = expected or range_total
    if not total and content_length:
        total = base + content_length

    if total and base > total:
        raise RuntimeError("resume offset exceeds expected media size")
    if payload_bytes and total and base + payload_bytes > total:
        raise RuntimeError("response payload exceeds expected media size")

    return ResponseWritePlan(
        mode=mode,
        base_offset=base,
        total_size=total,
        expected_payload_bytes=payload_bytes,
        restarted=restarted,
    )


def validate_completed_transfer(
    final_size: int,
    *,
    total_size: int,
    payload_written: int,
    expected_payload_bytes: int,
    minimum_size: int = 1024,
) -> None:
    size = max(0, int(final_size or 0))
    if size < max(1, int(minimum_size)):
        raise RuntimeError("downloaded media stream is unexpectedly small")
    if expected_payload_bytes and payload_written != expected_payload_bytes:
        raise RuntimeError("response body length mismatch after transfer")
    if total_size and size != total_size:
        raise RuntimeError("content-length mismatch after resumed transfer")
