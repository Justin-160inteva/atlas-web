#!/usr/bin/env python3
"""Inspect the real identity of Dada catalog sequence 20 without media download.

The current sequence-20 catalog row duplicates sequence 22. This diagnostic
queries the registered author collection and public search, verifies video owner
metadata, and reports all numbered entries around sequences 18-23. It never
changes the catalog or downloads video media.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import resolve_dada_sequence06 as resolver

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data/dada-ac-shadows-catalog.json"
REPORT_PATH = ROOT / "data/batch-analysis/dada-sequence-20-identity.json"
TARGET_SEQUENCE = 20
NEARBY_SEQUENCES = set(range(18, 24))
BVID_RE = re.compile(r"BV[0-9A-Za-z]+")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def bvid_from(item: dict[str, Any]) -> str | None:
    for value in (item.get("bvid"), item.get("uri"), item.get("arcurl"), item.get("url")):
        match = BVID_RE.search(str(value or ""))
        if match:
            return match.group(0)
    return None


def clean_title(value: Any) -> str:
    return re.sub(r"<[^>]+>", "", str(value or "")).strip()


def search_videos(keyword: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    params = urllib.parse.urlencode({
        "search_type": "video",
        "keyword": keyword,
        "page": 1,
        "page_size": 50,
    })
    endpoint = f"https://api.bilibili.com/x/web-interface/search/type?{params}"
    try:
        payload = resolver.request_json(endpoint)
        rows = ((payload.get("data") or {}).get("result") or [])
        return [row for row in rows if isinstance(row, dict)], {
            "keyword": keyword,
            "endpoint": endpoint.split("?")[0],
            "status": "ok",
            "count": len(rows),
        }
    except Exception as exc:
        return [], {
            "keyword": keyword,
            "endpoint": endpoint.split("?")[0],
            "status": "error",
            "detail": str(exc),
        }


def summarize_candidate(item: dict[str, Any], source: str) -> dict[str, Any] | None:
    bvid = bvid_from(item)
    if not bvid:
        return None
    title = clean_title(item.get("title") or item.get("name"))
    sequence = resolver.sequence_from_title(title)
    duration = resolver.parse_duration(item.get("duration"))
    row: dict[str, Any] = {
        "source": source,
        "bvid": bvid,
        "title": title,
        "sequence": sequence,
        "durationSeconds": duration,
        "ownerVerified": False,
        "acceptedForSequence20": False,
    }

    should_verify = sequence in NEARBY_SEQUENCES or "刺客信条影" in resolver.normalize_title(title)
    if not should_verify:
        return row

    try:
        details = resolver.view_details(bvid)
        owner = details.get("owner") or {}
        view_title = clean_title(details.get("title"))
        view_sequence = resolver.sequence_from_title(view_title)
        view_duration = resolver.parse_duration(details.get("duration"))
        author_exact = str(owner.get("name") or "") == resolver.AUTHOR
        author_mid_exact = int(owner.get("mid") or 0) == resolver.AUTHOR_MID
        row["view"] = {
            "title": view_title,
            "sequence": view_sequence,
            "durationSeconds": view_duration,
            "author": owner.get("name"),
            "authorMid": owner.get("mid"),
        }
        row["ownerVerified"] = author_exact and author_mid_exact
        row["acceptedForSequence20"] = (
            row["ownerVerified"]
            and view_sequence == TARGET_SEQUENCE
            and "刺客信条影" in resolver.normalize_title(view_title)
        )
    except Exception as exc:
        row["viewError"] = str(exc)
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-resolved", action="store_true")
    args = parser.parse_args()

    archives, collection_attempts = resolver.fetch_collection_archives()
    searches: list[dict[str, Any]] = []
    search_attempts: list[dict[str, Any]] = []
    for keyword in (
        f"{resolver.AUTHOR} 刺客信条影 20",
        f"{resolver.AUTHOR} 刺客信条影 新手攻略",
    ):
        rows, attempt = search_videos(keyword)
        searches.extend(rows)
        search_attempts.append(attempt)

    raw: list[tuple[dict[str, Any], str]] = [(row, "author-collection") for row in archives]
    raw.extend((row, "bilibili-search") for row in searches)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item, source in raw:
        row = summarize_candidate(item, source)
        if not row or row["bvid"] in seen:
            continue
        seen.add(row["bvid"])
        if row.get("sequence") in NEARBY_SEQUENCES or (row.get("view") or {}).get("sequence") in NEARBY_SEQUENCES:
            candidates.append(row)

    candidates.sort(key=lambda row: ((row.get("view") or {}).get("sequence") or row.get("sequence") or 999, row["bvid"]))
    accepted = [row for row in candidates if row.get("acceptedForSequence20")]

    catalog = read_json(CATALOG_PATH)
    current = next(item for item in catalog["items"] if int(item.get("sequence") or 0) == TARGET_SEQUENCE)
    canonical22 = next(item for item in catalog["items"] if int(item.get("sequence") or 0) == 22)
    status = "resolved" if len(accepted) == 1 else "blocked"
    reason = None
    if not accepted:
        reason = "No author-verified public video with title sequence 20 was found"
    elif len(accepted) > 1:
        reason = "Multiple author-verified sequence-20 candidates were found"

    report = {
        "schemaVersion": 1,
        "generatedAt": now_iso(),
        "author": resolver.AUTHOR,
        "authorMid": resolver.AUTHOR_MID,
        "collectionId": resolver.COLLECTION_ID,
        "targetSequence": TARGET_SEQUENCE,
        "status": status,
        "reason": reason,
        "mediaDownloaded": False,
        "networkAttempts": {
            "collection": collection_attempts,
            "search": search_attempts,
        },
        "currentCatalogIdentity": {
            "title": current.get("title"),
            "bvid": current.get("resolvedBvid") or bvid_from(current),
            "url": current.get("url"),
            "duration": current.get("duration"),
        },
        "canonicalSequence22Identity": {
            "title": canonical22.get("title"),
            "bvid": canonical22.get("resolvedBvid") or bvid_from(canonical22),
            "url": canonical22.get("url"),
            "duration": canonical22.get("duration"),
        },
        "duplicateWithSequence22": (
            (current.get("resolvedBvid") or bvid_from(current))
            == (canonical22.get("resolvedBvid") or bvid_from(canonical22))
        ),
        "candidateCount": len(candidates),
        "acceptedCount": len(accepted),
        "candidates": candidates,
        "resolved": accepted[0] if len(accepted) == 1 else None,
    }
    write_json(REPORT_PATH, report)
    print(json.dumps({
        "status": status,
        "candidateCount": len(candidates),
        "acceptedCount": len(accepted),
        "resolvedBvid": (accepted[0]["bvid"] if len(accepted) == 1 else None),
    }, ensure_ascii=False))
    if args.require_resolved and status != "resolved":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
