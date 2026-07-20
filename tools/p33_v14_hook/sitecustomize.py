#!/usr/bin/env python3
"""Conditional HTTP/1.1 and exact-tail hardening for the P33 scan transport.

Python imports ``sitecustomize`` automatically when this directory is placed on
``PYTHONPATH``. The hook is inert unless ``ATLAS_FORCE_HTTP11=1`` is present.
It preserves the existing bounded range/resume, authorization, privacy, and
media-retention rules while repairing small, verified end-of-stream gaps before
another CDN can replace a nearly complete partial file.
"""
from __future__ import annotations

import builtins
import os
import pathlib
import subprocess
import sys
from typing import Any

MIB = 1024 * 1024
ATLAS_HTTP11_PATCHED = False
ATLAS_TAIL_RESUME_PATCHED = False


def _tail_limit() -> int:
    try:
        configured = int(os.environ.get("ATLAS_EXACT_TAIL_MAX_BYTES", str(4 * MIB)))
    except (TypeError, ValueError):
        configured = 4 * MIB
    return max(1024, min(16 * MIB, configured))


def _curl_header_args(module: Any) -> list[str]:
    headers = getattr(getattr(module, "runner", None), "HEADERS", {}) or {}
    result: list[str] = []
    for name in ("Referer", "User-Agent", "Origin"):
        value = headers.get(name)
        if value:
            result.extend(["--header", f"{name}: {value}"])
    return result


def _response_is_exact_partial(header_path: pathlib.Path) -> bool:
    try:
        text = header_path.read_text(encoding="latin-1", errors="replace").lower()
    except OSError:
        return False
    status_lines = [line.strip() for line in text.splitlines() if line.lower().startswith("http/")]
    return bool(status_lines and " 206 " in f" {status_lines[-1]} ")


def _repair_exact_tail(
    module: Any,
    candidate: str,
    target: pathlib.Path,
    *,
    expected_size: int,
    heartbeat: Any,
    downloaded_before: int,
    segment_index: int,
) -> bool:
    """Append a small missing tail only when an exact HTTP 206 response is verified."""
    if expected_size <= 0 or not target.exists():
        return False
    existing = target.stat().st_size
    gap = expected_size - existing
    if gap <= 0 or gap > _tail_limit():
        return False

    tail_path = target.with_name(f"{target.name}.exact-tail.part")
    header_path = target.with_name(f"{target.name}.exact-tail.headers")
    tail_path.unlink(missing_ok=True)
    header_path.unlink(missing_ok=True)
    command = [
        "curl",
        "--http1.1",
        "--fail",
        "--location",
        "--silent",
        "--show-error",
        "--retry",
        "4",
        "--retry-delay",
        "1",
        "--retry-all-errors",
        "--connect-timeout",
        "20",
        "--max-time",
        "120",
        "--range",
        f"{existing}-{expected_size - 1}",
        "--header",
        "Accept-Encoding: identity",
        "--max-filesize",
        str(gap),
        "--dump-header",
        str(header_path),
        "--output",
        str(tail_path),
        *_curl_header_args(module),
        str(candidate),
    ]
    try:
        subprocess.run(command, capture_output=True, text=True, check=False)
        if not _response_is_exact_partial(header_path):
            return False
        if not tail_path.exists() or tail_path.stat().st_size != gap:
            return False
        with target.open("ab") as output, tail_path.open("rb") as source:
            while True:
                chunk = source.read(64 * 1024)
                if not chunk:
                    break
                output.write(chunk)
        if target.stat().st_size != expected_size:
            return False
        heartbeat.update(
            downloaded_bytes=downloaded_before + expected_size,
            segment_downloaded_bytes=expected_size,
            segment_total_bytes=expected_size,
            segment_index=segment_index,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        tail_path.unlink(missing_ok=True)
        header_path.unlink(missing_ok=True)


def _patch_v11(module: Any) -> bool:
    global ATLAS_TAIL_RESUME_PATCHED
    if getattr(module, "_atlas_exact_tail_patched", False):
        ATLAS_TAIL_RESUME_PATCHED = True
        return True
    original = getattr(module, "_single_stream_resume", None)
    if not callable(original):
        return False

    def exact_tail_resume(
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
        existing = target.stat().st_size if target.exists() else 0
        gap = expected_size - existing if expected_size else 0
        small_existing_gap = 0 < gap <= _tail_limit()
        if small_existing_gap and _repair_exact_tail(
            module,
            candidate,
            target,
            expected_size=expected_size,
            heartbeat=heartbeat,
            downloaded_before=downloaded_before,
            segment_index=segment_index,
        ):
            return
        if small_existing_gap:
            raise RuntimeError("exact tail repair failed; preserved near-complete partial stream")

        try:
            original(
                candidate,
                target,
                expected_size=expected_size,
                heartbeat=heartbeat,
                downloaded_before=downloaded_before,
                segment_index=segment_index,
                chunk_size=chunk_size,
                retries=retries,
            )
        except Exception:
            if _repair_exact_tail(
                module,
                candidate,
                target,
                expected_size=expected_size,
                heartbeat=heartbeat,
                downloaded_before=downloaded_before,
                segment_index=segment_index,
            ):
                return
            raise

    module._atlas_original_single_stream_resume = original
    module._single_stream_resume = exact_tail_resume
    module._atlas_exact_tail_patched = True
    ATLAS_TAIL_RESUME_PATCHED = True
    return True


def _install_import_hook() -> bool:
    current = builtins.__import__
    if getattr(current, "_atlas_exact_tail_import_hook", False):
        return True

    def importing(name: str, globals: Any = None, locals: Any = None, fromlist: Any = (), level: int = 0):
        result = current(name, globals, locals, fromlist, level)
        module = sys.modules.get("analyze_authorized_video_v11")
        if module is not None:
            _patch_v11(module)
        return result

    importing._atlas_exact_tail_import_hook = True
    importing._atlas_previous_import = current
    builtins.__import__ = importing
    module = sys.modules.get("analyze_authorized_video_v11")
    if module is not None:
        _patch_v11(module)
    return True


def _install_http11() -> bool:
    from curl_cffi import CurlHttpVersion, requests

    if getattr(requests, "_atlas_http11_patched", False):
        return True
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
    return True


if os.environ.get("ATLAS_FORCE_HTTP11") == "1":
    ATLAS_HTTP11_PATCHED = _install_http11()
    _install_import_hook()
