#!/usr/bin/env python3
"""Build reviewed geospatial anchors for Dada temple positions 25-36.

Only non-pixel evidence metadata is persisted. Directly readable popup labels are
linked to unique map candidates. Position 30 remains unresolved because the
sampled artifact did not capture a direct Miidera popup.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STAGE1 = ROOT / "data/geospatial/dada-temples-36-stage1.json"
MANIFEST = ROOT / "data/geospatial/dada-temples-36-evidence-manifest.json"
BATCH1 = ROOT / "data/geospatial/dada-temples-36-anchors-batch01.json"
BATCH2 = ROOT / "data/geospatial/dada-temples-36-anchors-batch02.json"
OUTPUT = ROOT / "data/geospatial/dada-temples-36-anchors-batch03.json"
STATUS = ROOT / "data/batch-analysis/dada-temples-36-anchor-batch03-status.json"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


REVIEWED = [
    {"videoPosition": 25, "observedLabelZh": "鞍马塔", "candidateId": "location-mapgenie-436354", "confidence": 0.96,
     "evidence": ["slot-25-late-178.828s.jpg"], "basis": "Direct fast-travel popup 鞍马塔 matches the Kuramadera Temple candidate and map position."},
    {"videoPosition": 26, "observedLabelZh": "相国塔", "candidateId": "location-mapgenie-434811", "confidence": 0.96,
     "evidence": ["slot-27-late-193.261s.jpg", "slot-28-late-200.478s.jpg"], "basis": "Direct popup 相国塔 matches the Shokokuji Temple candidate and its Kyoto position."},
    {"videoPosition": 27, "observedLabelZh": "银阁寺", "candidateId": "location-mapgenie-437937", "confidence": 0.99,
     "evidence": ["slot-28-middle-198.457s.jpg"], "basis": "Direct popup 银阁寺 matches Ginkakuji Temple."},
    {"videoPosition": 28, "observedLabelZh": "金阁寺", "candidateId": "location-mapgenie-436340", "confidence": 0.99,
     "evidence": ["slot-29-early-203.654s.jpg"], "basis": "Direct popup 金阁寺 matches Kinkakuji Temple."},
    {"videoPosition": 29, "observedLabelZh": "延历寺", "candidateId": "location-mapgenie-436781", "confidence": 0.99,
     "evidence": ["slot-30-middle-212.891s.jpg"], "basis": "Direct popup 延历寺 matches Enryakuji Temple."},
    {"videoPosition": 30, "observedLabelZh": "山间之塔路线中的第二处寺庙", "candidateOptions": ["location-mapgenie-435055"], "confidence": 0.76,
     "evidence": ["slot-31-early-218.087s.jpg"], "basis": "Miidera is the remaining Omi candidate in sequence, but no direct popup label was captured; coordinates remain unwritten."},
    {"videoPosition": 31, "observedLabelZh": "平等院", "candidateId": "location-mapgenie-437840", "confidence": 0.99,
     "evidence": ["slot-32-middle-227.324s.jpg"], "basis": "Direct popup 平等院 matches Byodoin Temple."},
    {"videoPosition": 32, "observedLabelZh": "清水寺", "candidateId": "location-mapgenie-435009", "confidence": 0.99,
     "evidence": ["slot-33-late-236.561s.jpg"], "basis": "Direct popup 清水寺 matches Kiyomizudera Temple."},
    {"videoPosition": 33, "observedLabelZh": "东福寺", "candidateId": "location-mapgenie-437825", "confidence": 0.98,
     "evidence": ["slot-34-early-239.737s.jpg"], "basis": "Direct popup 东福寺 matches Tofukuji Temple."},
    {"videoPosition": 34, "observedLabelZh": "天龙寺", "candidateId": "location-mapgenie-437845", "confidence": 0.99,
     "evidence": ["slot-35-late-250.994s.jpg"], "basis": "Direct popup 天龙寺 matches Tenryuji Temple."},
    {"videoPosition": 35, "observedLabelZh": "本能寺", "candidateId": "location-mapgenie-434779", "confidence": 0.99,
     "evidence": ["slot-36-early-254.170s.jpg"], "basis": "Direct popup 本能寺 matches Honnoji Temple."},
    {"videoPosition": 36, "observedLabelZh": "东寺", "candidateId": "location-mapgenie-434774", "confidence": 0.99,
     "evidence": ["slot-36-middle-256.190s.jpg"], "basis": "Direct popup 东寺 matches Toji Temple."},
]


def main() -> int:
    stage = load(STAGE1)
    manifest = load(MANIFEST)
    batch1 = load(BATCH1)
    batch2 = load(BATCH2)
    assert stage["source"]["bvid"] == "BV19EXYYWEdv"
    assert manifest["status"] == "artifact-uploaded-awaiting-visual-review"
    assert manifest["source"]["bvid"] == "BV19EXYYWEdv"
    assert manifest["extraction"]["frameCount"] == 108

    candidates = {row["locationId"]: row for row in stage["candidateTemples"]}
    frames = {row["filename"]: row for row in manifest["extraction"]["frames"]}
    prior_ids = {
        row["locationId"]
        for batch in (batch1, batch2)
        for row in batch["anchors"]
        if row["status"] == "confirmed"
    }
    anchors: list[dict[str, Any]] = []
    confirmed_ids: set[str] = set()

    for reviewed in REVIEWED:
        evidence_rows = []
        for filename in reviewed["evidence"]:
            frame = frames.get(filename)
            if frame is None:
                raise RuntimeError(f"missing evidence frame: {filename}")
            evidence_rows.append({"filename": filename, "timeSeconds": frame["timeSeconds"], "sha256": frame["sha256"]})

        row: dict[str, Any] = {
            "videoPosition": reviewed["videoPosition"],
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
            if candidate_id in prior_ids or candidate_id in confirmed_ids:
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
            options = []
            for option_id in reviewed.get("candidateOptions") or []:
                candidate = candidates.get(option_id)
                if candidate is None:
                    raise RuntimeError(f"unknown candidate option: {option_id}")
                options.append({"locationId": option_id, "title": candidate["title"], "regionTitle": candidate["regionTitle"], "atlas": candidate["atlas"]})
            row.update({"status": "unresolved", "candidateOptions": options})
        anchors.append(row)

    assert [row["videoPosition"] for row in anchors] == list(range(25, 37))
    confirmed = [row for row in anchors if row["status"] == "confirmed"]
    unresolved = [row for row in anchors if row["status"] == "unresolved"]
    timestamp = now()
    output = {
        "schemaVersion": 1,
        "generatedAt": timestamp,
        "stage": "visual-review-batch-03",
        "status": "complete",
        "source": {
            "bvid": "BV19EXYYWEdv",
            "analysisResultPath": stage["source"]["analysisResultPath"],
            "evidenceManifestPath": "data/geospatial/dada-temples-36-evidence-manifest.json",
            "artifactId": manifest.get("artifactId"),
            "artifactDigest": manifest.get("artifactDigest"),
            "artifactRetentionDays": manifest.get("artifactRetentionDays"),
        },
        "scope": {"videoPositions": [25, 36], "count": 12},
        "counts": {"reviewed": 12, "confirmed": len(confirmed), "unresolved": len(unresolved), "coordinatesWritten": len(confirmed)},
        "policy": {"confirmedThreshold": 0.9, "ambiguousPositionsRemainUnlinked": True, "repositoryContainsFramePixels": False},
        "anchors": anchors,
    }
    assert output["counts"] == {"reviewed": 12, "confirmed": 11, "unresolved": 1, "coordinatesWritten": 11}
    assert all(row["confidence"] >= 0.9 for row in confirmed)
    assert all("atlas" not in row and "locationId" not in row for row in unresolved)
    write(OUTPUT, output)
    write(STATUS, {
        "schemaVersion": 1,
        "status": "complete",
        "stage": "visual-review-batch-03",
        "generatedAt": timestamp,
        "checks": {
            "sourceExact": True,
            "manifestComplete": True,
            "positionsTwentyFiveThroughThirtySix": True,
            "confirmedCandidatesUniqueAcrossBatches": True,
            "confirmedConfidenceAtLeastPointNine": True,
            "unresolvedHaveNoWrittenCoordinates": True,
            "repositoryContainsNoEvidencePixels": True,
        },
        "counts": output["counts"],
        "outputPath": "data/geospatial/dada-temples-36-anchors-batch03.json",
    })
    print(json.dumps(output["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
