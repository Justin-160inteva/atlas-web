#!/usr/bin/env python3
"""Deterministic 128-check gate for Atlas source transport v14.

The established v13 suite runs in an isolated subprocess (96 checks). This process
then executes 32 byte-accurate resume checks for Content-Range validation,
curl(18)-style truncation, safe restart and durable heartbeat accounting.
"""
from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import types
from typing import Any

import resumable_transport_v14 as resume_v14

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_analyzer() -> Any:
    fake_runner = types.SimpleNamespace(HEADERS={}, requests=None)
    fake_v9 = types.SimpleNamespace(v6=types.SimpleNamespace(main=lambda: 0))
    fake_v11 = types.SimpleNamespace(_single_stream_resume=lambda *_a, **_k: None)
    fake_v13 = types.ModuleType("analyze_authorized_video_v13")
    fake_v13.v12 = types.SimpleNamespace()
    fake_v13.v11 = fake_v11
    fake_v13.v9 = fake_v9
    fake_v13.runner = fake_runner
    fake_v13.transport = types.SimpleNamespace()
    fake_v13.direct_bilibili_download = lambda *_a, **_k: None
    fake_v13.download_with_fallbacks = lambda *_a, **_k: None

    previous = sys.modules.get("analyze_authorized_video_v13")
    sys.modules["analyze_authorized_video_v13"] = fake_v13
    try:
        spec = importlib.util.spec_from_file_location(
            "atlas_analyzer_v14_smoke",
            pathlib.Path(__file__).with_name("analyze_authorized_video_v14.py"),
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("unable to load v14 analyzer")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            sys.modules.pop("analyze_authorized_video_v13", None)
        else:
            sys.modules["analyze_authorized_video_v13"] = previous


def main() -> int:
    legacy = subprocess.run(
        [sys.executable, "tools/bilibili_transport_smoke.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if legacy.returncode != 0 or "96/96" not in legacy.stdout:
        sys.stdout.write(legacy.stdout)
        sys.stderr.write(legacy.stderr)
        raise AssertionError("isolated v13 transport regression gate failed")

    analyzer = _load_analyzer()
    checks: list[str] = []

    def check(name: str, condition: object) -> None:
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    def raises(name: str, function: Any) -> None:
        try:
            function()
        except (TypeError, ValueError, RuntimeError):
            checks.append(name)
            return
        raise AssertionError(name)

    # 16 pure response-planning checks.
    for index in range(8):
        offset = 1024 + index * 257
        total = offset + 2048
        plan = resume_v14.plan_response_write(
            206,
            {"Content-Range": f"bytes {offset}-{total - 1}/{total}", "Content-Length": "2048"},
            requested_offset=offset,
            expected_size=total,
        )
        check(
            f"exact-resume-plan-{index:02d}",
            plan.mode == "ab"
            and plan.base_offset == offset
            and plan.total_size == total
            and plan.expected_payload_bytes == 2048
            and not plan.restarted,
        )

    for index in range(4):
        plan = resume_v14.plan_response_write(
            200,
            {"Content-Length": "4096"},
            requested_offset=1024 + index,
            expected_size=4096,
        )
        check(
            f"ignored-range-safe-restart-{index:02d}",
            plan.mode == "wb" and plan.base_offset == 0 and plan.restarted and plan.total_size == 4096,
        )

    raises(
        "reject-resume-without-content-range",
        lambda: resume_v14.plan_response_write(206, {"Content-Length": "10"}, requested_offset=10),
    )
    raises(
        "reject-resume-from-wrong-offset",
        lambda: resume_v14.plan_response_write(
            206, {"Content-Range": "bytes 7-9/10"}, requested_offset=5
        ),
    )
    raises("reject-invalid-content-range", lambda: resume_v14.parse_content_range("bytes bad"))
    raises("reject-incoherent-content-range", lambda: resume_v14.parse_content_range("bytes 8-4/10"))

    class FakeHeartbeat:
        def __init__(self) -> None:
            self.updates: list[dict[str, object]] = []

        def update(self, **values: object) -> None:
            self.updates.append(values)

    class FakeResponse:
        def __init__(self, status: int, headers: dict[str, str], chunks: list[bytes | Exception]) -> None:
            self.status_code = status
            self.headers = headers
            self.chunks = chunks

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

        def iter_content(self, *, chunk_size: int):
            del chunk_size
            for item in self.chunks:
                if isinstance(item, Exception):
                    raise item
                yield item

    class FakeRequests:
        def __init__(self, responses: list[FakeResponse]) -> None:
            self.responses = list(responses)
            self.headers_seen: list[dict[str, str]] = []

        def get(self, _candidate: str, *, headers: dict[str, str], **_values: object) -> FakeResponse:
            self.headers_seen.append(dict(headers))
            if not self.responses:
                raise AssertionError("unexpected request")
            return self.responses.pop(0)

    original_requests = analyzer.runner.requests
    original_headers = analyzer.runner.HEADERS
    original_sleep = analyzer.time.sleep
    analyzer.runner.HEADERS = {"User-Agent": "Atlas-v14-smoke"}
    analyzer.time.sleep = lambda _seconds: None

    def run_case(
        name: str,
        initial: bytes,
        responses: list[FakeResponse],
        expected: bytes,
        *,
        expected_size: int,
        downloaded_before: int = 0,
        retries: int = 1,
    ) -> tuple[FakeRequests, FakeHeartbeat]:
        target = test_root / f"{name}.m4s"
        if initial:
            target.write_bytes(initial)
        fake = FakeRequests(responses)
        heartbeat = FakeHeartbeat()
        analyzer.runner.requests = fake
        analyzer._single_stream_resume_v14(
            f"https://cdn.example/{name}",
            target,
            expected_size=expected_size,
            heartbeat=heartbeat,
            downloaded_before=downloaded_before,
            segment_index=1,
            chunk_size=512,
            retries=retries,
        )
        check(f"runtime-{name}-size", target.stat().st_size == len(expected))
        check(f"runtime-{name}-content", target.read_bytes() == expected)
        return fake, heartbeat

    try:
        with tempfile.TemporaryDirectory(prefix="atlas-v14-smoke-") as directory:
            test_root = pathlib.Path(directory)

            fake, heartbeat = run_case(
                "exact",
                b"a" * 1024,
                [FakeResponse(206, {"Content-Range": "bytes 1024-2047/2048", "Content-Length": "1024"}, [b"b" * 512, b"b" * 512])],
                b"a" * 1024 + b"b" * 1024,
                expected_size=2048,
            )
            check("runtime-exact-header", fake.headers_seen[0].get("Range") == "bytes=1024-")
            check("runtime-exact-heartbeat", heartbeat.updates[-1]["segmentDownloadedBytes"] == 2048)

            fake, heartbeat = run_case(
                "restart",
                b"old" * 500,
                [FakeResponse(200, {"Content-Length": "2048"}, [b"c" * 2048])],
                b"c" * 2048,
                expected_size=2048,
            )
            check("runtime-restart-range-requested", "Range" in fake.headers_seen[0])
            check("runtime-restart-no-residue", heartbeat.updates[-1]["segmentDownloadedBytes"] == 2048)

            fake, heartbeat = run_case(
                "truncation",
                b"",
                [
                    FakeResponse(200, {"Content-Length": "2048"}, [b"d" * 1024, RuntimeError("curl: (18) end of response")]),
                    FakeResponse(206, {"Content-Range": "bytes 1024-2047/2048", "Content-Length": "1024"}, [b"e" * 1024]),
                ],
                b"d" * 1024 + b"e" * 1024,
                expected_size=2048,
                retries=2,
            )
            check("runtime-truncation-second-offset", fake.headers_seen[1].get("Range") == "bytes=1024-")
            check("runtime-truncation-durable-count", heartbeat.updates[-1]["downloadedBytes"] == 2048)

            fake, heartbeat = run_case(
                "unknown-total",
                b"residue" * 200,
                [FakeResponse(200, {}, [b"f" * 2048])],
                b"f" * 2048,
                expected_size=0,
                downloaded_before=256,
            )
            check("runtime-unknown-total-range-requested", "Range" in fake.headers_seen[0])
            check("runtime-unknown-total-heartbeat", heartbeat.updates[-1]["downloadedBytes"] == 2304)
    finally:
        analyzer.runner.requests = original_requests
        analyzer.runner.HEADERS = original_headers
        analyzer.time.sleep = original_sleep

    if len(checks) != 32:
        raise AssertionError(f"expected 32 v14 checks, executed {len(checks)}")
    print(legacy.stdout.strip())
    print("128/128 v14 WBI transport, byte-accurate resume, safe restart, identity, and privacy checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
