#!/usr/bin/env python3
"""Resolve one authorized Dada video through Bilibili's public metadata API.

This phase deliberately resolves metadata only. It never downloads media. A separate
reprocess job may consume the approved output after author/title/sequence/duration
checks all pass.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = ROOT / "data/analysis-jobs/dada-quality-reprocess.json"
CATALOG_PATH = ROOT / "data/dada-ac-shadows-catalog.json"
REPORT_DIR = ROOT / "data/batch-analysis"
APPROVED_DIR = ROOT / "data/analysis-jobs"
API_VIEW = "https://api.bilibili.com/x/web-interface/view"
API_SEARCH = "https://api.bilibili.com/x/web-interface/search/type"
DEFAULT_ANCHORS = ["BV1jUwMzzEBK", "BV1vrXsYiE9W"]
EXPECTED_AUTHOR = "不再犹豫的达达猪"
SEQ_RE = re.compile(r"(?:攻略[】〗\s]*)?(\d{1,2})(?:\s|[^0-9])")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_title(value: str) -> str:
    text = str(value or "").lower()
    text = text.replace("【", "〖").replace("】", "〗")
    text = re.sub(r"[\s·:：_\-—]+", "", text)
    text = re.sub(r"[（）()]", "", text)
    return text


def title_sequence(value: str) -> int | None:
    match = SEQ_RE.search(str(value or ""))
    return int(match.group(1)) if match else None


def parse_duration(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        return int(value)
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


def fetch_json(url: str, attempts: int = 4) -> dict[str, Any]:
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
        "Accept": "application/json,text/plain,*/*",
    }
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("code") != 0:
                raise RuntimeError(f"Bilibili API code {payload.get('code')}: {payload.get('message')}")
            return payload
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(attempt * 1.5)
    raise RuntimeError(f"Bilibili metadata request failed after {attempts} attempts: {last_error}")


def view_video(bvid: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({"bvid": bvid})
    return fetch_json(f"{API_VIEW}?{query}").get("data") or {}


def collect_season_episodes(data: dict[str, Any]) -> list[dict[str, Any]]:
    episodes: list[dict[str, Any]] = []
    season = data.get("ugc_season") or {}
    for section in season.get("sections") or []:
        for episode in section.get("episodes") or []:
            arc = episode.get("arc") or {}
            page = episode.get("page") or {}
            episodes.append({
                "bvid": episode.get("bvid") or arc.get("bvid"),
                "title": episode.get("title") or arc.get("title"),
                "duration": arc.get("duration") or page.get("duration") or episode.get("duration"),
                "source": "ugc_season",
            })
    return [item for item in episodes if item.get("bvid") and item.get("title")]


def search_candidates(title: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"search_type": "video", "keyword": title, "page": 1})
    payload = fetch_json(f"{API_SEARCH}?{query}")
    result = (payload.get("data") or {}).get("result") or []
    candidates: list[dict[str, Any]] = []
    for item in result:
        bvid = item.get("bvid")
        candidate_title = re.sub(r"<[^>]+>", "", str(item.get("title") or ""))
        if bvid and candidate_title:
            candidates.append({
                "bvid": bvid,
                "title": candidate_title,
                "duration": item.get("duration"),
                "author": item.get("author"),
                "source": "search",
            })
    return candidates


def expected_item(sequence: int) -> tuple[dict[str, Any], dict[str, Any]]:
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    queue_item = next((item for item in queue.get("items", []) if int(item.get("sequence") or 0) == sequence), None)
    catalog_item = next((item for item in catalog.get("items", []) if int(item.get("sequence") or 0) == sequence), None)
    if not queue_item or not catalog_item:
        raise RuntimeError(f"Sequence {sequence:02d} is not present in both the safe queue and catalog")
    if queue_item.get("safeToDownloadNow") is not False:
        raise RuntimeError("Resolver input must remain download-disabled until metadata verification succeeds")
    return queue_item, catalog_item


def choose_candidate(sequence: int, expected_title: str, candidates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    target = normalize_title(expected_title)
    scored: list[dict[str, Any]] = []
    for candidate in candidates:
        title = str(candidate.get("title") or "")
        seq = title_sequence(title)
        normalized = normalize_title(title)
        exact = normalized == target
        contains_topic = "秘道试炼" in normalized if sequence == 6 else target in normalized or normalized in target
        score = (1000 if exact else 0) + (300 if seq == sequence else 0) + (200 if contains_topic else 0)
        scored.append({**candidate, "detectedSequence": seq, "normalizedExact": exact, "topicMatch": contains_topic, "score": score})
    scored.sort(key=lambda item: item["score"], reverse=True)
    best = scored[0] if scored and scored[0]["score"] >= 500 else None
    return best, scored[:10]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sequence", type=int, default=6)
    parser.add_argument("--anchor-bvid", action="append", default=[])
    parser.add_argument("--require-match", action="store_true")
    args = parser.parse_args()

    sequence = args.sequence
    queue_item, catalog_item = expected_item(sequence)
    expected_title = str(queue_item.get("expectedTitle") or catalog_item.get("title") or "")
    expected_duration = parse_duration(catalog_item.get("duration"))
    anchors = args.anchor_bvid or DEFAULT_ANCHORS
    report_path = REPORT_DIR / f"dada-seq{sequence:02d}-resolution.json"
    approved_path = APPROVED_DIR / f"dada-seq{sequence:02d}-approved-reprocess.json"

    report: dict[str, Any] = {
        "schemaVersion": 1,
        "generatedAt": now_iso(),
        "sequence": sequence,
        "author": EXPECTED_AUTHOR,
        "expectedTitle": expected_title,
        "expectedDurationSeconds": expected_duration,
        "anchors": anchors,
        "status": "unresolved",
        "checks": {},
        "candidate": None,
        "candidateSample": [],
        "errors": [],
        "mediaDownloaded": False,
    }

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for anchor in anchors:
        try:
            anchor_data = view_video(anchor)
            for candidate in collect_season_episodes(anchor_data):
                key = str(candidate.get("bvid"))
                if key not in seen:
                    seen.add(key)
                    candidates.append(candidate)
        except Exception as exc:  # report each anchor and continue to fallback search
            report["errors"].append({"stage": "anchor", "anchor": anchor, "message": str(exc)})

    if not candidates:
        try:
            candidates.extend(search_candidates(expected_title))
        except Exception as exc:
            report["errors"].append({"stage": "search", "message": str(exc)})

    best, sample = choose_candidate(sequence, expected_title, candidates)
    report["candidateSample"] = sample

    if best:
        try:
            verified = view_video(str(best["bvid"]))
            owner_name = str((verified.get("owner") or {}).get("name") or best.get("author") or "")
            verified_title = str(verified.get("title") or best.get("title") or "")
            verified_duration = parse_duration(verified.get("duration") or best.get("duration"))
            checks = {
                "authorExact": owner_name == EXPECTED_AUTHOR,
                "sequenceExact": title_sequence(verified_title) == sequence,
                "titleExact": normalize_title(verified_title) == normalize_title(expected_title),
                "durationWithinTolerance": expected_duration is not None and verified_duration is not None and abs(verified_duration - expected_duration) <= 3,
                "uniqueBvid": str(best["bvid"]) != str(queue_item.get("currentBvid") or ""),
            }
            passed = all(checks.values())
            report.update({
                "status": "verified" if passed else "rejected",
                "checks": checks,
                "candidate": {
                    "bvid": best["bvid"],
                    "url": f"https://www.bilibili.com/video/{best['bvid']}/",
                    "title": verified_title,
                    "author": owner_name,
                    "durationSeconds": verified_duration,
                    "source": best.get("source"),
                },
            })
            if passed:
                approved = {
                    "schemaVersion": 1,
                    "generatedAt": report["generatedAt"],
                    "author": EXPECTED_AUTHOR,
                    "authorizationId": queue_item.get("authorizationId") or "auth-dada-20260718",
                    "sequence": sequence,
                    "externalSourceId": queue_item.get("externalSourceId"),
                    "expectedTitle": expected_title,
                    "verifiedTitle": verified_title,
                    "verifiedBvid": best["bvid"],
                    "verifiedUrl": f"https://www.bilibili.com/video/{best['bvid']}/",
                    "verifiedDurationSeconds": verified_duration,
                    "safeToDownloadNow": True,
                    "action": "reprocess_verified_exact_video",
                    "replaceResultPath": queue_item.get("resultPath"),
                    "verificationChecks": checks,
                }
                APPROVED_DIR.mkdir(parents=True, exist_ok=True)
                approved_path.write_text(json.dumps(approved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            report["errors"].append({"stage": "candidate-verification", "message": str(exc)})

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"sequence": sequence, "status": report["status"], "candidate": report.get("candidate"), "checks": report.get("checks")}, ensure_ascii=False))

    if args.require_match and report["status"] != "verified":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
