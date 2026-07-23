#!/usr/bin/env python3
"""Build a deterministic construction skeleton for Atlas's fully original map artwork.

Only factual repository point coordinates are consumed. Third-party map pixels, vectors and the
geometry field in regions.json are intentionally ignored. Region hulls are construction guides,
not final coastlines or official boundaries.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TRIGGER_PATH = ROOT / "data/geospatial/geospatial-original-authored-base-trigger.json"
PLAN_PATH = ROOT / "data/geospatial/geospatial-original-authored-base-plan.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite_unit(value: Any, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0 or number > 1:
        raise RuntimeError(f"{label} must be finite and inside [0,1], got {value!r}")
    return number


def location_point(row: dict[str, Any]) -> tuple[float, float]:
    if "atlas_x" in row and "atlas_y" in row:
        return finite_unit(row["atlas_x"], "atlas_x"), finite_unit(row["atlas_y"], "atlas_y")
    atlas = row.get("atlas")
    if isinstance(atlas, dict) and "x" in atlas and "y" in atlas:
        return finite_unit(atlas["x"], "atlas.x"), finite_unit(atlas["y"], "atlas.y")
    raise RuntimeError(f"location {row.get('id')} has no Atlas coordinates")


def cross(origin: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    return (a[0] - origin[0]) * (b[1] - origin[1]) - (a[1] - origin[1]) * (b[0] - origin[0])


def convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    unique = sorted(set(points))
    if len(unique) <= 1:
        return unique
    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def polygon_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    return abs(
        sum(
            points[index][0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * points[index][1]
            for index in range(len(points))
        )
    ) / 2


def rounded_point(point: tuple[float, float]) -> dict[str, float]:
    return {"x": round(point[0], 8), "y": round(point[1], 8)}


def normalize_regions(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [row for row in raw if isinstance(row, dict)]
    if isinstance(raw, dict):
        for key in ("regions", "items", "data"):
            value = raw.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    raise RuntimeError("regions input must be a list or contain a regions/items/data list")


def region_title(row: dict[str, Any]) -> str:
    for key in ("title", "name", "label"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(row.get("id", "unknown-region"))


def density_grid(points: list[tuple[float, float]], size: int) -> list[list[int]]:
    grid = [[0 for _ in range(size)] for _ in range(size)]
    for x, y in points:
        column = min(size - 1, int(x * size))
        row = min(size - 1, int(y * size))
        grid[row][column] += 1
    return grid


def main() -> int:
    trigger = load_json(TRIGGER_PATH)
    plan = load_json(PLAN_PATH)
    inputs = trigger["inputs"]
    expected = trigger["expected"]
    outputs = trigger["outputs"]

    locations_path = ROOT / inputs["locationsPath"]
    regions_path = ROOT / inputs["regionsPath"]
    progress_path = ROOT / inputs["progressPath"]
    controls_path = ROOT / inputs["calibrationControlPointsPath"]
    output_path = ROOT / outputs["skeletonPath"]

    locations = load_json(locations_path)
    if not isinstance(locations, list):
        raise RuntimeError("locations input must be a list")
    if len(locations) != expected["locations"]:
        raise RuntimeError(f"expected {expected['locations']} locations, found {len(locations)}")

    region_rows = normalize_regions(load_json(regions_path))
    region_names = {
        str(row["id"]): region_title(row)
        for row in region_rows
        if row.get("id") is not None
    }

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unassigned: list[dict[str, Any]] = []
    all_points: list[tuple[float, float]] = []
    seen_ids: set[str] = set()

    for row in locations:
        if not isinstance(row, dict):
            raise RuntimeError("every location must be an object")
        location_id = str(row.get("id", ""))
        if not location_id or location_id in seen_ids:
            raise RuntimeError(f"missing or duplicate location id: {location_id!r}")
        seen_ids.add(location_id)
        point = location_point(row)
        row_copy = dict(row)
        row_copy["_point"] = point
        all_points.append(point)

        raw_region_id = row.get("region_id")
        if raw_region_id is None or str(raw_region_id).strip() == "":
            unassigned.append(row_copy)
        else:
            grouped[str(raw_region_id)].append(row_copy)

    if len(grouped) != expected["regions"]:
        raise RuntimeError(
            f"expected {expected['regions']} real represented regions, found {len(grouped)}: {sorted(grouped)}"
        )
    if len(unassigned) != expected["unassignedLocations"]:
        raise RuntimeError(
            f"expected {expected['unassignedLocations']} unassigned locations, found {len(unassigned)}"
        )

    progress = load_json(progress_path)
    anchors = progress.get("anchors")
    if not isinstance(anchors, list) or len(anchors) != expected["confirmedAnchors"]:
        raise RuntimeError(
            f"expected {expected['confirmedAnchors']} confirmed anchors, "
            f"found {len(anchors) if isinstance(anchors, list) else 'invalid'}"
        )
    anchor_counts: dict[str, int] = defaultdict(int)
    for anchor in anchors:
        anchor_counts[str(anchor["regionId"])] += 1

    regions_output: list[dict[str, Any]] = []
    centroids: dict[str, tuple[float, float]] = {}

    for region_id in sorted(grouped):
        rows = grouped[region_id]
        points = [row["_point"] for row in rows]
        hull = convex_hull(points)
        centroid = (
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        )
        centroids[region_id] = centroid
        minimum_x = min(point[0] for point in points)
        maximum_x = max(point[0] for point in points)
        minimum_y = min(point[1] for point in points)
        maximum_y = max(point[1] for point in points)

        def extreme(axis: int, minimum: bool) -> dict[str, Any]:
            key = lambda item: (item["_point"][axis], str(item["id"]))
            selected = min(rows, key=key) if minimum else max(rows, key=key)
            return {"locationId": selected["id"], **rounded_point(selected["_point"])}

        regions_output.append(
            {
                "regionId": region_id,
                "regionTitle": region_names.get(region_id, region_id),
                "locationCount": len(rows),
                "confirmedAnchorCount": anchor_counts.get(region_id, 0),
                "centroid": rounded_point(centroid),
                "boundingBox": {
                    "minimumX": round(minimum_x, 8),
                    "maximumX": round(maximum_x, 8),
                    "minimumY": round(minimum_y, 8),
                    "maximumY": round(maximum_y, 8),
                    "width": round(maximum_x - minimum_x, 8),
                    "height": round(maximum_y - minimum_y, 8),
                },
                "constructionHull": [rounded_point(point) for point in hull],
                "constructionHullArea": round(polygon_area(hull), 8),
                "extremeGuides": {
                    "minimumX": extreme(0, True),
                    "maximumX": extreme(0, False),
                    "minimumY": extreme(1, True),
                    "maximumY": extreme(1, False),
                },
                "boundaryMeaning": "location-distribution construction envelope only; not a copied or final game boundary",
            }
        )

    nearest_count = int(expected["nearestRegionNeighbors"])
    edge_keys: set[tuple[str, str]] = set()
    for region_id, centroid in centroids.items():
        nearest = sorted(
            (
                (math.hypot(centroid[0] - other[0], centroid[1] - other[1]), other_id)
                for other_id, other in centroids.items()
                if other_id != region_id
            ),
            key=lambda item: (item[0], item[1]),
        )[:nearest_count]
        for _, other_id in nearest:
            edge_keys.add(tuple(sorted((region_id, other_id))))

    adjacency = []
    for left, right in sorted(edge_keys):
        distance = math.hypot(
            centroids[left][0] - centroids[right][0],
            centroids[left][1] - centroids[right][1],
        )
        adjacency.append(
            {
                "fromRegionId": left,
                "toRegionId": right,
                "centroidDistance": round(distance, 8),
                "meaning": "composition-neighbor suggestion only",
            }
        )

    unassigned_guides = [
        {
            "locationId": row["id"],
            "title": row.get("title"),
            "categoryId": row.get("category_id"),
            **rounded_point(row["_point"]),
            "meaning": "global construction point pending region classification; excluded from region hulls",
        }
        for row in sorted(unassigned, key=lambda item: str(item["id"]))
    ]

    anchor_covered_regions = sorted(
        row["regionId"] for row in regions_output if row["confirmedAnchorCount"] > 0
    )
    unanchored_regions = sorted(
        row["regionId"] for row in regions_output if row["confirmedAnchorCount"] == 0
    )
    if len(anchor_covered_regions) != expected["confirmedAnchorCoveredRegions"]:
        raise RuntimeError(
            f"expected {expected['confirmedAnchorCoveredRegions']} anchor-covered regions, "
            f"found {len(anchor_covered_regions)}"
        )
    if unanchored_regions != sorted(expected["unanchoredRegionIds"]):
        raise RuntimeError(
            f"unexpected unanchored regions: expected {sorted(expected['unanchoredRegionIds'])}, "
            f"found {unanchored_regions}"
        )

    grid_size = int(expected["densityGridSize"])
    global_hull = convex_hull(all_points)
    skeleton = {
        "schemaVersion": 1,
        "generatedAt": trigger["requestedAt"],
        "status": "original-authored-spatial-skeleton-ready",
        "stage": "fully-original-map-spatial-construction",
        "strategy": plan["strategy"],
        "coordinateSystem": "atlas-normalized-top-left-origin",
        "sourceHashes": {
            inputs["locationsPath"]: sha256(locations_path),
            inputs["regionsPath"]: sha256(regions_path),
            inputs["progressPath"]: sha256(progress_path),
            inputs["calibrationControlPointsPath"]: sha256(controls_path),
            trigger["strategyPath"]: sha256(PLAN_PATH),
        },
        "counts": {
            "locations": len(locations),
            "regionAssignedLocations": sum(len(rows) for rows in grouped.values()),
            "unassignedLocations": len(unassigned_guides),
            "regions": len(regions_output),
            "confirmedAnchorCoveredRegions": len(anchor_covered_regions),
            "confirmedAnchors": len(anchors),
            "regionAdjacencyEdges": len(adjacency),
            "densityGridSize": grid_size,
        },
        "globalConstructionEnvelope": {
            "hull": [rounded_point(point) for point in global_hull],
            "area": round(polygon_area(global_hull), 8),
            "meaning": "point-distribution guide only; final coastline and silhouette must be authored",
        },
        "regions": regions_output,
        "anchorCoveredRegionIds": anchor_covered_regions,
        "unanchoredRegionIds": unanchored_regions,
        "unassignedLocationGuides": unassigned_guides,
        "compositionAdjacency": adjacency,
        "locationDensityGrid": {
            "size": grid_size,
            "origin": "top-left",
            "rows": density_grid(all_points, grid_size),
            "meaning": "location density guide for authored visual hierarchy; not terrain evidence",
        },
        "nextArtStage": {
            "status": "ready_for_original_regional_composition",
            "requiredDecisions": [
                "classify or intentionally retain the five unassigned global locations",
                "author original outer land silhouette and water negative space",
                "author ten region masses without tracing third-party map boundaries",
                "define original terrain hierarchy and travel corridors",
                "approve a repository-owned editable source format before raster export",
            ],
        },
        "safety": {
            "thirdPartyMapPixelsRead": False,
            "thirdPartyMapVectorsRead": False,
            "legacyRenderBaseUsedForGeometry": False,
            "regionsJsonGeometryUsed": False,
            "finalCoastlineClaimed": False,
            "finalRegionBoundariesClaimed": False,
            "pixelCoordinatesInvented": False,
            "repositoryPixelsModified": False,
        },
    }
    write_json(output_path, skeleton)

    stage_gates = progress.setdefault("stageGates", {})
    stage_gates["finalOriginalUltraHdBase"] = {
        "status": "in_progress",
        "strategy": "fully_original_authored_visual_base",
        "strategyPath": trigger["strategyPath"],
        "legacyRenderBase": {
            "path": "assets/world-map-4096.webp",
            "role": "temporary_development_preview_only",
            "finalBaseCandidate": False,
            "calibrationAuthority": False,
        },
        "authoredBase": {
            "status": "spatial_skeleton_ready",
            "skeletonPath": outputs["skeletonPath"],
            "locationCount": len(locations),
            "regionAssignedLocationCount": sum(len(rows) for rows in grouped.values()),
            "unassignedLocationCount": len(unassigned_guides),
            "regionCount": len(regions_output),
            "confirmedAnchorCoveredRegionCount": len(anchor_covered_regions),
            "confirmedAnchorCount": len(anchors),
            "unanchoredRegionIds": unanchored_regions,
            "nextStage": "original_regional_composition",
        },
    }
    calibration = stage_gates.setdefault("coordinateAndOverlayCalibration", {})
    calibration["status"] = "in_progress"
    calibration["pixelTransformStatus"] = "blocked_pending_original_authored_final_canvas"
    calibration["blockingReason"] = (
        "pixel calibration begins only after the original authored canvas is approved and frozen"
    )
    stage_gates["responsiveCompatibilityValidation"] = {
        "status": "pending_original_authored_final_base"
    }
    stage_gates["physicalDeviceVerification"] = {
        "status": "pending_original_authored_final_base"
    }
    progress["generatedAt"] = trigger["requestedAt"]
    progress["originalAuthoredBase"] = {
        "strategyStatus": "approved_in_development",
        "skeletonStatus": "ready",
        "strategyPath": trigger["strategyPath"],
        "skeletonPath": outputs["skeletonPath"],
        "legacyPreviewIsNonAuthoritative": True,
        "realRegionCount": len(regions_output),
        "unassignedLocationCount": len(unassigned_guides),
        "nextAction": "author original regional composition and classify five null-region locations",
    }
    write_json(progress_path, progress)

    print(
        json.dumps(
            {
                "status": skeleton["status"],
                "locations": len(locations),
                "regionAssignedLocations": skeleton["counts"]["regionAssignedLocations"],
                "unassignedLocations": len(unassigned_guides),
                "regions": len(regions_output),
                "anchorCoveredRegions": len(anchor_covered_regions),
                "unanchoredRegions": unanchored_regions,
                "anchors": len(anchors),
                "output": outputs["skeletonPath"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
