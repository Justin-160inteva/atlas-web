#!/usr/bin/env python3
"""Build deterministic timestamps for the P13 full-duration and P15 dense Sakai scans.

This planner reads only job metadata and existing numeric results. It creates no frame
pixels and no geometry. P13 reserves full-duration coverage before adding quality
candidates. P15 uses explicit human-reviewed candidate/context windows.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "data/geospatial/geospatial-2p5d-sakai-correction-scan-plan.json"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def clamp_time(value: float, duration: float) -> float:
    return round(max(0.5, min(duration - 0.5, value)), 3)


def metadata(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sharpness": float(row.get("sharpness") or 0),
        "edgeDensity": float(row.get("edgeDensity") or 0),
        "difference": float(row.get("difference") or 0),
        "numericDescriptorAvailable": True,
    }


def add_unique(
    selected: list[dict[str, Any]],
    used: set[float],
    *,
    time_value: float,
    duration: float,
    bucket: str,
    extra: dict[str, Any] | None = None,
) -> bool:
    rounded = clamp_time(time_value, duration)
    if rounded in used:
        return False
    row = {
        "time": rounded,
        "bucket": bucket,
        "sharpness": None,
        "edgeDensity": None,
        "difference": None,
        "numericDescriptorAvailable": False,
    }
    if extra:
        row.update(extra)
    selected.append(row)
    used.add(rounded)
    return True


def build_p13(job: dict[str, Any], result: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    duration = float(result.get("media", {}).get("durationSeconds") or 0)
    if duration <= 1:
        raise RuntimeError("P13 has no valid duration")
    selection = config["selection"]
    descriptors = [row for row in (result.get("descriptors") or []) if isinstance(row, dict)]
    clear = [row for row in (result.get("clearFrameTimes") or []) if isinstance(row, dict)]
    selected: list[dict[str, Any]] = []
    used: set[float] = set()

    uniform_count = int(selection["uniformFullDuration"])
    for index in range(uniform_count):
        add_unique(
            selected,
            used,
            time_value=duration * (index + 0.5) / uniform_count,
            duration=duration,
            bucket="uniformFullDuration",
            extra={"durationSegment": index + 1, "durationSegmentCount": uniform_count},
        )

    for row in sorted(clear, key=lambda item: (-float(item.get("sharpness") or 0), float(item.get("time") or 0))):
        if sum(1 for item in selected if item["bucket"] == "sharp") >= int(selection["sharp"]):
            break
        add_unique(selected, used, time_value=float(row.get("time") or 0), duration=duration, bucket="sharp", extra={
            "sharpness": float(row.get("sharpness") or 0),
            "edgeDensity": float(row.get("edgeDensity") or 0),
            "difference": None,
            "numericDescriptorAvailable": True,
        })

    for row in sorted(descriptors, key=lambda item: (-float(item.get("difference") or 0), float(item.get("time") or 0))):
        if sum(1 for item in selected if item["bucket"] == "sceneTransition") >= int(selection["sceneTransition"]):
            break
        add_unique(selected, used, time_value=float(row.get("time") or 0), duration=duration, bucket="sceneTransition", extra=metadata(row))

    target = int(config["frameCount"])
    for multiplier in (4, 8, 16):
        for index in range(target * multiplier):
            if len(selected) >= target:
                break
            add_unique(
                selected,
                used,
                time_value=duration * (index + 0.5) / (target * multiplier),
                duration=duration,
                bucket="coverageFill",
                extra={"reason": "fill after reserved full-duration, sharp and transition buckets"},
            )
        if len(selected) >= target:
            break
    selected = sorted(selected[:target], key=lambda row: float(row["time"]))
    if len(selected) != target:
        raise RuntimeError(f"P13 correction timestamp count mismatch: {len(selected)}/{target}")

    quarter_counts = Counter(min(3, int(float(row["time"]) / duration * 4)) for row in selected)
    covered_fraction = (float(selected[-1]["time"]) - float(selected[0]["time"])) / duration
    gates = config["hardGates"]
    checks = {
        "coveredDurationFraction": covered_fraction >= float(gates["minimumCoveredDurationFraction"]),
        "noEmptyQuarter": all(quarter_counts[index] > 0 for index in range(4)),
        "minimumFramesPerQuarter": all(quarter_counts[index] >= int(gates["minimumFramesPerDurationQuarter"]) for index in range(4)),
    }
    if not all(checks.values()):
        raise RuntimeError(f"P13 full-duration gates failed: {checks}, quarters={dict(quarter_counts)}")

    batch = job.get("batch") or {}
    return {
        "id": config["id"],
        "sourceJobId": job["id"],
        "jobPath": config["jobPath"],
        "resultPath": config["resultPath"],
        "page": batch.get("page"),
        "cid": batch.get("cid"),
        "durationSeconds": duration,
        "strategy": config["strategy"],
        "frameCount": len(selected),
        "contactSheetCount": int(config["contactSheetCount"]),
        "coverage": {
            "firstSecond": float(selected[0]["time"]),
            "lastSecond": float(selected[-1]["time"]),
            "coveredDurationFraction": round(covered_fraction, 6),
            "quarterCounts": {str(index + 1): quarter_counts[index] for index in range(4)},
            "checks": checks,
        },
        "timestamps": selected,
    }


def uniform_window_times(start: float, end: float, count: int) -> list[float]:
    if count <= 0 or end <= start:
        raise RuntimeError(f"invalid window allocation: {start}-{end} count={count}")
    return [start + (end - start) * (index + 0.5) / count for index in range(count)]


def build_p15(job: dict[str, Any], result: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    duration = float(result.get("media", {}).get("durationSeconds") or 0)
    if duration <= 1:
        raise RuntimeError("P15 has no valid duration")
    selected: list[dict[str, Any]] = []
    used: set[float] = set()

    allocation = {
        "elevated-city-water-panorama": 20,
        "settlement-road-watchtower-water": 36,
        "wooden-commercial-workshop-water-access": 48,
        "elevated-tiled-roof-compound": 32,
        "roof-and-compound-connectivity": 24,
    }
    for window in config["candidateWindows"]:
        window_id = str(window["id"])
        count = allocation[window_id]
        for time_value in uniform_window_times(float(window["startSeconds"]), float(window["endSeconds"]), count):
            if not add_unique(
                selected,
                used,
                time_value=time_value,
                duration=duration,
                bucket="candidateWindow",
                extra={
                    "windowId": window_id,
                    "windowPriority": window["priority"],
                    "reviewPurpose": "human-reviewed Sakai urban/waterfront candidate",
                },
            ):
                raise RuntimeError(f"duplicate P15 candidate time in {window_id}: {time_value}")

    for window in config["contextWindows"]:
        window_id = str(window["id"])
        for time_value in uniform_window_times(float(window["startSeconds"]), float(window["endSeconds"]), 8):
            if not add_unique(
                selected,
                used,
                time_value=time_value,
                duration=duration,
                bucket="contextWindow",
                extra={
                    "windowId": window_id,
                    "reviewPurpose": "map, mission or identity correlation only; not a geometry source",
                },
            ):
                raise RuntimeError(f"duplicate P15 context time in {window_id}: {time_value}")

    selected.sort(key=lambda row: float(row["time"]))
    target = int(config["frameCount"])
    if len(selected) != target:
        raise RuntimeError(f"P15 dense timestamp count mismatch: {len(selected)}/{target}")

    counts = Counter(str(row["windowId"]) for row in selected)
    gates = config["hardGates"]
    candidate_priorities = {str(row["id"]): str(row["priority"]) for row in config["candidateWindows"]}
    checks = {
        "allCandidateWindowsRepresented": all(counts[str(row["id"])] > 0 for row in config["candidateWindows"]),
        "allContextWindowsRepresented": all(counts[str(row["id"])] > 0 for row in config["contextWindows"]),
        "criticalMinimum": all(counts[window_id] >= int(gates["minimumFramesPerCriticalWindow"]) for window_id, priority in candidate_priorities.items() if priority == "critical"),
        "highMinimum": all(counts[window_id] >= int(gates["minimumFramesPerHighWindow"]) for window_id, priority in candidate_priorities.items() if priority == "high"),
        "mediumMinimum": all(counts[window_id] >= int(gates["minimumFramesPerMediumWindow"]) for window_id, priority in candidate_priorities.items() if priority == "medium"),
    }
    if not all(checks.values()):
        raise RuntimeError(f"P15 dense-window gates failed: {checks}, counts={dict(counts)}")

    batch = job.get("batch") or {}
    return {
        "id": config["id"],
        "sourceJobId": job["id"],
        "jobPath": config["jobPath"],
        "resultPath": config["resultPath"],
        "page": batch.get("page"),
        "cid": batch.get("cid"),
        "durationSeconds": duration,
        "strategy": config["strategy"],
        "frameCount": len(selected),
        "contactSheetCount": int(config["contactSheetCount"]),
        "windowCounts": dict(sorted(counts.items())),
        "checks": checks,
        "timestamps": selected,
    }


def main() -> int:
    plan = load(PLAN_PATH)
    jobs = []
    for config in plan["jobs"]:
        job = load(ROOT / config["jobPath"])
        result = load(ROOT / config["resultPath"])
        if result.get("source", {}).get("authorizationId") != plan["authorizationId"]:
            raise RuntimeError(f"authorization mismatch for {config['id']}")
        if config["strategy"] == "full-duration-stratified":
            jobs.append(build_p13(job, result, config))
        elif config["strategy"] == "dense-candidate-windows":
            jobs.append(build_p15(job, result, config))
        else:
            raise RuntimeError(f"unsupported strategy: {config['strategy']}")

    payload = {
        "schemaVersion": 1,
        "status": "correction-timestamp-plan-ready",
        "stage": plan["stage"],
        "authorizationId": plan["authorizationId"],
        "sourceVisualReview": plan["sourceVisualReview"],
        "counts": {
            "jobs": len(jobs),
            "frames": sum(int(row["frameCount"]) for row in jobs),
            "contactSheets": sum(int(row["contactSheetCount"]) for row in jobs),
        },
        "jobs": jobs,
        "safety": {
            "pixelsRead": false,
            "pixelsGenerated": false,
            "geometryGenerated": false,
            "existingCoordinatesModified": false
        },
        "nextAction": "download P13 and P15 transiently by explicit CID and extract one-day correction review artifacts"
    }
    output_path = ROOT / plan["outputs"]["timestampPlan"]
    write(output_path, payload)
    print(json.dumps({
        "status": payload["status"],
        "counts": payload["counts"],
        "p13Coverage": jobs[0]["coverage"],
        "p15WindowCounts": jobs[1]["windowCounts"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
