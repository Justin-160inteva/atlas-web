#!/usr/bin/env python3
"""Deterministic no-network gate for the P33 chunked-tail transport hook."""
from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import tempfile
import types
from typing import Any


class FakeDisconnect(RuntimeError):
    pass


class FakeResponse:
    def __init__(self, status: int, headers: dict[str, str], chunks: list[bytes | Exception]):
        self.status_code = status
        self.headers = headers
        self._chunks = chunks

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> bool:
        return False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, *, chunk_size: int):
        assert chunk_size >= 1024
        for item in self._chunks:
            if isinstance(item, Exception):
                raise item
            yield item


class FakeRequests:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if not self.responses:
            raise AssertionError("unexpected extra request")
        return self.responses.pop(0)

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        return self.get(url, method=method, **kwargs)


class Heartbeat:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def update(self, **values: Any) -> None:
        self.updates.append(values)


def main() -> int:
    os.environ["ATLAS_FORCE_HTTP11"] = "1"
    os.environ["ATLAS_TAIL_REQUEST_BYTES"] = "2048"

    responses = [
        FakeResponse(200, {"content-length": "2048"}, [b"X" * 2048]),
        FakeResponse(
            206,
            {"content-range": "bytes 2048-4095/8192", "content-length": "2048"},
            [b"B" * 1024, FakeDisconnect("simulated mid-range disconnect")],
        ),
        FakeResponse(
            206,
            {"content-range": "bytes 3072-5119/8192", "content-length": "2048"},
            [b"C" * 2048],
        ),
        FakeResponse(
            206,
            {"content-range": "bytes 5120-7167/8192", "content-length": "2048"},
            [b"D" * 2048],
        ),
        FakeResponse(
            206,
            {"content-range": "bytes 7168-8191/8192", "content-length": "1024"},
            [b"E" * 1024],
        ),
    ]
    fake_requests = FakeRequests(responses)

    curl_module = types.ModuleType("curl_cffi")
    curl_module.CurlHttpVersion = types.SimpleNamespace(V1_1="HTTP/1.1")
    curl_module.requests = fake_requests

    old_resume_calls: list[dict[str, Any]] = []

    def old_resume(*_args: object, **kwargs: Any) -> None:
        old_resume_calls.append(kwargs)

    fake_v11 = types.ModuleType("analyze_authorized_video_v11")
    fake_v11.runner = types.SimpleNamespace(HEADERS={"User-Agent": "smoke"}, requests=fake_requests)
    fake_v11._single_stream_resume = old_resume

    previous = {
        name: sys.modules.get(name)
        for name in ("curl_cffi", "analyze_authorized_video_v11")
    }
    sys.modules["curl_cffi"] = curl_module
    sys.modules["analyze_authorized_video_v11"] = fake_v11

    hook_path = pathlib.Path(__file__).parent / "p33_v14_hook" / "sitecustomize.py"
    spec = importlib.util.spec_from_file_location("atlas_p33_chunked_tail_smoke", hook_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load P33 transport hook")
    hook = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(hook)
        heartbeat = Heartbeat()
        with tempfile.TemporaryDirectory(prefix="atlas-p33-tail-") as directory:
            target = pathlib.Path(directory) / "partial.flv"
            target.write_bytes(b"A" * 2048)
            fake_v11._single_stream_resume(
                "https://cdn.invalid/video",
                target,
                expected_size=8192,
                heartbeat=heartbeat,
                downloaded_before=0,
                segment_index=1,
                chunk_size=4096,
                retries=2,
            )
            payload = target.read_bytes()
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    checks = {
        "http11-installed": hook.ATLAS_HTTP11_PATCHED is True,
        "tail-installed": hook.ATLAS_TAIL_REPAIR_PATCHED is True,
        "function-replaced": fake_v11._single_stream_resume is hook._preserving_single_stream_resume,
        "legacy-not-used": old_resume_calls == [],
        "final-size": len(payload) == 8192,
        "existing-prefix-preserved": payload[:2048] == b"A" * 2048,
        "ignored-200-not-written": b"X" not in payload,
        "disconnect-bytes-preserved": payload[2048:3072] == b"B" * 1024,
        "remaining-chunks-appended": payload[3072:] == b"C" * 2048 + b"D" * 2048 + b"E" * 1024,
        "exact-range-sequence": [
            call["headers"]["Range"] for call in fake_requests.calls
        ] == [
            "bytes=2048-4095",
            "bytes=2048-4095",
            "bytes=3072-5119",
            "bytes=5120-7167",
            "bytes=7168-8191",
        ],
        "http11-every-request": all(
            call.get("http_version") == "HTTP/1.1" for call in fake_requests.calls
        ),
        "heartbeat-monotonic": bool(heartbeat.updates) and all(
            left["segment_downloaded_bytes"] <= right["segment_downloaded_bytes"]
            for left, right in zip(heartbeat.updates, heartbeat.updates[1:])
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssertionError(f"chunked-tail smoke failed: {failed}")
    print(f"{len(checks)}/{len(checks)} P33 chunked-tail preservation checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
