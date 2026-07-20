#!/usr/bin/env python3
"""Deterministic no-network gates for Atlas resumable chunk transports."""
from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import tempfile
import threading
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


class SequentialRequests:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if not self.responses:
            raise AssertionError("unexpected extra sequential request")
        return self.responses.pop(0)

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        return self.get(url, method=method, **kwargs)


class RoutedParallelRequests:
    def __init__(self, mode: str):
        self.mode = mode
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def get(self, _url: str, **kwargs: Any) -> FakeResponse:
        range_header = kwargs["headers"]["Range"]
        with self._lock:
            self.calls.append(range_header)

        if self.mode == "first-cdn":
            if range_header == "bytes=0-2047":
                return FakeResponse(206, {"content-range": "bytes 0-2047/8192"}, [b"P" * 2048])
            return FakeResponse(503, {}, [])

        mapping: dict[str, FakeResponse] = {
            "bytes=2048-4095": FakeResponse(
                206,
                {"content-range": "bytes 2048-4095/8192"},
                [b"Q" * 1024, FakeDisconnect("parallel partial disconnect")],
            ),
            "bytes=3072-4095": FakeResponse(
                206,
                {"content-range": "bytes 3072-4095/8192"},
                [b"R" * 1024],
            ),
            "bytes=4096-6143": FakeResponse(
                206,
                {"content-range": "bytes 4096-6143/8192"},
                [b"S" * 2048],
            ),
            "bytes=6144-8191": FakeResponse(
                206,
                {"content-range": "bytes 6144-8191/8192"},
                [b"T" * 2048],
            ),
        }
        response = mapping.get(range_header)
        if response is None:
            raise AssertionError(f"unexpected parallel range: {range_header}")
        return response


class Heartbeat:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def update(self, **values: Any) -> None:
        with self._lock:
            self.updates.append(values)


