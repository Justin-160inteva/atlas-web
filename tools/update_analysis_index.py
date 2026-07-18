#!/usr/bin/env python3
"""Update Atlas analysis-index.json from one machine-readable analysis result."""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: update_analysis_index.py RESULT_JSON", file=sys.stderr)
        return 2

    result_path = pathlib.Path(sys.argv[1])
    result = json.loads(result_path.read_text(encoding="utf-8"))
    source = result.get("source") or {}
    external_id = source.get("externalSourceId")
    if not external_id:
        raise ValueError("analysis result is missing source.externalSourceId")

    index_path = pathlib.Path("data/analysis-index.json")
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        index = {"version": "0.9.1.4", "updatedAt": utc_now(), "items": []}

    analyzed = result.get("status") == "analyzed"
    media = result.get("media") or {}
    scan = result.get("scan") or {}
    entry: dict[str, Any] = {
        "id": f"analysis-{result.get('jobId', external_id)}",
        "jobId": result.get("jobId"),
        "externalSourceId": external_id,
        "authorizationId": source.get("authorizationId"),
        "author": source.get("author"),
        "title": source.get("title"),
        "status": "imported" if analyzed else "failed",
        "resultPath": result_path.as_posix(),
        "resultSha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
        "generatedAt": result.get("generatedAt") or utc_now(),
        "media": {
            "durationSeconds": media.get("durationSeconds"),
            "width": media.get("width"),
            "height": media.get("height"),
            "fps": media.get("fps"),
            "videoRetained": False,
            "framePixelsRetained": False,
        },
        "scan": {
            "sampled": scan.get("sampled", 0),
            "kept": scan.get("kept", 0),
            "blurred": scan.get("blurred", 0),
            "duplicates": scan.get("duplicates", 0),
            "keepRatio": scan.get("keepRatio", 0),
        },
        "pipeline": {
            "sourceDownloaded": analyzed,
            "numericDescriptorsGenerated": analyzed,
            "resultCommitted": True,
            "libraryImported": analyzed,
            "geospatialAnchoringCompleted": False,
        },
        "privacy": "原视频和画面像素已在分析后删除；公开仓库仅保存时间戳和数值视觉特征。",
    }
    if not analyzed:
        entry["failure"] = {"stage": result.get("stage"), "error": result.get("error")}

    items = [item for item in index.get("items", []) if item.get("externalSourceId") != external_id]
    items.append(entry)
    items.sort(key=lambda item: (item.get("author") or "", item.get("title") or ""))
    index["version"] = "0.9.1.4"
    index["updatedAt"] = utc_now()
    index["items"] = items
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"analysis index updated: {external_id} -> {entry['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
