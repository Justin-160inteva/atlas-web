#!/usr/bin/env python3
"""Run strict batch-two shrine promotion and persist non-pixel diagnostics on failure."""
from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

import promote_dada_shrine_direct_review_batch02 as promotion

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC_PATH = ROOT / "data/geospatial/dada-shrines-direct-promotion-batch02-diagnostic.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write(value: dict) -> None:
    DIAGNOSTIC_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = DIAGNOSTIC_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(DIAGNOSTIC_PATH)


def main() -> int:
    try:
        return promotion.main()
    except Exception as error:
        diagnostic = {
            "schemaVersion": 1,
            "generatedAt": now(),
            "status": "promotion-preflight-failed",
            "stage": "strict-shrine-anchor-promotion-batch02",
            "errorType": type(error).__name__,
            "errorMessage": str(error),
            "tracebackTail": traceback.format_exc().splitlines()[-10:],
            "policy": {
                "promotionBypassed": False,
                "coordinatesWritten": False,
                "canonicalAnchorModified": False,
                "repositoryContainsPixels": False
            }
        }
        write(diagnostic)
        print(json.dumps(diagnostic, ensure_ascii=False))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
