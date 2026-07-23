#!/usr/bin/env python3
"""Append six independently confirmed shrine anchors and complete the 50-anchor phase-one target."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import promote_dada_shrine_direct_review_batch01 as shared

ROOT = Path(__file__).resolve().parents[1]
REVIEW_PATH = ROOT / "data/geospatial/dada-shrines-direct-review-batch02.json"
CANDIDATE_PATH = ROOT / "data/geospatial/dada-shrines-27-anchor-candidates.json"
STAGE1_PATH = ROOT / "data/geospatial/dada-shrines-27-stage1.json"
LOCATIONS_PATH = ROOT / "data/locations.json"
TEMPLE_PATH = ROOT / "data/geospatial/dada-temples-36-anchors-final.json"
ANCHOR_PATH = ROOT / "data/geospatial/dada-shrines-27-anchors-batch01.json"
REPORT_PATH = ROOT / "data/geospatial/dada-shrines-direct-promotion-batch02.json"

EXPECTED_ORDINALS = tuple(range(9, 15))
MODELS = ("openai/gpt-4.1-mini", "openai/gpt-4o-mini")
MINIMUM_CONFIDENCE = 0.92


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    review = load(REVIEW_PATH)
    package = load(CANDIDATE_PATH)
    stage1 = load(STAGE1_PATH)
    locations = load(LOCATIONS_PATH)
    temples = load(TEMPLE_PATH)
    existing = load(ANCHOR_PATH)

    if review.get("schemaVersion") != 2 or review.get("reviewStrategyVersion") != 2:
        raise RuntimeError("batch-two review is not deterministic version 2")
    if review.get("status") != "complete":
        raise RuntimeError("batch-two review is not complete")
    if review.get("counts", {}).get("confirmed") != 6 or review.get("counts", {}).get("unresolved") != 0:
        raise RuntimeError("batch-two review must contain exactly six confirmed candidates")
    if review.get("counts", {}).get("successfulReviewerModels") != 2:
        raise RuntimeError("batch-two review does not contain two complete reviewer models")
    if package.get("status") != "shrine-anchor-candidate-package-ready":
        raise RuntimeError("candidate package is not ready")
    if temples.get("status") != "complete" or temples.get("counts", {}).get("confirmed") != 36:
        raise RuntimeError("temple anchor set is not the canonical 36-anchor set")
    if existing.get("schemaVersion") != 2 or existing.get("counts", {}).get("confirmed") != 8:
        raise RuntimeError("existing shrine anchor set is not the verified eight-anchor batch one result")

    candidates = {int(row["ordinal"]): row for row in package["directPopupCandidates"]}
    stage_candidates = {str(row["locationId"]): row for row in stage1["candidateShrines"]}
    locations_by_id = {str(row["id"]): row for row in locations}
    consensus = {int(row["ordinal"]): row for row in review["consensus"]}
    evidence_by_ordinal = {int(row["ordinal"]): row for row in review["evidence"]}
    if tuple(sorted(consensus)) != EXPECTED_ORDINALS:
        raise RuntimeError(f"batch-two consensus ordinals changed: {sorted(consensus)}")

    temple_anchors = [row for row in temples["anchors"] if row.get("status") == "confirmed"]
    temple_ids = {str(row["locationId"]) for row in temple_anchors}
    temple_coordinates = {shared.coordinate_key(row["atlas"]) for row in temple_anchors}
    existing_anchors = [row for row in existing["anchors"] if row.get("status") == "confirmed"]
    existing_ids = {str(row["locationId"]) for row in existing_anchors}
    existing_coordinates = {shared.coordinate_key(row["atlas"]) for row in existing_anchors}
    if len(temple_ids) != 36 or len(temple_coordinates) != 36:
        raise RuntimeError("temple anchors are not unique")
    if len(existing_ids) != 8 or len(existing_coordinates) != 8:
        raise RuntimeError("existing shrine anchors are not unique")
    if temple_ids.intersection(existing_ids) or temple_coordinates.intersection(existing_coordinates):
        raise RuntimeError("existing shrine anchors overlap the temple anchor set")

    promoted: list[dict[str, Any]] = []
    promoted_ids: set[str] = set()
    promoted_coordinates: set[tuple[float, float]] = set()
    minimum_confidences: list[float] = []

    for ordinal in EXPECTED_ORDINALS:
        candidate = candidates[ordinal]
        decision = consensus[ordinal]
        evidence = evidence_by_ordinal[ordinal]
        location_id = str(candidate["locationId"])
        if decision.get("status") != "confirmed" or decision.get("promotionReady") is not True:
            raise RuntimeError(f"ordinal {ordinal} is not promotion-ready")
        if str(decision.get("locationId")) != location_id:
            raise RuntimeError(f"ordinal {ordinal} consensus location changed")
        if location_id in temple_ids or location_id in existing_ids or location_id in promoted_ids:
            raise RuntimeError(f"duplicate promoted location: {location_id}")
        if location_id not in stage_candidates or location_id not in locations_by_id:
            raise RuntimeError(f"location absent from source datasets: {location_id}")

        stage_candidate = stage_candidates[location_id]
        location = locations_by_id[location_id]
        candidate_atlas = candidate["atlasCandidate"]
        location_atlas = {"x": location["atlas_x"], "y": location["atlas_y"]}
        if not shared.coordinates_equal(candidate_atlas, stage_candidate["atlas"]):
            raise RuntimeError(f"candidate/stage coordinate mismatch: {location_id}")
        if not shared.coordinates_equal(candidate_atlas, location_atlas):
            raise RuntimeError(f"candidate/locations coordinate mismatch: {location_id}")
        if str(candidate["candidateTitle"]) != str(location["title"]):
            raise RuntimeError(f"candidate/locations title mismatch: {location_id}")
        if str(candidate["regionId"]) != str(location["region_id"]):
            raise RuntimeError(f"candidate/locations region mismatch: {location_id}")
        source_location_id = int(location.get("source", {}).get("location_id"))
        if source_location_id != int(stage_candidate["sourceLocationId"]):
            raise RuntimeError(f"source location ID mismatch: {location_id}")

        coordinate = shared.coordinate_key(candidate_atlas)
        if coordinate in temple_coordinates or coordinate in existing_coordinates or coordinate in promoted_coordinates:
            raise RuntimeError(f"duplicate promoted coordinate: {location_id} {coordinate}")

        reviewer_rows = decision.get("reviewers", {})
        if set(reviewer_rows) != set(MODELS):
            raise RuntimeError(f"ordinal {ordinal} reviewer set changed")
        reviewer_summary: list[dict[str, Any]] = []
        confidences: list[float] = []
        for model in MODELS:
            row = reviewer_rows[model]
            confidence = float(row.get("confidence") or 0.0)
            if row.get("programmaticLabelMatch") is not True:
                raise RuntimeError(f"ordinal {ordinal} label mismatch for {model}")
            if str(row.get("selectedLocationId")) != location_id:
                raise RuntimeError(f"ordinal {ordinal} selected location mismatch for {model}")
            if confidence < MINIMUM_CONFIDENCE:
                raise RuntimeError(f"ordinal {ordinal} confidence below threshold for {model}")
            confidences.append(confidence)
            reviewer_summary.append({
                "model": model,
                "visibleLabel": row.get("visibleLabel"),
                "confidence": confidence,
                "programmaticLabelMatch": True,
            })

        confidence = min(confidences)
        minimum_confidences.append(confidence)
        promoted.append({
            "directPopupOrdinal": ordinal,
            "popupEvent": int(candidate["event"]),
            "representativeTimeSeconds": float(candidate["representativeTimeSeconds"]),
            "observedLabelZh": candidate["visibleLabelZhCN"],
            "confidence": confidence,
            "resolutionMethod": "direct-popup-two-model-programmatic-label-consensus",
            "basis": "Two independent models transcribed the same popup title and deterministic normalized equality matched the expected candidate.",
            "evidence": [{
                "timeSeconds": float(evidence["representativeTimeSeconds"]),
                "popupSha256": evidence["sha256"],
                "sourcePopupSha256": candidate["popupSha256"],
                "sourceTitleSha256": candidate["titleSha256"],
            }],
            "reviewers": reviewer_summary,
            "reviewResultPath": "data/geospatial/dada-shrines-direct-review-batch02.json",
            "status": "confirmed",
            "locationId": location_id,
            "title": candidate["candidateTitle"],
            "regionId": candidate["regionId"],
            "regionTitle": candidate["regionTitle"],
            "atlas": {"x": float(candidate_atlas["x"]), "y": float(candidate_atlas["y"])},
            "sourceLocationId": source_location_id,
        })
        promoted_ids.add(location_id)
        promoted_coordinates.add(coordinate)

    combined = sorted(existing_anchors + promoted, key=lambda row: int(row["directPopupOrdinal"]))
    combined_ids = {str(row["locationId"]) for row in combined}
    combined_coordinates = {shared.coordinate_key(row["atlas"]) for row in combined}
    if len(combined) != 14 or len(combined_ids) != 14 or len(combined_coordinates) != 14:
        raise RuntimeError("combined shrine anchor set is not 14 unique anchors")
    if temple_ids.intersection(combined_ids) or temple_coordinates.intersection(combined_coordinates):
        raise RuntimeError("combined shrine anchor set overlaps temples")

    remaining_direct = [
        {
            "directPopupOrdinal": int(row["ordinal"]),
            "popupEvent": int(row["event"]),
            "locationId": row["locationId"],
            "title": row["candidateTitle"],
            "status": "pending-independent-review",
        }
        for row in package["directPopupCandidates"]
        if int(row["ordinal"]) > 14
    ]
    missing = package["catalogSetDifferenceCandidate"]
    unresolved = remaining_direct + [{
        "locationId": missing["locationId"],
        "title": missing["candidateTitle"],
        "status": "blocked-pending-independent-resolution",
        "reason": missing["blockReason"],
    }]
    if len(unresolved) != 13:
        raise RuntimeError(f"expected 13 remaining shrine candidates, found {len(unresolved)}")

    timestamp = now()
    updated = dict(existing)
    updated.update({
        "generatedAt": timestamp,
        "stage": "direct-shrine-anchor-promotion-batches01-02",
        "status": "partial",
        "counts": {
            "eligibleSequenceCandidates": 27,
            "reviewedCandidates": 14,
            "confirmed": 14,
            "unresolved": 13,
            "coordinatesWritten": 14,
            "mapShrineCandidates": 32,
            "excludedAwajiCandidates": 5,
        },
        "anchors": combined,
        "unresolved": unresolved,
    })
    updated["source"] = dict(existing["source"])
    updated["source"]["reviewResultPaths"] = [
        "data/geospatial/dada-shrines-direct-review-batch01.json",
        "data/geospatial/dada-shrines-direct-review-batch02.json",
    ]

    report = {
        "schemaVersion": 1,
        "generatedAt": timestamp,
        "status": "promotion-complete",
        "stage": "shrine-direct-review-batch02-to-canonical-anchor-set",
        "counts": {
            "promotedThisBatch": 6,
            "previousShrineAnchors": 8,
            "totalShrineAnchors": 14,
            "remainingShrineCandidates": 13,
            "templeAnchorsCompared": 36,
            "globalConfirmedAnchorsExpected": 50,
            "duplicateLocationIds": 0,
            "duplicateCoordinates": 0,
        },
        "minimumPromotedConfidence": min(minimum_confidences),
        "promotedLocationIds": sorted(promoted_ids),
        "safety": {
            "reviewComplete": True,
            "twoModelsPerAnchor": True,
            "minimumConfidenceMet": all(value >= MINIMUM_CONFIDENCE for value in minimum_confidences),
            "candidateStageLocationCoordinatesMatch": True,
            "canonicalLocationCoordinatesMatch": True,
            "noTempleLocationOverlap": True,
            "noTempleCoordinateOverlap": True,
            "noExistingShrineLocationOverlap": True,
            "noExistingShrineCoordinateOverlap": True,
            "uniqueCombinedShrineLocations": len(combined_ids) == 14,
            "uniqueCombinedShrineCoordinates": len(combined_coordinates) == 14,
            "repositoryContainsNoPixels": True,
        },
    }
    if not all(report["safety"].values()):
        raise RuntimeError(f"batch-two promotion safety checks failed: {report['safety']}")

    write(ANCHOR_PATH, updated)
    write(REPORT_PATH, report)
    print(json.dumps({"promoted": 6, "totalShrineAnchors": 14, "globalExpected": 50, "minimumConfidence": report["minimumPromotedConfidence"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