def main() -> int:
    os.environ["ATLAS_FORCE_HTTP11"] = "1"
    os.environ["ATLAS_TAIL_REQUEST_BYTES"] = "2048"
    os.environ["ATLAS_PARALLEL_THRESHOLD_BYTES"] = "4096"
    os.environ["ATLAS_PARALLEL_RANGE_WORKERS"] = "2"

    sequential = SequentialRequests([
        FakeResponse(200, {"content-length": "2048"}, [b"X" * 2048]),
        FakeResponse(
            206,
            {"content-range": "bytes 2048-4095/8192"},
            [b"B" * 1024, FakeDisconnect("sequential partial disconnect")],
        ),
        FakeResponse(206, {"content-range": "bytes 3072-5119/8192"}, [b"C" * 2048]),
        FakeResponse(206, {"content-range": "bytes 5120-7167/8192"}, [b"D" * 2048]),
        FakeResponse(206, {"content-range": "bytes 7168-8191/8192"}, [b"E" * 1024]),
    ])

    curl_module = types.ModuleType("curl_cffi")
    curl_module.CurlHttpVersion = types.SimpleNamespace(V1_1="HTTP/1.1")
    curl_module.requests = sequential

    old_single_calls: list[dict[str, Any]] = []
    old_parallel_calls: list[dict[str, Any]] = []

    def old_single(*_args: object, **kwargs: Any) -> None:
        old_single_calls.append(kwargs)

    def old_parallel(*_args: object, **kwargs: Any) -> None:
        old_parallel_calls.append(kwargs)

    fake_v11 = types.ModuleType("analyze_authorized_video_v11")
    fake_v11.runner = types.SimpleNamespace(HEADERS={"User-Agent": "smoke"}, requests=sequential)
    fake_v11._single_stream_resume = old_single
    fake_v11._parallel_range_download = old_parallel

    previous = {name: sys.modules.get(name) for name in ("curl_cffi", "analyze_authorized_video_v11")}
    sys.modules["curl_cffi"] = curl_module
    sys.modules["analyze_authorized_video_v11"] = fake_v11

    hook_path = pathlib.Path(__file__).parent / "p33_v14_hook" / "sitecustomize.py"
    spec = importlib.util.spec_from_file_location("atlas_chunk_transport_smoke", hook_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load transport hook")
    hook = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(hook)
        hook.time.sleep = lambda _seconds: None

        sequential_heartbeat = Heartbeat()
        with tempfile.TemporaryDirectory(prefix="atlas-sequential-tail-") as directory:
            sequential_target = pathlib.Path(directory) / "partial.flv"
            sequential_target.write_bytes(b"A" * 2048)
            hook._preserving_single_stream_resume(
                "https://cdn.invalid/sequential",
                sequential_target,
                expected_size=8192,
                heartbeat=sequential_heartbeat,
                downloaded_before=0,
                segment_index=1,
                chunk_size=4096,
                retries=2,
            )
            sequential_payload = sequential_target.read_bytes()

        with tempfile.TemporaryDirectory(prefix="atlas-parallel-tail-") as directory:
            parallel_target = pathlib.Path(directory) / "parallel.flv"
            first_cdn = RoutedParallelRequests("first-cdn")
            fake_v11.runner.requests = first_cdn
            first_failed = False
            try:
                hook._preserving_parallel_range_download(
                    "https://cdn.invalid/first",
                    parallel_target,
                    total_size=8192,
                    heartbeat=Heartbeat(),
                    downloaded_before=0,
                    segment_index=1,
                    workers=2,
                    chunk_size=2048,
                    retries=1,
                )
            except Exception:
                first_failed = True

            preserved_parts = sorted(pathlib.Path(directory).glob("parallel.flv.atlas-range-*.part"))
            preserved_zero = next(
                (part for part in preserved_parts if part.name.endswith("00000.part")),
                None,
            )
            preserved_zero_size = preserved_zero.stat().st_size if preserved_zero is not None else -1
            marker = pathlib.Path(directory) / "parallel.flv.atlas-parallel-candidate"
            marker_before_second = marker.exists()

            second_cdn = RoutedParallelRequests("second-cdn")
            fake_v11.runner.requests = second_cdn
            parallel_heartbeat = Heartbeat()
            hook._preserving_parallel_range_download(
                "https://cdn.invalid/second",
                parallel_target,
                total_size=8192,
                heartbeat=parallel_heartbeat,
                downloaded_before=0,
                segment_index=1,
                workers=2,
                chunk_size=2048,
                retries=2,
            )
            parallel_payload = parallel_target.read_bytes()
            remaining_parts = list(pathlib.Path(directory).glob("parallel.flv.atlas-range-*.part"))
            marker_remaining = marker.exists()
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    checks = {
        "http11-installed": hook.ATLAS_HTTP11_PATCHED is True,
        "tail-installed": hook.ATLAS_TAIL_REPAIR_PATCHED is True,
        "parallel-installed": hook.ATLAS_PARALLEL_CHUNK_PATCHED is True,
        "single-function-replaced": fake_v11._single_stream_resume is hook._preserving_single_stream_resume,
        "parallel-function-replaced": fake_v11._parallel_range_download is hook._preserving_parallel_range_download,
        "legacy-single-not-used": old_single_calls == [],
        "legacy-parallel-not-used": old_parallel_calls == [],
        "sequential-final-size": len(sequential_payload) == 8192,
        "sequential-prefix-preserved": sequential_payload[:2048] == b"A" * 2048,
        "sequential-ignored-200": b"X" not in sequential_payload,
        "sequential-disconnect-preserved": sequential_payload[2048:3072] == b"B" * 1024,
        "sequential-http11": all(call.get("http_version") == "HTTP/1.1" for call in sequential.calls),
        "first-cdn-failed": first_failed,
        "first-cdn-part-preserved": preserved_zero_size == 2048,
        "first-cdn-marker-preserved": marker_before_second,
        "second-cdn-skipped-complete-part": "bytes=0-2047" not in second_cdn.calls,
        "parallel-final-size": len(parallel_payload) == 8192,
        "parallel-final-content": parallel_payload == b"P" * 2048 + b"Q" * 1024 + b"R" * 1024 + b"S" * 2048 + b"T" * 2048,
        "parallel-parts-cleaned": remaining_parts == [],
        "parallel-marker-cleaned": marker_remaining is False,
        "parallel-heartbeat-present": bool(parallel_heartbeat.updates),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssertionError(f"chunk transport smoke failed: {failed}")
    print(f"{len(checks)}/{len(checks)} sequential and parallel chunk checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
