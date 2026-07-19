#!/usr/bin/env python3
"""Repair Dada catalog sequence 20 identity and stage verified reprocessing.

Sequence 20 was incorrectly duplicated from canonical sequence 22. This tool
reuses the proven author-collection resolver, requires the real sequence-20
title/topic and duration, updates all identity-bearing catalog/status/queue
fields, and creates the isolated replacement manifest. It does not download
media; media processing remains in the dedicated workflow.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import resolve_dada_sequence06 as resolver

resolver.SEQUENCE = 20
resolver.TOPIC = "锁链晕眩流"
resolver.EXPECTED_DURATION = 135
resolver.DURATION_TOLERANCE = 2
resolver.OLD_WRONG_BVID = "BV1Ub7N6zEKa"
resolver.REPORT_PATH = resolver.ROOT / "data/batch-analysis/dada-sequence-20-resolution.json"

CATALOG_PATH = resolver.ROOT / "data/dada-ac-shadows-catalog.json"
STATUS_PATH = resolver.ROOT / "data/batch-analysis/dada-author-catalog-status.json"
QUEUE_PATH = resolver.ROOT / "data/analysis-jobs/dada-quality-reprocess.json"
RESULT_PATH = resolver.ROOT / "data/analysis-results/dada-20.json"
MANIFEST_PATH = resolver.ROOT / "data/reprocess/dada-seq20.json"
EXPECTED_TITLE = "【刺客信条影 新手攻略】20 锁链晕眩流（奈绪江配装）"
EXPECTED_BVID = "BV1Gqj867Eep"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def repair_identity_and_stage() -> None:
    report = read_json(resolver.REPORT_PATH)
    resolved = report.get("resolved") or {}
    if report.get("status") != "resolved" or report.get("acceptedCount") != 1:
        raise RuntimeError("sequence 20 identity repair requires exactly one accepted candidate")
    if resolved.get("bvid") != EXPECTED_BVID:
        raise RuntimeError(f"unexpected sequence 20 BVID: {resolved.get('bvid')}")
    resolved_title = str((resolved.get("view") or {}).get("title") or resolved.get("title") or "")
    resolved_duration = int((resolved.get("view") or {}).get("durationSeconds") or resolved.get("durationSeconds") or 0)
    if resolver.normalize_title(resolved_title) != resolver.normalize_title(EXPECTED_TITLE):
        raise RuntimeError(f"unexpected sequence 20 title: {resolved_title}")
    if abs(resolved_duration - resolver.EXPECTED_DURATION) > resolver.DURATION_TOLERANCE:
        raise RuntimeError(f"unexpected sequence 20 duration: {resolved_duration}")

    stale_result = read_json(RESULT_PATH)
    replace_job_id = str(stale_result.get("jobId") or "")
    stale_source_bvid = resolver.BVID_RE.search(str((stale_result.get("source") or {}).get("url") or ""))
    if replace_job_id != "dada-20-v1" or not stale_source_bvid or stale_source_bvid.group(0) != resolver.OLD_WRONG_BVID:
        raise RuntimeError("sequence 20 stale-result identity does not match the duplicated sequence 22 result")

    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    exact_url = f"https://www.bilibili.com/video/{EXPECTED_BVID}/"

    catalog = read_json(CATALOG_PATH)
    item = next(entry for entry in catalog["items"] if int(entry.get("sequence") or 0) == 20)
    item.update({
        "title": EXPECTED_TITLE,
        "type": "配装与装备",
        "duration": "02:15",
        "url": exact_url,
        "resolvedBvid": EXPECTED_BVID,
        "resolvedTitle": EXPECTED_TITLE,
        "resolvedAt": timestamp,
        "exactUrlVerified": True,
        "catalogVerified": True,
        "analysisQualityStatus": "stale-wrong-source-pending-reprocess",
        "value": "主要用于配装；本轮已修复此前误与序列22重复的目录身份。",
        "mapUtility": "低",
        "priority": 32,
        "resolutionEvidence": {
            "method": "author-collection-plus-video-view-and-identity-repair",
            "authorMid": resolver.AUTHOR_MID,
            "collectionId": resolver.COLLECTION_ID,
            "durationSeconds": resolved_duration,
            "verifiedAt": timestamp,
            "replacesDuplicateSequence": 22,
        },
    })
    write_json(CATALOG_PATH, catalog)

    status = read_json(STATUS_PATH)
    status_item = next(entry for entry in status["items"] if int(entry.get("sequence") or 0) == 20)
    status_item.update({
        "title": EXPECTED_TITLE,
        "url": exact_url,
        "qualityState": "exact-url-verified-pending-reprocess",
        "resultStale": True,
        "staleReason": (
            "Previous sequence 20 catalog/result duplicated canonical sequence 22 "
            "BV1Ub7N6zEKa instead of the real sequence 20 video"
        ),
        "verifiedResolution": {
            "bvid": EXPECTED_BVID,
            "url": exact_url,
            "title": EXPECTED_TITLE,
            "durationSeconds": resolved_duration,
            "author": resolver.AUTHOR,
            "authorMid": resolver.AUTHOR_MID,
            "collectionId": resolver.COLLECTION_ID,
            "verifiedAt": timestamp,
        },
    })
    write_json(STATUS_PATH, status)

    queue = read_json(QUEUE_PATH)
    queue_item = next(entry for entry in queue["items"] if int(entry.get("sequence") or 0) == 20)
    queue_item.update({
        "expectedTitle": EXPECTED_TITLE,
        "currentUrl": exact_url,
        "currentBvid": EXPECTED_BVID,
        "exactUrl": exact_url,
        "exactBvid": EXPECTED_BVID,
        "resolvedTitle": EXPECTED_TITLE,
        "durationSeconds": resolved_duration,
        "resolutionStatus": "verified",
        "resolutionVerifiedAt": timestamp,
        "action": "reprocess_verified_video",
        "safeToDownloadNow": True,
        "requiresExactUrlVerification": False,
        "identityRepair": {
            "previousDuplicateSequence": 22,
            "previousBvid": resolver.OLD_WRONG_BVID,
            "verifiedAt": timestamp,
        },
    })
    queue["readyForReprocessSequences"] = [20]
    queue["automaticDownloadEnabled"] = False
    write_json(QUEUE_PATH, queue)

    manifest = {
        "schemaVersion": 1,
        "sequence": 20,
        "author": resolver.AUTHOR,
        "authorizationId": "auth-dada-20260718",
        "expectedTitle": EXPECTED_TITLE,
        "verifiedBvid": EXPECTED_BVID,
        "verifiedUrl": exact_url,
        "expectedDurationSeconds": resolver.EXPECTED_DURATION,
        "replaceWrongBvid": resolver.OLD_WRONG_BVID,
        "replaceJobId": replace_job_id,
        "replaceResultPath": "data/analysis-results/dada-20.json",
        "expectedRemainingSequences": [],
        "selfCheckRounds": 400,
        "timeoutSeconds": 1800,
        "requestedAt": timestamp,
        "scope": "sequence-20-only",
        "workflowOwner": "dada-sequence-20-resolution.yml",
        "identityRepair": {
            "previousDuplicateSequence": 22,
            "canonicalSequence22Bvid": resolver.OLD_WRONG_BVID,
        },
    }
    write_json(MANIFEST_PATH, manifest)


if __name__ == "__main__":
    exit_code = resolver.main()
    if exit_code == 0 and "--apply" in sys.argv:
        repair_identity_and_stage()
    raise SystemExit(exit_code)
