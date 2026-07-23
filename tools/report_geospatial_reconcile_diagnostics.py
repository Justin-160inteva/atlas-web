#!/usr/bin/env python3
"""Persist compact, non-pixel diagnostics before global geospatial reconciliation."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/geospatial/geospatial-reconcile-diagnostic.json"


def load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    locations = load(ROOT / "data/locations.json", [])
    index = load(ROOT / "data/analysis-index.json", {"items": []})
    temple = load(ROOT / "data/geospatial/dada-temples-36-anchors-final.json", {})
    shrine = load(ROOT / "data/geospatial/dada-shrines-27-anchors-batch01.json", {})

    temple_rows = [row for row in temple.get("anchors", []) if row.get("status") == "confirmed"]
    shrine_rows = [row for row in shrine.get("anchors", []) if row.get("status") == "confirmed"]
    combined = temple_rows + shrine_rows
    ids = [str(row.get("locationId") or "") for row in combined]
    duplicates = sorted(location_id for location_id, count in Counter(ids).items() if location_id and count > 1)
    known = {str(row.get("id")) for row in locations}
    unknown = sorted(location_id for location_id in set(ids) if location_id and location_id not in known)

    matches = {
        "templeByExternalSourceId": [],
        "templeByResultPath": [],
        "shrineByExternalSourceId": [],
        "shrineByResultPath": [],
    }
    for position, item in enumerate(index.get("items", [])):
        summary = {
            "position": position,
            "id": item.get("id"),
            "jobId": item.get("jobId"),
            "externalSourceId": item.get("externalSourceId"),
            "resultPath": item.get("resultPath"),
            "status": item.get("status"),
        }
        if item.get("externalSourceId") == "bili-dada-acshadows-03":
            matches["templeByExternalSourceId"].append(summary)
        if item.get("resultPath") == "data/analysis-results/dada-temples-36.json":
            matches["templeByResultPath"].append(summary)
        if item.get("externalSourceId") == "bili-dada-acshadows-02":
            matches["shrineByExternalSourceId"].append(summary)
        if item.get("resultPath") == "data/analysis-results/dada-02.json":
            matches["shrineByResultPath"].append(summary)

    report = {
        "schemaVersion": 1,
        "generatedAt": now(),
        "locationsCount": len(locations),
        "analysisIndexItemCount": len(index.get("items", [])),
        "temple": {
            "status": temple.get("status"),
            "confirmed": len(temple_rows),
            "minimumConfidence": min((float(row.get("confidence") or 0) for row in temple_rows), default=None),
        },
        "shrine": {
            "status": shrine.get("status"),
            "counts": shrine.get("counts"),
            "confirmed": len(shrine_rows),
            "minimumConfidence": min((float(row.get("confidence") or 0) for row in shrine_rows), default=None),
            "modelErrors": shrine.get("modelErrors", []),
        },
        "combined": {
            "confirmed": len(combined),
            "uniqueLocationIds": len(set(ids)),
            "duplicateLocationIds": duplicates,
            "unknownLocationIds": unknown,
        },
        "analysisIndexMatches": matches,
        "preflight": {
            "templeComplete": temple.get("status") == "complete",
            "templeHas36Confirmed": len(temple_rows) == 36,
            "shrineReviewComplete": shrine.get("status") == "complete",
            "locationsCount3430": len(locations) == 3430,
            "noDuplicateAssignments": not duplicates,
            "allLocationsKnown": not unknown,
            "templeIndexFound": bool(matches["templeByExternalSourceId"] or matches["templeByResultPath"]),
            "shrineIndexFound": bool(matches["shrineByExternalSourceId"] or matches["shrineByResultPath"]),
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "temple": report["temple"]["confirmed"],
        "shrine": report["shrine"]["confirmed"],
        "duplicates": duplicates,
        "unknown": unknown,
        "indexMatches": {key: len(value) for key, value in matches.items()},
        "preflight": report["preflight"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
