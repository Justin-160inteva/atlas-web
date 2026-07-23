#!/usr/bin/env python3
"""Build a deterministic transient review timeline for the Sakai 2.5D pilot.

Only timestamps and existing numeric metadata are read. No video or frame pixels are
used here. The plan prioritizes clear frames and scene changes, then fills the complete
time axis so sparse legacy analyses cannot block the authorized transient review.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "data/geospatial/geospatial-2p5d-sakai-pilot-evidence-plan.json"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def descriptor_metadata(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sharpness": float(row.get("sharpness") or 0),
        "edgeDensity": float(row.get("edgeDensity") or 0),
        "difference": float(row.get("difference") or 0),
        "numericDescriptorAvailable": True,
    }


def main() -> int:
    plan = load(PLAN_PATH)
    target = int(plan["extraction"]["selectedFramesPerVideo"])
    output_path = ROOT / plan["outputs"]["timestampPlan"]
    videos: list[dict[str, Any]] = []

    for job_name, result_name in zip(plan["authorizedVideoJobs"], plan["existingNumericResults"], strict=True):
        job = load(ROOT / job_name)
        result = load(ROOT / result_name)
        if result.get("status") != "analyzed":
            raise RuntimeError(f"numeric result is not analyzed: {result_name}")
        if result.get("source", {}).get("authorizationId") != plan["authorizationId"]:
            raise RuntimeError(f"authorization mismatch: {result_name}")

        duration = float(result.get("media", {}).get("durationSeconds") or 0)
        descriptors = [row for row in (result.get("descriptors") or []) if isinstance(row, dict)]
        clear_frames = [row for row in (result.get("clearFrameTimes") or []) if isinstance(row, dict)]
        if duration <= 1:
            raise RuntimeError(f"invalid duration in {result_name}: {duration}")

        selected: list[dict[str, Any]] = []
        used: set[float] = set()

        def add(time_value: Any, bucket: str, metadata: dict[str, Any] | None = None) -> bool:
            try:
                numeric_time = float(time_value)
            except (TypeError, ValueError):
                return False
            numeric_time = max(0.5, min(duration - 0.5, numeric_time))
            rounded = round(numeric_time, 3)
            if rounded in used or len(selected) >= target:
                return False
            record = {
                "time": rounded,
                "bucket": bucket,
                "sharpness": None,
                "edgeDensity": None,
                "difference": None,
                "numericDescriptorAvailable": False,
            }
            if metadata:
                record.update(metadata)
            selected.append(record)
            used.add(rounded)
            return True

        # Bucket 1: the clearest known frames from the legacy numeric scan.
        for row in sorted(clear_frames, key=lambda item: (-float(item.get("sharpness") or 0), float(item.get("time") or 0)))[:32]:
            add(row.get("time"), "sharp", {
                "sharpness": float(row.get("sharpness") or 0),
                "edgeDensity": float(row.get("edgeDensity") or 0),
                "difference": None,
                "numericDescriptorAvailable": True,
            })

        # Bucket 2: strongest visual changes, useful for scene and map transitions.
        for row in sorted(descriptors, key=lambda item: (-float(item.get("difference") or 0), float(item.get("time") or 0))):
            if sum(1 for item in selected if item["bucket"] == "sceneTransition") >= 32:
                break
            add(row.get("time"), "sceneTransition", descriptor_metadata(row))

        # Bucket 3: representative legacy descriptors spread across the full time axis.
        ordered = sorted(descriptors, key=lambda item: float(item.get("time") or 0))
        if ordered:
            for index in range(32):
                source_index = min(len(ordered) - 1, int((index + 0.5) * len(ordered) / 32))
                add(ordered[source_index].get("time"), "temporalCoverage", descriptor_metadata(ordered[source_index]))

        # Reuse all remaining numeric descriptors before introducing non-descriptor times.
        for row in sorted(
            descriptors,
            key=lambda item: (
                -float(item.get("sharpness") or 0),
                -float(item.get("difference") or 0),
                float(item.get("time") or 0),
            ),
        ):
            if len(selected) >= target:
                break
            add(row.get("time"), "balancedFill", descriptor_metadata(row))

        # Fill any sparse legacy scan with evenly distributed authorized review times.
        supplement_count = 0
        for multiplier in (4, 8, 16, 32):
            slots = target * multiplier
            for index in range(slots):
                if len(selected) >= target:
                    break
                time_value = duration * (index + 0.5) / slots
                if add(time_value, "temporalSupplement", {
                    "sharpness": None,
                    "edgeDensity": None,
                    "difference": None,
                    "numericDescriptorAvailable": False,
                    "reason": "full-duration transient coverage beyond the legacy numeric descriptor set",
                }):
                    supplement_count += 1
            if len(selected) >= target:
                break

        selected.sort(key=lambda row: float(row["time"]))
        if len(selected) != target:
            raise RuntimeError(f"failed to select {target} unique timestamps for {job['id']}: {len(selected)}")

        batch = job.get("batch") or {}
        videos.append({
            "jobId": job["id"],
            "jobPath": job_name,
            "resultPath": result_name,
            "url": job["url"],
            "title": job["title"],
            "page": batch.get("page"),
            "cid": batch.get("cid"),
            "durationSeconds": duration,
            "sourceFileSha256": result.get("media", {}).get("fileSha256"),
            "numericDescriptorCount": len(descriptors),
            "temporalSupplementCount": supplement_count,
            "timestampCount": len(selected),
            "timestamps": selected,
        })

    supplements = {row["jobId"]: row["temporalSupplementCount"] for row in videos if row["temporalSupplementCount"]}
    payload = {
        "schemaVersion": 1,
        "status": "transient-timestamp-plan-ready",
        "stage": plan["stage"],
        "pilotScope": plan["pilotScope"],
        "authorizationId": plan["authorizationId"],
        "selectionPolicy": {
            "buckets": plan["extraction"]["selectionBuckets"],
            "pixelDataUsed": False,
            "source": "legacy numeric descriptors plus deterministic full-duration supplements",
            "temporalSupplementsAreNumericEvidence": False,
        },
        "counts": {
            "videos": len(videos),
            "timestampsPerVideo": target,
            "totalTimestamps": sum(row["timestampCount"] for row in videos),
        },
        "temporalSupplementAudit": {
            "total": sum(row["temporalSupplementCount"] for row in videos),
            "byVideo": supplements,
        },
        "videos": videos,
        "safety": {
            "framePixelsGenerated": False,
            "videosDownloaded": False,
            "geometryGenerated": False,
            "existingAnalysisModified": False,
        },
        "nextAction": "download the four authorized pages transiently by explicit CID and extract one-day low-resolution review artifacts",
    }
    write(output_path, payload)
    print(json.dumps({
        "status": payload["status"],
        "videos": payload["counts"]["videos"],
        "totalTimestamps": payload["counts"]["totalTimestamps"],
        "temporalSupplements": payload["temporalSupplementAudit"]["total"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
