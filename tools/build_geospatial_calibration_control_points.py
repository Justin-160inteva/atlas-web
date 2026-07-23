#!/usr/bin/env python3
"""Build a deterministic calibration/validation split from the 50 confirmed anchors.

This stage prepares normalized Atlas control points only. It deliberately does not invent pixel
coordinates or a homography before the final original map base has fixed dimensions and crop.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
PROGRESS_PATH = ROOT / "data/geospatial/geospatial-progress.json"
CONTROL_PATH = ROOT / "data/geospatial/geospatial-calibration-control-points.json"
READINESS_PATH = ROOT / "data/geospatial/geospatial-calibration-readiness.json"

CONTROL_TARGET = 24
HOLDOUT_TARGET = 12
EXPECTED_ANCHORS = 50


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object in {path}")
    return value


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def point(row: dict[str, Any]) -> tuple[float, float]:
    return float(row["atlas"]["x"]), float(row["atlas"]["y"])


def distance(left: dict[str, Any], right: dict[str, Any]) -> float:
    lx, ly = point(left)
    rx, ry = point(right)
    return math.hypot(lx - rx, ly - ry)


def distance_xy(row: dict[str, Any], xy: tuple[float, float]) -> float:
    x, y = point(row)
    return math.hypot(x - xy[0], y - xy[1])


def nearest_distance(row: dict[str, Any], selected: Iterable[dict[str, Any]]) -> float:
    values = [distance(row, other) for other in selected]
    return min(values) if values else float("inf")


def cross(origin: tuple[float, float], left: tuple[float, float], right: tuple[float, float]) -> float:
    return (left[0] - origin[0]) * (right[1] - origin[1]) - (left[1] - origin[1]) * (right[0] - origin[0])


def convex_hull(rows: Iterable[dict[str, Any]]) -> list[tuple[float, float]]:
    coordinates = sorted({point(row) for row in rows})
    if len(coordinates) <= 1:
        return coordinates
    lower: list[tuple[float, float]] = []
    for coordinate in coordinates:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], coordinate) <= 0:
            lower.pop()
        lower.append(coordinate)
    upper: list[tuple[float, float]] = []
    for coordinate in reversed(coordinates):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], coordinate) <= 0:
            upper.pop()
        upper.append(coordinate)
    return lower[:-1] + upper[:-1]


def polygon_area(vertices: list[tuple[float, float]]) -> float:
    if len(vertices) < 3:
        return 0.0
    return abs(sum(
        vertices[index][0] * vertices[(index + 1) % len(vertices)][1]
        - vertices[(index + 1) % len(vertices)][0] * vertices[index][1]
        for index in range(len(vertices))
    )) / 2.0


def bbox(rows: Iterable[dict[str, Any]]) -> dict[str, float]:
    coordinates = [point(row) for row in rows]
    xs = [value[0] for value in coordinates]
    ys = [value[1] for value in coordinates]
    minimum_x, maximum_x = min(xs), max(xs)
    minimum_y, maximum_y = min(ys), max(ys)
    return {
        "minimumX": minimum_x,
        "maximumX": maximum_x,
        "minimumY": minimum_y,
        "maximumY": maximum_y,
        "width": maximum_x - minimum_x,
        "height": maximum_y - minimum_y,
        "area": (maximum_x - minimum_x) * (maximum_y - minimum_y),
    }


def pairwise_nearest_distances(rows: list[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for index, row in enumerate(rows):
        others = rows[:index] + rows[index + 1:]
        values.append(nearest_distance(row, others))
    return values


def quadrant(row: dict[str, Any]) -> str:
    x, y = point(row)
    horizontal = "west" if x < 0.5 else "east"
    vertical = "north" if y < 0.5 else "south"
    return f"{vertical}-{horizontal}"


def serialize_anchor(row: dict[str, Any], role: str, order: int) -> dict[str, Any]:
    return {
        "order": order,
        "role": role,
        "locationId": row["locationId"],
        "title": row["title"],
        "regionId": row["regionId"],
        "regionTitle": row["regionTitle"],
        "atlas": {"x": float(row["atlas"]["x"]), "y": float(row["atlas"]["y"])},
        "confidence": float(row["confidence"]),
        "sourceName": row["sourceName"],
        "sourcePath": row["sourcePath"],
        "sourceVideoPosition": row.get("sourceVideoPosition"),
        "resolutionMethod": row["resolutionMethod"],
    }


def main() -> int:
    progress = load(PROGRESS_PATH)
    if progress.get("status") != "phase1-complete":
        raise RuntimeError("geospatial phase one must be complete before calibration splitting")
    if progress.get("phase1") != {
        "targetConfirmedAnchors": 50,
        "confirmedAnchors": 50,
        "remainingToTarget": 0,
        "progressPercent": 100.0,
        "nextSource": None,
    }:
        raise RuntimeError("authoritative phase-one state changed")

    anchors = list(progress.get("anchors", []))
    if len(anchors) != EXPECTED_ANCHORS:
        raise RuntimeError(f"expected {EXPECTED_ANCHORS} anchors, found {len(anchors)}")
    ids = [str(row["locationId"]) for row in anchors]
    coordinates = [point(row) for row in anchors]
    if len(set(ids)) != EXPECTED_ANCHORS or len(set(coordinates)) != EXPECTED_ANCHORS:
        raise RuntimeError("anchor pool contains duplicate locations or coordinates")
    if any(not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0) for x, y in coordinates):
        raise RuntimeError("anchor coordinate lies outside normalized Atlas bounds")
    if any(float(row.get("confidence", 0.0)) < 0.92 for row in anchors):
        raise RuntimeError("anchor pool contains confidence below 0.92")

    by_id = {str(row["locationId"]): row for row in anchors}
    role_by_id: dict[str, str] = {}
    selected_ids: list[str] = []

    def select(row: dict[str, Any], role: str) -> None:
        location_id = str(row["locationId"])
        if location_id not in role_by_id:
            selected_ids.append(location_id)
            role_by_id[location_id] = role

    # Preserve global boundary geometry first.
    extremes = [
        (min(anchors, key=lambda row: (point(row)[0], point(row)[1])), "boundary-min-x"),
        (max(anchors, key=lambda row: (point(row)[0], -point(row)[1])), "boundary-max-x"),
        (min(anchors, key=lambda row: (point(row)[1], point(row)[0])), "boundary-min-y"),
        (max(anchors, key=lambda row: (point(row)[1], -point(row)[0])), "boundary-max-y"),
    ]
    for row, role in extremes:
        select(row, role)

    # Guarantee every represented game region has a control point near its regional centroid.
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in anchors:
        grouped[str(row["regionTitle"])].append(row)
    for region in sorted(grouped):
        rows = grouped[region]
        centroid = (
            statistics.fmean(point(row)[0] for row in rows),
            statistics.fmean(point(row)[1] for row in rows),
        )
        representative = min(rows, key=lambda row: (distance_xy(row, centroid), str(row["locationId"])))
        select(representative, "regional-representative")

    # Fill remaining controls with deterministic farthest-point sampling.
    while len(selected_ids) < CONTROL_TARGET:
        selected = [by_id[location_id] for location_id in selected_ids]
        candidates = [row for row in anchors if str(row["locationId"]) not in role_by_id]
        chosen = max(
            candidates,
            key=lambda row: (
                nearest_distance(row, selected),
                float(row["confidence"]),
                str(row["locationId"]),
            ),
        )
        select(chosen, "spatial-fill")

    controls = [by_id[location_id] for location_id in selected_ids]
    remaining = [row for row in anchors if str(row["locationId"]) not in role_by_id]

    # Select spatially distributed holdouts without changing the control fit.
    holdouts: list[dict[str, Any]] = []
    while len(holdouts) < HOLDOUT_TARGET:
        chosen = max(
            remaining,
            key=lambda row: (
                nearest_distance(row, controls + holdouts),
                float(row["confidence"]),
                str(row["locationId"]),
            ),
        )
        holdouts.append(chosen)
        remaining.remove(chosen)
    reserves = sorted(remaining, key=lambda row: (str(row["regionTitle"]), str(row["locationId"])))

    all_hull = convex_hull(anchors)
    control_hull = convex_hull(controls)
    all_hull_area = polygon_area(all_hull)
    control_hull_area = polygon_area(control_hull)
    hull_ratio = control_hull_area / all_hull_area if all_hull_area else 0.0
    control_nearest = pairwise_nearest_distances(controls)
    holdout_to_control = [nearest_distance(row, controls) for row in holdouts]
    region_counts = Counter(str(row["regionTitle"]) for row in anchors)
    control_region_counts = Counter(str(row["regionTitle"]) for row in controls)
    quadrant_counts = Counter(quadrant(row) for row in controls)

    missing_control_regions = sorted(set(region_counts) - set(control_region_counts))
    missing_quadrants = sorted({"north-west", "north-east", "south-west", "south-east"} - set(quadrant_counts))
    gates = {
        "anchorPoolExactly50": len(anchors) == 50,
        "controlPointsExactly24": len(controls) == CONTROL_TARGET,
        "validationHoldoutsExactly12": len(holdouts) == HOLDOUT_TARGET,
        "reservePointsExactly14": len(reserves) == 14,
        "allLocationIdsUniqueAcrossSplits": len({str(row["locationId"]) for row in controls + holdouts + reserves}) == 50,
        "allCoordinatesUniqueAcrossSplits": len({point(row) for row in controls + holdouts + reserves}) == 50,
        "allRegionsRepresentedInControlSet": not missing_control_regions,
        "allQuadrantsRepresentedInControlSet": not missing_quadrants,
        "controlHullCoversAtLeast90Percent": hull_ratio >= 0.90,
        "allConfidenceAtLeast092": all(float(row["confidence"]) >= 0.92 for row in anchors),
        "repositoryContainsPixels": False,
    }
    positive_gates = {key: value for key, value in gates.items() if key != "repositoryContainsPixels"}
    if not all(positive_gates.values()) or gates["repositoryContainsPixels"] is not False:
        raise RuntimeError(f"calibration split gates failed: {gates}")

    timestamp = now()
    control_document = {
        "schemaVersion": 1,
        "generatedAt": timestamp,
        "status": "calibration-control-point-set-ready",
        "stage": "normalized-control-and-holdout-selection",
        "source": {
            "progressPath": "data/geospatial/geospatial-progress.json",
            "confirmedAnchorPool": 50,
            "coordinateSystem": "atlas-normalized-top-left-origin",
        },
        "counts": {
            "anchorPool": 50,
            "calibrationControlPoints": len(controls),
            "validationHoldouts": len(holdouts),
            "reservePoints": len(reserves),
            "regions": len(region_counts),
        },
        "selectionPolicy": {
            "boundaryExtremes": True,
            "regionalCentroidRepresentatives": True,
            "deterministicFarthestPointFill": True,
            "holdoutsExcludedFromCalibrationFit": True,
            "minimumAnchorConfidence": 0.92,
        },
        "calibrationControlPoints": [
            serialize_anchor(row, role_by_id[str(row["locationId"])], index)
            for index, row in enumerate(controls, start=1)
        ],
        "validationHoldouts": [
            serialize_anchor(row, "validation-holdout", index)
            for index, row in enumerate(holdouts, start=1)
        ],
        "reservePoints": [
            serialize_anchor(row, "reserve", index)
            for index, row in enumerate(reserves, start=1)
        ],
        "pixelTransformContract": {
            "status": "blocked-pending-final-base-dimensions-and-crop",
            "normalizedToPixelFormula": {
                "x": "atlas.x * (finalBaseWidthPx - 1)",
                "y": "atlas.y * (finalBaseHeightPx - 1)",
            },
            "candidateModelsInOrder": ["similarity", "affine", "projective-homography"],
            "selectionRule": "choose the lowest-complexity model that passes independent holdout residual gates",
            "requiredInputs": [
                "finalBaseWidthPx",
                "finalBaseHeightPx",
                "finalBaseCropBox",
                "pixelObservationForEachControlPoint",
            ],
            "acceptancePolicy": {
                "maximumMedianNormalizedHoldoutResidual": 0.0025,
                "maximumP95NormalizedHoldoutResidual": 0.005,
                "noAxisInversion": True,
                "noFoldover": True,
                "all12HoldoutsRequired": True,
            },
        },
    }

    readiness = {
        "schemaVersion": 1,
        "generatedAt": timestamp,
        "status": "control-points-ready-pixel-calibration-blocked",
        "stage": "coordinate-and-overlay-calibration-readiness",
        "counts": control_document["counts"],
        "distribution": {
            "anchorRegions": dict(sorted(region_counts.items())),
            "controlRegions": dict(sorted(control_region_counts.items())),
            "controlQuadrants": dict(sorted(quadrant_counts.items())),
            "missingControlRegions": missing_control_regions,
            "missingControlQuadrants": missing_quadrants,
        },
        "geometry": {
            "allAnchorBoundingBox": bbox(anchors),
            "controlBoundingBox": bbox(controls),
            "allAnchorConvexHullArea": round(all_hull_area, 8),
            "controlConvexHullArea": round(control_hull_area, 8),
            "controlToAllHullAreaRatio": round(hull_ratio, 8),
            "controlNearestNeighborMinimum": round(min(control_nearest), 8),
            "controlNearestNeighborMedian": round(statistics.median(control_nearest), 8),
            "holdoutToControlDistanceMedian": round(statistics.median(holdout_to_control), 8),
            "holdoutToControlDistanceMaximum": round(max(holdout_to_control), 8),
        },
        "gates": gates,
        "blockingItems": [
            "final original ultra-HD base dimensions are not fixed",
            "final base crop and overlay origin are not fixed",
            "control-point pixel observations do not exist yet",
            "12-point holdout residual validation cannot run before a transform exists",
        ],
        "nextAction": "fix final base dimensions/crop, measure 24 control pixels, fit transform, validate on 12 holdouts",
        "safety": {
            "noPixelCoordinatesInvented": True,
            "noTransformClaimed": True,
            "finalBaseStillNotStarted": progress["stageGates"]["finalOriginalUltraHdBase"]["status"] == "not_started",
            "repositoryContainsPixels": False,
        },
    }

    progress["generatedAt"] = timestamp
    progress["stageGates"]["coordinateAndOverlayCalibration"] = {
        "status": "in_progress",
        "controlPointSetStatus": "ready",
        "confirmedAnchorPool": 50,
        "calibrationControlPoints": len(controls),
        "validationHoldouts": len(holdouts),
        "reservePoints": len(reserves),
        "pixelTransformStatus": "blocked_pending_final_base_dimensions_and_crop",
        "controlPointPath": "data/geospatial/geospatial-calibration-control-points.json",
        "readinessPath": "data/geospatial/geospatial-calibration-readiness.json",
    }
    progress["stageGates"]["finalOriginalUltraHdBase"] = {"status": "not_started"}

    write(CONTROL_PATH, control_document)
    write(READINESS_PATH, readiness)
    write(PROGRESS_PATH, progress)
    print(json.dumps({
        "status": readiness["status"],
        "counts": readiness["counts"],
        "hullCoverage": readiness["geometry"]["controlToAllHullAreaRatio"],
        "regions": readiness["distribution"]["controlRegions"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
