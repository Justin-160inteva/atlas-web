#!/usr/bin/env python3
"""Use resumable curl transfers for Bilibili CDN media."""

from __future__ import annotations

import pathlib
import subprocess

import analyze_authorized_video_v2 as runner


def stream_to_file(url: str, destination: pathlib.Path) -> None:
    destination.unlink(missing_ok=True)
    command = [
        "curl",
        "--location",
        "--fail",
        "--silent",
        "--show-error",
        "--http1.1",
        "--retry", "12",
        "--retry-all-errors",
        "--retry-delay", "2",
        "--continue-at", "-",
        "--user-agent", runner.HEADERS["User-Agent"],
        "--referer", runner.HEADERS["Referer"],
        "--header", "Origin: https://www.bilibili.com",
        "--output", str(destination),
        url,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=900)
    if result.returncode != 0:
        raise RuntimeError(runner.clean_error(result.stderr or f"curl exited {result.returncode}"))
    if not destination.exists() or destination.stat().st_size < 1024:
        raise RuntimeError("Resumable Bilibili media download produced no usable file")


runner.stream_to_file = stream_to_file


if __name__ == "__main__":
    raise SystemExit(runner.main())
