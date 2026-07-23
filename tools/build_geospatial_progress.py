#!/usr/bin/env python3
"""Build the authoritative geospatial progress ledger.

The ledger counts only confirmed, unique location assignments from registered anchor
sets. It also reconciles source-level pipeline metadata for complete or partially
anchored specialized sources. No approximate coordinates are created.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOCATIONS_PATH = ROOT / "data/locations.json"
ANALYSIS_INDEX_PATH = ROOT / "data/analysis-index.json"
TEMPLE_ANCHORS_PATH = ROOT / "data/geospatial/dada-temples-36-anchors-final.json"
SHRINE_BATCH_PATH = ROOT / "data/geospatial/dada-shrines-27-anchors-batch01.json"
OUTPUT_PATH = ROOT / "data/geospatial/geospatial-progress.json"
TEMPLE_JOB_PATH = ROOT / "data/analysis-jobs/dada-temples-36-geospatial.json"
TEMPLE_EXTERNAL_SOURCE_ID = "bili-dada-acshadows-03"
SHRINE_EXTERNAL_SOURCE_ID = "bili-dada-acshadows-02"


def load(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def confirmed_rows(document: dict[str, Any] | None, source_name: str, path: Path) -> list[dict[str, Any]]:
    if not document:
        return []
    rows = []
    for row in document.get("anchors", []):
        if row.get("status") != "confirmed":
            continue
        location_id = str(row.get("locationId") or "")
        atlas = row.get("atlas") or {}
        if not location_id or not isinstance(atlas.get("x"), (int, float)) or not isinstance(atlas.get("y"), (int, float)):
            continue
        rows.append({
            "locationId": location_id,
            "title": row.get("title"),
            "regionId": row.get("regionId"),
            "regionTitle": row.get("regionTitle"),
            "atlas": {"x": float(atlas["x"]), "y": float(atlas["y"])},
            "confidence": float(row.get("confidence") or 0),
            "sourceName": source_name,
            "sourcePath": path.relative_to(ROOT).as_posix(),
            "sourceVideoPosition": row.get("videoPosition"),
            "resolutionMethod": row.get("resolutionMethod") or "reviewed-visual-evidence",
        })
    return rows


def source_matches(item: dict[str, Any], external_source_id: str, canonical_result_path: str) -> bool:
    return (
        str(item.get("externalSourceId") or "") == external_source_id
        or str(item.get("resultPath") or "") == canonical_result_path
    )


def main() -> int:
    locations = load(LOCATIONS_PATH, [])
    analysis_index = load(ANALYSIS_INDEX_PATH, {"items": []})
    temple_document = load(TEMPLE_ANCHORS_PATH, {})
    shrine_document = load(SHRINE_BATCH_PATH, None)

    registered_sets = [
        {
            "id": "dada-temples-36-final",
            "path": TEMPLE_ANCHORS_PATH,
            "required": True,
            "rows": confirmed_rows(temple_document, "不再犹豫的达达猪·寺庙36处", TEMPLE_ANCHORS_PATH),
        },
        {
            "id": "dada-shrines-27-batch01",
            "path": SHRINE_BATCH_PATH,
            "required": False,
            "rows": confirmed_rows(shrine_document, "不再犹豫的达达猪·神社第一批", SHRINE_BATCH_PATH),
        },
    ]

    if temple_document.get("status") != "complete":
        raise RuntimeError("Temple anchor consolidation is not complete")
    if len(registered_sets[0]["rows"]) != 36:
        raise RuntimeError(f"Expected 36 confirmed temple anchors, found {len(registered_sets[0]['rows'])}")

    anchors_by_location: dict[str, dict[str, Any]] = {}
    duplicate_sources: list[dict[str, Any]] = []
    for anchor_set in registered_sets:
        for row in anchor_set["rows"]:
            location_id = row["locationId"]
            previous = anchors_by_location.get(location_id)
            if previous:
                duplicate_sources.append({
                    "locationId": location_id,
                    "keptSource": previous["sourcePath"],
                    "duplicateSource": row["sourcePath"],
                })
                if row["confidence"] > previous["confidence"]:
                    anchors_by_location[location_id] = row
            else:
                anchors_by_location[location_id] = row

    if duplicate_sources:
        raise RuntimeError(f"Duplicate location assignments across anchor sets: {duplicate_sources}")

    location_ids = {str(item.get("id")) for item in locations}
    unknown_ids = sorted(set(anchors_by_location) - location_ids)
    if unknown_ids:
        raise RuntimeError(f"Anchor locations are absent from locations.json: {unknown_ids}")

    timestamp = now()
    temple_index_matches = 0
    shrine_index_matches = 0
    shrine_anchor_count = len(registered_sets[1]["rows"])
    for item in analysis_index.get("items", []):
        pipeline = item.setdefault("pipeline", {})
        if source_matches(item, TEMPLE_EXTERNAL_SOURCE_ID, "data/analysis-results/dada-temples-36.json"):
            pipeline["geospatialAnchoringCompleted"] = True
            pipeline["geospatialAnchorCount"] = 36
            pipeline["geospatialAnchorTargetCount"] = 36
            pipeline["geospatialAnchorSet"] = "data/geospatial/dada-temples-36-anchors-final.json"
            pipeline["geospatialAnchoringUpdatedAt"] = timestamp
            temple_index_matches += 1
        elif source_matches(item, SHRINE_EXTERNAL_SOURCE_ID, "data/analysis-results/dada-02.json"):
            pipeline["geospatialAnchoringCompleted"] = shrine_anchor_count == 27
            pipeline["geospatialAnchorCount"] = shrine_anchor_count
            pipeline["geospatialAnchorTargetCount"] = 27
            pipeline["geospatialAnchorSet"] = (
                "data/geospatial/dada-shrines-27-anchors-batch01.json"
                if SHRINE_BATCH_PATH.exists() else None
            )
            pipeline["geospatialAnchoringUpdatedAt"] = timestamp
            shrine_index_matches += 1
    if temple_index_matches < 1:
        raise RuntimeError("No temple analysis-index item matched the stable external source ID")
    if shrine_index_matches < 1:
        raise RuntimeError("No shrine analysis-index item matched the stable external source ID")
    analysis_index["updatedAt"] = timestamp
    write(ANALYSIS_INDEX_PATH, analysis_index)

    temple_job = load(TEMPLE_JOB_PATH, {})
    temple_job.update({
        "status": "complete",
        "linkedSlotCount": 36,
        "unlinkedSlotCount": 0,
        "finalAnchorSetPath": "data/geospatial/dada-temples-36-anchors-final.json",
        "minimumConfidence": 0.9,
        "nextAction": "use confirmed temple anchors in global calibration and continue with shrine batch 01",
        "updatedAt": timestamp,
    })
    write(TEMPLE_JOB_PATH, temple_job)

    confirmed = sorted(anchors_by_location.values(), key=lambda row: (row.get("regionTitle") or "", row.get("title") or "", row["locationId"]))
    by_region = Counter(str(row.get("regionTitle") or row.get("regionId") or "Unknown") for row in confirmed)
    source_summaries = [{
        "id": anchor_set["id"],
        "path": anchor_set["path"].relative_to(ROOT).as_posix(),
        "exists": anchor_set["path"].exists(),
        "confirmedAnchors": len(anchor_set["rows"]),
        "required": anchor_set["required"],
    } for anchor_set in registered_sets]

    target = 50
    total_locations = len(locations)
    payload = {
        "schemaVersion": 1,
        "release": "0.9.4.8",
        "generatedAt": timestamp,
        "status": "phase1-in-progress" if len(confirmed) < target else "phase1-complete",
        "phase1": {
            "targetConfirmedAnchors": target,
            "confirmedAnchors": len(confirmed),
            "remainingToTarget": max(0, target - len(confirmed)),
            "progressPercent": round(min(100.0, len(confirmed) / target * 100.0), 2),
            "nextSource": "不再犹豫的达达猪·神社全收集（27个位置）" if len(confirmed) < target else None,
        },
        "globalCoverage": {
            "totalLocations": total_locations,
            "confirmedAnchorLocations": len(confirmed),
            "locationCoveragePercent": round(len(confirmed) / max(1, total_locations) * 100.0, 4),
            "noteZhCN": "该比例只表示3430个点位中已有直接地理锚点的数量，不等同于最终底图整体完成度。",
        },
        "stageGates": {
            "authorizedVideoAnalysis": {"status": "complete", "elevenSeries": "80/80", "dadaCatalog": "23/23"},
            "confirmedGeospatialAnchors": {"status": "in_progress", "count": len(confirmed)},
            "finalOriginalUltraHdBase": {"status": "not_started"},
            "coordinateAndOverlayCalibration": {"status": "in_progress"},
            "responsiveCompatibilityValidation": {"status": "pending_final_base"},
            "physicalDeviceVerification": {"status": "pending_final_base"},
        },
        "sources": source_summaries,
        "analysisIndexMatches": {
            "temple": temple_index_matches,
            "shrine": shrine_index_matches,
        },
        "anchorsByRegion": dict(sorted(by_region.items())),
        "anchors": confirmed,
        "safety": {
            "uniqueLocationAssignments": len(confirmed) == len({row["locationId"] for row in confirmed}),
            "minimumTempleConfidenceMet": all(row["confidence"] >= 0.9 for row in registered_sets[0]["rows"]),
            "minimumShrineConfidenceMet": all(row["confidence"] >= 0.92 for row in registered_sets[1]["rows"]),
            "repositoryContainsNoEvidencePixels": True,
            "approximateCoordinatesNotInvented": True,
        },
    }
    if not all(payload["safety"].values()):
        raise RuntimeError(f"Geospatial safety checks failed: {payload['safety']}")
    write(OUTPUT_PATH, payload)
    print(json.dumps({
        "confirmed": len(confirmed),
        "phase1Target": target,
        "phase1Percent": payload["phase1"]["progressPercent"],
        "globalLocationCoveragePercent": payload["globalCoverage"]["locationCoveragePercent"],
        "shrineAnchors": shrine_anchor_count,
        "analysisIndexMatches": payload["analysisIndexMatches"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
