#!/usr/bin/env python3
"""Make the confirmed-anchor stage gate follow the authoritative 50-anchor target.

The patch is exact and idempotent: it replaces the one legacy fixed expression, accepts the one
already-patched expression, and fails for every other source state. It does not alter final-map,
calibration or physical-device gates.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tools/build_geospatial_progress.py"
OLD = '            "confirmedGeospatialAnchors": {"status": "in_progress", "count": len(confirmed)},\n'
NEW = '            "confirmedGeospatialAnchors": {"status": "complete" if len(confirmed) >= target else "in_progress", "count": len(confirmed)},\n'


def main() -> int:
    source = TARGET.read_text(encoding="utf-8")
    old_count = source.count(OLD)
    new_count = source.count(NEW)
    if old_count == 1 and new_count == 0:
        TARGET.write_text(source.replace(OLD, NEW, 1), encoding="utf-8")
        print("Patched confirmedGeospatialAnchors gate to complete at target")
        return 0
    if old_count == 0 and new_count == 1:
        print("confirmedGeospatialAnchors gate is already target-aware")
        return 0
    raise RuntimeError(
        f"unexpected anchor-gate source state: legacy={old_count}, targetAware={new_count}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
