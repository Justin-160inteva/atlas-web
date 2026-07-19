#!/usr/bin/env python3
"""Reprocess exactly one Dada catalog item whose source has already been verified.

The tool refuses unresolved URLs, enforces the author-level authorization and
retention policy, validates the replacement result, and updates catalog/status
metadata. Original media remains transient and is removed by the workflow.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data/dada-ac-shadows-catalog.json"
QUEUE_PATH = ROOT / "data/analysis-jobs/dada-quality-reprocess.json"
STATUS_PATH = ROOT / "data/batch-analysis/dada-author-catalog-status.json"
INDEX_PATH = ROOT / "data/analysis-index.json"
EXPECTED_AUTHOR = "不再犹豫的达达猪"
EXPECTED_AUTHORIZATION = "auth-dada-20260718"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def normalized(value: Any) -> str:
    text = str(value or "").lower().replace("【", "〖").replace("】", "〗")
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", text)


def bvid_from(value: Any) -> str | None:
    match = re.search(r"(BV[0-9A-Za-z]+)", str(value or ""))
    return match.group(1) if match else None


def duration_seconds(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        return int(round(float(value)))
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parts = [int(part) for part in text.split(":")]
    except ValueError:
        return None
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return None


def find_sequence(items: list[dict[str, Any]], sequence: int) -> dict[str, Any]:
    item = next((entry for entry in items if int(entry.get("sequence") or 0) == sequence), None)
    if not item:
        raise RuntimeError(f"sequence {sequence:02d} is missing")
    return item


def validate_inputs(manifest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str, int]:
    sequence = int(manifest.get("sequence") or 0)
    expected_bvid = str(manifest.get("verifiedBvid") or "")
    expected_title = str(manifest.get("expectedTitle") or "")
    expected_duration = int(manifest.get("expectedDurationSeconds") or 0)
    if sequence <= 0 or not expected_bvid.startswith("BV") or not expected_title or expected_duration <= 0:
        raise RuntimeError("manifest lacks sequence, verifiedBvid, expectedTitle, or expectedDurationSeconds")
    if manifest.get("author") != EXPECTED_AUTHOR or manifest.get("authorizationId") != EXPECTED_AUTHORIZATION:
        raise RuntimeError("manifest author or authorization does not match the registered author-level permission")

    catalog = load(CATALOG_PATH)
    queue = load(QUEUE_PATH)
    status = load(STATUS_PATH)
    catalog_item = find_sequence(catalog.get("items", []), sequence)
    queue_item = find_sequence(queue.get("items", []), sequence)
    status_item = find_sequence(status.get("items", []), sequence)

    checks = {
        "catalogAuthor": catalog_item.get("author") == EXPECTED_AUTHOR,
        "catalogAuthorization": catalog_item.get("authorizationId") == EXPECTED_AUTHORIZATION,
        "catalogExactUrlVerified": catalog_item.get("exactUrlVerified") is True,
        "catalogBvid": str(catalog_item.get("resolvedBvid") or bvid_from(catalog_item.get("url")) or "") == expected_bvid,
        "catalogTitle": normalized(catalog_item.get("title")) == normalized(expected_title),
        "catalogDuration": duration_seconds(catalog_item.get("duration")) == expected_duration,
        "queueApproved": queue_item.get("safeToDownloadNow") is True,
        "queueExactBvid": str(queue_item.get("exactBvid") or "") == expected_bvid,
        "queueResolutionVerified": queue_item.get("resolutionStatus") == "verified",
        "oldResultMarkedStale": catalog_item.get("analysisQualityStatus") == "stale-wrong-source-pending-reprocess",
        "statusVerifiedBvid": str((status_item.get("verifiedResolution") or {}).get("bvid") or "") == expected_bvid,
    }
    if not all(checks.values()):
        raise RuntimeError("verified-source preconditions failed: " + json.dumps(checks, ensure_ascii=False))
    return catalog, queue, status, expected_bvid, expected_duration


def build_job(manifest: dict[str, Any], catalog_item: dict[str, Any], expected_bvid: str) -> pathlib.Path:
    sequence = int(manifest["sequence"])
    result_path = f"data/analysis-results/dada-{sequence:02d}.json"
    job_path = ROOT / f"data/analysis-jobs/dada-{sequence:02d}.json"
    job = {
        "id": f"dada-{sequence:02d}-v2-correct-source",
        "externalSourceId": catalog_item["id"],
        "authorizationId": EXPECTED_AUTHORIZATION,
        "author": EXPECTED_AUTHOR,
        "platform": catalog_item.get("platform", "哔哩哔哩"),
        "title": manifest["expectedTitle"],
        "url": f"https://www.bilibili.com/video/{expected_bvid}/",
        "intervalSeconds": 1.0,
        "maxSamples": 480,
        "minimumSharpness": 18,
        "duplicateHashDistance": 0.11,
        "duplicateColorDistance": 0.055,
        "output": result_path,
        "retention": {
            "originalVideo": False,
            "framePixels": False,
            "numericDescriptorsOnly": True,
        },
        "batch": {
            "catalog": "data/dada-ac-shadows-catalog.json",
            "sequence": sequence,
            "resolvedBvid": expected_bvid,
            "reason": "replace-stale-wrong-source",
        },
    }
    write(job_path, job)
    return job_path


def run(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def validate_result(result: dict[str, Any], manifest: dict[str, Any], expected_bvid: str, expected_duration: int) -> dict[str, bool]:
    source = result.get("source") or {}
    media = result.get("media") or {}
    checks = {
        "statusAnalyzed": result.get("status") == "analyzed",
        "authorExact": source.get("author") == EXPECTED_AUTHOR,
        "titleExact": normalized(source.get("title")) == normalized(manifest["expectedTitle"]),
        "bvidExact": bvid_from(source.get("url")) == expected_bvid,
        "durationWithinTolerance": abs(float(media.get("durationSeconds") or 0) - expected_duration) <= 3,
        "originalVideoDeleted": media.get("videoRetained") is False,
        "framePixelsDeleted": media.get("framePixelsRetained") is False,
    }
    if not all(checks.values()):
        raise RuntimeError("replacement result validation failed: " + json.dumps(checks, ensure_ascii=False))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    manifest_path = (ROOT / args.manifest).resolve()
    manifest = load(manifest_path)
    catalog, queue, status, expected_bvid, expected_duration = validate_inputs(manifest)
    sequence = int(manifest["sequence"])
    catalog_item = find_sequence(catalog["items"], sequence)

    if args.validate_only:
        print(json.dumps({"sequence": sequence, "status": "ready", "bvid": expected_bvid}, ensure_ascii=False))
        return 0

    started = now()
    job_path = build_job(manifest, catalog_item, expected_bvid)
    result_path = ROOT / f"data/analysis-results/dada-{sequence:02d}.json"
    analysis = run([sys.executable, "tools/analyze_authorized_video_v4.py", job_path.relative_to(ROOT).as_posix()], int(manifest.get("timeoutSeconds") or 1800))
    if analysis.returncode != 0 or not result_path.exists():
        raise RuntimeError((analysis.stdout + "\n" + analysis.stderr)[-5000:] or "analyzer failed without output")

    result = load(result_path)
    result_checks = validate_result(result, manifest, expected_bvid, expected_duration)
    index_update = run([sys.executable, "tools/update_analysis_index.py", result_path.relative_to(ROOT).as_posix()], 180)
    if index_update.returncode != 0:
        raise RuntimeError((index_update.stdout + "\n" + index_update.stderr)[-4000:])

    finished = now()
    catalog_item["analysisStatus"] = "imported"
    catalog_item["analysisUpdatedAt"] = finished
    catalog_item["analysisQualityStatus"] = "verified-correct-source"
    catalog_item["analysisVerification"] = {
        "verifiedBvid": expected_bvid,
        "verifiedAt": finished,
        "resultChecks": result_checks,
        "replacesJobId": f"dada-{sequence:02d}-v1",
        "replacementJobId": result.get("jobId"),
    }

    queue_item = find_sequence(queue["items"], sequence)
    queue_item["action"] = "reprocess_complete"
    queue_item["safeToDownloadNow"] = False
    queue_item["reprocessStatus"] = "complete"
    queue_item["reprocessedAt"] = finished
    queue_item["verifiedResultPath"] = result_path.relative_to(ROOT).as_posix()
    queue_item["resultChecks"] = result_checks

    status_item = find_sequence(status["items"], sequence)
    status_item["title"] = manifest["expectedTitle"]
    status_item["url"] = f"https://www.bilibili.com/video/{expected_bvid}/"
    status_item["state"] = "imported"
    status_item["attemptCount"] = int(status_item.get("attemptCount") or 0) + 1
    status_item["resultPath"] = result_path.relative_to(ROOT).as_posix()
    status_item["qualityState"] = "verified-correct-source"
    status_item["resultStale"] = False
    status_item.pop("staleReason", None)
    status_item["lastAttempt"] = {
        "externalSourceId": catalog_item["id"],
        "sequence": sequence,
        "startedAt": started,
        "resolution": {
            "url": f"https://www.bilibili.com/video/{expected_bvid}/",
            "bvid": expected_bvid,
            "title": result["source"]["title"],
            "author": result["source"]["author"],
            "score": 1000,
            "source": "verified-catalog-source",
        },
        "analyzerReturnCode": analysis.returncode,
        "analyzerOutput": (analysis.stdout + "\n" + analysis.stderr)[-3000:],
        "analysisStatus": result.get("status"),
        "indexReturnCode": index_update.returncode,
        "completed": True,
        "resultChecks": result_checks,
        "finishedAt": finished,
    }
    status["updatedAt"] = finished
    status["complete"] = True
    status["summary"].update({
        "total": 23,
        "imported": 23,
        "failed": 0,
        "unresolved": 0,
        "remaining": 0,
        "attemptedThisRun": 1,
        "newlyImportedThisRun": 1,
    })

    catalog.setdefault("catalogStatus", {})["analysisUpdatedAt"] = finished
    catalog["catalogStatus"]["analysisImported"] = 23
    catalog["catalogStatus"]["analysisRemaining"] = 0
    catalog["catalogStatus"]["analysisComplete"] = True

    report = {
        "schemaVersion": 1,
        "sequence": sequence,
        "status": "complete",
        "startedAt": started,
        "finishedAt": finished,
        "verifiedBvid": expected_bvid,
        "resultPath": result_path.relative_to(ROOT).as_posix(),
        "resultChecks": result_checks,
        "oldWrongBvid": manifest.get("replaceWrongBvid"),
        "mediaRetention": "original video and frame pixels deleted after transient analysis",
    }

    write(CATALOG_PATH, catalog)
    write(QUEUE_PATH, queue)
    write(STATUS_PATH, status)
    write(ROOT / f"data/batch-analysis/dada-seq{sequence:02d}-reprocess-status.json", report)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
