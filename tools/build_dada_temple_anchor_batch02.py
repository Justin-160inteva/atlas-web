#!/usr/bin/env python3
"""Build visually reviewed Dada temple anchors for video positions 13-24.

The transient evidence artifact was reviewed manually. Only non-pixel evidence
references, candidate IDs, coordinates and confidence are committed.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STAGE1 = ROOT / "data/geospatial/dada-temples-36-stage1.json"
MANIFEST = ROOT / "data/geospatial/dada-temples-36-evidence-manifest.json"
OUTPUT = ROOT / "data/geospatial/dada-temples-36-anchors-batch02.json"
STATUS = ROOT / "data/batch-analysis/dada-temples-36-anchor-batch02-status.json"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


REVIEWED = [
    {
        "videoPosition": 13,
        "observedLabelZh": "伊崎寺",
        "candidateId": "location-mapgenie-435820",
        "confidence": 0.99,
        "evidence": ["slot-15-early-102.621s.jpg"],
        "basis": "Direct popup text 伊崎寺 matches Isakiji Temple in Omi.",
    },
    {
        "videoPosition": 14,
        "observedLabelZh": "总见寺",
        "candidateId": "location-mapgenie-436705",
        "confidence": 0.99,
        "evidence": ["slot-15-middle-104.642s.jpg"],
        "basis": "Direct popup text 总见寺 matches Sokenji Temple in Omi.",
    },
    {
        "videoPosition": 15,
        "observedLabelZh": "宝严寺",
        "candidateId": "location-mapgenie-435908",
        "confidence": 0.99,
        "evidence": ["slot-16-late-113.878s.jpg"],
        "basis": "Direct popup text 宝严寺 matches Hogonji Temple in Omi.",
    },
    {
        "videoPosition": 16,
        "observedLabelZh": "大吉寺",
        "candidateId": "location-mapgenie-435886",
        "confidence": 0.99,
        "evidence": ["slot-17-middle-119.075s.jpg"],
        "basis": "Direct popup text 大吉寺 matches Daikichiji Temple in Omi.",
    },
    {
        "videoPosition": 17,
        "observedLabelZh": "三之堂",
        "candidateId": "location-mapgenie-437649",
        "confidence": 0.98,
        "evidence": ["slot-18-late-128.311s.jpg"],
        "basis": "Direct popup text 三之堂 matches the Mitsunodo Hall temple candidate in Harima.",
    },
    {
        "videoPosition": 18,
        "observedLabelZh": "阿贺本德寺",
        "candidateId": "location-mapgenie-437692",
        "confidence": 0.99,
        "evidence": ["slot-19-early-131.487s.jpg"],
        "basis": "Direct popup text 阿贺本德寺 matches Aga Hontokuji Temple in Harima.",
    },
    {
        "videoPosition": 19,
        "observedLabelZh": "教海寺",
        "candidateId": "location-mapgenie-437593",
        "confidence": 0.99,
        "evidence": ["slot-20-middle-140.725s.jpg"],
        "basis": "Direct popup text 教海寺 matches Kyokaiji Temple in Harima.",
    },
    {
        "videoPosition": 20,
        "observedLabelZh": "丹生山妙养寺",
        "candidateId": "location-mapgenie-437563",
        "confidence": 0.99,
        "evidence": ["slot-20-late-142.745s.jpg"],
        "basis": "Direct popup text 丹生山妙养寺 matches Tanjosan Myoyoji Temple in Harima.",
    },
    {
        "videoPosition": 21,
        "observedLabelZh": "安稳寺",
        "candidateId": "location-mapgenie-435078",
        "confidence": 0.99,
        "evidence": ["slot-22-middle-155.157s.jpg"],
        "basis": "Direct popup text 安稳寺 matches Annonji Temple in Tamba.",
    },
    {
        "videoPosition": 22,
        "observedLabelZh": "宗镜寺",
        "candidateId": "location-mapgenie-438261",
        "confidence": 0.99,
        "evidence": ["slot-23-late-164.395s.jpg"],
        "basis": "Direct popup text 宗镜寺 matches Sukyoji Temple in Tamba.",
    },
    {
        "videoPosition": 23,
        "observedLabelZh": "西福寺",
        "candidateId": "location-mapgenie-437090",
        "confidence": 0.99,
        "evidence": ["slot-25-early-174.787s.jpg"],
        "basis": "Direct popup text 西福寺 matches Saifukuji Temple in Wakasa.",
    },
    {
        "videoPosition": 24,
        "observedLabelZh": "极乐寺",
        "candidateId": "location-mapgenie-438274",
        "confidence": 0.99,
        "evidence": ["slot-26-middle-184.024s.jpg"],
        "basis": "Direct popup text 极乐寺 matches Gokurakuji Temple in Wakasa.",
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
        candidate_id = reviewed["candidateId"]
        candidate = candidates.get(candidate_id)
        if candidate is None:
            raise RuntimeError(f"unknown confirmed candidate: {candidate_id}")
        if candidate_id in confirmed_ids:
            raise RuntimeError(f"duplicate confirmed candidate: {candidate_id}")
        confirmed_ids.add(candidate_id)

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

        anchors.append({
            "videoPosition": reviewed["videoPosition"],
            "observedLabelZh": reviewed["observedLabelZh"],
            "confidence": reviewed["confidence"],
            "basis": reviewed["basis"],
            "evidence": evidence_rows,
            "status": "confirmed",
            "locationId": candidate_id,
            "title": candidate["title"],
            "regionId": candidate["regionId"],
            "regionTitle": candidate["regionTitle"],
            "atlas": candidate["atlas"],
            "sourceLocationId": candidate["sourceLocationId"],
        })

    assert [row["videoPosition"] for row in anchors] == list(range(13, 25))
    assert len({row["locationId"] for row in anchors}) == 12
    assert all(row["confidence"] >= 0.9 for row in anchors)

    timestamp = now()
    output = {
        "schemaVersion": 1,
        "generatedAt": timestamp,
        "stage": "visual-review-batch-02",
        "status": "complete",
        "source": {
            "bvid": "BV19EXYYWEdv",
            "analysisResultPath": stage["source"]["analysisResultPath"],
            "evidenceManifestPath": "data/geospatial/dada-temples-36-evidence-manifest.json",
            "artifactId": manifest.get("artifactId"),
            "artifactDigest": manifest.get("artifactDigest"),
            "artifactRetentionDays": manifest.get("artifactRetentionDays"),
        },
        "scope": {"videoPositions": [13, 24], "count": 12},
        "counts": {
            "reviewed": 12,
            "confirmed": 12,
            "unresolved": 0,
            "coordinatesWritten": 12,
        },
        "policy": {
            "confirmedThreshold": 0.9,
            "directPopupRequired": True,
            "repositoryContainsFramePixels": False,
        },
        "anchors": anchors,
    }
    write(OUTPUT, output)
    write(STATUS, {
        "schemaVersion": 1,
        "status": "complete",
        "stage": "visual-review-batch-02",
        "generatedAt": timestamp,
        "checks": {
            "sourceExact": True,
            "manifestComplete": True,
            "positionsThirteenThroughTwentyFour": True,
            "confirmedCandidatesUnique": True,
            "confirmedConfidenceAtLeastPointNine": True,
            "allReviewedPositionsHaveCoordinates": True,
            "repositoryContainsNoEvidencePixels": True,
        },
        "counts": output["counts"],
        "outputPath": "data/geospatial/dada-temples-36-anchors-batch02.json",
    })
    print(json.dumps(output["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
