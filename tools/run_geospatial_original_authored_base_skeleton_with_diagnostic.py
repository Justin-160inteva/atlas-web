#!/usr/bin/env python3
"""Run the original authored skeleton builder and persist a compact failure diagnostic."""
from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

import build_geospatial_original_authored_base_skeleton as builder

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC = ROOT / "data/geospatial/geospatial-original-authored-base-diagnostic.json"


def main() -> int:
    try:
        result = builder.main()
        if DIAGNOSTIC.exists():
            DIAGNOSTIC.unlink()
        return result
    except Exception as exc:
        DIAGNOSTIC.parent.mkdir(parents=True, exist_ok=True)
        DIAGNOSTIC.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "status": "original-authored-skeleton-build-failed",
                    "errorType": type(exc).__name__,
                    "errorMessage": str(exc),
                    "tracebackTail": traceback.format_exc().splitlines()[-12:],
                    "safety": {
                        "legacyRenderBaseModified": False,
                        "thirdPartyMapPixelsRead": False,
                        "finalMapClaimed": False,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
