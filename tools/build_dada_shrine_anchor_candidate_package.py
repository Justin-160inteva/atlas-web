#!/usr/bin/env python3
"""Build a non-pixel candidate package for the authorized 27-shrine video.

The exact catalog proof establishes 26 one-to-one direct popup mappings and one unique
set-difference candidate. This tool attaches existing Atlas candidate coordinates while keeping
all canonical promotion disabled until the required independent review gate is satisfied.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROOF_PATH = ROOT / "data/geospatial/dada-shrines-catalog-completeness-proof.json"
STAGE1_PATH = ROOT / "data/geospatial/dada-shrines-27-stage1.json"
PAIRWISE_REVIEW_PATH = ROOT / "data/geospatial/tokei-pairwise-map-review.json"
OUTPUT_PATH = ROOT / "data/geospatial/dada-shrines-27-anchor-candidates.json"

MINIMUM_REVIEW_MODELS = 2
MINIMUM_CONFIDENCE_PER_MODEL = 0.92


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected object in {path}")
    return value


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    proof = load(PROOF_PATH)
    stage1 = load(STAGE1_PATH)
    pairwise = load(PAIRWISE_REVIEW_PATH)

    if proof.get("status") != "single-candidate-completeness-proof-ready":
        raise RuntimeError("catalog completeness proof is not ready")
    if proof.get("counts") != {
        "allMapShrineCandidates": 32,
        "excludedAwajiCandidates": 5,
        "eligibleSequenceCandidates": 27,
        "directReadableShrinePopups": 26,
        "setDifferenceCandidates": 1,
    }:
        raise RuntimeError("catalog proof counts changed")
    if int(stage1["counts"]["videoClaimedShrines"]) != 27:
        raise RuntimeError("video shrine claim changed")

    candidates = {row["locationId"]: row for row in stage1["candidateShrines"]}
    direct_rows: list[dict[str, Any]] = []
    for ordinal, mapping in enumerate(proof["directPopupMappings"], start=1):
        location_id = mapping["locationId"]
        if location_id not in candidates:
            raise RuntimeError(f"candidate missing from stage one: {location_id}")
        candidate = candidates[location_id]
        if candidate["title"] != mapping["candidateTitle"]:
            raise RuntimeError(f"candidate title mismatch: {location_id}")
        direct_rows.append({
            "ordinal": ordinal,
            "event": mapping["event"],
            "representativeTimeSeconds": mapping["representativeTimeSeconds"],
            "visibleLabelZhCN": mapping["visibleLabelZhCN"],
            "locationId": location_id,
            "candidateTitle": candidate["title"],
            "regionId": candidate["regionId"],
            "regionTitle": candidate["regionTitle"],
            "atlasCandidate": candidate["atlas"],
            "popupSha256": mapping["popupSha256"],
            "titleSha256": mapping["titleSha256"],
            "evidenceType": "direct-readable-popup-title-plus-unique-catalog-candidate",
            "candidateStatus": "pending-independent-two-model-review",
            "promotionAllowed": False,
            "requiredReview": {
                "minimumIndependentModels": MINIMUM_REVIEW_MODELS,
                "minimumConfidencePerModel": MINIMUM_CONFIDENCE_PER_MODEL,
                "requireSameLocationId": True,
            },
        })

    direct_ids = [row["locationId"] for row in direct_rows]
    if len(direct_rows) != 26 or len(set(direct_ids)) != 26:
        raise RuntimeError("direct candidate package is not 26 unique locations")

    missing = proof["uniqueSetDifference"]
    missing_id = missing["locationId"]
    if missing_id != "location-mapgenie-438414" or missing_id not in candidates:
        raise RuntimeError("unique set-difference candidate changed")
    if missing_id in set(direct_ids):
        raise RuntimeError("set-difference candidate overlaps direct candidates")
    missing_candidate = candidates[missing_id]

    set_difference = {
        "locationId": missing_id,
        "candidateTitle": missing_candidate["title"],
        "regionId": missing_candidate["regionId"],
        "regionTitle": missing_candidate["regionTitle"],
        "atlasCandidate": missing_candidate["atlas"],
        "evidenceType": "complete-catalog-single-set-difference",
        "pairwiseReviewStatus": pairwise.get("status"),
        "candidateStatus": "blocked-pending-independent-resolution",
        "promotionAllowed": False,
        "blockReason": "direct pairwise geometry review did not reach two-model consensus",
    }

    all_ids = direct_ids + [missing_id]
    if len(all_ids) != 27 or len(set(all_ids)) != 27:
        raise RuntimeError("candidate package does not contain 27 unique shrine candidates")

    result = {
        "schemaVersion": 1,
        "generatedAt": now(),
        "status": "shrine-anchor-candidate-package-ready",
        "stage": "direct-popup-candidates-before-independent-review",
        "source": proof["source"],
        "counts": {
            "totalCandidateAnchors": 27,
            "directPopupCandidates": 26,
            "catalogSetDifferenceCandidates": 1,
            "promotionReady": 0,
            "pendingIndependentReview": 26,
            "blockedPendingResolution": 1,
        },
        "policy": {
            "minimumIndependentModels": MINIMUM_REVIEW_MODELS,
            "minimumConfidencePerModel": MINIMUM_CONFIDENCE_PER_MODEL,
            "requireSameLocationId": True,
            "candidateCoordinatesIncluded": True,
            "coordinatesPromoted": False,
            "canonicalAnchorModified": False,
        },
        "directPopupCandidates": direct_rows,
        "catalogSetDifferenceCandidate": set_difference,
        "safety": {
            "sourceProofStatus": proof["status"],
            "pairwiseGeometryReviewStatus": pairwise.get("status"),
            "noCandidatePromotedWithoutIndependentReview": True,
            "repositoryContainsPixels": False,
        },
    }
    write(OUTPUT_PATH, result)
    print(json.dumps({"status": result["status"], "counts": result["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
