#!/usr/bin/env python3
"""Promote the first eight independently confirmed shrine candidates into canonical anchors.

The promotion is deliberately narrow: only ordinals 1-8 from the completed direct-popup review
may be written. Candidate coordinates must exactly match both the stage-one catalog and the
canonical locations dataset, and must not duplicate any confirmed temple location or coordinate.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REVIEW_PATH = ROOT / "data/geospatial/dada-shrines-direct-review-batch01.json"
CANDIDATE_PATH = ROOT / "data/geospatial/dada-shrines-27-anchor-candidates.json"
STAGE1_PATH = ROOT / "data/geospatial/dada-shrines-27-stage1.json"
LOCATIONS_PATH = ROOT / "data/locations.json"
TEMPLE_PATH = ROOT / "data/geospatial/dada-temples-36-anchors-final.json"
OUTPUT_PATH = ROOT / "data/geospatial/dada-shrines-27-anchors-batch01.json"
PROMOTION_REPORT_PATH = ROOT / "data/geospatial/dada-shrines-direct-promotion-batch01.json"

MINIMUM_CONFIDENCE = 0.92
EXPECTED_ORDINALS = tuple(range(1, 9))
COORDINATE_TOLERANCE = 1e-12


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def coordinates_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        math.isclose(float(left["x"]), float(right["x"]), rel_tol=0.0, abs_tol=COORDINATE_TOLERANCE)
        and math.isclose(float(left["y"]), float(right["y"]), rel_tol=0.0, abs_tol=COORDINATE_TOLERANCE)
    )


def coordinate_key(atlas: dict[str, Any]) -> tuple[float, float]:
    return (round(float(atlas["x"]), 12), round(float(atlas["y"]), 12))


def main() -> int:
    review = load(REVIEW_PATH)
    package = load(CANDIDATE_PATH)
    stage1 = load(STAGE1_PATH)
    locations = load(LOCATIONS_PATH)
    temples = load(TEMPLE_PATH)

    if review.get("schemaVersion") != 2 or review.get("reviewStrategyVersion") != 2:
        raise RuntimeError("direct review is not the deterministic version 2 result")
    if review.get("status") != "complete":
        raise RuntimeError("direct review is not complete")
    if review.get("counts", {}).get("confirmed") != 8 or review.get("counts", {}).get("unresolved") != 0:
        raise RuntimeError("direct review must contain exactly eight confirmed candidates")
    if review.get("counts", {}).get("successfulReviewerModels") != 2:
        raise RuntimeError("direct review does not have two complete reviewer models")
    if review.get("policy", {}).get("coordinatesPromoted") is not False:
        raise RuntimeError("review result unexpectedly claims coordinates were already promoted")
    if package.get("status") != "shrine-anchor-candidate-package-ready":
        raise RuntimeError("candidate package is not ready")
    if temples.get("status") != "complete" or temples.get("counts", {}).get("confirmed") != 36:
        raise RuntimeError("canonical temple anchor set is not the expected complete 36-anchor set")

    candidates = {int(row["ordinal"]): row for row in package["directPopupCandidates"]}
    stage1_candidates = {str(row["locationId"]): row for row in stage1["candidateShrines"]}
    locations_by_id = {str(row["id"]): row for row in locations}
    consensus = {int(row["ordinal"]): row for row in review["consensus"]}
    review_evidence = {int(row["ordinal"]): row for row in review["evidence"]}

    if tuple(sorted(consensus)) != EXPECTED_ORDINALS:
        raise RuntimeError(f"review consensus ordinals changed: {sorted(consensus)}")

    temple_ids = {
        str(row["locationId"])
        for row in temples.get("anchors", [])
        if row.get("status") == "confirmed"
    }
    temple_coordinate_keys = {
        coordinate_key(row["atlas"])
        for row in temples.get("anchors", [])
        if row.get("status") == "confirmed"
    }
    if len(temple_ids) != 36 or len(temple_coordinate_keys) != 36:
        raise RuntimeError("temple anchors are not unique by location and coordinate")

    promoted: list[dict[str, Any]] = []
    promoted_ids: set[str] = set()
    promoted_coordinate_keys: set[tuple[float, float]] = set()
    minimum_confidences: list[float] = []

    for ordinal in EXPECTED_ORDINALS:
        candidate = candidates[ordinal]
        decision = consensus[ordinal]
        evidence = review_evidence[ordinal]
        location_id = str(candidate["locationId"])

        if decision.get("status") != "confirmed" or decision.get("promotionReady") is not True:
            raise RuntimeError(f"ordinal {ordinal} is not promotion-ready")
        if str(decision.get("locationId")) != location_id:
            raise RuntimeError(f"ordinal {ordinal} consensus location changed")
        if location_id in temple_ids:
            raise RuntimeError(f"shrine candidate duplicates a temple location: {location_id}")
        if location_id in promoted_ids:
            raise RuntimeError(f"duplicate shrine location in promotion batch: {location_id}")
        if location_id not in stage1_candidates or location_id not in locations_by_id:
            raise RuntimeError(f"promoted location absent from source datasets: {location_id}")

        stage_candidate = stage1_candidates[location_id]
        location = locations_by_id[location_id]
        candidate_atlas = candidate["atlasCandidate"]
        stage_atlas = stage_candidate["atlas"]
        location_atlas = {"x": location["atlas_x"], "y": location["atlas_y"]}
        if not coordinates_equal(candidate_atlas, stage_atlas):
            raise RuntimeError(f"candidate/stage coordinate mismatch: {location_id}")
        if not coordinates_equal(candidate_atlas, location_atlas):
            raise RuntimeError(f"candidate/locations coordinate mismatch: {location_id}")
        if str(location.get("title")) != str(candidate["candidateTitle"]):
            raise RuntimeError(f"candidate/locations title mismatch: {location_id}")
        if str(location.get("region_id")) != str(candidate["regionId"]):
            raise RuntimeError(f"candidate/locations region mismatch: {location_id}")
        source_location_id = int(location.get("source", {}).get("location_id"))
        if source_location_id != int(stage_candidate["sourceLocationId"]):
            raise RuntimeError(f"source location ID mismatch: {location_id}")

        key = coordinate_key(candidate_atlas)
        if key in temple_coordinate_keys:
            raise RuntimeError(f"shrine coordinate duplicates a temple coordinate: {location_id} {key}")
        if key in promoted_coordinate_keys:
            raise RuntimeError(f"duplicate shrine coordinate in promotion batch: {location_id} {key}")

        reviewer_rows = decision.get("reviewers", {})
        if set(reviewer_rows) != {"openai/gpt-4.1-mini", "openai/gpt-4o-mini"}:
            raise RuntimeError(f"ordinal {ordinal} reviewer set changed")
        reviewer_confidences: list[float] = []
        reviewer_summary: list[dict[str, Any]] = []
        for model in ("openai/gpt-4.1-mini", "openai/gpt-4o-mini"):
            reviewer = reviewer_rows[model]
            confidence = float(reviewer.get("confidence") or 0.0)
            if reviewer.get("programmaticLabelMatch") is not True:
                raise RuntimeError(f"ordinal {ordinal} label mismatch for {model}")
            if str(reviewer.get("selectedLocationId")) != location_id:
                raise RuntimeError(f"ordinal {ordinal} selected location mismatch for {model}")
            if confidence < MINIMUM_CONFIDENCE:
                raise RuntimeError(f"ordinal {ordinal} confidence below threshold for {model}")
            reviewer_confidences.append(confidence)
            reviewer_summary.append({
                "model": model,
                "visibleLabel": reviewer.get("visibleLabel"),
                "confidence": confidence,
                "programmaticLabelMatch": True,
            })

        confidence = min(reviewer_confidences)
        minimum_confidences.append(confidence)
        promoted.append({
            "directPopupOrdinal": ordinal,
            "popupEvent": int(candidate["event"]),
            "representativeTimeSeconds": float(candidate["representativeTimeSeconds"]),
            "observedLabelZh": candidate["visibleLabelZhCN"],
            "confidence": confidence,
            "resolutionMethod": "direct-popup-two-model-programmatic-label-consensus",
            "basis": (
                "Two independent vision models directly transcribed the same popup title; "
                "deterministic normalized label equality matched the expected catalog candidate."
            ),
            "evidence": [{
                "timeSeconds": float(evidence["representativeTimeSeconds"]),
                "popupSha256": evidence["sha256"],
                "sourcePopupSha256": candidate["popupSha256"],
                "sourceTitleSha256": candidate["titleSha256"],
            }],
            "reviewers": reviewer_summary,
            "reviewResultPath": "data/geospatial/dada-shrines-direct-review-batch01.json",
            "status": "confirmed",
            "locationId": location_id,
            "title": candidate["candidateTitle"],
            "regionId": candidate["regionId"],
            "regionTitle": candidate["regionTitle"],
            "atlas": {"x": float(candidate_atlas["x"]), "y": float(candidate_atlas["y"])},
            "sourceLocationId": source_location_id,
        })
        promoted_ids.add(location_id)
        promoted_coordinate_keys.add(key)

    remaining_direct = [
        {
            "directPopupOrdinal": int(row["ordinal"]),
            "popupEvent": int(row["event"]),
            "locationId": row["locationId"],
            "title": row["candidateTitle"],
            "status": "pending-independent-review",
        }
        for row in package["directPopupCandidates"]
        if int(row["ordinal"]) not in EXPECTED_ORDINALS
    ]
    set_difference = package["catalogSetDifferenceCandidate"]
    unresolved = remaining_direct + [{
        "locationId": set_difference["locationId"],
        "title": set_difference["candidateTitle"],
        "status": "blocked-pending-independent-resolution",
        "reason": set_difference["blockReason"],
    }]
    if len(unresolved) != 19:
        raise RuntimeError(f"expected 19 remaining shrine candidates, found {len(unresolved)}")

    timestamp = now()
    anchor_document = {
        "schemaVersion": 2,
        "generatedAt": timestamp,
        "stage": "direct-shrine-anchor-promotion-batch01",
        "status": "partial",
        "source": {
            "bvid": package["source"]["bvid"],
            "title": package["source"]["title"],
            "authorizationId": package["source"]["authorizationId"],
            "candidatePackagePath": "data/geospatial/dada-shrines-27-anchor-candidates.json",
            "reviewResultPath": "data/geospatial/dada-shrines-direct-review-batch01.json",
            "catalogProofPath": "data/geospatial/dada-shrines-catalog-completeness-proof.json",
        },
        "counts": {
            "eligibleSequenceCandidates": 27,
            "reviewedCandidates": 8,
            "confirmed": 8,
            "unresolved": 19,
            "coordinatesWritten": 8,
            "mapShrineCandidates": 32,
            "excludedAwajiCandidates": 5,
        },
        "policy": {
            "minimumIndependentModels": 2,
            "minimumConfidencePerModel": MINIMUM_CONFIDENCE,
            "programmaticVisibleLabelEquality": True,
            "uniqueLocationAssignment": True,
            "uniqueCoordinateAssignment": True,
            "crossCategoryLocationOverlapRejected": True,
            "crossCategoryCoordinateOverlapRejected": True,
            "coordinatesMustMatchCanonicalLocations": True,
            "repositoryContainsEvidencePixels": False,
        },
        "anchors": promoted,
        "unresolved": unresolved,
    }
    promotion_report = {
        "schemaVersion": 1,
        "generatedAt": timestamp,
        "status": "promotion-complete",
        "stage": "shrine-direct-review-batch01-to-canonical-anchor-set",
        "counts": {
            "promoted": 8,
            "remaining": 19,
            "templeAnchorsCompared": 36,
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
            "uniqueShrineLocations": len(promoted_ids) == 8,
            "uniqueShrineCoordinates": len(promoted_coordinate_keys) == 8,
            "repositoryContainsPixels": False,
        },
    }
    if not all(promotion_report["safety"].values()):
        raise RuntimeError(f"promotion safety checks failed: {promotion_report['safety']}")

    write(OUTPUT_PATH, anchor_document)
    write(PROMOTION_REPORT_PATH, promotion_report)
    print(json.dumps({
        "status": promotion_report["status"],
        "promoted": 8,
        "remaining": 19,
        "minimumConfidence": promotion_report["minimumPromotedConfidence"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
