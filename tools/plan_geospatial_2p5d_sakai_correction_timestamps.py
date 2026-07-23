#!/usr/bin/env python3
"""Plan P13 full-duration and P15 dense Sakai correction timestamps without pixels."""
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


def add(selected: list[dict[str, Any]], used: set[float], time_value: float, duration: float, bucket: str, **extra: Any) -> bool:
    timestamp = round(max(0.5, min(duration - 0.5, float(time_value))), 3)
    if timestamp in used:
        return False
    selected.append({
        "time": timestamp,
        "bucket": bucket,
        "sharpness": None,
        "edgeDensity": None,
        "difference": None,
        "numericDescriptorAvailable": False,
        **extra,
    })
    used.add(timestamp)
    return True


def numeric_extra(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sharpness": float(row.get("sharpness") or 0),
        "edgeDensity": float(row.get("edgeDensity") or 0),
        "difference": float(row.get("difference") or 0),
        "numericDescriptorAvailable": True,
    }


def source_record(config: dict[str, Any], job: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    batch = job.get("batch") or {}
    return {
        "id": config["id"],
        "sourceJobId": job["id"],
        "jobPath": config["jobPath"],
        "resultPath": config["resultPath"],
        "page": batch.get("page"),
        "cid": batch.get("cid"),
        "durationSeconds": float(result.get("media", {}).get("durationSeconds") or 0),
        "strategy": config["strategy"],
        "contactSheetCount": int(config["contactSheetCount"]),
    }


def build_p13(config: dict[str, Any], job: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    record = source_record(config, job, result)
    duration = record["durationSeconds"]
    if duration <= 1:
        raise RuntimeError("P13 duration is invalid")
    selected: list[dict[str, Any]] = []
    used: set[float] = set()
    selection = config["selection"]

    uniform_count = int(selection["uniformFullDuration"])
    for index in range(uniform_count):
        add(selected, used, duration * (index + 0.5) / uniform_count, duration, "uniformFullDuration",
            durationSegment=index + 1, durationSegmentCount=uniform_count)

    clear = [row for row in (result.get("clearFrameTimes") or []) if isinstance(row, dict)]
    for row in sorted(clear, key=lambda item: (-float(item.get("sharpness") or 0), float(item.get("time") or 0))):
        if sum(item["bucket"] == "sharp" for item in selected) >= int(selection["sharp"]):
            break
        add(selected, used, row.get("time") or 0, duration, "sharp", **{
            "sharpness": float(row.get("sharpness") or 0),
            "edgeDensity": float(row.get("edgeDensity") or 0),
            "difference": None,
            "numericDescriptorAvailable": True,
        })

    descriptors = [row for row in (result.get("descriptors") or []) if isinstance(row, dict)]
    for row in sorted(descriptors, key=lambda item: (-float(item.get("difference") or 0), float(item.get("time") or 0))):
        if sum(item["bucket"] == "sceneTransition" for item in selected) >= int(selection["sceneTransition"]):
            break
        add(selected, used, row.get("time") or 0, duration, "sceneTransition", **numeric_extra(row))

    target = int(config["frameCount"])
    for index in range(target * 16):
        if len(selected) >= target:
            break
        add(selected, used, duration * (index + 0.5) / (target * 16), duration, "coverageFill")
    selected = sorted(selected[:target], key=lambda row: row["time"])
    if len(selected) != target:
        raise RuntimeError(f"P13 timestamp count mismatch: {len(selected)}/{target}")

    quarters = Counter(min(3, int(row["time"] / duration * 4)) for row in selected)
    fraction = (selected[-1]["time"] - selected[0]["time"]) / duration
    gates = config["hardGates"]
    checks = {
        "coveredDurationFraction": fraction >= float(gates["minimumCoveredDurationFraction"]),
        "noEmptyQuarter": all(quarters[index] > 0 for index in range(4)),
        "minimumFramesPerQuarter": all(quarters[index] >= int(gates["minimumFramesPerDurationQuarter"]) for index in range(4)),
    }
    if not all(checks.values()):
        raise RuntimeError(f"P13 coverage gates failed: {checks}, quarters={dict(quarters)}")
    record.update({
        "frameCount": len(selected),
        "coverage": {
            "firstSecond": selected[0]["time"],
            "lastSecond": selected[-1]["time"],
            "coveredDurationFraction": round(fraction, 6),
            "quarterCounts": {str(index + 1): quarters[index] for index in range(4)},
            "checks": checks,
        },
        "timestamps": selected,
    })
    return record


def window_times(start: float, end: float, count: int) -> list[float]:
    return [start + (end - start) * (index + 0.5) / count for index in range(count)]


def build_p15(config: dict[str, Any], job: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    record = source_record(config, job, result)
    duration = record["durationSeconds"]
    if duration <= 1:
        raise RuntimeError("P15 duration is invalid")
    allocation = {
        "elevated-city-water-panorama": 20,
        "settlement-road-watchtower-water": 36,
        "wooden-commercial-workshop-water-access": 48,
        "elevated-tiled-roof-compound": 32,
        "roof-and-compound-connectivity": 24,
    }
    selected: list[dict[str, Any]] = []
    used: set[float] = set()
    for window in config["candidateWindows"]:
        window_id = str(window["id"])
        for timestamp in window_times(float(window["startSeconds"]), float(window["endSeconds"]), allocation[window_id]):
            if not add(selected, used, timestamp, duration, "candidateWindow", windowId=window_id,
                       windowPriority=window["priority"], reviewPurpose="human-reviewed urban/waterfront candidate"):
                raise RuntimeError(f"duplicate P15 candidate timestamp in {window_id}")
    for window in config["contextWindows"]:
        window_id = str(window["id"])
        for timestamp in window_times(float(window["startSeconds"]), float(window["endSeconds"]), 8):
            if not add(selected, used, timestamp, duration, "contextWindow", windowId=window_id,
                       reviewPurpose="identity correlation only; not a geometry source"):
                raise RuntimeError(f"duplicate P15 context timestamp in {window_id}")
    selected.sort(key=lambda row: row["time"])
    if len(selected) != int(config["frameCount"]):
        raise RuntimeError(f"P15 timestamp count mismatch: {len(selected)}/{config['frameCount']}")

    counts = Counter(str(row["windowId"]) for row in selected)
    gates = config["hardGates"]
    priorities = {str(row["id"]): str(row["priority"]) for row in config["candidateWindows"]}
    checks = {
        "allCandidateWindowsRepresented": all(counts[str(row["id"])] > 0 for row in config["candidateWindows"]),
        "allContextWindowsRepresented": all(counts[str(row["id"])] > 0 for row in config["contextWindows"]),
        "criticalMinimum": all(counts[key] >= int(gates["minimumFramesPerCriticalWindow"]) for key, value in priorities.items() if value == "critical"),
        "highMinimum": all(counts[key] >= int(gates["minimumFramesPerHighWindow"]) for key, value in priorities.items() if value == "high"),
        "mediumMinimum": all(counts[key] >= int(gates["minimumFramesPerMediumWindow"]) for key, value in priorities.items() if value == "medium"),
    }
    if not all(checks.values()):
        raise RuntimeError(f"P15 window gates failed: {checks}, counts={dict(counts)}")
    record.update({
        "frameCount": len(selected),
        "windowCounts": dict(sorted(counts.items())),
        "checks": checks,
        "timestamps": selected,
    })
    return record


def main() -> int:
    plan = load(PLAN_PATH)
    jobs: list[dict[str, Any]] = []
    for config in plan["jobs"]:
        job = load(ROOT / config["jobPath"])
        result = load(ROOT / config["resultPath"])
        if result.get("source", {}).get("authorizationId") != plan["authorizationId"]:
            raise RuntimeError(f"authorization mismatch for {config['id']}")
        jobs.append(build_p13(config, job, result) if config["strategy"] == "full-duration-stratified" else build_p15(config, job, result))

    payload = {
        "schemaVersion": 1,
        "status": "correction-timestamp-plan-ready",
        "stage": plan["stage"],
        "authorizationId": plan["authorizationId"],
        "sourceVisualReview": plan["sourceVisualReview"],
        "counts": {
            "jobs": len(jobs),
            "frames": sum(row["frameCount"] for row in jobs),
            "contactSheets": sum(row["contactSheetCount"] for row in jobs),
        },
        "jobs": jobs,
        "safety": {
            "pixelsRead": False,
            "pixelsGenerated": False,
            "geometryGenerated": False,
            "existingCoordinatesModified": False,
        },
        "nextAction": "download P13 and P15 transiently by explicit CID and extract one-day correction review artifacts",
    }
    write(ROOT / plan["outputs"]["timestampPlan"], payload)
    print(json.dumps({"status": payload["status"], "counts": payload["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
