#!/usr/bin/env python3
"""Relax only the minimum aspect ratio for tall full map-popup panels.

Calibration confirmed that the missing 熊野那智大社 panel has aspect ratio 1.13057 and
passes every other geometry/density gate. The patch changes 1.15 to 0.88 while leaving
width, height, area, center bounds, darkness and rectangularity checks untouched.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tools/detect_dada_shrine_popup_events.py"
OLD = "if area < 32000 or not (1.15 <= aspect <= 5.2):"
NEW = "if area < 32000 or not (0.88 <= aspect <= 5.2):"


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    old_count = text.count(OLD)
    new_count = text.count(NEW)
    if old_count == 0 and new_count == 1:
        print("tall-popup aspect patch already applied")
        return 0
    if old_count != 1 or new_count != 0:
        raise RuntimeError(
            f"unexpected popup detector source state: old={old_count}, new={new_count}"
        )
    TARGET.write_text(text.replace(OLD, NEW), encoding="utf-8")
    print("relaxed only minimum popup aspect ratio: 1.15 -> 0.88")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
