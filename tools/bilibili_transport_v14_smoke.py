#!/usr/bin/env python3
"""Deterministic 128-check gate for Atlas source transport v14.

The established v13 gate contributes 96 checks. This gate adds 32 byte-accurate
resume checks covering Content-Range validation, curl(18)-style truncation,
cross-response resume and safe overwrite when a server ignores Range.
"""
from __future__ import annotations

import pathlib
import tempfile
from typing import Any

import bilibili_transport_smoke as v13_smoke
import resumable_transport_v14 as resume_v14


def main() -> int:
    if v13_smoke.main() != 0:
        raise AssertionError("v13 source transport gate failed")

    import analyze_authorized_video_v14 as analyzer_v14

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

    # 16 deterministic response-planning checks.
    for index in range(8):
        offset = 1024 + index * 257
        total = offset + 2048
        plan = resume_v14.plan_response_write(
            206,
            {
                "Content-Range": f"bytes {offset}-{total - 1}/{total}",
                "Content-Length": "2048",
            },
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
        offset = 1024 + index
        plan = resume_v14.plan_response_write(
            200,
            {"Content-Length": "4096"},
            requested_offset=offset,
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

    original_requests = analyzer_v14.runner.requests
    original_headers = analyzer_v14.runner.HEADERS
    original_sleep = analyzer_v14.time.sleep
    analyzer_v14.runner.HEADERS = {"User-Agent": "Atlas-v14-smoke"}
    analyzer_v14.time.sleep = lambda _seconds: None

    try:
        with tempfile.TemporaryDirectory(prefix="atlas-v14-smoke-") as directory:
            root = pathlib.Path(directory)

            # Exact second-half append.
            target = root / "exact.m4s"
            target.write_bytes(b"a" * 1024)
            heartbeat = FakeHeartbeat()
            fake = FakeRequests([FakeResponse(
                206,
                {"Content-Range": "bytes 1024-2047/2048", "Content-Length": "1024"},
                [b"b" * 512, b"b" * 512],
            )])
            analyzer_v14.runner.requests = fake
            analyzer_v14._single_stream_resume_v14(
                "https://cdn.example/exact", target, expected_size=2048,
                heartbeat=heartbeat, downloaded_before=0, segment_index=1,
                chunk_size=512, retries=1,
            )
            check("runtime-exact-resume-size", target.stat().st_size == 2048)
            check("runtime-exact-resume-content", target.read_bytes() == b"a" * 1024 + b"b" * 1024)
            check("runtime-exact-resume-header", fake.headers_seen == [{"User-Agent": "Atlas-v14-smoke", "Accept-Encoding": "identity", "Range": "bytes=1024-"}])
            check("runtime-exact-resume-heartbeat", heartbeat.updates[-1]["segmentDownloadedBytes"] == 2048)

            # Range ignored: overwrite, never append a fresh full response to residue.
            target = root / "overwrite.m4s"
            target.write_bytes(b"old" * 500)
            heartbeat = FakeHeartbeat()
            fake = FakeRequests([FakeResponse(200, {"Content-Length": "2048"}, [b"c" * 2048])])
            analyzer_v14.runner.requests = fake
            analyzer_v14._single_stream_resume_v14(
                "https://cdn.example/full", target, expected_size=2048,
                heartbeat=heartbeat, downloaded_before=0, segment_index=1,
                chunk_size=512, retries=1,
            )
            check("runtime-full-restart-size", target.stat().st_size == 2048)
            check("runtime-full-restart-content", target.read_bytes() == b"c" * 2048)
            check("runtime-full-restart-no-residue", b"old" not in target.read_bytes())
            check("runtime-full-restart-requested-range", fake.headers_seen[0]["Range"].startswith("bytes="))

            # curl(18)-style mid-body failure resumes from the durable byte count.
            target = root / "truncated.m4s"
            heartbeat = FakeHeartbeat()
            fake = FakeRequests([
                FakeResponse(200, {"Content-Length": "2048"}, [b"d" * 1024, RuntimeError("curl: (18) end of response")]),
                FakeResponse(206, {"Content-Range": "bytes 1024-2047/2048", "Content-Length": "1024"}, [b"e" * 1024]),
            ])
            analyzer_v14.runner.requests = fake
            analyzer_v14._single_stream_resume_v14(
                "https://cdn.example/truncated", target, expected_size=2048,
                heartbeat=heartbeat, downloaded_before=0, segment_index=1,
                chunk_size=512, retries=2,
            )
            check("runtime-truncation-resume-size", target.stat().st_size == 2048)
            check("runtime-truncation-resume-content", target.read_bytes() == b"d" * 1024 + b"e" * 1024)
            check("runtime-truncation-second-offset", fake.headers_seen[1]["Range"] == "bytes=1024-")
            check("runtime-truncation-count-synchronized", heartbeat.updates[-1]["downloadedBytes"] == 2048)

            # Missing total length plus a fresh full response must safely restart.
            target = root / "unknown-total.m4s"
            target.write_bytes(b"residue" * 200)
            heartbeat = FakeHeartbeat()
            fake = FakeRequests([FakeResponse(200, {}, [b"f" * 2048])])
            analyzer_v14.runner.requests = fake
            analyzer_v14._single_stream_resume_v14(
                "https://cdn.example/unknown", target, expected_size=0,
                heartbeat=heartbeat, downloaded_before=256, segment_index=2,
                chunk_size=1024, retries=1,
            )
            check("runtime-unknown-total-size", target.stat().st_size == 2048)
            check("runtime-unknown-total-content", target.read_bytes() == b"f" * 2048)
            check("runtime-unknown-total-no-append", b"residue" not in target.read_bytes())
            check("runtime-unknown-total-heartbeat", heartbeat.updates[-1]["downloadedBytes"] == 2304)
    finally:
        analyzer_v14.runner.requests = original_requests
        analyzer_v14.runner.HEADERS = original_headers
        analyzer_v14.time.sleep = original_sleep

    if len(checks) != 32:
        raise AssertionError(f"expected 32 v14 checks, executed {len(checks)}")
    print("128/128 v14 WBI transport, byte-accurate resume, safe restart, identity, and privacy checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
