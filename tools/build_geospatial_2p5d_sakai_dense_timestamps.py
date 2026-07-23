#!/usr/bin/env python3
"""Build exact targeted timestamps for the Sakai dense visual-evidence scan."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "data/geospatial/geospatial-2p5d-sakai-dense-evidence-plan.json"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    plan = load(PLAN_PATH)
    interval = float(plan["sampling"]["intervalSeconds"])
    if interval <= 0:
        raise RuntimeError("sampling interval must be positive")

    videos: list[dict[str, Any]] = []
    total = 0
    for source in plan["videos"]:
        job = load(ROOT / source["jobPath"])
        batch = job.get("batch") or {}
        if job.get("id") != source["jobId"]:
            raise RuntimeError(f"job id mismatch: {source['jobPath']}")
        if job.get("authorizationId") != plan["authorizationId"]:
            raise RuntimeError(f"authorization mismatch: {source['jobId']}")
        if int(batch.get("page") or 0) != int(source["page"]):
            raise RuntimeError(f"page mismatch: {source['jobId']}")
        if int(batch.get("cid") or 0) != int(source["cid"]):
            raise RuntimeError(f"cid mismatch: {source['jobId']}")

        timestamps: list[dict[str, Any]] = []
        used: set[float] = set()
        window_counts: dict[str, int] = {}

        def add(time_value: float, bucket: str, *, window_id: str | None, purpose: str) -> bool:
            rounded = round(float(time_value), 3)
            if rounded in used:
                return False
            if rounded < 0 or rounded >= float(source["expectedDurationSeconds"]):
                raise RuntimeError(f"timestamp outside expected duration: {source['jobId']} {rounded}")
            timestamps.append({
                "time": rounded,
                "bucket": bucket,
                "windowId": window_id,
                "purpose": purpose,
            })
            used.add(rounded)
            if window_id:
                window_counts[window_id] = window_counts.get(window_id, 0) + 1
            return True

        for window in source["windows"]:
            start = float(window["startSeconds"])
            end = float(window["endSeconds"])
            if not (0 <= start <= end < float(source["expectedDurationSeconds"])):
                raise RuntimeError(f"invalid dense window: {source['jobId']} {window}")
            steps = int((end - start) // interval)
            for index in range(steps + 1):
                add(
                    start + index * interval,
                    "denseWindow",
                    window_id=str(window["id"]),
                    purpose=str(window["purpose"]),
                )

        for time_value in source.get("contextTimestamps") or []:
            add(
                float(time_value),
                "context",
                window_id=None,
                purpose="map, mission or transition context only; never a geometry source",
            )

        timestamps.sort(key=lambda row: float(row["time"]))
        expected = int(source["expectedFrameCount"])
        if len(timestamps) != expected:
            raise RuntimeError(
                f"dense timestamp count mismatch for {source['jobId']}: {len(timestamps)} != {expected}"
            )
        expected_sheets = (expected + int(plan["sampling"]["contactSheetColumns"]) * int(plan["sampling"]["contactSheetRows"]) - 1) // (
            int(plan["sampling"]["contactSheetColumns"]) * int(plan["sampling"]["contactSheetRows"])
        )
        if expected_sheets != int(source["expectedContactSheetCount"]):
            raise RuntimeError(f"contact-sheet count mismatch for {source['jobId']}")

        videos.append({
            "jobId": source["jobId"],
            "jobPath": source["jobPath"],
            "url": job["url"],
            "title": job["title"],
            "page": int(source["page"]),
            "cid": int(source["cid"]),
            "expectedDurationSeconds": float(source["expectedDurationSeconds"]),
            "frameCount": len(timestamps),
            "contactSheetCount": expected_sheets,
            "windowCounts": window_counts,
            "timestamps": timestamps,
        })
        total += len(timestamps)

    payload = {
        "schemaVersion": 1,
        "status": "dense-timestamp-plan-ready",
        "stage": plan["stage"],
        "authorizationId": plan["authorizationId"],
        "pilotScope": plan["pilotScope"],
        "sampling": plan["sampling"],
        "counts": {
            "videos": len(videos),
            "frames": total,
            "contactSheets": sum(row["contactSheetCount"] for row in videos),
        },
        "videos": videos,
        "safety": {
            "pixelsGenerated": False,
            "videosDownloaded": False,
            "geometryGenerated": False,
            "sourceCoordinatesModified": False,
        },
        "nextAction": "download P13 and P15 transiently by explicit CID and extract only the targeted dense windows",
    }
    output = ROOT / plan["outputs"]["timestampPlan"]
    write(output, payload)
    print(json.dumps({
        "status": payload["status"],
        "counts": payload["counts"],
        "videos": [{"jobId": row["jobId"], "frames": row["frameCount"]} for row in videos],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
