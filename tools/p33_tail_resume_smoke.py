#!/usr/bin/env python3
"""Deterministic no-network checks for the P33 exact-tail repair hook."""
from __future__ import annotations

import importlib.util
import os
import pathlib
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOOK = ROOT / "tools/p33_v14_hook/sitecustomize.py"


def load_hook():
    previous = os.environ.pop("ATLAS_FORCE_HTTP11", None)
    try:
        spec = importlib.util.spec_from_file_location("atlas_p33_tail_hook_smoke", HOOK)
        if spec is None or spec.loader is None:
            raise RuntimeError("unable to load exact-tail hook")
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

    runner = types.SimpleNamespace(HEADERS={"Referer": "https://example.invalid/video", "User-Agent": "Atlas-Smoke"})
    fake_module = types.SimpleNamespace(runner=runner)
    calls: list[list[str]] = []
    mode = {"status": 206, "tail_adjust": 0, "returncode": 18}

    def fake_run(command: list[str], **_kwargs: object):
        calls.append(command)
        range_value = command[command.index("--range") + 1]
        start_text, end_text = range_value.split("-", 1)
        expected = int(end_text) - int(start_text) + 1 + int(mode["tail_adjust"])
        output = pathlib.Path(command[command.index("--output") + 1])
        headers = pathlib.Path(command[command.index("--dump-header") + 1])
        output.write_bytes(b"t" * max(0, expected))
        headers.write_text(f"HTTP/1.1 {mode['status']} Test\r\n\r\n", encoding="latin-1")
        return types.SimpleNamespace(returncode=mode["returncode"], stdout="", stderr="curl: (18)")

    original_run = hook.subprocess.run
    hook.subprocess.run = fake_run
    try:
        with tempfile.TemporaryDirectory(prefix="atlas-tail-smoke-") as directory:
            base = pathlib.Path(directory)

            target = base / "gap-378.flv"
            target.write_bytes(b"a" * 1000)
            heartbeat = Heartbeat()
            repaired = hook._repair_exact_tail(
                fake_module,
                "https://cdn.invalid/video",
                target,
                expected_size=1378,
                heartbeat=heartbeat,
                downloaded_before=50,
                segment_index=1,
            )
            check("accepts-exact-378-tail", repaired and target.stat().st_size == 1378)
            check("accepts-curl18-with-complete-206", calls[-1][0] == "curl" and heartbeat.updates[-1]["downloaded_bytes"] == 1428)

            mode.update(status=206, tail_adjust=0, returncode=0)
            target = base / "gap-4096.flv"
            target.write_bytes(b"b" * 8192)
            repaired = hook._repair_exact_tail(
                fake_module,
                "https://cdn.invalid/video",
                target,
                expected_size=12288,
                heartbeat=Heartbeat(),
                downloaded_before=0,
                segment_index=2,
            )
            check("accepts-exact-4k-tail", repaired and target.stat().st_size == 12288)
            check("sends-bounded-range", "8192-12287" in calls[-1])

            mode.update(status=200, tail_adjust=0, returncode=0)
            target = base / "wrong-status.flv"
            target.write_bytes(b"c" * 1000)
            repaired = hook._repair_exact_tail(
                fake_module,
                "https://cdn.invalid/video",
                target,
                expected_size=1378,
                heartbeat=Heartbeat(),
                downloaded_before=0,
                segment_index=1,
            )
            check("rejects-non-206-response", not repaired and target.stat().st_size == 1000)

            mode.update(status=206, tail_adjust=-1, returncode=0)
            target = base / "wrong-size.flv"
            target.write_bytes(b"d" * 1000)
            repaired = hook._repair_exact_tail(
                fake_module,
                "https://cdn.invalid/video",
                target,
                expected_size=1378,
                heartbeat=Heartbeat(),
                downloaded_before=0,
                segment_index=1,
            )
            check("rejects-short-tail", not repaired and target.stat().st_size == 1000)

            before_calls = len(calls)
            target = base / "oversized-gap.flv"
            target.write_bytes(b"e" * 1024)
            repaired = hook._repair_exact_tail(
                fake_module,
                "https://cdn.invalid/video",
                target,
                expected_size=1024 + hook._tail_limit() + 1,
                heartbeat=Heartbeat(),
                downloaded_before=0,
                segment_index=1,
            )
            check("rejects-oversized-gap-without-network", not repaired and len(calls) == before_calls)

            mode.update(status=206, tail_adjust=0, returncode=18)
            original_calls: list[int] = []

            def original_resume(_candidate: str, _target: pathlib.Path, **_kwargs: object) -> None:
                original_calls.append(1)
                raise RuntimeError("original transport should not run for a small existing gap")

            patched_module = types.SimpleNamespace(runner=runner, _single_stream_resume=original_resume)
            check("installs-v11-wrapper", hook._patch_v11(patched_module))
            target = base / "pre-repair.flv"
            target.write_bytes(b"f" * 1000)
            patched_module._single_stream_resume(
                "https://cdn.invalid/video",
                target,
                expected_size=1378,
                heartbeat=Heartbeat(),
                downloaded_before=0,
                segment_index=1,
                chunk_size=1024,
                retries=1,
            )
            check("repairs-before-original-resume", target.stat().st_size == 1378 and not original_calls)

            mode.update(status=200, tail_adjust=0, returncode=0)
            target = base / "preserve-partial.flv"
            target.write_bytes(b"g" * 1000)
            raised = False
            try:
                patched_module._single_stream_resume(
                    "https://cdn.invalid/video",
                    target,
                    expected_size=1378,
                    heartbeat=Heartbeat(),
                    downloaded_before=0,
                    segment_index=1,
                    chunk_size=1024,
                    retries=1,
                )
            except RuntimeError:
                raised = True
            check("preserves-near-complete-partial-on-failure", raised and target.stat().st_size == 1000 and not original_calls)

            mode.update(status=206, tail_adjust=0, returncode=18)

            def partial_then_fail(_candidate: str, target_path: pathlib.Path, **_kwargs: object) -> None:
                target_path.write_bytes(b"h" * 1000)
                raise RuntimeError("curl: (18) end of response with 378 bytes missing")

            post_module = types.SimpleNamespace(runner=runner, _single_stream_resume=partial_then_fail)
            hook._patch_v11(post_module)
            target = base / "post-repair.flv"
            post_module._single_stream_resume(
                "https://cdn.invalid/video",
                target,
                expected_size=1378,
                heartbeat=Heartbeat(),
                downloaded_before=0,
                segment_index=1,
                chunk_size=1024,
                retries=1,
            )
            check("repairs-after-curl18", target.stat().st_size == 1378)
            check("cleans-temporary-tail-files", not list(base.glob("*.exact-tail.*")))
    finally:
        hook.subprocess.run = original_run

    if len(checks) != 12:
        raise AssertionError(f"expected 12 checks, executed {len(checks)}")
    print("12/12 exact-tail resume and partial-preservation checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
