#!/usr/bin/env python3
"""Generate Atlas's first repository-owned editable regional composition SVG.

The SVG is constructed only from the original-authored spatial skeleton and confirmed anchor
coordinates. It does not read or sample the legacy render image, regions.json geometry, or any
third-party raster/vector artwork. The result is an art-direction draft, not a final coastline,
terrain map, road network, or calibrated production base.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TRIGGER_PATH = ROOT / "data/geospatial/geospatial-original-regional-composition-trigger.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def point(row: dict[str, Any], size: int) -> tuple[float, float]:
    return float(row["x"]) * size, float(row["y"]) * size


def anchor_point(row: dict[str, Any], size: int) -> tuple[float, float]:
    atlas = row["atlas"]
    return float(atlas["x"]) * size, float(atlas["y"]) * size


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def midpoint(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return (a[0] + b[0]) / 2, (a[1] + b[1]) / 2


def smooth_closed_path(points: list[tuple[float, float]]) -> str:
    if len(points) < 3:
        raise RuntimeError("a closed composition path requires at least three points")
    start = midpoint(points[-1], points[0])
    commands = [f"M {start[0]:.2f} {start[1]:.2f}"]
    for index, current in enumerate(points):
        following = points[(index + 1) % len(points)]
        end = midpoint(current, following)
        commands.append(f"Q {current[0]:.2f} {current[1]:.2f} {end[0]:.2f} {end[1]:.2f}")
    commands.append("Z")
    return " ".join(commands)


def scaled_points(
    points: list[tuple[float, float]],
    center: tuple[float, float],
    factor: float,
    size: int,
    margin: float = 18,
) -> list[tuple[float, float]]:
    return [
        (
            clamp(center[0] + (x - center[0]) * factor, margin, size - margin),
            clamp(center[1] + (y - center[1]) * factor, margin, size - margin),
        )
        for x, y in points
    ]


def xml_text(value: Any) -> str:
    return html.escape(str(value), quote=True)


def region_slug(region_id: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in region_id).strip("-")


def top_density_cells(rows: list[list[int]], size: int, limit: int = 72) -> list[tuple[int, int, int]]:
    cells = [
        (count, column, row)
        for row, values in enumerate(rows)
        for column, count in enumerate(values)
        if count > 0
    ]
    cells.sort(key=lambda item: (-item[0], item[2], item[1]))
    return cells[:limit]


def main() -> int:
    trigger = load_json(TRIGGER_PATH)
    inputs = trigger["inputs"]
    expected = trigger["expected"]
    outputs = trigger["outputs"]

    plan_path = ROOT / inputs["planPath"]
    skeleton_path = ROOT / inputs["skeletonPath"]
    progress_path = ROOT / inputs["progressPath"]
    svg_path = ROOT / outputs["svgPath"]
    manifest_path = ROOT / outputs["manifestPath"]

    plan = load_json(plan_path)
    skeleton = load_json(skeleton_path)
    progress = load_json(progress_path)
    width = int(expected["canvasWidth"])
    height = int(expected["canvasHeight"])
    if width != height:
        raise RuntimeError("regional composition v1 currently requires a square canvas")
    size = width

    counts = skeleton["counts"]
    required_counts = {
        "locations": expected["locations"],
        "regionAssignedLocations": expected["regionAssignedLocations"],
        "unassignedLocations": expected["unassignedLocations"],
        "regions": expected["regions"],
        "confirmedAnchors": expected["confirmedAnchors"],
        "regionAdjacencyEdges": expected["adjacencyEdges"],
    }
    for key, value in required_counts.items():
        if counts[key] != value:
            raise RuntimeError(f"skeleton {key} mismatch: expected {value}, found {counts[key]}")

    anchors = progress.get("anchors")
    if not isinstance(anchors, list) or len(anchors) != expected["confirmedAnchors"]:
        raise RuntimeError("progress does not contain the expected 50 confirmed anchors")

    palette = plan["artDirection"]["palette"]
    region_washes = [
        "#b88f72", "#7f9b91", "#9b8aa5", "#b5a36f", "#718d9e",
        "#9a786c", "#81956f", "#aa8f63", "#7f7d9e", "#8d9a82",
    ]

    global_points = [point(row, size) for row in skeleton["globalConstructionEnvelope"]["hull"]]
    global_center = (
        sum(x for x, _ in global_points) / len(global_points),
        sum(y for _, y in global_points) / len(global_points),
    )
    global_path = smooth_closed_path(scaled_points(global_points, global_center, 1.035, size, 10))

    region_fragments: list[str] = []
    contour_fragments: list[str] = []
    label_fragments: list[str] = []
    region_centers: dict[str, tuple[float, float]] = {}

    for index, region in enumerate(skeleton["regions"]):
        region_id = str(region["regionId"])
        title = xml_text(region["regionTitle"])
        slug = region_slug(region_id)
        center = point(region["centroid"], size)
        region_centers[region_id] = center
        hull = [point(row, size) for row in region["constructionHull"]]
        outer = scaled_points(hull, center, 1.055, size)
        middle = scaled_points(hull, center, 0.88, size)
        inner = scaled_points(hull, center, 0.71, size)
        fill = region_washes[index % len(region_washes)]
        anchor_count = int(region["confirmedAnchorCount"])
        location_count = int(region["locationCount"])

        region_fragments.append(
            f'<g id="region-{slug}" class="region-mass" data-region-id="{xml_text(region_id)}" '
            f'data-location-count="{location_count}" data-anchor-count="{anchor_count}">'
            f'<path d="{smooth_closed_path(outer)}" fill="{fill}" fill-opacity="0.55" '
            f'stroke="{palette["ink"]}" stroke-opacity="0.58" stroke-width="7"/>'
            f'<path d="{smooth_closed_path(middle)}" fill="{palette["paperLight"]}" fill-opacity="0.08"/>'
            f'</g>'
        )
        contour_fragments.extend(
            [
                f'<path d="{smooth_closed_path(middle)}" class="contour contour-middle"/>',
                f'<path d="{smooth_closed_path(inner)}" class="contour contour-inner"/>',
            ]
        )
        label_fragments.append(
            f'<g class="region-label" transform="translate({center[0]:.2f} {center[1]:.2f})">'
            f'<circle r="48" fill="{palette["paperLight"]}" fill-opacity="0.15"/>'
            f'<text y="-8" text-anchor="middle" class="region-name">{title}</text>'
            f'<text y="27" text-anchor="middle" class="region-count">{location_count} LOC · {anchor_count} ANCHOR</text>'
            f'</g>'
        )

    adjacency_fragments: list[str] = []
    for edge in skeleton["compositionAdjacency"]:
        left = region_centers[edge["fromRegionId"]]
        right = region_centers[edge["toRegionId"]]
        distance = float(edge["centroidDistance"])
        adjacency_fragments.append(
            f'<path d="M {left[0]:.2f} {left[1]:.2f} L {right[0]:.2f} {right[1]:.2f}" '
            f'class="composition-link" data-distance="{distance:.8f}"/>'
        )

    anchor_fragments: list[str] = []
    for index, anchor in enumerate(sorted(anchors, key=lambda row: str(row["locationId"]))):
        x, y = anchor_point(anchor, size)
        anchor_fragments.append(
            f'<g class="confirmed-anchor" transform="translate({x:.2f} {y:.2f})" '
            f'data-location-id="{xml_text(anchor["locationId"])}">'
            f'<circle r="13"/><circle r="4" class="anchor-core"/>'
            f'<title>{xml_text(anchor["title"])}</title></g>'
        )

    unassigned_fragments: list[str] = []
    for guide in skeleton["unassignedLocationGuides"]:
        x, y = point(guide, size)
        label = guide.get("title") or guide["locationId"]
        unassigned_fragments.append(
            f'<g class="unassigned-guide" transform="translate({x:.2f} {y:.2f})" '
            f'data-location-id="{xml_text(guide["locationId"])}">'
            f'<path d="M 0 -18 L 18 0 L 0 18 L -18 0 Z"/>'
            f'<title>{xml_text(label)} — pending region classification</title></g>'
        )

    density_fragments: list[str] = []
    grid = skeleton["locationDensityGrid"]
    grid_size = int(grid["size"])
    cell_size = size / grid_size
    for count, column, row in top_density_cells(grid["rows"], grid_size):
        x = (column + 0.5) * cell_size
        y = (row + 0.5) * cell_size
        radius = 28 + min(105, math.sqrt(count) * 16)
        opacity = min(0.17, 0.035 + count / 500)
        density_fragments.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" '
            f'fill="{palette["ink"]}" fill-opacity="{opacity:.4f}" class="density-bloom" '
            f'data-location-count="{count}"/>'
        )

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"
     role="img" aria-labelledby="title description" data-atlas-asset="original-regional-composition-v1">
  <title id="title">Atlas Original Regional Composition V1</title>
  <desc id="description">Repository-owned editable construction draft generated from Atlas point data and confirmed anchors. Not a final coastline, terrain map, road map, or calibrated production base.</desc>
  <metadata>{xml_text(json.dumps({
      "strategy": "fully-original-authored-visual-base",
      "stage": "original-regional-composition",
      "generatedAt": trigger["requestedAt"],
      "sourceSkeleton": inputs["skeletonPath"],
      "thirdPartyRasterUsed": False,
      "thirdPartyVectorUsed": False,
      "finalBaseApproved": False,
  }, ensure_ascii=False, separators=(",", ":")))}</metadata>
  <defs>
    <linearGradient id="oceanGradient" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{palette['ocean']}"/>
      <stop offset="0.55" stop-color="#131c20"/>
      <stop offset="1" stop-color="#070b0d"/>
    </linearGradient>
    <linearGradient id="landGradient" x1="0" y1="0" x2="0.8" y2="1">
      <stop offset="0" stop-color="{palette['landHighlight']}"/>
      <stop offset="0.58" stop-color="{palette['land']}"/>
      <stop offset="1" stop-color="#b9a47b"/>
    </linearGradient>
    <pattern id="oceanLines" width="92" height="92" patternUnits="userSpaceOnUse" patternTransform="rotate(-12)">
      <path d="M -20 28 Q 20 12 60 28 T 140 28" fill="none" stroke="{palette['oceanLine']}" stroke-width="3" stroke-opacity="0.42"/>
      <path d="M -20 68 Q 20 52 60 68 T 140 68" fill="none" stroke="{palette['oceanLine']}" stroke-width="2" stroke-opacity="0.25"/>
    </pattern>
    <filter id="paperGrain" x="-10%" y="-10%" width="120%" height="120%">
      <feTurbulence type="fractalNoise" baseFrequency="0.008 0.03" numOctaves="2" seed="47" result="noise"/>
      <feColorMatrix in="noise" values="0.25 0 0 0 0.62  0 0.22 0 0 0.55  0 0 0.18 0 0.45  0 0 0 0.16 0" result="grain"/>
      <feBlend in="SourceGraphic" in2="grain" mode="multiply"/>
    </filter>
    <clipPath id="landClip"><path d="{global_path}"/></clipPath>
    <style>
      .composition-link {{ fill:none; stroke:{palette['brass']}; stroke-width:6; stroke-opacity:.34; stroke-dasharray:18 24; }}
      .contour {{ fill:none; stroke:{palette['ink']}; stroke-linecap:round; stroke-linejoin:round; }}
      .contour-middle {{ stroke-width:4; stroke-opacity:.22; stroke-dasharray:10 17; }}
      .contour-inner {{ stroke-width:3; stroke-opacity:.13; stroke-dasharray:4 13; }}
      .region-name {{ font-family:Georgia,'Times New Roman',serif; font-size:31px; font-weight:700; letter-spacing:7px; fill:{palette['ink']}; paint-order:stroke; stroke:{palette['paperLight']}; stroke-width:5px; stroke-opacity:.45; }}
      .region-count {{ font-family:Arial,sans-serif; font-size:15px; font-weight:700; letter-spacing:3px; fill:{palette['softInk']}; }}
      .confirmed-anchor > circle:first-of-type {{ fill:{palette['vermilion']}; fill-opacity:.22; stroke:{palette['vermilion']}; stroke-width:5; }}
      .confirmed-anchor .anchor-core {{ fill:{palette['paperLight']}; stroke:{palette['vermilion']}; stroke-width:3; }}
      .unassigned-guide path {{ fill:none; stroke:{palette['brass']}; stroke-width:6; stroke-dasharray:7 6; }}
      .draft-title {{ font-family:Georgia,'Times New Roman',serif; font-size:55px; font-weight:700; letter-spacing:11px; fill:{palette['paperLight']}; }}
      .draft-subtitle {{ font-family:Arial,sans-serif; font-size:20px; font-weight:700; letter-spacing:8px; fill:{palette['brass']}; }}
      .legend {{ font-family:Arial,sans-serif; font-size:18px; letter-spacing:2px; fill:{palette['paperLight']}; }}
    </style>
  </defs>

  <rect width="4096" height="4096" fill="url(#oceanGradient)"/>
  <rect width="4096" height="4096" fill="url(#oceanLines)" opacity="0.72"/>
  <g id="title-block" transform="translate(190 180)">
    <text class="draft-title">ATLAS</text>
    <text y="52" class="draft-subtitle">ORIGINAL REGIONAL COMPOSITION · V1</text>
  </g>

  <g id="land-composition" filter="url(#paperGrain)">
    <path id="original-land-silhouette" d="{global_path}" fill="url(#landGradient)" stroke="{palette['ink']}" stroke-width="18" stroke-linejoin="round"/>
    <g clip-path="url(#landClip)">
      <g id="density-composition">{''.join(density_fragments)}</g>
      <g id="regional-adjacency">{''.join(adjacency_fragments)}</g>
      <g id="regional-masses">{''.join(region_fragments)}</g>
      <g id="regional-contours">{''.join(contour_fragments)}</g>
    </g>
  </g>

  <g id="region-labels">{''.join(label_fragments)}</g>
  <g id="confirmed-anchor-guides">{''.join(anchor_fragments)}</g>
  <g id="unassigned-location-guides">{''.join(unassigned_fragments)}</g>

  <g id="legend" transform="translate(180 3750)">
    <rect width="1300" height="190" rx="28" fill="#070b0d" fill-opacity="0.78" stroke="{palette['brass']}" stroke-opacity="0.58" stroke-width="3"/>
    <circle cx="62" cy="62" r="13" fill="{palette['vermilion']}" fill-opacity="0.35" stroke="{palette['vermilion']}" stroke-width="5"/>
    <text x="98" y="70" class="legend">CONFIRMED ALIGNMENT ANCHOR · 50</text>
    <path d="M 46 128 L 62 112 L 78 128 L 62 144 Z" fill="none" stroke="{palette['brass']}" stroke-width="5" stroke-dasharray="6 5"/>
    <text x="98" y="137" class="legend">UNASSIGNED LOCATION GUIDE · 5</text>
    <text x="760" y="70" class="legend">10 ORIGINAL REGION MASSES</text>
    <text x="760" y="137" class="legend">CONSTRUCTION DRAFT · NOT FINAL TERRAIN</text>
  </g>
</svg>
'''

    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(svg, encoding="utf-8")
    svg_digest = sha256(svg_path)
    svg_size = svg_path.stat().st_size

    manifest = {
        "schemaVersion": 1,
        "generatedAt": trigger["requestedAt"],
        "status": "original-regional-composition-draft-ready",
        "stage": "original-regional-composition",
        "asset": {
            "path": outputs["svgPath"],
            "format": "svg",
            "width": width,
            "height": height,
            "sizeBytes": svg_size,
            "sha256": svg_digest,
            "editableSource": True,
            "repositoryOwned": True,
        },
        "sourceHashes": {
            inputs["planPath"]: sha256(plan_path),
            inputs["skeletonPath"]: sha256(skeleton_path),
            inputs["progressPath"]: sha256(progress_path),
        },
        "counts": {
            "locations": counts["locations"],
            "regionAssignedLocations": counts["regionAssignedLocations"],
            "unassignedLocations": counts["unassignedLocations"],
            "regions": counts["regions"],
            "confirmedAnchors": counts["confirmedAnchors"],
            "adjacencyEdges": counts["regionAdjacencyEdges"],
            "densityBlooms": len(density_fragments),
        },
        "authorship": {
            "strategy": "fully-original-authored-visual-base",
            "thirdPartyRasterUsed": False,
            "thirdPartyVectorUsed": False,
            "regionsJsonGeometryUsed": False,
            "legacyRenderBaseRead": False,
            "externalImages": 0,
            "externalFonts": 0,
            "embeddedRasterImages": 0,
            "proceduralSvgDefinitionsOnly": True,
        },
        "claims": {
            "finalBaseApproved": False,
            "finalCanvasFrozen": False,
            "finalCoastline": False,
            "finalTerrain": False,
            "finalRoadNetwork": False,
            "pixelCalibrationComplete": False,
        },
        "nextAction": "review original regional composition, classify five unassigned points, then author terrain and coastline detailing",
    }
    write_json(manifest_path, manifest)

    final_base = progress["stageGates"]["finalOriginalUltraHdBase"]
    final_base["strategy"] = "fully_original_authored_visual_base"
    final_base["authoredBase"].update(
        {
            "status": "regional_composition_draft_ready",
            "compositionPath": outputs["svgPath"],
            "compositionManifestPath": outputs["manifestPath"],
            "compositionSha256": svg_digest,
            "compositionDimensions": {"width": width, "height": height},
            "editableSourceFormat": "svg",
            "finalCanvasFrozen": False,
            "nextStage": "original_terrain_and_coastline_art",
        }
    )
    progress["generatedAt"] = trigger["requestedAt"]
    progress["originalAuthoredBase"].update(
        {
            "skeletonStatus": "ready",
            "regionalCompositionStatus": "draft_ready",
            "regionalCompositionPath": outputs["svgPath"],
            "regionalCompositionManifestPath": outputs["manifestPath"],
            "nextAction": "review composition and continue original terrain/coastline art",
        }
    )
    progress["stageGates"]["coordinateAndOverlayCalibration"]["pixelTransformStatus"] = (
        "blocked_pending_original_authored_final_canvas"
    )
    write_json(progress_path, progress)

    print(
        json.dumps(
            {
                "status": manifest["status"],
                "asset": manifest["asset"],
                "counts": manifest["counts"],
                "nextAction": manifest["nextAction"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
