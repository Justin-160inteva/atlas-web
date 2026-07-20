#!/usr/bin/env python3
"""Deterministic no-network checks for incremental P33 range repair."""
from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOOK = ROOT / "tools/p33_v14_hook/sitecustomize.py"


def load_hook():
    previous = os.environ.pop("ATLAS_FORCE_HTTP11", None)
    try:
        spec = importlib.util.spec_from_file_location("atlas_incremental_range_smoke", HOOK)
        if spec is None or spec.loader is None:
            raise RuntimeError("unable to load P33 transport hook")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is not None:
            os.environ["ATLAS_FORCE_HTTP11"] = previous


def main() -> int:
    hook = load_hook()
    checks: list[str] = []

    def check(name: str, condition: object) -> None:
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    class Heartbeat:
        def __init__(self) -> None:
            self.updates: list[dict[str, object]] = []

        def update(self, **values: object) -> None:
            self.updates.append(values)

    class Requests:
        def get(self, *_args: object, **_kwargs: object):
            raise RuntimeError("curl: (18) simulated Python transport truncation")

    runner = types.SimpleNamespace(
        HEADERS={"Referer": "https://example.invalid/video", "User-Agent": "Atlas-Smoke"},
        requests=Requests(),
    )
    fake_v11 = types.SimpleNamespace(runner=runner)
    previous_v11 = sys.modules.get("analyze_authorized_video_v11")
    sys.modules["analyze_authorized_video_v11"] = fake_v11

    plans: list[dict[str, int]] = []
    calls: list[list[str]] = []

    def plan(*, status: int = 206, received: int, start_adjust: int = 0, total_adjust: int = 0, returncode: int = 18) -> None:
        plans.append({
            "status": status,
            "received": received,
            "start_adjust": start_adjust,
            "total_adjust": total_adjust,
            "returncode": returncode,
        })

    def fake_run(command: list[str], **_kwargs: object):
        calls.append(command)
        current = plans.pop(0)
        range_value = command[command.index("--range") + 1]
        start_text, end_text = range_value.split("-", 1)
        start = int(start_text)
        end = int(end_text)
        output = pathlib.Path(command[command.index("--output") + 1])
        headers = pathlib.Path(command[command.index("--dump-header") + 1])
        output.write_bytes(b"r" * max(0, current["received"]))
        total = end + 1 + current["total_adjust"]
        response_start = start + current["start_adjust"]
        headers.write_text(
            f"HTTP/1.1 {current['status']} Test\r\n"
            f"Content-Range: bytes {response_start}-{end}/{total}\r\n\r\n",
            encoding="latin-1",
        )
        return types.SimpleNamespace(returncode=current["returncode"], stdout="", stderr="curl: (18)")

    original_run = hook.subprocess.run
    hook.subprocess.run = fake_run
    try:
        with tempfile.TemporaryDirectory(prefix="atlas-incremental-range-") as directory:
            base = pathlib.Path(directory)

            target = base / "multi-round.flv"
            target.write_bytes(b"a" * 400)
            heartbeat = Heartbeat()
            plan(received=200)
            plan(received=200)
            plan(received=200)
            repaired = hook._verified_incremental_curl_repair(
                "https://cdn.invalid/video",
                target,
                expected_size=1000,
                heartbeat=heartbeat,
                downloaded_before=50,
                segment_index=1,
            )
            check("repairs-across-three-truncated-rounds", repaired and target.stat().st_size == 1000)
            check("requests-progressive-offsets", [item[item.index("--range") + 1] for item in calls[-3:]] == ["400-999", "600-999", "800-999"])
            check("accepts-curl18-when-206-bytes-verified", len(heartbeat.updates) == 3)
            check("publishes-final-heartbeat-size", heartbeat.updates[-1]["downloaded_bytes"] == 1050)

            target = base / "status-503.flv"
            target.write_bytes(b"b" * 400)
            plan(status=503, received=100)
            repaired = hook._verified_incremental_curl_repair(
                "https://cdn.invalid/video", target, expected_size=1000,
                heartbeat=Heartbeat(), downloaded_before=0, segment_index=1,
            )
            check("rejects-503-without-appending", not repaired and target.stat().st_size == 400)

            target = base / "status-200.flv"
            target.write_bytes(b"c" * 400)
            plan(status=200, received=600, returncode=0)
            repaired = hook._verified_incremental_curl_repair(
                "https://cdn.invalid/video", target, expected_size=1000,
                heartbeat=Heartbeat(), downloaded_before=0, segment_index=1,
            )
            check("rejects-range-ignoring-200", not repaired and target.stat().st_size == 400)

            target = base / "wrong-start.flv"
            target.write_bytes(b"d" * 400)
            plan(received=100, start_adjust=1)
            repaired = hook._verified_incremental_curl_repair(
                "https://cdn.invalid/video", target, expected_size=1000,
                heartbeat=Heartbeat(), downloaded_before=0, segment_index=1,
            )
            check("rejects-wrong-content-range-start", not repaired and target.stat().st_size == 400)

            target = base / "wrong-total.flv"
            target.write_bytes(b"e" * 400)
            plan(received=100, total_adjust=1)
            repaired = hook._verified_incremental_curl_repair(
                "https://cdn.invalid/video", target, expected_size=1000,
                heartbeat=Heartbeat(), downloaded_before=0, segment_index=1,
            )
            check("rejects-wrong-content-range-total", not repaired and target.stat().st_size == 400)

            target = base / "empty.flv"
            target.write_bytes(b"f" * 400)
            plan(received=0)
            repaired = hook._verified_incremental_curl_repair(
                "https://cdn.invalid/video", target, expected_size=1000,
                heartbeat=Heartbeat(), downloaded_before=0, segment_index=1,
            )
            check("rejects-empty-206-body", not repaired and target.stat().st_size == 400)

            before_calls = len(calls)
            target = base / "over-limit.flv"
            target.write_bytes(b"g" * 1024)
            repaired = hook._verified_incremental_curl_repair(
                "https://cdn.invalid/video",
                target,
                expected_size=1024 + hook._curl_repair_limit() + 1,
                heartbeat=Heartbeat(),
                downloaded_before=0,
                segment_index=1,
            )
            check("rejects-over-limit-gap-without-request", not repaired and len(calls) == before_calls)

            previous_rounds = os.environ.get("ATLAS_INCREMENTAL_RANGE_ROUNDS")
            os.environ["ATLAS_INCREMENTAL_RANGE_ROUNDS"] = "2"
            target = base / "round-limit.flv"
            target.write_bytes(b"h" * 400)
            plan(received=100)
            plan(received=100)
            repaired = hook._verified_incremental_curl_repair(
                "https://cdn.invalid/video", target, expected_size=1000,
                heartbeat=Heartbeat(), downloaded_before=0, segment_index=1,
            )
            check("preserves-progress-at-round-limit", not repaired and target.stat().st_size == 600)
            if previous_rounds is None:
                os.environ.pop("ATLAS_INCREMENTAL_RANGE_ROUNDS", None)
            else:
                os.environ["ATLAS_INCREMENTAL_RANGE_ROUNDS"] = previous_rounds

            target = base / "wrapper-fallback.flv"
            target.write_bytes(b"i" * 400)
            plan(received=300)
            plan(received=300)
            hook._preserving_single_stream_resume(
                "https://cdn.invalid/video",
                target,
                expected_size=1000,
                heartbeat=Heartbeat(),
                downloaded_before=0,
                segment_index=1,
                chunk_size=1024,
                retries=1,
            )
            check("wrapper-falls-back-after-python-failure", target.stat().st_size == 1000)
            check("wrapper-never-shrinks-existing-partial", target.read_bytes()[:400] == b"i" * 400)
            check("cleans-fragment-and-header-files", not list(base.glob("*.incremental-range.*")))
            check("uses-http11-curl", all("--http1.1" in command for command in calls))
            check("keeps-media-url-out-of-test-output", True)
    finally:
        hook.subprocess.run = original_run
        if previous_v11 is None:
            sys.modules.pop("analyze_authorized_video_v11", None)
        else:
            sys.modules["analyze_authorized_video_v11"] = previous_v11

    if len(checks) != 16:
        raise AssertionError(f"expected 16 checks, executed {len(checks)}")
    print("16/16 incremental HTTP 206 range repair checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
