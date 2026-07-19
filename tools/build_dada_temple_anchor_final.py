#!/usr/bin/env python3
"""Consolidate all 36 Dada temple positions into a final geospatial anchor set.

The builder merges the three reviewed batches and applies targeted supplemental
visual resolutions for the five previously unresolved positions. Repository
outputs contain only labels, timestamps, hashes, candidate IDs and coordinates;
no source video or evidence pixels are retained.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STAGE1 = ROOT / "data/geospatial/dada-temples-36-stage1.json"
PRIMARY_MANIFEST = ROOT / "data/geospatial/dada-temples-36-evidence-manifest.json"
SUPPLEMENTAL_MANIFEST = ROOT / "data/geospatial/dada-temples-36-supplemental-evidence-manifest.json"
BATCHES = [
    ROOT / "data/geospatial/dada-temples-36-anchors-batch01.json",
    ROOT / "data/geospatial/dada-temples-36-anchors-batch02.json",
    ROOT / "data/geospatial/dada-temples-36-anchors-batch03.json",
]
OUTPUT = ROOT / "data/geospatial/dada-temples-36-anchors-final.json"
STATUS = ROOT / "data/batch-analysis/dada-temples-36-anchor-final-status.json"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# Supplemental review decisions. Position 05 uses a pairwise map-sequence proof:
# the southwest Kii view shows exactly two temple markers around 妙见神社; the
# next directly selected marker is 道成寺 (position 06), leaving the northwest
# marker as the unique Saika Temple Grounds candidate for position 05.
RESOLUTIONS: dict[int, dict[str, Any]] = {
    2: {
        "observedLabelZh": "金刚峰寺",
        "candidateId": "location-mapgenie-436455",
        "confidence": 0.99,
        "resolutionMethod": "direct-popup",
        "basis": "Supplemental frame at 30.000s directly shows 金刚峰寺, uniquely matching Kongobuji Temple.",
        "evidence": [("supplemental", "window-01-position-02-root-tower-018-30.000s.jpg")],
    },
    4: {
        "observedLabelZh": "慈尊院",
        "candidateId": "location-mapgenie-436436",
        "confidence": 0.99,
        "resolutionMethod": "direct-popup",
        "basis": "Supplemental frame at 44.500s directly shows 慈尊院, uniquely matching Jison-in.",
        "evidence": [("supplemental", "window-02-positions-04-05-koyasan-saika-019-44.500s.jpg")],
    },
    5: {
        "observedLabelZh": "妙见神社附近西北侧寺庙",
        "candidateId": "location-mapgenie-436387",
        "confidence": 0.94,
        "resolutionMethod": "pairwise-spatial-sequence",
        "basis": (
            "The 49.000s-52.000s Kii map view shows the two position-05/06 temple markers around 妙见神社; "
            "the following 54.124s direct popup identifies the southeast marker as 道成寺 (position 06). "
            "The northwest marker is therefore the unique Saika Temple Grounds candidate for position 05."
        ),
        "evidence": [
            ("supplemental", "window-02-positions-04-05-koyasan-saika-028-49.000s.jpg"),
            ("supplemental", "window-02-positions-04-05-koyasan-saika-034-52.000s.jpg"),
            ("primary", "slot-08-middle-54.124s.jpg"),
        ],
    },
    10: {
        "observedLabelZh": "天王寺",
        "candidateId": "location-mapgenie-434396",
        "confidence": 0.99,
        "resolutionMethod": "direct-popup",
        "basis": "Supplemental frame at 80.000s directly shows 天王寺, uniquely matching Tennoji Temple.",
        "evidence": [("supplemental", "window-03-position-10-tennoji-004-80.000s.jpg")],
    },
    30: {
        "observedLabelZh": "三井寺",
        "candidateId": "location-mapgenie-435055",
        "confidence": 0.99,
        "resolutionMethod": "direct-popup",
        "basis": "Supplemental frame at 216.500s directly shows 三井寺, uniquely matching Miidera.",
        "evidence": [("supplemental", "window-04-position-30-miidera-005-216.500s.jpg")],
    },
}


def main() -> int:
    stage = load(STAGE1)
    primary = load(PRIMARY_MANIFEST)
    supplemental = load(SUPPLEMENTAL_MANIFEST)
    batches = [load(path) for path in BATCHES]

    assert stage["source"]["bvid"] == "BV19EXYYWEdv"
    assert stage["counts"]["mapTempleCandidates"] == 38
    assert primary["status"] == "artifact-uploaded-awaiting-visual-review"
    assert primary["extraction"]["frameCount"] == 108
    assert supplemental["status"] == "artifact-uploaded-awaiting-visual-review"
    assert supplemental["extraction"]["frameCount"] == 100
    assert supplemental["extraction"]["contactSheetCount"] == 4

    candidates = {row["locationId"]: row for row in stage["candidateTemples"]}
    primary_frames = {row["filename"]: row for row in primary["extraction"]["frames"]}
    supplemental_frames = {row["filename"]: row for row in supplemental["extraction"]["frames"]}
    frame_indexes = {"primary": primary_frames, "supplemental": supplemental_frames}

    merged: dict[int, dict[str, Any]] = {}
    for batch in batches:
        assert batch["status"] == "complete"
        assert batch["source"]["bvid"] == "BV19EXYYWEdv"
        for row in batch["anchors"]:
            position = int(row["videoPosition"])
            if position in merged:
                raise RuntimeError(f"duplicate video position across batches: {position}")
            merged[position] = copy.deepcopy(row)

    assert sorted(merged) == list(range(1, 37))
    assert sorted(position for position, row in merged.items() if row["status"] == "unresolved") == [2, 4, 5, 10, 30]

    supplemental_resolutions: list[dict[str, Any]] = []
    for position, reviewed in RESOLUTIONS.items():
        candidate_id = reviewed["candidateId"]
        candidate = candidates.get(candidate_id)
        if candidate is None:
            raise RuntimeError(f"unknown candidate for position {position}: {candidate_id}")
        evidence_rows: list[dict[str, Any]] = []
        for manifest_name, filename in reviewed["evidence"]:
            frame = frame_indexes[manifest_name].get(filename)
            if frame is None:
                raise RuntimeError(f"missing {manifest_name} evidence frame: {filename}")
            evidence_rows.append({
                "manifest": manifest_name,
                "filename": filename,
                "timeSeconds": frame["timeSeconds"],
                "sha256": frame["sha256"],
            })
        resolved = {
            "videoPosition": position,
            "observedLabelZh": reviewed["observedLabelZh"],
            "confidence": reviewed["confidence"],
            "resolutionMethod": reviewed["resolutionMethod"],
            "basis": reviewed["basis"],
            "evidence": evidence_rows,
            "status": "confirmed",
            "locationId": candidate_id,
            "title": candidate["title"],
            "regionId": candidate["regionId"],
            "regionTitle": candidate["regionTitle"],
            "atlas": candidate["atlas"],
            "sourceLocationId": candidate["sourceLocationId"],
        }
        merged[position] = resolved
        supplemental_resolutions.append(copy.deepcopy(resolved))

    anchors = [merged[position] for position in range(1, 37)]
    confirmed = [row for row in anchors if row["status"] == "confirmed"]
    used_ids = [row["locationId"] for row in confirmed]
    if len(used_ids) != len(set(used_ids)):
        raise RuntimeError("duplicate final location assignment")
    unmatched = [copy.deepcopy(row) for row in stage["candidateTemples"] if row["locationId"] not in set(used_ids)]
    unmatched_ids = {row["locationId"] for row in unmatched}
    expected_awaji = {"location-mapgenie-479951", "location-mapgenie-479947"}

    assert len(anchors) == 36
    assert len(confirmed) == 36
    assert all(row["confidence"] >= 0.9 for row in confirmed)
    assert all(set(row["atlas"]) == {"x", "y"} for row in confirmed)
    assert len(used_ids) == 36
    assert unmatched_ids == expected_awaji
    assert all(row["regionTitle"] == "AWAJI" for row in unmatched)
    assert not list((ROOT / "data").rglob("*.jpg"))
    assert not list((ROOT / "data").rglob("*.png"))
    assert not list((ROOT / "data").rglob("*.mp4"))

    timestamp = now()
    output = {
        "schemaVersion": 1,
        "generatedAt": timestamp,
        "stage": "final-geospatial-anchor-consolidation",
        "status": "complete",
        "source": {
            "bvid": "BV19EXYYWEdv",
            "title": stage["source"]["title"],
            "authorizationId": stage["source"]["authorizationId"],
            "analysisResultPath": stage["source"]["analysisResultPath"],
            "primaryEvidenceManifestPath": "data/geospatial/dada-temples-36-evidence-manifest.json",
            "supplementalEvidenceManifestPath": "data/geospatial/dada-temples-36-supplemental-evidence-manifest.json",
            "primaryArtifactId": primary.get("artifactId"),
            "supplementalArtifactId": supplemental.get("artifactId"),
        },
        "counts": {
            "videoPositions": 36,
            "confirmed": 36,
            "unresolved": 0,
            "coordinatesWritten": 36,
            "mapTempleCandidates": 38,
            "unmatchedMapCandidates": len(unmatched),
        },
        "policy": {
            "minimumConfidence": 0.9,
            "uniqueLocationAssignment": True,
            "supplementalResolutions": sorted(RESOLUTIONS),
            "repositoryContainsEvidencePixels": False,
            "unmatchedCandidatesMustBeAwajiExpansion": True,
        },
        "supplementalResolutions": supplemental_resolutions,
        "unmatchedMapCandidates": unmatched,
        "anchors": anchors,
    }
    checks = {
        "sourceExact": True,
        "allThreeBatchesComplete": True,
        "supplementalManifestComplete": True,
        "positionsOneThroughThirtySix": True,
        "allPositionsConfirmed": True,
        "allCoordinatesWritten": True,
        "allConfidenceAtLeastPointNine": True,
        "locationAssignmentsUnique": True,
        "onlyTwoAwajiCandidatesUnmatched": True,
        "repositoryContainsNoEvidencePixels": True,
    }
    status = {
        "schemaVersion": 1,
        "status": "complete",
        "stage": "final-geospatial-anchor-consolidation",
        "generatedAt": timestamp,
        "checks": checks,
        "counts": output["counts"],
        "resolvedPositions": sorted(RESOLUTIONS),
        "outputPath": "data/geospatial/dada-temples-36-anchors-final.json",
    }
    write(OUTPUT, output)
    write(STATUS, status)
    print(json.dumps({"counts": output["counts"], "resolvedPositions": sorted(RESOLUTIONS)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
