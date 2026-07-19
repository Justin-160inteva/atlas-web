#!/usr/bin/env python3
"""400-round gates for Dada sequence 20 identity repair and replacement."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TITLE = "【刺客信条影 新手攻略】20 锁链晕眩流（奈绪江配装）"
BVID = "BV1Gqj867Eep"
BVID_22 = "BV1Ub7N6zEKa"


def load(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def preflight() -> None:
    report = load("data/batch-analysis/dada-sequence-20-resolution.json")
    resolved = report["resolved"]
    assert report["status"] == "resolved"
    assert report["acceptedCount"] == 1
    assert report["mediaDownloaded"] is False
    assert resolved["accepted"] is True
    assert all(resolved["checks"].values())
    assert resolved["bvid"] == BVID
    assert resolved["sequence"] == 20
    assert 133 <= resolved["durationSeconds"] <= 137

    manifest = load("data/reprocess/dada-seq20.json")
    assert manifest["expectedTitle"] == TITLE
    assert manifest["verifiedBvid"] == BVID
    assert manifest["replaceWrongBvid"] == BVID_22
    assert manifest["replaceJobId"] == "dada-20-v1"
    assert manifest["expectedRemainingSequences"] == []

    catalog = load("data/dada-ac-shadows-catalog.json")
    item20 = next(item for item in catalog["items"] if int(item["sequence"]) == 20)
    item22 = next(item for item in catalog["items"] if int(item["sequence"]) == 22)
    assert item20["title"] == TITLE
    assert item20["duration"] == "02:15"
    assert item20["resolvedBvid"] == BVID
    assert item20["analysisQualityStatus"] == "stale-wrong-source-pending-reprocess"
    assert item22["resolvedBvid"] == BVID_22
    assert item20["resolvedBvid"] != item22["resolvedBvid"]

    queue = load("data/analysis-jobs/dada-quality-reprocess.json")
    assert queue["sequences"] == [20]
    assert queue["readyForReprocessSequences"] == [20]
    item = queue["items"][0]
    assert item["expectedTitle"] == TITLE
    assert item["exactBvid"] == BVID
    assert item["safeToDownloadNow"] is True
    assert item["requiresExactUrlVerification"] is False


def final() -> None:
    result = load("data/analysis-results/dada-20.json")
    report = load("data/batch-analysis/dada-seq20-reprocess-status.json")
    catalog = load("data/dada-ac-shadows-catalog.json")
    queue = load("data/analysis-jobs/dada-quality-reprocess.json")
    item20 = next(item for item in catalog["items"] if int(item["sequence"]) == 20)
    item22 = next(item for item in catalog["items"] if int(item["sequence"]) == 22)

    assert result["status"] == "analyzed"
    assert result["jobId"] == "dada-20-v2-correct-source"
    assert result["source"]["title"] == TITLE
    assert result["source"]["url"].endswith(f"/{BVID}/")
    assert abs(float(result["media"]["durationSeconds"]) - 135) <= 3
    assert result["media"]["fileSha256"]
    assert result["media"]["videoRetained"] is False
    assert result["media"]["framePixelsRetained"] is False
    assert report["status"] == "complete"
    assert all(report["resultChecks"].values())
    assert item20["analysisQualityStatus"] == "verified-correct-source"
    assert item20["resolvedBvid"] == BVID
    assert item22["resolvedBvid"] == BVID_22
    assert item20["resolvedBvid"] != item22["resolvedBvid"]
    assert queue.get("sequences") == []
    assert queue.get("items") == []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "final"))
    parser.add_argument("--rounds", type=int, default=400)
    args = parser.parse_args()
    assert 1 <= args.rounds <= 2000
    check = preflight if args.mode == "preflight" else final
    for _ in range(args.rounds):
        check()
    print(json.dumps({"sequence": 20, "mode": args.mode, "rounds": args.rounds, "status": "passed"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
