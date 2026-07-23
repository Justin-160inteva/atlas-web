#!/usr/bin/env python3
"""Build a non-pixel completeness proof for the authorized 27-shrine video.

Twenty-six shrine names are directly readable in stable popup events. The stage-one map
candidate index contains 32 shrine candidates, five of which are Awaji expansion candidates
not covered by this 27-location sequence. This tool verifies all direct popup event references,
unique candidate mappings and the exact one-item set difference without assigning coordinates.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CENSUS_PATH = ROOT / "data/geospatial/dada-shrines-popup-event-census.json"
STAGE1_PATH = ROOT / "data/geospatial/dada-shrines-27-stage1.json"
OUTPUT_PATH = ROOT / "data/geospatial/dada-shrines-catalog-completeness-proof.json"

# event, representative time, directly visible Simplified Chinese label, candidate ID
DIRECT_POPUPS: tuple[tuple[int, float, str, str], ...] = (
    (2, 19.200, "高原熊野神社", "location-mapgenie-437477"),
    (4, 55.733, "熊野那智大社", "location-mapgenie-436647"),
    (5, 59.733, "熊野本宫大社", "location-mapgenie-437483"),
    (7, 73.333, "熊野速玉大社", "location-mapgenie-436521"),
    (8, 77.067, "神仓神社", "location-mapgenie-436509"),
    (10, 90.133, "丹生川上神社", "location-mapgenie-435783"),
    (12, 102.133, "住吉神社", "location-mapgenie-434532"),
    (14, 115.467, "大神神社", "location-mapgenie-435742"),
    (15, 117.867, "春日大社", "location-mapgenie-437898"),
    (16, 120.800, "日出神社", "location-mapgenie-438333"),
    (18, 133.867, "春日神社", "location-mapgenie-434406"),
    (19, 137.333, "敢国神社", "location-mapgenie-434366"),
    (21, 148.800, "石清水八幡宫", "location-mapgenie-437835"),
    (23, 160.000, "长滨八幡宫", "location-mapgenie-435872"),
    (25, 171.200, "西宫神社", "location-mapgenie-434692"),
    (27, 182.400, "高砂神社", "location-mapgenie-437384"),
    (28, 185.067, "生石神社", "location-mapgenie-434986"),
    (29, 188.800, "射楯兵主神社", "location-mapgenie-434988"),
    (31, 200.000, "加舎神社", "location-mapgenie-437663"),
    (33, 211.200, "爱宕神社", "location-mapgenie-438225"),
    (35, 224.267, "鬼岳神社", "location-mapgenie-438198"),
    (37, 235.733, "祇园神社", "location-mapgenie-437865"),
    (38, 239.200, "上贺茂神社", "location-mapgenie-438281"),
    (40, 247.733, "白须神社", "location-mapgenie-437262"),
    (42, 258.400, "若狭彦神社", "location-mapgenie-435994"),
    (44, 268.267, "常宫神社", "location-mapgenie-437096"),
)
EXPECTED_MISSING_ID = "location-mapgenie-438414"
EXPECTED_MISSING_TITLE = "Tokei Shrine"


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
    census = load(CENSUS_PATH)
    stage1 = load(STAGE1_PATH)
    if census.get("status") != "popup-event-census-complete":
        raise RuntimeError("popup census is not complete")
    if int(census["counts"]["stableEvents"]) != 44:
        raise RuntimeError("expected the tall-popup census with 44 stable events")
    if int(stage1["counts"]["videoClaimedShrines"]) != 27:
        raise RuntimeError("video shrine claim changed from 27")

    events = {int(row["event"]): row for row in census["events"]}
    candidates = {row["locationId"]: row for row in stage1["candidateShrines"]}
    eligible = {
        location_id: row
        for location_id, row in candidates.items()
        if str(row.get("regionTitle") or "").upper() != "AWAJI"
    }
    excluded_awaji = sorted(set(candidates) - set(eligible))
    if len(candidates) != 32 or len(excluded_awaji) != 5 or len(eligible) != 27:
        raise RuntimeError("candidate partition is not 32 total / 5 Awaji / 27 eligible")

    observed_rows: list[dict[str, Any]] = []
    observed_ids: list[str] = []
    observed_events: list[int] = []
    for event_number, expected_time, visible_label, location_id in DIRECT_POPUPS:
        if event_number not in events:
            raise RuntimeError(f"popup event {event_number} is missing")
        event = events[event_number]
        actual_time = float(event["representativeTimeSeconds"])
        if abs(actual_time - expected_time) > 0.01:
            raise RuntimeError(
                f"popup event {event_number} time changed: {actual_time:.3f} vs {expected_time:.3f}"
            )
        if location_id not in eligible:
            raise RuntimeError(f"direct popup maps outside eligible candidate set: {location_id}")
        candidate = eligible[location_id]
        observed_ids.append(location_id)
        observed_events.append(event_number)
        observed_rows.append({
            "event": event_number,
            "representativeTimeSeconds": round(actual_time, 3),
            "visibleLabelZhCN": visible_label,
            "locationId": location_id,
            "candidateTitle": candidate["title"],
            "regionId": candidate["regionId"],
            "regionTitle": candidate["regionTitle"],
            "popupSha256": event["popupSha256"],
            "titleSha256": event["titleSha256"],
            "evidenceType": "direct_readable_popup_title",
            "coordinatesAssigned": False,
        })

    if len(observed_rows) != 26:
        raise RuntimeError("expected 26 direct shrine popup rows")
    if len(set(observed_events)) != 26 or len(set(observed_ids)) != 26:
        raise RuntimeError("direct popup events or candidate mappings are not unique")

    missing_ids = sorted(set(eligible) - set(observed_ids))
    if missing_ids != [EXPECTED_MISSING_ID]:
        raise RuntimeError(f"eligible candidate set difference is not uniquely Tokei: {missing_ids}")
    missing = eligible[EXPECTED_MISSING_ID]
    if missing["title"] != EXPECTED_MISSING_TITLE:
        raise RuntimeError("missing candidate title changed")

    result = {
        "schemaVersion": 1,
        "generatedAt": now(),
        "status": "single-candidate-completeness-proof-ready",
        "stage": "direct-popup-catalog-set-difference",
        "source": {
            "bvid": stage1["source"]["bvid"],
            "title": stage1["source"]["title"],
            "authorizationId": stage1["source"]["authorizationId"],
            "videoClaimedShrines": 27,
        },
        "counts": {
            "allMapShrineCandidates": len(candidates),
            "excludedAwajiCandidates": len(excluded_awaji),
            "eligibleSequenceCandidates": len(eligible),
            "directReadableShrinePopups": len(observed_rows),
            "setDifferenceCandidates": len(missing_ids),
        },
        "method": {
            "candidateScope": "all stage-one Shrine candidates excluding region AWAJI",
            "directEvidenceRequirement": "stable popup event with readable shrine title",
            "candidateMappingUniqueness": True,
            "setDifferenceApplied": True,
            "coordinatesAssigned": False,
            "canonicalAnchorModified": False,
            "requiresIndependentModelReviewBeforePromotion": True,
        },
        "excludedAwajiCandidateIds": excluded_awaji,
        "directPopupMappings": observed_rows,
        "uniqueSetDifference": {
            "locationId": EXPECTED_MISSING_ID,
            "candidateTitle": missing["title"],
            "regionId": missing["regionId"],
            "regionTitle": missing["regionTitle"],
            "atlas": missing["atlas"],
            "inferenceType": "complete-catalog-single-set-difference",
            "promotionAllowed": False,
        },
        "safety": {
            "pairwiseGeometryReviewStatus": "complete-unresolved",
            "setDifferenceDoesNotOverrideDirectVisualGate": True,
            "noCoordinatesPromotedByThisProof": True,
            "repositoryContainsPixels": False,
        },
    }
    write(OUTPUT_PATH, result)
    print(json.dumps({"status": result["status"], "counts": result["counts"], "missing": missing_ids}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
