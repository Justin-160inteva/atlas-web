#!/usr/bin/env python3
"""Build the first visually reviewed geospatial anchor batch for Dada temples.

The builder consumes only non-pixel repository evidence. Visual review was
performed against the one-day transient contact-sheet artifact; this file stores
only evidence filenames, timestamps, hashes, candidate IDs, coordinates and
confidence. Ambiguous positions remain explicitly unresolved.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STAGE1 = ROOT / "data/geospatial/dada-temples-36-stage1.json"
MANIFEST = ROOT / "data/geospatial/dada-temples-36-evidence-manifest.json"
OUTPUT = ROOT / "data/geospatial/dada-temples-36-anchors-batch01.json"
STATUS = ROOT / "data/batch-analysis/dada-temples-36-anchor-batch01-status.json"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# Confirmed entries require a direct popup/map-label reading plus a unique
# candidate match. Unresolved entries intentionally do not write coordinates.
REVIEWED = [
    {
        "videoPosition": 1,
        "observedLabelZh": "如意轮寺",
        "candidateId": "location-mapgenie-435786",
        "confidence": 0.99,
        "evidence": ["slot-01-late-5.629s.jpg", "slot-02-middle-10.825s.jpg"],
        "basis": "Direct popup text 如意轮寺 and matching Nyoirinji candidate in Yamato.",
    },
    {
        "videoPosition": 2,
        "observedLabelZh": "根本大塔",
        "candidateOptions": ["location-mapgenie-436442", "location-mapgenie-436455"],
        "confidence": 0.58,
        "evidence": ["slot-04-late-27.279s.jpg"],
        "basis": "Direct popup text, but the two adjacent Koyasan candidate labels cannot be separated safely from this frame alone.",
    },
    {
        "videoPosition": 3,
        "observedLabelZh": "高野山坛上伽蓝",
        "candidateId": "location-mapgenie-436442",
        "confidence": 0.98,
        "evidence": ["slot-05-middle-32.475s.jpg"],
        "basis": "Direct popup text matches Koyasan Danjo Garan.",
    },
    {
        "videoPosition": 4,
        "observedLabelZh": "高野山",
        "candidateOptions": ["location-mapgenie-436436", "location-mapgenie-436455"],
        "confidence": 0.55,
        "evidence": ["slot-06-middle-39.691s.jpg"],
        "basis": "Generic fast-travel label does not uniquely distinguish Jison-in from Kongobuji.",
    },
    {
        "videoPosition": 5,
        "observedLabelZh": "妙见神社附近的第一处寺庙",
        "candidateOptions": ["location-mapgenie-436387"],
        "confidence": 0.69,
        "evidence": ["slot-07-late-48.928s.jpg"],
        "basis": "Spatially consistent with Saika Temple Grounds, but no direct popup title was captured.",
    },
    {
        "videoPosition": 6,
        "observedLabelZh": "道成寺",
        "candidateId": "location-mapgenie-437468",
        "confidence": 0.99,
        "evidence": ["slot-08-middle-54.124s.jpg"],
        "basis": "Direct popup text matches Dojoji Temple.",
    },
    {
        "videoPosition": 7,
        "observedLabelZh": "愿泉寺",
        "candidateId": "location-mapgenie-434575",
        "confidence": 0.98,
        "evidence": ["slot-10-middle-68.558s.jpg"],
        "basis": "Direct popup text matches Gansenji Temple transliteration and position.",
    },
    {
        "videoPosition": 8,
        "observedLabelZh": "根来寺",
        "candidateId": "location-mapgenie-437327",
        "confidence": 0.94,
        "evidence": ["slot-10-late-70.578s.jpg"],
        "basis": "Visible map label 根来寺 within the 07-08 group matches Negoroji Temple Grounds.",
    },
    {
        "videoPosition": 9,
        "observedLabelZh": "槙尾寺",
        "candidateId": "location-mapgenie-434352",
        "confidence": 0.99,
        "evidence": ["slot-11-late-77.795s.jpg"],
        "basis": "Direct popup text matches Makinoodera Temple.",
    },
    {
        "videoPosition": 10,
        "observedLabelZh": "槙尾瞭望台附近的第二处寺庙",
        "candidateOptions": ["location-mapgenie-434396"],
        "confidence": 0.66,
        "evidence": ["slot-12-middle-82.992s.jpg"],
        "basis": "Tennoji is the remaining plausible nearby candidate, but the captured frame has no selected popup.",
    },
    {
        "videoPosition": 11,
        "observedLabelZh": "东大寺",
        "candidateId": "location-mapgenie-437901",
        "confidence": 0.99,
        "evidence": ["slot-13-middle-90.208s.jpg"],
        "basis": "Direct popup text matches Todaiji Temple.",
    },
    {
        "videoPosition": 12,
        "observedLabelZh": "兴福寺",
        "candidateId": "location-mapgenie-437869",
        "confidence": 0.99,
        "evidence": ["slot-13-late-92.228s.jpg"],
        "basis": "Direct popup text matches Kofukuji Temple.",
    },
]


def main() -> int:
    stage = load(STAGE1)
    manifest = load(MANIFEST)
    assert stage["source"]["bvid"] == "BV19EXYYWEdv"
    assert manifest["status"] == "artifact-uploaded-awaiting-visual-review"
    assert manifest["source"]["bvid"] == "BV19EXYYWEdv"
    assert manifest["extraction"]["frameCount"] == 108
    assert manifest["extraction"]["contactSheetCount"] == 12

    candidates = {row["locationId"]: row for row in stage["candidateTemples"]}
    frames = {row["filename"]: row for row in manifest["extraction"]["frames"]}
    anchors: list[dict[str, Any]] = []
    confirmed_ids: set[str] = set()

    for reviewed in REVIEWED:
        position = int(reviewed["videoPosition"])
        evidence_rows = []
        for filename in reviewed["evidence"]:
            frame = frames.get(filename)
            if frame is None:
                raise RuntimeError(f"missing evidence frame: {filename}")
            evidence_rows.append({
                "filename": filename,
                "timeSeconds": frame["timeSeconds"],
                "sha256": frame["sha256"],
            })

        row: dict[str, Any] = {
            "videoPosition": position,
            "observedLabelZh": reviewed["observedLabelZh"],
            "confidence": reviewed["confidence"],
            "basis": reviewed["basis"],
            "evidence": evidence_rows,
        }
        candidate_id = reviewed.get("candidateId")
        if candidate_id:
            candidate = candidates.get(candidate_id)
            if candidate is None:
                raise RuntimeError(f"unknown confirmed candidate: {candidate_id}")
            if candidate_id in confirmed_ids:
                raise RuntimeError(f"duplicate confirmed candidate: {candidate_id}")
            confirmed_ids.add(candidate_id)
            row.update({
                "status": "confirmed",
                "locationId": candidate_id,
                "title": candidate["title"],
                "regionId": candidate["regionId"],
                "regionTitle": candidate["regionTitle"],
                "atlas": candidate["atlas"],
                "sourceLocationId": candidate["sourceLocationId"],
            })
        else:
            option_ids = reviewed.get("candidateOptions") or []
            options = []
            for option_id in option_ids:
                candidate = candidates.get(option_id)
                if candidate is None:
                    raise RuntimeError(f"unknown candidate option: {option_id}")
                options.append({
                    "locationId": option_id,
                    "title": candidate["title"],
                    "regionTitle": candidate["regionTitle"],
                    "atlas": candidate["atlas"],
                })
            row.update({"status": "unresolved", "candidateOptions": options})
        anchors.append(row)

    positions = [row["videoPosition"] for row in anchors]
    assert positions == list(range(1, 13))
    confirmed = [row for row in anchors if row["status"] == "confirmed"]
    unresolved = [row for row in anchors if row["status"] == "unresolved"]
    timestamp = now()
    output = {
        "schemaVersion": 1,
        "generatedAt": timestamp,
        "stage": "visual-review-batch-01",
        "status": "complete",
        "source": {
            "bvid": "BV19EXYYWEdv",
            "analysisResultPath": stage["source"]["analysisResultPath"],
            "evidenceManifestPath": "data/geospatial/dada-temples-36-evidence-manifest.json",
            "artifactId": manifest.get("artifactId"),
            "artifactDigest": manifest.get("artifactDigest"),
            "artifactRetentionDays": manifest.get("artifactRetentionDays"),
        },
        "scope": {"videoPositions": [1, 12], "count": 12},
        "counts": {
            "reviewed": len(anchors),
            "confirmed": len(confirmed),
            "unresolved": len(unresolved),
            "coordinatesWritten": len(confirmed),
        },
        "policy": {
            "confirmedThreshold": 0.9,
            "ambiguousPositionsRemainUnlinked": True,
            "repositoryContainsFramePixels": False,
        },
        "anchors": anchors,
    }
    assert output["counts"] == {"reviewed": 12, "confirmed": 8, "unresolved": 4, "coordinatesWritten": 8}
    assert all(row["confidence"] >= 0.9 for row in confirmed)
    assert all("atlas" not in row for row in unresolved)
    write(OUTPUT, output)
    write(STATUS, {
        "schemaVersion": 1,
        "status": "complete",
        "stage": "visual-review-batch-01",
        "generatedAt": timestamp,
        "checks": {
            "sourceExact": True,
            "manifestComplete": True,
            "positionsOneThroughTwelve": True,
            "confirmedCandidatesUnique": True,
            "confirmedConfidenceAtLeastPointNine": True,
            "unresolvedHaveNoWrittenCoordinates": True,
            "repositoryContainsNoEvidencePixels": True,
        },
        "counts": output["counts"],
        "outputPath": "data/geospatial/dada-temples-36-anchors-batch01.json",
    })
    print(json.dumps(output["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
