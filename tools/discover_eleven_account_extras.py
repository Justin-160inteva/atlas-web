#!/usr/bin/env python3
"""Find additional authorized AC Shadows videos without mutating the scan catalog.

The audit enumerates the authorized Bilibili account through public metadata APIs,
yt-dlp flat-playlist metadata, and exact-author search fallback. It compares matched
video containers by BVID against the existing catalog and writes a report only.
No video media or frame pixels are downloaded.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from discover_bilibili_author_catalog import (
    clean,
    discover_search,
    discover_space_api,
    discover_ytdlp,
    norm,
    seed_info,
)

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    args = parser.parse_args()

    manifest_path = (ROOT / args.manifest).resolve()
    manifest = load(manifest_path, {})
    author = clean(manifest["author"])
    needles = [clean(value) for value in manifest.get("titleMustContainAny", []) if clean(value)]
    if not needles:
        needles = ["刺客信条影", "刺客信条：影", "AC Shadows", "Assassin's Creed Shadows"]

    catalog_path = ROOT / manifest.get("existingCatalog", "data/eleven-game-world-ac-shadows-catalog.json")
    report_path = ROOT / manifest.get("reportOutput", "data/batch-analysis/eleven-account-extra-video-report.json")
    catalog = load(catalog_path, {"items": []})
    diagnostics: list[str] = []

    seed = seed_info(clean(manifest["seedBvid"]))
    if norm(seed["name"]) != norm(author):
        raise RuntimeError(f"seed owner mismatch: {seed['name']} != {author}")

    api_videos, api_complete = discover_space_api(seed["mid"], seed["name"], diagnostics)
    ytdlp_videos, ytdlp_complete = discover_ytdlp(seed["mid"], seed["name"], diagnostics)
    search_videos = discover_search(seed["name"], needles, diagnostics)
    account = {**api_videos, **ytdlp_videos, **search_videos}
    account[seed["bvid"]] = {
        "bvid": seed["bvid"],
        "title": seed["title"],
        "author": seed["name"],
        "durationSeconds": seed["durationSeconds"],
        "publishedAtUnix": seed["publishedAtUnix"],
        "url": f"https://www.bilibili.com/video/{seed['bvid']}/",
    }

    matched = [
        video for video in account.values()
        if any(norm(needle) in norm(video.get("title")) for needle in needles)
    ]
    matched.sort(key=lambda item: (int(item.get("publishedAtUnix") or 0), str(item.get("bvid") or "")))

    existing_bvids = {str(item.get("bvid") or "") for item in catalog.get("items", []) if item.get("bvid")}
    existing_bvids.add(str(catalog.get("seedVideo", {}).get("bvid") or ""))
    candidates = []
    for video in matched:
        bvid = str(video.get("bvid") or "")
        if not bvid or bvid in existing_bvids:
            continue
        candidates.append({
            "bvid": bvid,
            "title": video.get("title"),
            "author": author,
            "durationSeconds": int(video.get("durationSeconds") or 0),
            "publishedAtUnix": int(video.get("publishedAtUnix") or 0),
            "url": video.get("url") or f"https://www.bilibili.com/video/{bvid}/",
            "authorizationId": manifest["authorizationId"],
            "matchReason": "exact_author_and_title_keyword",
            "requiresMetadataVerificationBeforeQueueing": True,
        })

    enumeration_complete = bool(api_complete or ytdlp_complete)
    generated_at = now_iso()
    if enumeration_complete and not candidates:
        conclusion = "账号完整枚举未发现当前目录之外的《刺客信条：影》视频容器。"
    elif candidates:
        conclusion = f"发现{len(candidates)}个当前目录之外的候选视频，需完成标题、URL和内容元数据复核后再入队。"
    else:
        conclusion = "账号枚举仍为部分结果；当前未发现新增候选，但不能据此断言账号没有其他相关视频。"

    report = {
        "schemaVersion": 1,
        "release": "0.9.4.8",
        "generatedAt": generated_at,
        "author": author,
        "authorMid": seed["mid"],
        "authorizationId": manifest["authorizationId"],
        "seedBvid": seed["bvid"],
        "titleMustContainAny": needles,
        "accountEnumerationComplete": enumeration_complete,
        "accountVideosDiscovered": len(account),
        "matchedGameContainers": len(matched),
        "existingCatalogContainers": len(existing_bvids - {""}),
        "newCandidateCount": len(candidates),
        "newCandidates": candidates,
        "conclusionZhCN": conclusion,
        "diagnostics": diagnostics[-30:],
        "invariants": {
            "reportOnly": True,
            "existingCatalogNotModified": True,
            "productionQueueNotModified": True,
            "noMediaDownloaded": True,
            "allCandidatesExactAuthor": all(norm(item["author"]) == norm(author) for item in candidates),
            "allCandidatesOutsideExistingCatalog": all(item["bvid"] not in existing_bvids for item in candidates),
            "allCandidatesMatchTitleKeyword": all(any(norm(needle) in norm(item["title"]) for needle in needles) for item in candidates),
        },
        "privacy": "Metadata-only account audit. No video media, cookies, frame pixels, or private paths are stored."
    }
    write(report_path, report)
    print(json.dumps({
        "enumerationComplete": enumeration_complete,
        "accountVideos": len(account),
        "matchedContainers": len(matched),
        "newCandidates": len(candidates),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
