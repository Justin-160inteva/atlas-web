#!/usr/bin/env python3
"""Build a deterministic, pixel-free full-duration review plan for authorized P06."""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "data/geospatial/geospatial-2p5d-sakai-p006-scan-plan.json"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def add(rows: list[dict[str, Any]], used: set[float], value: float, duration: float, bucket: str, **extra: Any) -> bool:
    timestamp = round(max(0.5, min(duration - 0.5, float(value))), 3)
    if timestamp in used:
        return False
    rows.append({"time": timestamp, "bucket": bucket, **extra})
    used.add(timestamp)
    return True


def count_locations(rows: list[dict[str, Any]], scope: dict[str, Any]) -> int:
    bounds = scope["normalizedBounds"]
    return sum(
        1 for row in rows
        if isinstance(row.get("atlas_x"), (int, float))
        and isinstance(row.get("atlas_y"), (int, float))
        and bounds["minX"] <= row["atlas_x"] <= bounds["maxX"]
        and bounds["minY"] <= row["atlas_y"] <= bounds["maxY"]
    )


def main() -> int:
    plan = load(PLAN_PATH)
    source = plan["source"]
    sampling = plan["sampling"]
    gates = plan["hardGates"]
    job = load(ROOT / source["jobPath"])
    result = load(ROOT / source["resultPath"])
    locations = load(ROOT / "data/locations.json")
    authorizations = load(ROOT / "data/authorizations.json")
    authorization = next(row for row in authorizations["records"] if row["id"] == plan["authorizationId"])

    required_scope = (
        "localDownloadAndAnalysis", "downloadFromPublicVideoPage", "computerVisionAnalysis",
        "privateLowResolutionKeyframes", "original2DVectorReconstruction", "original3DReconstruction",
        "roadReconstruction", "terrainReconstruction", "waterAndBoundaryReconstruction",
        "geospatialAnchoring", "publicDerivedMapPublication", "publicDerivedDataPublication",
    )
    if authorization["status"] != "active" or any(authorization["scope"].get(key) is not True for key in required_scope):
        raise RuntimeError("P06 authorization does not cover the planned evidence and modeling operations")
    if job["id"] != source["jobId"] or job["authorizationId"] != plan["authorizationId"]:
        raise RuntimeError("P06 job identity or authorization drifted")
    if result["jobId"] != source["jobId"] or result["source"]["authorizationId"] != plan["authorizationId"]:
        raise RuntimeError("P06 result identity or authorization drifted")
    batch = job["batch"]
    if batch["page"] != source["expectedPage"] or batch["cid"] != source["expectedCid"]:
        raise RuntimeError("P06 page/CID drifted")
    duration = float(result["media"]["durationSeconds"])
    if abs(duration - float(source["expectedDurationSeconds"])) > 0.01:
        raise RuntimeError("P06 duration drifted")
    pilot_count = count_locations(locations, plan["pilotScope"])
    evidence_count = count_locations(locations, plan["evidenceScope"])
    if pilot_count != int(plan["pilotScope"]["locationTarget"]):
        raise RuntimeError(f"P06 parent-tile location count drifted: {pilot_count}")
    if evidence_count != int(plan["evidenceScope"]["locationTarget"]):
        raise RuntimeError(f"P06 Sakai-core location count drifted: {evidence_count}")

    selected: list[dict[str, Any]] = []
    used: set[float] = set()
    uniform_count = int(sampling["uniformFullDuration"])
    for index in range(uniform_count):
        add(selected, used, duration * (index + 0.5) / uniform_count, duration, "uniformFullDuration",
            sequence=index + 1, sequenceCount=uniform_count)

    for row in sorted(result.get("clearFrameTimes") or [], key=lambda item: (-float(item.get("sharpness") or 0), float(item.get("time") or 0))):
        if sum(item["bucket"] == "sharp" for item in selected) >= int(sampling["sharp"]):
            break
        add(selected, used, row["time"], duration, "sharp", sharpness=float(row.get("sharpness") or 0), edgeDensity=float(row.get("edgeDensity") or 0))

    for row in sorted(result.get("descriptors") or [], key=lambda item: (-float(item.get("difference") or 0), float(item.get("time") or 0))):
        if sum(item["bucket"] == "sceneTransition" for item in selected) >= int(sampling["sceneTransition"]):
            break
        add(selected, used, row["time"], duration, "sceneTransition", difference=float(row.get("difference") or 0), sharpness=float(row.get("sharpness") or 0), edgeDensity=float(row.get("edgeDensity") or 0))

    target = int(sampling["frameCount"])
    for index in range(target * 8):
        if len(selected) >= target:
            break
        add(selected, used, duration * (index + 0.5) / (target * 8), duration, "coverageFill")
    selected.sort(key=lambda row: row["time"])
    if len(selected) != target:
        raise RuntimeError(f"P06 timestamp count mismatch: {len(selected)}/{target}")

    quarters = Counter(min(3, int(row["time"] / duration * 4)) for row in selected)
    eighths = Counter(min(7, int(row["time"] / duration * 8)) for row in selected)
    covered_fraction = (selected[-1]["time"] - selected[0]["time"]) / duration
    checks = {
        "coveredDurationFraction": covered_fraction >= float(gates["minimumCoveredDurationFraction"]),
        "minimumFramesPerQuarter": all(quarters[index] >= int(gates["minimumFramesPerQuarter"]) for index in range(4)),
        "minimumFramesPerEighth": all(eighths[index] >= int(gates["minimumFramesPerEighth"]) for index in range(8)),
    }
    if not all(checks.values()):
        raise RuntimeError(f"P06 coverage gates failed: {checks}")

    payload = {
        "schemaVersion": 1,
        "status": "p006-authorized-timestamp-plan-ready",
        "stage": plan["stage"],
        "authorizationId": plan["authorizationId"],
        "source": {
            "scanId": source["scanId"], "jobId": job["id"], "jobPath": source["jobPath"],
            "resultPath": source["resultPath"], "page": batch["page"], "cid": batch["cid"],
            "durationSeconds": duration,
        },
        "counts": {
            "frames": len(selected), "contactSheets": int(sampling["contactSheetCount"]),
            "quarters": {str(index + 1): quarters[index] for index in range(4)},
            "eighths": {str(index + 1): eighths[index] for index in range(8)},
            "buckets": dict(sorted(Counter(row["bucket"] for row in selected).items())),
        },
        "coverage": {
            "firstSecond": selected[0]["time"], "lastSecond": selected[-1]["time"],
            "coveredDurationFraction": round(covered_fraction, 6), "checks": checks,
        },
        "extraction": {
            key: sampling[key] for key in (
                "frameWidth", "frameHeight", "contactSheetColumns", "contactSheetRows",
                "contactSheetCount", "jpegQuality", "artifactRetentionDays",
            )
        },
        "timestamps": selected,
        "safety": {"pixelsRead": False, "pixelsGenerated": False, "geometryGenerated": False, "existingCoordinatesModified": False},
        "nextAction": "extract a one-day private review artifact, then record only non-pixel multi-view landmark correspondences",
    }
    output = ROOT / plan["outputs"]["timestampPlan"]
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    dense_sampling = plan["denseSampling"]
    dense_rows: list[dict[str, Any]] = []
    dense_used: set[float] = set()
    for window in dense_sampling["windows"]:
        start = float(window["startSeconds"])
        end = float(window["endSeconds"])
        step = float(window["stepSeconds"])
        sample_count = math.floor((end - start) / step) + 1
        for index in range(sample_count):
            add(
                dense_rows, dense_used, start + index * step, duration, "denseWindow",
                windowId=window["id"], purpose=window["purpose"],
            )
    dense_rows.sort(key=lambda row: row["time"])
    per_sheet = int(dense_sampling["contactSheetColumns"]) * int(dense_sampling["contactSheetRows"])
    dense_sheet_count = math.ceil(len(dense_rows) / per_sheet)
    dense_payload = {
        "schemaVersion": 1,
        "status": "p006-authorized-dense-timestamp-plan-ready",
        "stage": "2p5d-sakai-p006-authorized-dense-evidence",
        "authorizationId": plan["authorizationId"],
        "source": payload["source"],
        "scopeCounts": {"parentPilotTile": pilot_count, "sakaiUrbanCore": evidence_count},
        "counts": {
            "frames": len(dense_rows),
            "contactSheets": dense_sheet_count,
            "windows": dict(sorted(Counter(row["windowId"] for row in dense_rows).items())),
        },
        "extraction": {
            "frameWidth": dense_sampling["frameWidth"],
            "frameHeight": dense_sampling["frameHeight"],
            "contactSheetColumns": dense_sampling["contactSheetColumns"],
            "contactSheetRows": dense_sampling["contactSheetRows"],
            "contactSheetCount": dense_sheet_count,
            "jpegQuality": dense_sampling["jpegQuality"],
            "artifactRetentionDays": dense_sampling["artifactRetentionDays"],
        },
        "timestamps": dense_rows,
        "safety": payload["safety"],
        "nextAction": "review repeated Sakai structures and record a non-pixel correspondence graph before geometry",
    }
    dense_output = ROOT / plan["outputs"]["denseTimestampPlan"]
    dense_output.write_text(json.dumps(dense_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"], "counts": payload["counts"], "coverage": payload["coverage"],
        "denseStatus": dense_payload["status"], "denseCounts": dense_payload["counts"],
        "scopeCounts": dense_payload["scopeCounts"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
