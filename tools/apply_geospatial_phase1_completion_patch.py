#!/usr/bin/env python3
"""Make the confirmed-anchor stage gate follow the authoritative 50-anchor target.

The patch is exact and fails if the builder source changes or the target expression appears more
than once. It does not alter the final-map, calibration or physical-device gates.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tools/build_geospatial_progress.py"
OLD = '            "confirmedGeospatialAnchors": {"status": "in_progress", "count": len(confirmed)},\n'
NEW = '            "confirmedGeospatialAnchors": {"status": "complete" if len(confirmed) >= target else "in_progress", "count": len(confirmed)},\n'


def main() -> int:
    source = TARGET.read_text(encoding="utf-8")
    count = source.count(OLD)
    if count != 1:
        raise RuntimeError(f"expected one fixed anchor-gate status expression, found {count}")
    patched = source.replace(OLD, NEW, 1)
    if patched.count(NEW) != 1:
        raise RuntimeError("dynamic anchor-gate status expression was not written exactly once")
    TARGET.write_text(patched, encoding="utf-8")
    print("Patched confirmedGeospatialAnchors gate to complete at target")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
