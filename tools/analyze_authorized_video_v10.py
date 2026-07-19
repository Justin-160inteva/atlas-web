#!/usr/bin/env python3
"""Compatibility-fixed minute-heartbeat analyzer for curl_cffi responses.

curl_cffi.requests.Response does not implement the context-manager protocol in the
runner environment. v9 expected `with requests.get(...)`, so public-API downloads
failed before receiving the first byte. This adapter preserves the v9 telemetry
pipeline while wrapping responses in an explicit closing context manager.
"""
from __future__ import annotations

from typing import Any

import analyze_authorized_video_v9 as v9


class ClosingResponse:
    """Delegate to a curl_cffi response and close it after a with block."""

    def __init__(self, response: Any) -> None:
        self._response = response

    def __enter__(self) -> Any:
        return self._response

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> bool:
        close = getattr(self._response, "close", None)
        if callable(close):
            close()
        return False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._response, name)


_original_get = v9.runner.requests.get


def compatible_get(*args: Any, **kwargs: Any) -> ClosingResponse:
    return ClosingResponse(_original_get(*args, **kwargs))


v9.runner.requests.get = compatible_get


if __name__ == "__main__":
    raise SystemExit(v9.v6.main())
