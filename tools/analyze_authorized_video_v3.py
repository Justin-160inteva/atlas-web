#!/usr/bin/env python3
"""Compatibility layer for curl_cffi streamed Bilibili downloads."""

from __future__ import annotations

import pathlib

from curl_cffi import requests

import analyze_authorized_video_v2 as runner


def stream_to_file(url: str, destination: pathlib.Path) -> None:
    response = requests.get(
        url,
        headers=runner.HEADERS,
        impersonate="chrome",
        stream=True,
        timeout=60,
    )
    try:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    finally:
        response.close()
    if destination.stat().st_size < 1024:
        raise RuntimeError("Downloaded Bilibili media segment is unexpectedly small")


runner.stream_to_file = stream_to_file


if __name__ == "__main__":
    raise SystemExit(runner.main())
