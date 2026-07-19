#!/usr/bin/env python3
"""Resolve and stage Dada sequence 14 without downloading media.

The shared sequence-06 resolver verifies collection membership, title topic,
sequence number, duration, author name, author MID, and independent view
metadata. A successful apply also creates the isolated replacement manifest.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import resolve_dada_sequence06 as resolver

resolver.SEQUENCE = 14
resolver.TOPIC = "锁链出血流"
resolver.EXPECTED_DURATION = 414
resolver.DURATION_TOLERANCE = 2
resolver.OLD_WRONG_BVID = "BV1A5P9z7EGM"
resolver.REPORT_PATH = resolver.ROOT / "data/batch-analysis/dada-sequence-14-resolution.json"

STATUS_PATH = resolver.ROOT / "data/batch-analysis/dada-author-catalog-status.json"
CATALOG_PATH = resolver.ROOT / "data/dada-ac-shadows-catalog.json"
RESULT_PATH = resolver.ROOT / "data/analysis-results/dada-14.json"
MANIFEST_PATH = resolver.ROOT / "data/reprocess/dada-seq14.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def finalize_staging() -> None:
    report = read_json(resolver.REPORT_PATH)
    resolved = report.get("resolved") or {}
    if report.get("status") != "resolved" or report.get("acceptedCount") != 1:
        raise RuntimeError("sequence 14 cannot be staged without exactly one accepted resolution")

    bvid = str(resolved.get("bvid") or "")
    if not bvid.startswith("BV") or bvid == resolver.OLD_WRONG_BVID:
        raise RuntimeError("sequence 14 resolved BVID is missing or still points at the stale source")

    catalog = read_json(CATALOG_PATH)
    catalog_item = next(item for item in catalog["items"] if int(item.get("sequence") or 0) == 14)
    stale_result = read_json(RESULT_PATH)
    replace_job_id = str(stale_result.get("jobId") or "")
    if not replace_job_id:
        raise RuntimeError("sequence 14 stale result has no jobId")

    status = read_json(STATUS_PATH)
    status_item = next(item for item in status["items"] if int(item.get("sequence") or 0) == 14)
    status_item["staleReason"] = (
        "Previous analysis used BV1A5P9z7EGM "
        "(sequence 09 开局配装, not sequence 14 锁链出血流)"
    )
    write_json(STATUS_PATH, status)

    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    manifest = {
        "schemaVersion": 1,
        "sequence": 14,
        "author": resolver.AUTHOR,
        "authorizationId": "auth-dada-20260718",
        "expectedTitle": catalog_item["title"],
        "verifiedBvid": bvid,
        "verifiedUrl": f"https://www.bilibili.com/video/{bvid}/",
        "expectedDurationSeconds": resolver.EXPECTED_DURATION,
        "replaceWrongBvid": resolver.OLD_WRONG_BVID,
        "replaceJobId": replace_job_id,
        "replaceResultPath": "data/analysis-results/dada-14.json",
        "expectedRemainingSequences": [20],
        "selfCheckRounds": 400,
        "timeoutSeconds": 1800,
        "requestedAt": timestamp,
        "scope": "sequence-14-only",
        "workflowOwner": "dada-sequence-14-resolution.yml",
    }
    write_json(MANIFEST_PATH, manifest)


if __name__ == "__main__":
    exit_code = resolver.main()
    if exit_code == 0 and "--apply" in sys.argv:
        finalize_staging()
    raise SystemExit(exit_code)
