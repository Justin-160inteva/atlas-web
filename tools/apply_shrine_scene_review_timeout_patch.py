#!/usr/bin/env python3
"""Apply bounded retry timing to the resumable shrine scene reviewer.

This patch keeps the evidence and consensus policy unchanged. It only prevents a large
Retry-After header or repeated socket timeouts from occupying an Actions runner for the
entire job timeout. Partial model packets are persisted and retried in a later run.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tools/review_dada_shrine_scene_segments.py"


def replace_exact(text: str, old: str, new: str, expected: int) -> str:
    found = text.count(old)
    if found == 0 and new in text:
        return text
    if found != expected:
        raise RuntimeError(f"expected {expected} occurrences of {old!r}, found {found}")
    return text.replace(old, new)


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    text = replace_exact(text, "for attempt in range(1, 4):", "for attempt in range(1, 3):", 1)
    text = replace_exact(text, "with urllib.request.urlopen(request, timeout=timeout) as response:", "with urllib.request.urlopen(request, timeout=min(timeout, 90)) as response:", 1)
    text = replace_exact(text, "if attempt < 3:", "if attempt < 2:", 2)
    text = replace_exact(
        text,
        "time.sleep(max(retry_after, 12 * attempt))",
        "time.sleep(min(30, max(retry_after, 12 * attempt)))",
        1,
    )
    TARGET.write_text(text, encoding="utf-8")
    print("bounded shrine scene model retries to two attempts, 90 seconds, and 30-second Retry-After waits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
