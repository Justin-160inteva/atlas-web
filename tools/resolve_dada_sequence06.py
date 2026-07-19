#!/usr/bin/env python3
"""Resolve 达达猪 sequence 06 without downloading media.

The resolver accepts a candidate only when collection membership, title topic,
number, duration and independent video-owner metadata all agree.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data/dada-ac-shadows-catalog.json"
STATUS_PATH = ROOT / "data/batch-analysis/dada-author-catalog-status.json"
QUEUE_PATH = ROOT / "data/analysis-jobs/dada-quality-reprocess.json"
REPORT_PATH = ROOT / "data/batch-analysis/dada-sequence-06-resolution.json"

AUTHOR = "不再犹豫的达达猪"
AUTHOR_MID = 3493082095946091
COLLECTION_ID = 5059842
SEQUENCE = 6
TOPIC = "秘道试炼"
EXPECTED_DURATION = 107
DURATION_TOLERANCE = 2
OLD_WRONG_BVID = "BV1eeZ7YdEDs"
BVID_RE = re.compile(r"BV[0-9A-Za-z]+")
SEQ_RE = re.compile(r"(?:攻略[】〗\s]*)?0?(\d{1,2})(?:\s|[^0-9])")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def request_json(url: str, attempts: int = 3) -> dict[str, Any]:
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
        "Referer": f"https://space.bilibili.com/{AUTHOR_MID}/channel/collectiondetail?sid={COLLECTION_ID}",
        "Origin": "https://www.bilibili.com",
    }
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("code") not in (None, 0):
                raise RuntimeError(f"Bilibili API code={payload.get('code')} message={payload.get('message')}")
            return payload
        except Exception as exc:  # network/API failures are reported, never guessed around
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"request failed for {url}: {last_error}")


def parse_duration(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        return int(round(value))
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    parts = text.split(":")
    if all(part.isdigit() for part in parts):
        total = 0
        for part in parts:
            total = total * 60 + int(part)
        return total
    return None


def sequence_from_title(title: str) -> int | None:
    match = SEQ_RE.search(str(title or ""))
    return int(match.group(1)) if match else None


def normalize_title(title: str) -> str:
    return re.sub(r"[\s【】〖〗（）()·:：_\-]", "", str(title or "").lower())


def archives_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") or {}
    possible = [
        data.get("archives"),
        (data.get("page") or {}).get("archives") if isinstance(data.get("page"), dict) else None,
        (data.get("items") or {}).get("archives") if isinstance(data.get("items"), dict) else None,
    ]
    for value in possible:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def fetch_collection_archives() -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    params = urllib.parse.urlencode({
        "mid": AUTHOR_MID,
        "season_id": COLLECTION_ID,
        "sort_reverse": "true",
        "page_num": 1,
        "page_size": 100,
    })
    endpoints = [
        f"https://api.bilibili.com/x/polymer/web-space/seasons_archives_list?{params}",
        f"https://api.bilibili.com/x/polymer/space/seasons_archives_list?{params}",
    ]
    attempts: list[dict[str, str]] = []
    for endpoint in endpoints:
        try:
            payload = request_json(endpoint)
            archives = archives_from_payload(payload)
            attempts.append({"endpoint": endpoint.split("?")[0], "status": "ok", "count": str(len(archives))})
            if archives:
                return archives, attempts
        except Exception as exc:
            attempts.append({"endpoint": endpoint.split("?")[0], "status": "error", "detail": str(exc)})
    return [], attempts


def fetch_search_candidates() -> tuple[list[dict[str, Any]], dict[str, str]]:
    keyword = f"{AUTHOR} 刺客信条影 06 {TOPIC}"
    params = urllib.parse.urlencode({
        "search_type": "video",
        "keyword": keyword,
        "page": 1,
        "page_size": 50,
    })
    endpoint = f"https://api.bilibili.com/x/web-interface/search/type?{params}"
    try:
        payload = request_json(endpoint)
        result = ((payload.get("data") or {}).get("result") or [])
        return [item for item in result if isinstance(item, dict)], {"endpoint": endpoint.split("?")[0], "status": "ok", "count": str(len(result))}
    except Exception as exc:
        return [], {"endpoint": endpoint.split("?")[0], "status": "error", "detail": str(exc)}


def candidate_bvid(item: dict[str, Any]) -> str | None:
    for value in (item.get("bvid"), item.get("uri"), item.get("arcurl"), item.get("url")):
        match = BVID_RE.search(str(value or ""))
        if match:
            return match.group(0)
    return None


def view_details(bvid: str) -> dict[str, Any]:
    endpoint = "https://api.bilibili.com/x/web-interface/view?" + urllib.parse.urlencode({"bvid": bvid})
    payload = request_json(endpoint)
    return payload.get("data") or {}


def evaluate_candidate(item: dict[str, Any], source: str) -> dict[str, Any] | None:
    bvid = candidate_bvid(item)
    if not bvid:
        return None
    title = str(item.get("title") or item.get("name") or "")
    title = re.sub(r"<[^>]+>", "", title)
    duration = parse_duration(item.get("duration"))
    sequence = sequence_from_title(title)
    topic_match = TOPIC in normalize_title(title)
    sequence_match = sequence == SEQUENCE
    duration_match = duration is not None and abs(duration - EXPECTED_DURATION) <= DURATION_TOLERANCE
    result: dict[str, Any] = {
        "source": source,
        "bvid": bvid,
        "title": title,
        "durationSeconds": duration,
        "sequence": sequence,
        "checks": {
            "topic": topic_match,
            "sequence": sequence_match,
            "duration": duration_match,
            "author": False,
            "authorMid": False,
            "viewTitle": False,
        },
        "accepted": False,
    }
    if not (topic_match and sequence_match and duration_match):
        return result
    try:
        details = view_details(bvid)
        owner = details.get("owner") or {}
        view_title = str(details.get("title") or "")
        view_duration = parse_duration(details.get("duration"))
        result["view"] = {
            "title": view_title,
            "durationSeconds": view_duration,
            "author": owner.get("name"),
            "authorMid": owner.get("mid"),
        }
        result["checks"]["author"] = str(owner.get("name") or "") == AUTHOR
        result["checks"]["authorMid"] = int(owner.get("mid") or 0) == AUTHOR_MID
        result["checks"]["viewTitle"] = (
            TOPIC in normalize_title(view_title)
            and sequence_from_title(view_title) == SEQUENCE
            and view_duration is not None
            and abs(view_duration - EXPECTED_DURATION) <= DURATION_TOLERANCE
        )
        result["accepted"] = all(result["checks"].values())
    except Exception as exc:
        result["viewError"] = str(exc)
    return result


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_sequence(items: list[dict[str, Any]], sequence: int) -> dict[str, Any]:
    for item in items:
        if int(item.get("sequence") or 0) == sequence:
            return item
    raise RuntimeError(f"sequence {sequence} missing")


def apply_resolution(resolved: dict[str, Any], timestamp: str) -> None:
    bvid = resolved["bvid"]
    title = resolved.get("view", {}).get("title") or resolved["title"]
    duration = resolved.get("view", {}).get("durationSeconds") or resolved["durationSeconds"]
    url = f"https://www.bilibili.com/video/{bvid}/"

    catalog = read_json(CATALOG_PATH)
    catalog_item = find_sequence(catalog.get("items", []), SEQUENCE)
    catalog_item.update({
        "url": url,
        "resolvedBvid": bvid,
        "resolvedTitle": title,
        "resolvedAt": timestamp,
        "exactUrlVerified": True,
        "catalogVerified": True,
        "analysisQualityStatus": "stale-wrong-source-pending-reprocess",
        "resolutionEvidence": {
            "method": "author-collection-plus-video-view",
            "authorMid": AUTHOR_MID,
            "collectionId": COLLECTION_ID,
            "durationSeconds": duration,
            "verifiedAt": timestamp,
        },
    })
    write_json(CATALOG_PATH, catalog)

    status = read_json(STATUS_PATH)
    status_item = find_sequence(status.get("items", []), SEQUENCE)
    status_item["url"] = url
    status_item["verifiedResolution"] = {
        "bvid": bvid,
        "url": url,
        "title": title,
        "durationSeconds": duration,
        "author": AUTHOR,
        "authorMid": AUTHOR_MID,
        "collectionId": COLLECTION_ID,
        "verifiedAt": timestamp,
    }
    status_item["qualityState"] = "exact-url-verified-pending-reprocess"
    status_item["resultStale"] = True
    status_item["staleReason"] = f"Previous analysis used {OLD_WRONG_BVID} (sequence 05)"
    write_json(STATUS_PATH, status)

    queue = read_json(QUEUE_PATH)
    queue_item = find_sequence(queue.get("items", []), SEQUENCE)
    queue_item.update({
        "exactUrl": url,
        "exactBvid": bvid,
        "resolvedTitle": title,
        "durationSeconds": duration,
        "resolutionStatus": "verified",
        "resolutionVerifiedAt": timestamp,
        "action": "reprocess_verified_video",
        "safeToDownloadNow": True,
        "requiresExactUrlVerification": False,
    })
    ready = {int(value) for value in queue.get("readyForReprocessSequences", [])}
    ready.add(SEQUENCE)
    queue["readyForReprocessSequences"] = sorted(ready)
    queue["automaticDownloadEnabled"] = False
    write_json(QUEUE_PATH, queue)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--require-resolved", action="store_true")
    args = parser.parse_args()

    timestamp = now_iso()
    archives, collection_attempts = fetch_collection_archives()
    search_items: list[dict[str, Any]] = []
    search_attempt: dict[str, str] | None = None
    if not archives:
        search_items, search_attempt = fetch_search_candidates()

    raw_candidates: list[tuple[dict[str, Any], str]] = [(item, "author-collection") for item in archives]
    raw_candidates.extend((item, "bilibili-search") for item in search_items)
    evaluated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item, source in raw_candidates:
        evaluated_item = evaluate_candidate(item, source)
        if not evaluated_item:
            continue
        key = evaluated_item["bvid"]
        if key in seen:
            continue
        seen.add(key)
        evaluated.append(evaluated_item)

    accepted = [item for item in evaluated if item.get("accepted")]
    status = "resolved" if len(accepted) == 1 else "blocked"
    reason = None
    if not raw_candidates:
        reason = "No collection/search candidates were returned"
    elif not accepted:
        reason = "No candidate passed topic, sequence, duration and author checks"
    elif len(accepted) > 1:
        reason = "More than one candidate passed all checks"

    report: dict[str, Any] = {
        "schemaVersion": 1,
        "generatedAt": timestamp,
        "author": AUTHOR,
        "authorMid": AUTHOR_MID,
        "collectionId": COLLECTION_ID,
        "sequence": SEQUENCE,
        "expected": {"titleTopic": TOPIC, "durationSeconds": EXPECTED_DURATION},
        "status": status,
        "reason": reason,
        "networkAttempts": {"collection": collection_attempts, "search": search_attempt},
        "candidateCount": len(evaluated),
        "acceptedCount": len(accepted),
        "candidates": evaluated,
        "resolved": accepted[0] if len(accepted) == 1 else None,
        "mediaDownloaded": False,
    }
    write_json(REPORT_PATH, report)

    if status == "resolved" and args.apply:
        apply_resolution(accepted[0], timestamp)
        report["applied"] = True
        write_json(REPORT_PATH, report)
    else:
        report["applied"] = False
        write_json(REPORT_PATH, report)

    print(json.dumps({"status": status, "accepted": len(accepted), "candidates": len(evaluated), "applied": report["applied"]}, ensure_ascii=False))
    if args.require_resolved and status != "resolved":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
