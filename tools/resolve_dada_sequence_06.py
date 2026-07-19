#!/usr/bin/env python3
"""Resolve and verify 达达猪 sequence 06 using Bilibili public metadata only.

This phase never downloads media. It queries public JSON metadata, verifies the
creator, sequence number, topic and expected duration, then writes a structured
resolution record for a later catalog-update phase.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data/dada-ac-shadows-catalog.json"
STATUS_PATH = ROOT / "data/batch-analysis/dada-author-catalog-status.json"
OUTPUT_PATH = ROOT / "data/analysis-jobs/dada-sequence-06-resolution.json"

EXPECTED_AUTHOR = "不再犹豫的达达猪"
EXPECTED_SEQUENCE = 6
EXPECTED_TOPIC = "秘道试炼"
EXPECTED_DURATION_SECONDS = 107
DURATION_TOLERANCE_SECONDS = 8
SEED_BVIDS = ["BV1jUwMzzEBK", "BV1vrXsYiE9W", "BV19EXYYWEdv"]
BVID_RE = re.compile(r"BV[0-9A-Za-z]+")
SEQUENCE_RE = re.compile(r"(?:攻略[】〗\s]*)?0?(\d{1,2})(?:\s|[^0-9])")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
    "Accept": "application/json,text/plain,*/*",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def request_json(url: str, attempts: int = 3) -> dict[str, Any]:
    errors: list[str] = []
    for attempt in range(1, attempts + 1):
        try:
            request = Request(url, headers=HEADERS)
            with urlopen(request, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("code") not in (0, None):
                raise RuntimeError(f"Bilibili API code {payload.get('code')}: {payload.get('message')}")
            return payload
        except Exception as exc:  # network/API failures are recorded in output
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
            if attempt < attempts:
                time.sleep(attempt * 2)
    raise RuntimeError("; ".join(errors))


def sequence_from_title(title: str) -> int | None:
    match = SEQUENCE_RE.search(str(title or ""))
    return int(match.group(1)) if match else None


def duration_seconds(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
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


def normalize_episode(raw: dict[str, Any], source: str, author: str | None = None) -> dict[str, Any]:
    arc = raw.get("arc") if isinstance(raw.get("arc"), dict) else {}
    title = str(raw.get("title") or arc.get("title") or "")
    bvid = str(raw.get("bvid") or arc.get("bvid") or "")
    duration = duration_seconds(raw.get("duration") or arc.get("duration"))
    return {
        "source": source,
        "author": author,
        "title": title,
        "sequence": sequence_from_title(title),
        "bvid": bvid if BVID_RE.fullmatch(bvid) else None,
        "url": f"https://www.bilibili.com/video/{bvid}/" if BVID_RE.fullmatch(bvid) else None,
        "durationSeconds": duration,
    }


def episodes_from_view(seed_bvid: str) -> tuple[str | None, list[dict[str, Any]]]:
    query = urlencode({"bvid": seed_bvid})
    payload = request_json(f"https://api.bilibili.com/x/web-interface/view?{query}")
    data = payload.get("data") or {}
    owner = data.get("owner") or {}
    author = str(owner.get("name") or "") or None
    episodes: list[dict[str, Any]] = []

    ugc_season = data.get("ugc_season") or {}
    for section in ugc_season.get("sections") or []:
        for episode in section.get("episodes") or []:
            episodes.append(normalize_episode(episode, f"view:{seed_bvid}:ugc_season", author))

    # Some API responses expose a redirect/season archive without ugc_season.
    if not episodes:
        episodes.append(normalize_episode(data, f"view:{seed_bvid}:single", author))
    return author, episodes


def episodes_from_search() -> list[dict[str, Any]]:
    keyword = "刺客信条影 新手攻略 06 秘道试炼"
    query = urlencode({"search_type": "video", "keyword": keyword, "page": 1})
    payload = request_json(f"https://api.bilibili.com/x/web-interface/search/type?{query}")
    results = ((payload.get("data") or {}).get("result") or [])
    episodes: list[dict[str, Any]] = []
    for item in results:
        author = re.sub(r"<[^>]+>", "", str(item.get("author") or "")) or None
        title = re.sub(r"<[^>]+>", "", str(item.get("title") or ""))
        bvid = str(item.get("bvid") or "")
        episodes.append({
            "source": "search",
            "author": author,
            "title": title,
            "sequence": sequence_from_title(title),
            "bvid": bvid if BVID_RE.fullmatch(bvid) else None,
            "url": f"https://www.bilibili.com/video/{bvid}/" if BVID_RE.fullmatch(bvid) else None,
            "durationSeconds": duration_seconds(item.get("duration")),
        })
    return episodes


def score_candidate(candidate: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    checks: list[str] = []
    title = candidate.get("title") or ""
    author = candidate.get("author")
    duration = candidate.get("durationSeconds")

    if author == EXPECTED_AUTHOR:
        score += 50
        checks.append("author_exact")
    if candidate.get("sequence") == EXPECTED_SEQUENCE:
        score += 50
        checks.append("sequence_exact")
    if EXPECTED_TOPIC in title:
        score += 50
        checks.append("topic_exact")
    if duration is not None and abs(duration - EXPECTED_DURATION_SECONDS) <= DURATION_TOLERANCE_SECONDS:
        score += 25
        checks.append("duration_match")
    if candidate.get("bvid"):
        score += 10
        checks.append("bvid_valid")
    return score, checks


def main() -> int:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    catalog_item = next(item for item in catalog.get("items", []) if int(item.get("sequence") or 0) == EXPECTED_SEQUENCE)
    status_item = next(item for item in status.get("items", []) if int(item.get("sequence") or 0) == EXPECTED_SEQUENCE)

    candidates: list[dict[str, Any]] = []
    request_log: list[dict[str, Any]] = []
    verified_seed_authors: list[str] = []

    for seed in SEED_BVIDS:
        try:
            author, episodes = episodes_from_view(seed)
            request_log.append({"source": "view", "seedBvid": seed, "ok": True, "author": author, "episodeCount": len(episodes)})
            if author:
                verified_seed_authors.append(author)
            candidates.extend(episodes)
        except Exception as exc:
            request_log.append({"source": "view", "seedBvid": seed, "ok": False, "error": str(exc)})

    try:
        search_candidates = episodes_from_search()
        candidates.extend(search_candidates)
        request_log.append({"source": "search", "ok": True, "episodeCount": len(search_candidates)})
    except Exception as exc:
        request_log.append({"source": "search", "ok": False, "error": str(exc)})

    deduped: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = candidate.get("bvid") or f"{candidate.get('title')}|{candidate.get('source')}"
        previous = deduped.get(str(key))
        if previous is None or score_candidate(candidate)[0] > score_candidate(previous)[0]:
            deduped[str(key)] = candidate

    ranked: list[dict[str, Any]] = []
    for candidate in deduped.values():
        score, checks = score_candidate(candidate)
        ranked.append({**candidate, "verificationScore": score, "checks": checks})
    ranked.sort(key=lambda item: (-int(item.get("verificationScore") or 0), str(item.get("bvid") or "")))

    winner = ranked[0] if ranked else None
    required_checks = {"author_exact", "sequence_exact", "topic_exact", "duration_match", "bvid_valid"}
    winner_checks = set((winner or {}).get("checks") or [])
    verified = bool(winner and required_checks.issubset(winner_checks))

    old_bvid = status_item.get("lastAttempt", {}).get("resolution", {}).get("bvid") or status_item.get("resolvedBvid")
    if verified and winner.get("bvid") == old_bvid:
        verified = False
        winner = {**winner, "rejectedReason": "resolved BVID is unchanged from the known sequence-05 misassignment"}

    report = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "phase": "dada-sequence-06-exact-metadata-resolution",
        "mediaDownloadPerformed": False,
        "expected": {
            "author": EXPECTED_AUTHOR,
            "sequence": EXPECTED_SEQUENCE,
            "title": catalog_item.get("title"),
            "topic": EXPECTED_TOPIC,
            "durationSeconds": EXPECTED_DURATION_SECONDS,
        },
        "previousAssignment": {
            "url": status_item.get("url"),
            "bvid": old_bvid,
            "resolvedTitle": status_item.get("lastAttempt", {}).get("resolution", {}).get("title"),
        },
        "verified": verified,
        "winner": winner,
        "requestLog": request_log,
        "seedAuthorChecks": {
            "authors": sorted(set(verified_seed_authors)),
            "allExact": bool(verified_seed_authors) and all(author == EXPECTED_AUTHOR for author in verified_seed_authors),
        },
        "candidateCount": len(ranked),
        "topCandidates": ranked[:10],
        "nextAction": "update_catalog_and_prepare_single_video_rescan" if verified else "manual_metadata_review_required",
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verified": verified, "winner": winner, "candidateCount": len(ranked)}, ensure_ascii=False))
    return 0 if verified else 2


if __name__ == "__main__":
    sys.exit(main())
