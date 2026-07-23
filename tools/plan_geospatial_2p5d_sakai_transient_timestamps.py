#!/usr/bin/env python3
"""Select deterministic transient review timestamps for the Sakai 2.5D pilot.

The planner reads only existing numeric authorized-video results. It does not read or
create frame pixels. Per video it prioritizes sharp frames, scene transitions and
representative coverage across the full time axis. If a legacy scan contains fewer
unique descriptors than the review target, missing positions are added as explicitly
marked temporal supplements for transient re-reading of the authorized source.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "data/geospatial/geospatial-2p5d-sakai-pilot-evidence-plan.json"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def separated(candidate_time: float, selected: list[dict[str, Any]], minimum_seconds: float) -> bool:
    return all(abs(candidate_time - float(row["time"])) >= minimum_seconds for row in selected)


def descriptor_record(row: dict[str, Any], bucket: str) -> dict[str, Any]:
    return {
        "time": round(float(row.get("time") or 0), 3),
        "bucket": bucket,
        "sharpness": float(row.get("sharpness") or 0),
        "edgeDensity": float(row.get("edgeDensity") or 0),
        "difference": float(row.get("difference") or 0),
        "numericDescriptorAvailable": True,
    }


def pick_ranked(
    descriptors: list[dict[str, Any]],
    *,
    count: int,
    score_key: Callable[[dict[str, Any]], float],
    selected: list[dict[str, Any]],
    bucket: str,
    minimum_seconds: float,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    ordered = sorted(descriptors, key=lambda row: (-float(score_key(row)), float(row.get("time") or 0)))
    for row in ordered:
        time_value = float(row.get("time") or 0)
        if separated(time_value, selected + output, minimum_seconds):
            output.append(descriptor_record(row, bucket))
        if len(output) == count:
            break
    return output


def pick_temporal_coverage(
    descriptors: list[dict[str, Any]],
    *,
    duration_seconds: float,
    count: int,
    selected: list[dict[str, Any]],
    minimum_seconds: float,
) -> list[dict[str, Any]]:
    """Select one strong unused descriptor near each time-axis segment center."""
    output: list[dict[str, Any]] = []
    if duration_seconds <= 0 or count <= 0:
        return output
    for segment in range(count):
        center = duration_seconds * (segment + 0.5) / count
        candidates = [
            row for row in descriptors
            if separated(float(row.get("time") or 0), selected + output, minimum_seconds)
        ]
        if not candidates:
            break
        row = min(
            candidates,
            key=lambda item: (
                abs(float(item.get("time") or 0) - center),
                -float(item.get("sharpness") or 0),
                -float(item.get("difference") or 0),
            ),
        )
        output.append(descriptor_record(row, "temporalCoverage"))
    return output


def fill_remaining(
    descriptors: list[dict[str, Any]],
    *,
    target: int,
    selected: list[dict[str, Any]],
) -> None:
    def combined_score(row: dict[str, Any]) -> float:
        sharpness = min(1.0, math.log1p(max(0.0, float(row.get("sharpness") or 0))) / 9.0)
        return (
            float(row.get("difference") or 0) * 0.45
            + sharpness * 0.35
            + float(row.get("edgeDensity") or 0) * 0.20
        )

    ordered = sorted(descriptors, key=lambda row: (-combined_score(row), float(row.get("time") or 0)))
    for minimum_seconds in (5.0, 3.0, 1.0, 0.0):
        for row in ordered:
            if len(selected) >= target:
                return
            time_value = float(row.get("time") or 0)
            if separated(time_value, selected, minimum_seconds):
                selected.append(descriptor_record(row, "balancedFill"))


def fill_temporal_supplements(
    *,
    duration_seconds: float,
    target: int,
    selected: list[dict[str, Any]],
) -> int:
    needed = target - len(selected)
    if needed <= 0:
        return 0
    if duration_seconds <= 1:
        raise RuntimeError("cannot add temporal supplements without a valid duration")

    added = 0
    for multiplier in (4, 8, 16, 32):
        slots = max(target * multiplier, needed * multiplier)
        for index in range(slots):
            if len(selected) >= target:
                return added
            fraction = (index + 0.5) / slots
            time_value = max(0.5, min(duration_seconds - 0.5, duration_seconds * fraction))
            if not separated(time_value, selected, 1.0):
                continue
            selected.append({
                "time": round(time_value, 3),
                "bucket": "temporalSupplement",
                "sharpness": None,
                "edgeDensity": None,
                "difference": None,
                "numericDescriptorAvailable": False,
                "reason": "legacy numeric scan had fewer usable unique descriptors than the transient review target",
            })
            added += 1
    if len(selected) < target:
        raise RuntimeError(f"failed to add enough temporal supplements: {len(selected)}/{target}")
    return added


def main() -> int:
    plan = load(PLAN_PATH)
    target_count = int(plan["extraction"]["selectedFramesPerVideo"])
    buckets = plan["extraction"]["selectionBuckets"]
    output_path = ROOT / plan["outputs"]["timestampPlan"]
    videos: list[dict[str, Any]] = []

    pairs = list(zip(plan["authorizedVideoJobs"], plan["existingNumericResults"], strict=True))
    for job_name, result_name in pairs:
        job_path = ROOT / job_name
        result_path = ROOT / result_name
        job = load(job_path)
        result = load(result_path)
        if result.get("status") != "analyzed":
            raise RuntimeError(f"numeric result is not analyzed: {result_path}")
        if result.get("source", {}).get("authorizationId") != plan["authorizationId"]:
            raise RuntimeError(f"authorization mismatch: {result_path}")

        descriptors = list(result.get("descriptors") or [])
        duration_seconds = float(result.get("media", {}).get("durationSeconds") or 0)
        if len(descriptors) < 24:
            raise RuntimeError(f"numeric result is too sparse: {result_path} ({len(descriptors)} descriptors)")
        if duration_seconds <= 1:
            raise RuntimeError(f"invalid duration in {result_path}: {duration_seconds}")

        selected: list[dict[str, Any]] = []
        selected.extend(pick_ranked(
            descriptors,
            count=int(buckets["sharp"]),
            score_key=lambda row: float(row.get("sharpness") or 0),
            selected=selected,
            bucket="sharp",
            minimum_seconds=8.0,
        ))
        selected.extend(pick_ranked(
            descriptors,
            count=int(buckets["sceneTransition"]),
            score_key=lambda row: float(row.get("difference") or 0),
            selected=selected,
            bucket="sceneTransition",
            minimum_seconds=8.0,
        ))
        selected.extend(pick_temporal_coverage(
            descriptors,
            duration_seconds=duration_seconds,
            count=int(buckets["visualDiversity"]),
            selected=selected,
            minimum_seconds=8.0,
        ))
        fill_remaining(descriptors, target=target_count, selected=selected)
        supplement_count = fill_temporal_supplements(
            duration_seconds=duration_seconds,
            target=target_count,
            selected=selected,
        )

        selected = sorted(selected[:target_count], key=lambda row: float(row["time"]))
        if len(selected) != target_count:
            raise RuntimeError(f"failed to select {target_count} timestamps for {job['id']}: {len(selected)}")
        if len({float(row["time"]) for row in selected}) != target_count:
            raise RuntimeError(f"duplicate timestamps selected for {job['id']}")

        batch = job.get("batch") or {}
        videos.append({
            "jobId": job["id"],
            "jobPath": job_name,
            "resultPath": result_name,
            "url": job["url"],
            "title": job["title"],
            "page": batch.get("page"),
            "cid": batch.get("cid"),
            "durationSeconds": duration_seconds,
            "sourceFileSha256": result.get("media", {}).get("fileSha256"),
            "numericDescriptorCount": len(descriptors),
            "temporalSupplementCount": supplement_count,
            "timestampCount": len(selected),
            "timestamps": selected,
        })

    supplemental = {row["jobId"]: row["temporalSupplementCount"] for row in videos if row["temporalSupplementCount"]}
    payload = {
        "schemaVersion": 1,
        "status": "transient-timestamp-plan-ready",
        "stage": plan["stage"],
        "pilotScope": plan["pilotScope"],
        "authorizationId": plan["authorizationId"],
        "selectionPolicy": {
            "buckets": buckets,
            "minimumInitialSeparationSeconds": 8,
            "pixelDataUsed": False,
            "source": "existing numeric-only authorized analysis results with full-duration temporal coverage",
            "temporalSupplementsAreNumericEvidence": False,
        },
        "counts": {
            "videos": len(videos),
            "timestampsPerVideo": target_count,
            "totalTimestamps": sum(row["timestampCount"] for row in videos),
        },
        "temporalSupplementAudit": {
            "total": sum(row["temporalSupplementCount"] for row in videos),
            "byVideo": supplemental,
            "meaning": "review timestamps without a matching legacy descriptor; source frames are read only during the authorized transient scan",
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
        "output": str(output_path.relative_to(ROOT)),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
