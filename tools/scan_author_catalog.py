#!/usr/bin/env python3
"""Resolve, scan, index, and import every authorized video in an author catalog.

The runner processes a bounded number of videos per invocation so GitHub Actions can
chain reliable runs. Original media and frame pixels remain transient.
"""

from __future__ import annotations

import argparse
import difflib
import html
import json
import pathlib
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import quote

from curl_cffi import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: pathlib.Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def clean_markup(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def normalized(value: Any) -> str:
    text = clean_markup(value).lower()
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", text)


def sequence_present(title: str, sequence: int) -> bool:
    plain = clean_markup(title)
    patterns = [
        rf"(?<!\d)0?{sequence}(?!\d)",
        rf"第\s*0?{sequence}\s*[期集篇条]",
    ]
    return any(re.search(pattern, plain, flags=re.IGNORECASE) for pattern in patterns)


def iter_video_results(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, dict):
        if payload.get("bvid") or payload.get("arcurl"):
            yield payload
        for value in payload.values():
            yield from iter_video_results(value)
    elif isinstance(payload, list):
        for value in payload:
            yield from iter_video_results(value)


def request_search(keyword: str) -> list[dict[str, Any]]:
    encoded = quote(keyword)
    endpoints = [
        f"https://api.bilibili.com/x/web-interface/search/type?search_type=video&page=1&page_size=50&keyword={encoded}",
        f"https://api.bilibili.com/x/web-interface/search/all/v2?page=1&page_size=50&keyword={encoded}",
    ]
    errors: list[str] = []
    for endpoint in endpoints:
        try:
            response = requests.get(endpoint, headers=HEADERS, impersonate="chrome", timeout=30)
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != 0:
                errors.append(f"code={payload.get('code')} {payload.get('message')}")
                continue
            candidates = list(iter_video_results(payload.get("data")))
            if candidates:
                return candidates
        except Exception as exc:  # network/API diagnostics are persisted in batch status
            errors.append(repr(exc))
    if errors:
        raise RuntimeError("; ".join(errors)[-2500:])
    return []


def candidate_score(candidate: dict[str, Any], item: dict[str, Any], author: str) -> float:
    title = clean_markup(candidate.get("title"))
    candidate_author = clean_markup(candidate.get("author") or candidate.get("up_name"))
    expected_title = clean_markup(item.get("title"))
    score = 0.0

    author_norm = normalized(author)
    candidate_author_norm = normalized(candidate_author)
    if candidate_author_norm == author_norm:
        score += 120
    elif author_norm and (author_norm in candidate_author_norm or candidate_author_norm in author_norm):
        score += 80

    sequence = int(item.get("sequence") or 0)
    if sequence and sequence_present(title, sequence):
        score += 55
    if "刺客信条影" in normalized(title) or "刺客信条：影" in title:
        score += 25
    if "新手攻略" in title:
        score += 15

    expected_norm = normalized(expected_title)
    title_norm = normalized(title)
    if expected_norm and "待核实" not in expected_title:
        score += difflib.SequenceMatcher(None, expected_norm, title_norm).ratio() * 45
    return score


def resolve_video(item: dict[str, Any], author: str) -> dict[str, Any]:
    existing_url = str(item.get("url") or "")
    match = re.search(r"(BV[0-9A-Za-z]+)", existing_url)
    if match:
        return {
            "url": f"https://www.bilibili.com/video/{match.group(1)}/",
            "bvid": match.group(1),
            "title": item.get("title"),
            "author": author,
            "score": 999,
            "source": "catalog",
        }

    sequence = int(item.get("sequence") or 0)
    queries: list[str] = []
    title = clean_markup(item.get("title"))
    if title and "待核实" not in title:
        queries.append(title)
    queries.extend(
        [
            f"{author} 刺客信条影 新手攻略 {sequence:02d}",
            f"刺客信条影 新手攻略 {sequence:02d}",
            f"刺客信条影 {sequence:02d} {author}",
        ]
    )

    best: tuple[float, dict[str, Any]] | None = None
    diagnostics: list[str] = []
    seen_queries: set[str] = set()
    for query in queries:
        if query in seen_queries:
            continue
        seen_queries.add(query)
        try:
            candidates = request_search(query)
        except Exception as exc:
            diagnostics.append(f"{query}: {exc}")
            continue
        for candidate in candidates:
            bvid = clean_markup(candidate.get("bvid"))
            if not bvid.startswith("BV"):
                arcurl = clean_markup(candidate.get("arcurl"))
                bvid_match = re.search(r"(BV[0-9A-Za-z]+)", arcurl)
                bvid = bvid_match.group(1) if bvid_match else ""
            if not bvid:
                continue
            score = candidate_score(candidate, item, author)
            if best is None or score > best[0]:
                best = (score, candidate | {"_bvid": bvid, "_query": query})
        if best and best[0] >= 190:
            break

    if not best or best[0] < 150:
        detail = diagnostics[-3:] if diagnostics else ["no sufficiently strong matching result"]
        raise RuntimeError(" | ".join(detail))

    score, candidate = best
    bvid = candidate["_bvid"]
    return {
        "url": f"https://www.bilibili.com/video/{bvid}/",
        "bvid": bvid,
        "title": clean_markup(candidate.get("title")) or item.get("title"),
        "author": clean_markup(candidate.get("author") or candidate.get("up_name")) or author,
        "duration": candidate.get("duration"),
        "score": round(score, 3),
        "source": "bilibili-search-api",
        "query": candidate.get("_query"),
    }


def scan_settings(item: dict[str, Any]) -> tuple[float, int]:
    priority = int(item.get("priority") or 0)
    if priority >= 90:
        return 1.0, 480
    if priority >= 60:
        return 1.5, 360
    return 2.0, 240


def build_job(item: dict[str, Any], resolved: dict[str, Any], authorization_id: str) -> tuple[pathlib.Path, pathlib.Path]:
    sequence = int(item["sequence"])
    interval, max_samples = scan_settings(item)
    job_path = ROOT / f"data/analysis-jobs/dada-{sequence:02d}.json"
    result_path = ROOT / f"data/analysis-results/dada-{sequence:02d}.json"
    job = {
        "id": f"dada-{sequence:02d}-v1",
        "externalSourceId": item["id"],
        "authorizationId": authorization_id,
        "author": item["author"],
        "platform": item.get("platform", "哔哩哔哩"),
        "title": resolved.get("title") or item["title"],
        "url": resolved["url"],
        "intervalSeconds": interval,
        "maxSamples": max_samples,
        "minimumSharpness": 18,
        "duplicateHashDistance": 0.11,
        "duplicateColorDistance": 0.055,
        "output": result_path.relative_to(ROOT).as_posix(),
        "retention": {
            "originalVideo": False,
            "framePixels": False,
            "numericDescriptorsOnly": True,
        },
        "batch": {
            "catalog": "data/dada-ac-shadows-catalog.json",
            "sequence": sequence,
            "resolvedBvid": resolved.get("bvid"),
        },
    }
    write_json(job_path, job)
    return job_path, result_path


def run_command(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def index_by_source(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get("externalSourceId")): entry
        for entry in index.get("items", [])
        if entry.get("externalSourceId")
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    args = parser.parse_args()

    manifest_path = (ROOT / args.manifest).resolve()
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError("batch manifest must be a JSON object")

    catalog_path = ROOT / manifest.get("catalog", "data/dada-ac-shadows-catalog.json")
    status_path = ROOT / manifest.get("statusOutput", "data/batch-analysis/dada-author-catalog-status.json")
    index_path = ROOT / "data/analysis-index.json"
    catalog = load_json(catalog_path)
    index = load_json(index_path, {"version": "0.9.1.4", "items": []})
    previous_status = load_json(status_path, {"items": []}) or {"items": []}

    if not isinstance(catalog, dict) or not isinstance(catalog.get("items"), list):
        raise ValueError("catalog is missing items")

    author = str(catalog.get("author") or manifest.get("author") or "")
    authorization_id = str(catalog.get("authorizationId") or manifest.get("authorizationId") or "")
    if not author or not authorization_id:
        raise ValueError("author and authorizationId are required")

    imported_before = index_by_source(index)
    previous_items = {
        str(entry.get("externalSourceId")): entry
        for entry in previous_status.get("items", [])
        if entry.get("externalSourceId")
    }

    recommended = [int(value) for value in catalog.get("recommendedScanOrder", [])]
    order_rank = {sequence: rank for rank, sequence in enumerate(recommended)}

    def attempts_for(item: dict[str, Any]) -> int:
        return int(previous_items.get(str(item.get("id")), {}).get("attemptCount", 0))

    pending = [
        item for item in catalog["items"]
        if imported_before.get(str(item.get("id")), {}).get("status") != "imported"
    ]
    pending.sort(
        key=lambda item: (
            attempts_for(item),
            order_rank.get(int(item.get("sequence") or 0), 1000 + int(item.get("sequence") or 0)),
            -int(item.get("priority") or 0),
        )
    )

    max_items = max(1, int(manifest.get("maxItemsPerRun", 6)))
    timeout_seconds = max(300, int(manifest.get("perItemTimeoutSeconds", 1500)))
    delay_seconds = max(0.0, float(manifest.get("delayBetweenItemsSeconds", 3)))
    selected = pending[:max_items]

    run_events: dict[str, dict[str, Any]] = {}
    newly_imported = 0
    attempted = 0

    for item in selected:
        external_id = str(item["id"])
        attempted += 1
        event: dict[str, Any] = {
            "externalSourceId": external_id,
            "sequence": item.get("sequence"),
            "startedAt": utc_now(),
        }
        try:
            resolved = resolve_video(item, author)
            event["resolution"] = resolved
            item["url"] = resolved["url"]
            item["exactUrlVerified"] = True
            item["resolvedBvid"] = resolved.get("bvid")
            item["resolvedAt"] = utc_now()
            if resolved.get("title"):
                item["resolvedTitle"] = resolved["title"]
                if "待核实" in str(item.get("title") or ""):
                    item["title"] = resolved["title"]
                    item["catalogVerified"] = True
            if resolved.get("duration") and not item.get("duration"):
                item["duration"] = resolved["duration"]

            job_path, result_path = build_job(item, resolved, authorization_id)
            process = run_command(
                [sys.executable, "tools/analyze_authorized_video_v4.py", job_path.relative_to(ROOT).as_posix()],
                timeout_seconds,
            )
            event["analyzerReturnCode"] = process.returncode
            event["analyzerOutput"] = (process.stdout + "\n" + process.stderr)[-3000:]
            if not result_path.exists():
                raise RuntimeError("analyzer did not write a result file")

            result = load_json(result_path)
            event["analysisStatus"] = result.get("status")
            update_process = run_command(
                [sys.executable, "tools/update_analysis_index.py", result_path.relative_to(ROOT).as_posix()],
                120,
            )
            event["indexReturnCode"] = update_process.returncode
            if update_process.returncode != 0:
                raise RuntimeError((update_process.stdout + "\n" + update_process.stderr)[-2500:])

            item["analysisStatus"] = "imported" if result.get("status") == "analyzed" else "failed"
            item["analysisResultPath"] = result_path.relative_to(ROOT).as_posix()
            item["analysisUpdatedAt"] = utc_now()
            if result.get("status") == "analyzed":
                newly_imported += 1
                event["completed"] = True
            else:
                event["completed"] = False
                event["error"] = result.get("error")
        except subprocess.TimeoutExpired as exc:
            event["completed"] = False
            event["error"] = f"timeout after {exc.timeout} seconds"
            item["analysisStatus"] = "failed"
            item["analysisUpdatedAt"] = utc_now()
        except Exception as exc:
            event["completed"] = False
            event["error"] = repr(exc)[-3000:]
            item["analysisStatus"] = "unresolved" if "resolve" in repr(exc).lower() or not item.get("exactUrlVerified") else "failed"
            item["analysisUpdatedAt"] = utc_now()
        event["finishedAt"] = utc_now()
        run_events[external_id] = event
        write_json(catalog_path, catalog)
        if delay_seconds:
            time.sleep(delay_seconds)

    index = load_json(index_path, index)
    indexed = index_by_source(index)
    status_items: list[dict[str, Any]] = []
    imported_count = 0
    failed_count = 0
    unresolved_count = 0

    for item in sorted(catalog["items"], key=lambda value: int(value.get("sequence") or 0)):
        external_id = str(item["id"])
        prior = previous_items.get(external_id, {})
        event = run_events.get(external_id)
        index_entry = indexed.get(external_id)
        if index_entry and index_entry.get("status") == "imported":
            state = "imported"
            imported_count += 1
        elif item.get("analysisStatus") == "unresolved":
            state = "unresolved"
            unresolved_count += 1
        elif index_entry and index_entry.get("status") == "failed":
            state = "failed"
            failed_count += 1
        elif item.get("analysisStatus") == "failed":
            state = "failed"
            failed_count += 1
        else:
            state = "pending"

        attempt_count = int(prior.get("attemptCount", 0)) + (1 if event else 0)
        record = {
            "externalSourceId": external_id,
            "sequence": item.get("sequence"),
            "title": item.get("title"),
            "url": item.get("url"),
            "state": state,
            "attemptCount": attempt_count,
            "resultPath": index_entry.get("resultPath") if index_entry else item.get("analysisResultPath"),
        }
        if event:
            record["lastAttempt"] = event
        elif prior.get("lastAttempt"):
            record["lastAttempt"] = prior["lastAttempt"]
        status_items.append(record)

    total = len(catalog["items"])
    remaining = total - imported_count
    status = {
        "schemaVersion": 1,
        "batchId": manifest.get("id", "dada-author-catalog-v1"),
        "author": author,
        "authorizationId": authorization_id,
        "updatedAt": utc_now(),
        "complete": remaining == 0,
        "summary": {
            "total": total,
            "imported": imported_count,
            "failed": failed_count,
            "unresolved": unresolved_count,
            "remaining": remaining,
            "attemptedThisRun": attempted,
            "newlyImportedThisRun": newly_imported,
        },
        "items": status_items,
        "privacy": "Original videos and frame pixels are deleted after each transient analysis.",
    }
    write_json(status_path, status)

    catalog.setdefault("catalogStatus", {})["analysisImported"] = imported_count
    catalog["catalogStatus"]["analysisRemaining"] = remaining
    catalog["catalogStatus"]["analysisComplete"] = remaining == 0
    catalog["catalogStatus"]["analysisUpdatedAt"] = status["updatedAt"]
    write_json(catalog_path, catalog)

    print(json.dumps(status["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
