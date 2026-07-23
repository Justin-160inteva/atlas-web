#!/usr/bin/env python3
"""Build a deterministic full-duration review timeline for the Sakai 2.5D pilot.

Only timestamps and existing numeric metadata are read. No video or frame pixels are
used here. Full-duration slots are reserved before legacy descriptor-based selections,
so a truncated legacy scan can never consume the complete review budget.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

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
    extraction = plan["extraction"]
    target = int(extraction["selectedFramesPerVideo"])
    bucket_limits = {key: int(value) for key, value in extraction["selectionBuckets"].items()}
    if sum(bucket_limits.values()) != target:
        raise RuntimeError(f"selection bucket total must equal {target}: {bucket_limits}")

    coverage_gates = extraction.get("coverageGates") or {}
    minimum_end_ratio = float(coverage_gates.get("minimumEndCoverageRatio", 0.95))
    maximum_gap_fraction = float(coverage_gates.get("maximumGapAsDurationFraction", 1 / 24))
    require_near_start = bool(coverage_gates.get("requireNearStartFrame", True))
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
        bucket_counts: dict[str, int] = {key: 0 for key in bucket_limits}
        supplement_count = 0

        def add(time_value: Any, bucket: str, metadata: dict[str, Any] | None = None) -> bool:
            try:
                numeric_time = float(time_value)
            except (TypeError, ValueError):
                return False
            numeric_time = max(0.5, min(duration - 0.5, numeric_time))
            rounded = round(numeric_time, 3)
            if rounded in used or len(selected) >= target:
                return False
            record: dict[str, Any] = {
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
            bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
            return True

        def add_rows(bucket: str, limit: int, rows: Iterable[dict[str, Any]]) -> None:
            for row in rows:
                if bucket_counts.get(bucket, 0) >= limit:
                    break
                add(row.get("time"), bucket, descriptor_metadata(row))

        # Reserve complete temporal coverage first. This is the hard fix for sparse or
        # truncated legacy descriptor scans such as the previous P13/P16 review.
        temporal_count = bucket_limits.get("temporalCoverage", 0)
        if temporal_count:
            start = 0.5
            end = duration - 0.5
            for index in range(temporal_count):
                fraction = index / (temporal_count - 1) if temporal_count > 1 else 0.5
                add(start + (end - start) * fraction, "temporalCoverage", {
                    "reason": "deterministic full-duration coverage independent of legacy descriptor span"
                })

        sharp_limit = bucket_limits.get("sharp", 0)
        sharp_rows = sorted(
            [*clear_frames, *descriptors],
            key=lambda item: (-float(item.get("sharpness") or 0), float(item.get("time") or 0)),
        )
        add_rows("sharp", sharp_limit, sharp_rows)

        transition_limit = bucket_limits.get("sceneTransition", 0)
        transition_rows = sorted(
            descriptors,
            key=lambda item: (-float(item.get("difference") or 0), float(item.get("time") or 0)),
        )
        add_rows("sceneTransition", transition_limit, transition_rows)

        balanced_limit = bucket_limits.get("balancedFill", 0)
        balanced_rows = sorted(
            descriptors,
            key=lambda item: (
                -(float(item.get("sharpness") or 0) * 0.55
                  + float(item.get("edgeDensity") or 0) * 900
                  + float(item.get("difference") or 0) * 500),
                float(item.get("time") or 0),
            ),
        )
        add_rows("balancedFill", balanced_limit, balanced_rows)

        # Descriptor collisions can leave a small deficit. Fill it deterministically
        # across the full duration without changing or inventing any geometry.
        for multiplier in (4, 8, 16, 32, 64):
            slots = target * multiplier
            for index in range(slots):
                if len(selected) >= target:
                    break
                time_value = duration * (index + 0.5) / slots
                if add(time_value, "temporalSupplement", {
                    "reason": "deterministic collision replacement for exact frame count"
                }):
                    supplement_count += 1
            if len(selected) >= target:
                break

        selected.sort(key=lambda row: float(row["time"]))
        if len(selected) != target:
            raise RuntimeError(f"failed to select {target} unique timestamps for {job['id']}: {len(selected)}")

        times = [float(row["time"]) for row in selected]
        gaps = [right - left for left, right in zip(times, times[1:])]
        maximum_gap = max(gaps, default=0.0)
        end_coverage_ratio = times[-1] / duration
        maximum_gap_ratio = maximum_gap / duration
        near_start = times[0] <= 1.0
        coverage_passed = (
            end_coverage_ratio >= minimum_end_ratio
            and maximum_gap_ratio <= maximum_gap_fraction + 1e-9
            and (near_start or not require_near_start)
        )
        if not coverage_passed:
            raise RuntimeError(
                f"full-duration coverage gate failed for {job['id']}: "
                f"start={times[0]:.3f}, endRatio={end_coverage_ratio:.6f}, "
                f"maxGapRatio={maximum_gap_ratio:.6f}"
            )

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
            "timestampCount": len(selected),
            "bucketCounts": bucket_counts,
            "temporalSupplementCount": supplement_count,
            "coverage": {
                "firstTimestamp": times[0],
                "lastTimestamp": times[-1],
                "endCoverageRatio": round(end_coverage_ratio, 6),
                "maximumGapSeconds": round(maximum_gap, 3),
                "maximumGapAsDurationFraction": round(maximum_gap_ratio, 6),
                "minimumEndCoverageRatio": minimum_end_ratio,
                "maximumAllowedGapAsDurationFraction": maximum_gap_fraction,
                "nearStartFramePresent": near_start,
                "passed": coverage_passed,
            },
            "timestamps": selected,
        })

    payload = {
        "schemaVersion": 2,
        "status": "transient-timestamp-plan-ready",
        "stage": plan["stage"],
        "pilotScope": plan["pilotScope"],
        "authorizationId": plan["authorizationId"],
        "selectionPolicy": {
            "buckets": bucket_limits,
            "pixelDataUsed": False,
            "source": "guaranteed full-duration timeline plus legacy numeric descriptors",
            "fullDurationCoverageReservedBeforeDescriptorSelection": True,
        },
        "coverageGateStatus": "passed",
        "counts": {
            "videos": len(videos),
            "timestampsPerVideo": target,
            "totalTimestamps": sum(row["timestampCount"] for row in videos),
        },
        "temporalSupplementAudit": {
            "total": sum(row["temporalSupplementCount"] for row in videos),
            "byVideo": {
                row["jobId"]: row["temporalSupplementCount"]
                for row in videos if row["temporalSupplementCount"]
            },
        },
        "videos": videos,
        "safety": {
            "framePixelsGenerated": False,
            "videosDownloaded": False,
            "geometryGenerated": False,
            "existingAnalysisModified": False,
        },
        "nextAction": "extract authorized low-resolution transient frames across the complete duration and visually classify Sakai evidence windows",
    }
    write(output_path, payload)
    print(json.dumps({
        "status": payload["status"],
        "videos": payload["counts"]["videos"],
        "totalTimestamps": payload["counts"]["totalTimestamps"],
        "coverageGateStatus": payload["coverageGateStatus"],
        "coverage": {
            row["jobId"]: row["coverage"] for row in videos
        },
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
