#!/usr/bin/env python3
"""Repair the last two non-media Dada catalog metadata inconsistencies.

Sequence 03 already has a valid analyzed result under its historical descriptive
filename. Sequence 06 has a verified replacement result, but its status row
retained the pre-reprocess stale flags. No media is downloaded or reprocessed.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data/dada-ac-shadows-catalog.json"
STATUS_PATH = ROOT / "data/batch-analysis/dada-author-catalog-status.json"
RESULT03_PATH = ROOT / "data/analysis-results/dada-temples-36.json"
RESULT06_PATH = ROOT / "data/analysis-results/dada-06.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    result03 = load(RESULT03_PATH)
    result06 = load(RESULT06_PATH)
    assert result03["status"] == "analyzed"
    assert result03["source"]["url"].endswith("/BV19EXYYWEdv/")
    assert result03["media"]["videoRetained"] is False
    assert result03["media"]["framePixelsRetained"] is False
    assert result06["status"] == "analyzed"
    assert result06["source"]["url"].endswith("/BV13ioXYEE8d/")
    assert result06["media"]["videoRetained"] is False
    assert result06["media"]["framePixelsRetained"] is False

    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    catalog = load(CATALOG_PATH)
    item03 = next(item for item in catalog["items"] if int(item["sequence"]) == 3)
    item03["analysisStatus"] = "imported"
    item03["analysisResultPath"] = "data/analysis-results/dada-temples-36.json"
    item03["analysisUpdatedAt"] = result03.get("generatedAt") or timestamp
    item03["analysisQualityStatus"] = "verified-correct-source"
    item03["analysisVerification"] = {
        "verifiedBvid": "BV19EXYYWEdv",
        "verifiedAt": timestamp,
        "resultChecks": {
            "statusAnalyzed": True,
            "authorExact": result03["source"].get("author") == "不再犹豫的达达猪",
            "titleExact": "03寺庙全收集" in "".join(ch for ch in result03["source"].get("title", "") if ch.isalnum()),
            "bvidExact": result03["source"]["url"].endswith("/BV19EXYYWEdv/"),
            "originalVideoDeleted": result03["media"].get("videoRetained") is False,
            "framePixelsDeleted": result03["media"].get("framePixelsRetained") is False,
        },
        "canonicalResultPath": "data/analysis-results/dada-temples-36.json",
    }
    item06 = next(item for item in catalog["items"] if int(item["sequence"]) == 6)
    assert item06.get("analysisQualityStatus") == "verified-correct-source"
    write(CATALOG_PATH, catalog)

    status = load(STATUS_PATH)
    status03 = next(item for item in status["items"] if int(item["sequence"]) == 3)
    status03["resultPath"] = "data/analysis-results/dada-temples-36.json"
    status03["qualityState"] = "verified-correct-source"
    status03["resultStale"] = False
    status03.pop("staleReason", None)
    status06 = next(item for item in status["items"] if int(item["sequence"]) == 6)
    status06["qualityState"] = "verified-correct-source"
    status06["resultStale"] = False
    status06.pop("staleReason", None)
    status["updatedAt"] = timestamp
    write(STATUS_PATH, status)

    print(json.dumps({
        "status": "repaired",
        "sequence03ResultPath": status03["resultPath"],
        "sequence06Stale": status06["resultStale"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
