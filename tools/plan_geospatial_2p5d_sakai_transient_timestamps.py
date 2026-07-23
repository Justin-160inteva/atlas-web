#!/usr/bin/env python3
"""Select deterministic transient review timestamps for the Sakai 2.5D pilot.

The planner primarily uses existing numeric-only authorized-video results. It does not
read or create frame pixels. Three evidence-driven buckets are selected per video:
sharp frames, scene transitions, and visual-diversity representatives. When an older
numeric scan contains fewer unique descriptors than the review target, the remaining
timestamps are distributed deterministically across the authorized video's duration and
are explicitly marked as temporal supplements rather than invented numeric evidence.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "data/geospatial/geospatial-2p5d-sakai-pilot-evidence-plan.json"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def vector(row: dict[str, Any]) -> np.ndarray:
    values = [
        float(row.get("brightness") or 0),
        min(1.0, math.log1p(max(0.0, float(row.get("sharpness") or 0))) / 9.0),
        float(row.get("edgeDensity") or 0),
        float(row.get("difference") or 0),
    ]
    values.extend(float(value) for value in (row.get("edge") or [])[:8])
    values.extend(float(value) for value in (row.get("color") or [])[:24])
    result = np.asarray(values, dtype=np.float32)
    norm = float(np.linalg.norm(result))
    return result / norm if norm > 0 else result


def separated(candidate_time: float, selected: list[dict[str, Any]], minimum_seconds: float) -> bool:
    return all(abs(candidate_time - float(row["time"])) >= minimum_seconds for row in selected)


def pick_ranked(
    descriptors: list[dict[str, Any]],
    *,
    count: int,
    score_key,
    selected: list[dict[str, Any]],
    bucket: str,
    minimum_seconds: float,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    ordered = sorted(descriptors, key=lambda row: (-float(score_key(row)), float(row.get("time") or 0)))
    for row in ordered:
        time_value = float(row.get("time") or 0)
        if not separated(time_value, selected + output, minimum_seconds):
            continue
        output.append({
            "time": round(time_value, 3),
            "bucket": bucket,
            "sharpness": float(row.get("sharpness") or 0),
            "edgeDensity": float(row.get("edgeDensity") or 0),
            "difference": float(row.get("difference") or 0),
            "numericDescriptorAvailable": True,
        })
        if len(output) == count:
            break
    return output


def pick_diverse(
    descriptors: list[dict[str, Any]],
    *,
    count: int,
    selected: list[dict[str, Any]],
    minimum_seconds: float,
) -> list[dict[str, Any]]:
    candidates = [row for row in descriptors if separated(float(row.get("time") or 0), selected, minimum_seconds)]
    if not candidates:
        return []
    candidate_vectors = [vector(row) for row in candidates]
    quality = [
        math.log1p(max(0.0, float(row.get("sharpness") or 0))) * (0.25 + float(row.get("edgeDensity") or 0))
        for row in candidates
    ]
    first = max(range(len(candidates)), key=lambda index: (quality[index], -float(candidates[index].get("time") or 0)))
    chosen = [first]
    available = set(range(len(candidates))) - {first}
    while available and len(chosen) < count:
        best_index = None
        best_score = -1.0
        for index in available:
            time_value = float(candidates[index].get("time") or 0)
            chosen_rows = [
                {"time": float(candidates[chosen_index].get("time") or 0)}
                for chosen_index in chosen
            ]
            if not separated(time_value, selected + chosen_rows, minimum_seconds):
                continue
            distance = min(float(np.linalg.norm(candidate_vectors[index] - candidate_vectors[other])) for other in chosen)
            score = distance * (0.7 + min(1.5, quality[index] / 8.0))
            if score > best_score:
                best_score = score
                best_index = index
        if best_index is None:
            break
        chosen.append(best_index)
        available.remove(best_index)
    output = []
    for index in chosen[:count]:
        row = candidates[index]
        output.append({
            "time": round(float(row.get("time") or 0), 3),
            "bucket": "visualDiversity",
            "sharpness": float(row.get("sharpness") or 0),
            "edgeDensity": float(row.get("edgeDensity") or 0),
            "difference": float(row.get("difference") or 0),
            "numericDescriptorAvailable": True,
        })
    return output


def fill_remaining(
    descriptors: list[dict[str, Any]],
    *,
    target: int,
    selected: list[dict[str, Any]],
) -> None:
    ordered = sorted(
        descriptors,
        key=lambda row: (
            -(float(row.get("difference") or 0) * 0.45
              + min(1.0, math.log1p(max(0.0, float(row.get("sharpness") or 0))) / 9.0) * 0.35
              + float(row.get("edgeDensity") or 0) * 0.20),
            float(row.get("time") or 0),
        ),
    )
    for minimum_seconds in (5.0, 3.0, 1.0, 0.0):
        for row in ordered:
            if len(selected) >= target:
                return
            time_value = float(row.get("time") or 0)
            if not separated(time_value, selected, minimum_seconds):
                continue
            selected.append({
                "time": round(time_value, 3),
                "bucket": "balancedFill",
                "sharpness": float(row.get("sharpness") or 0),
                "edgeDensity": float(row.get("edgeDensity") or 0),
                "difference": float(row.get("difference") or 0),
                "numericDescriptorAvailable": True,
            })


def fill_temporal_supplements(
    *,
    duration_seconds: float,
    target: int,
    selected: list[dict[str, Any]],
) -> int:
    """Fill a sparse legacy scan using explicit, uniformly distributed review times."""
    needed = target - len(selected)
    if needed <= 0:
        return 0
    if duration_seconds <= 0:
        raise RuntimeError("cannot add temporal supplements without a positive duration")

    added = 0
    # Use an increasingly dense deterministic grid while keeping clear of the start/end slates.
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
                "reason": "legacy numeric scan had fewer unique descriptors than the transient review target",
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
    videos = []
    for job_name, result_name in zip(plan["authorizedVideoJobs"], plan["existingNumericResults"], strict=True):
        job_path = ROOT / job_name
        result_path = ROOT / result_name
        job = load(job_path)
        result = load(result_path)
        if result.get("status") != "analyzed":
            raise RuntimeError(f"numeric result is not analyzed: {result_path}")
        if result.get("source", {}).get("authorizationId") != plan["authorizationId"]:
            raise RuntimeError(f"authorization mismatch: {result_path}")
        descriptors = list(result.get("descriptors") or [])
        if len(descriptors) < 24:
            raise RuntimeError(f"numeric result is too sparse for evidence-driven planning: {result_path} ({len(descriptors)})")
        duration_seconds = float(result.get("media", {}).get("durationSeconds") or 0)

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
        selected.extend(pick_diverse(
            descriptors,
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
            "source": "existing numeric-only authorized analysis results, with explicit temporal supplements only where a legacy scan is sparse",
            "temporalSupplementsAreNumericEvidence": False,
        },
        "counts": {
            "videos": len(videos),
            "timestampsPerVideo": target_count,
            "totalTimestamps": sum(row["timestampCount"] for row in videos),
            "temporalSupplements": sum(row["temporalSupplementCount"] for row in videos),
        },
        "videos": videos,
        "safety": {
            "framePixelsGenerated": False,
            "videosDownloaded": False,
            "geometryGenerated": False,
            "existingAnalysisModified": False,
            "temporalSupplementsMisrepresentedAsNumericEvidence": False,
        },
        "nextAction": "download the four authorized pages transiently by explicit CID and extract one-day low-resolution review artifacts",
    }
    write(output_path, payload)
    print(json.dumps({
        "status": payload["status"],
        "videos": payload["counts"]["videos"],
        "totalTimestamps": payload["counts"]["totalTimestamps"],
        "temporalSupplements": payload["counts"]["temporalSupplements"],
        "output": str(output_path.relative_to(ROOT)),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
