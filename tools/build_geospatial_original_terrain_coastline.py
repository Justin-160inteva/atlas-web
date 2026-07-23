#!/usr/bin/env python3
"""Generate Atlas's first repository-owned terrain and coastline SVG draft.

The generator consumes only Atlas's authored spatial skeleton, the repository-owned regional
composition manifest and confirmed anchors. It does not read the legacy render image, regions.json
geometry or third-party raster/vector artwork. Mountains, forests, rivers, route corridors and
shoreline details are deterministic art-direction elements, not claims about official game terrain.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
import random
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TRIGGER_PATH = ROOT / "data/geospatial/geospatial-original-terrain-coastline-trigger.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_seed(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:16], 16)


def xml_text(value: Any) -> str:
    return html.escape(str(value), quote=True)


def slug(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value).strip("-")


def project(row: dict[str, Any], size: int, inset: int) -> tuple[float, float]:
    extent = size - inset * 2
    return inset + float(row["x"]) * extent, inset + float(row["y"]) * extent


def project_anchor(row: dict[str, Any], size: int, inset: int) -> tuple[float, float]:
    extent = size - inset * 2
    atlas = row["atlas"]
    return inset + float(atlas["x"]) * extent, inset + float(atlas["y"]) * extent


def midpoint(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return (a[0] + b[0]) / 2, (a[1] + b[1]) / 2


def smooth_closed_path(points: list[tuple[float, float]]) -> str:
    if len(points) < 3:
        raise RuntimeError("closed terrain path requires at least three points")
    start = midpoint(points[-1], points[0])
    commands = [f"M {start[0]:.2f} {start[1]:.2f}"]
    for index, current in enumerate(points):
        following = points[(index + 1) % len(points)]
        end = midpoint(current, following)
        commands.append(f"Q {current[0]:.2f} {current[1]:.2f} {end[0]:.2f} {end[1]:.2f}")
    commands.append("Z")
    return " ".join(commands)


def scaled_points(
    points: list[tuple[float, float]], center: tuple[float, float], factor: float, size: int
) -> list[tuple[float, float]]:
    minimum = 72
    maximum = size - 72
    return [
        (
            max(minimum, min(maximum, center[0] + (x - center[0]) * factor)),
            max(minimum, min(maximum, center[1] + (y - center[1]) * factor)),
        )
        for x, y in points
    ]


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y):
            intersection = (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1
            if x < intersection:
                inside = not inside
        previous = current
    return inside


def polygon_bounds(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def sample_inside(
    polygon: list[tuple[float, float]], center: tuple[float, float], rng: random.Random
) -> tuple[float, float]:
    minimum_x, minimum_y, maximum_x, maximum_y = polygon_bounds(polygon)
    for _ in range(100):
        candidate = (rng.uniform(minimum_x, maximum_x), rng.uniform(minimum_y, maximum_y))
        if point_in_polygon(candidate, polygon):
            return candidate
    return center


def curved_route(
    left: tuple[float, float], right: tuple[float, float], seed: int
) -> tuple[str, tuple[float, float]]:
    dx = right[0] - left[0]
    dy = right[1] - left[1]
    length = max(1.0, math.hypot(dx, dy))
    normal_x = -dy / length
    normal_y = dx / length
    direction = -1 if seed % 2 else 1
    bend = direction * min(175.0, 42.0 + length * (0.08 + (seed % 17) / 250.0))
    control = ((left[0] + right[0]) / 2 + normal_x * bend, (left[1] + right[1]) / 2 + normal_y * bend)
    return (
        f"M {left[0]:.2f} {left[1]:.2f} Q {control[0]:.2f} {control[1]:.2f} {right[0]:.2f} {right[1]:.2f}",
        control,
    )


def top_density_cells(rows: list[list[int]], limit: int = 72) -> list[tuple[int, int, int]]:
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
    composition_manifest_path = ROOT / inputs["compositionManifestPath"]
    progress_path = ROOT / inputs["progressPath"]
    output_svg_path = ROOT / outputs["svgPath"]
    output_manifest_path = ROOT / outputs["manifestPath"]

    plan = load_json(plan_path)
    skeleton = load_json(skeleton_path)
    composition_manifest = load_json(composition_manifest_path)
    progress = load_json(progress_path)

    width = int(expected["canvasWidth"])
    height = int(expected["canvasHeight"])
    inset = int(expected["coordinateInsetPixels"])
    if width != height:
        raise RuntimeError("terrain and coastline v1 requires a square canvas")
    size = width

    counts = skeleton["counts"]
    checks = {
        "locations": expected["locations"],
        "regionAssignedLocations": expected["regionAssignedLocations"],
        "unassignedLocations": expected["unassignedLocations"],
        "regions": expected["regions"],
        "confirmedAnchors": expected["confirmedAnchors"],
        "regionAdjacencyEdges": expected["adjacencyEdges"],
    }
    for key, expected_value in checks.items():
        if counts[key] != expected_value:
            raise RuntimeError(f"skeleton {key} mismatch: {counts[key]} != {expected_value}")

    if composition_manifest["status"] != "original-regional-composition-draft-ready":
        raise RuntimeError("regional composition manifest is not ready")
    composition_svg_path = ROOT / composition_manifest["asset"]["path"]
    if sha256(composition_svg_path) != composition_manifest["asset"]["sha256"]:
        raise RuntimeError("regional composition SVG hash does not match its manifest")

    anchors = progress.get("anchors")
    if not isinstance(anchors, list) or len(anchors) != expected["confirmedAnchors"]:
        raise RuntimeError("progress must contain the expected confirmed anchors")

    palette = plan["artDirection"]["palette"]
    region_washes = [
        "#b88f72", "#7f9b91", "#9b8aa5", "#b5a36f", "#718d9e",
        "#9a786c", "#81956f", "#aa8f63", "#7f7d9e", "#8d9a82",
    ]

    centers: dict[str, tuple[float, float]] = {}
    records: list[dict[str, Any]] = []
    for index, region in enumerate(skeleton["regions"]):
        region_id = str(region["regionId"])
        center = project(region["centroid"], size, inset)
        hull = [project(row, size, inset) for row in region["constructionHull"]]
        outer = scaled_points(hull, center, 1.10, size)
        wash = scaled_points(hull, center, 1.035, size)
        terrain = scaled_points(hull, center, 0.89, size)
        inner = scaled_points(hull, center, 0.72, size)
        centers[region_id] = center
        records.append(
            {
                "index": index,
                "region": region,
                "regionId": region_id,
                "slug": slug(region_id),
                "center": center,
                "outer": outer,
                "wash": wash,
                "terrain": terrain,
                "inner": inner,
                "outerPath": smooth_closed_path(outer),
                "washPath": smooth_closed_path(wash),
                "terrainPath": smooth_closed_path(terrain),
                "innerPath": smooth_closed_path(inner),
                "fill": region_washes[index % len(region_washes)],
            }
        )

    connector_underlays: list[str] = []
    connector_masks: list[str] = []
    route_fragments: list[str] = []
    for edge in skeleton["compositionAdjacency"]:
        left = centers[edge["fromRegionId"]]
        right = centers[edge["toRegionId"]]
        straight = f"M {left[0]:.2f} {left[1]:.2f} L {right[0]:.2f} {right[1]:.2f}"
        connector_underlays.append(
            f'<path d="{straight}" stroke="url(#landGradient)" stroke-width="118" '
            f'stroke-linecap="round" stroke-opacity="0.98"/>'
        )
        connector_masks.append(
            f'<path d="{straight}" stroke="white" stroke-width="118" stroke-linecap="round"/>'
        )
        route_path, _ = curved_route(left, right, stable_seed(f"route:{edge['fromRegionId']}:{edge['toRegionId']}"))
        route_fragments.append(
            f'<g class="route-corridor" data-from="{xml_text(edge["fromRegionId"])}" '
            f'data-to="{xml_text(edge["toRegionId"])}">'
            f'<path d="{route_path}" class="route-underlay"/>'
            f'<path d="{route_path}" class="route-line"/>'
            f'</g>'
        )

    land_underlays = [
        f'<path d="{record["outerPath"]}" fill="url(#landGradient)" '
        f'stroke="{palette["ink"]}" stroke-width="19" stroke-linejoin="round"/>'
        for record in records
    ]
    land_masks = [f'<path d="{record["outerPath"]}" fill="white"/>' for record in records]

    region_washes_fragments: list[str] = []
    contour_fragments: list[str] = []
    coastline_fragments: list[str] = []
    coastline_hachures: list[str] = []
    label_fragments: list[str] = []
    mountain_fragments: list[str] = []
    forest_fragments: list[str] = []
    river_fragments: list[str] = []

    for record in records:
        region = record["region"]
        region_id = record["regionId"]
        center = record["center"]
        title = xml_text(region["regionTitle"])
        location_count = int(region["locationCount"])
        anchor_count = int(region["confirmedAnchorCount"])
        rng = random.Random(stable_seed(f"terrain:{region_id}"))

        region_washes_fragments.append(
            f'<g id="region-{record["slug"]}" class="region-mass" '
            f'data-region-id="{xml_text(region_id)}" data-location-count="{location_count}" '
            f'data-anchor-count="{anchor_count}">'
            f'<path d="{record["washPath"]}" fill="{record["fill"]}" fill-opacity="0.42"/>'
            f'</g>'
        )
        contour_fragments.extend(
            [
                f'<path d="{record["terrainPath"]}" class="contour contour-middle"/>',
                f'<path d="{record["innerPath"]}" class="contour contour-inner"/>',
            ]
        )
        coastline_fragments.extend(
            [
                f'<path d="{record["outerPath"]}" class="coastline-ink"/>',
                f'<path d="{record["outerPath"]}" class="coastline-light"/>',
            ]
        )

        hachure_step = max(1, len(record["outer"]) // 22)
        for point_index in range(0, len(record["outer"]), hachure_step):
            x, y = record["outer"][point_index]
            dx = x - center[0]
            dy = y - center[1]
            length = max(1.0, math.hypot(dx, dy))
            normal_x = dx / length
            normal_y = dy / length
            jitter = rng.uniform(-4.0, 4.0)
            start_x = x + normal_x * 5 + (-normal_y) * jitter
            start_y = y + normal_y * 5 + normal_x * jitter
            end_x = x + normal_x * rng.uniform(18.0, 32.0) + (-normal_y) * jitter
            end_y = y + normal_y * rng.uniform(18.0, 32.0) + normal_x * jitter
            coastline_hachures.append(
                f'<path d="M {start_x:.2f} {start_y:.2f} L {end_x:.2f} {end_y:.2f}" '
                f'class="coast-hachure" data-region-id="{xml_text(region_id)}"/>'
            )

        mountain_count = max(6, min(16, 6 + location_count // 65))
        for mountain_index in range(mountain_count):
            x, y = sample_inside(record["inner"], center, rng)
            scale = rng.uniform(0.78, 1.32)
            rotation = rng.uniform(-10.0, 10.0)
            mountain_fragments.append(
                f'<g class="mountain-symbol" transform="translate({x:.2f} {y:.2f}) rotate({rotation:.2f}) scale({scale:.3f})" '
                f'data-region-id="{xml_text(region_id)}" data-index="{mountain_index}">'
                f'<path d="M -38 24 L -8 -28 L 14 6 L 31 -17 L 58 24"/>'
                f'<path d="M -8 -28 L -1 -6 L 7 -13 L 14 6" class="mountain-highlight"/>'
                f'<path d="M -31 28 Q 4 20 65 29" class="mountain-base"/>'
                f'</g>'
            )

        forest_count = max(10, min(25, 9 + location_count // 38))
        for forest_index in range(forest_count):
            x, y = sample_inside(record["terrain"], center, rng)
            scale = rng.uniform(0.66, 1.08)
            rotation = rng.uniform(-6.0, 6.0)
            forest_fragments.append(
                f'<g class="forest-symbol" transform="translate({x:.2f} {y:.2f}) rotate({rotation:.2f}) scale({scale:.3f})" '
                f'data-region-id="{xml_text(region_id)}" data-index="{forest_index}">'
                f'<path d="M 0 -26 L -15 -2 H -8 L -20 17 H 20 L 8 -2 H 15 Z"/>'
                f'<path d="M 0 17 V 29" class="tree-trunk"/>'
                f'</g>'
            )

        river_count = 1 + (1 if location_count >= 340 else 0)
        minimum_x, minimum_y, maximum_x, maximum_y = polygon_bounds(record["terrain"])
        for river_index in range(river_count):
            direction = -1 if river_index % 2 else 1
            start_x = center[0] + direction * (maximum_x - minimum_x) * rng.uniform(0.04, 0.16)
            start_y = minimum_y + (maximum_y - minimum_y) * rng.uniform(0.10, 0.28)
            end_x = center[0] - direction * (maximum_x - minimum_x) * rng.uniform(0.16, 0.36)
            end_y = maximum_y - (maximum_y - minimum_y) * rng.uniform(0.03, 0.16)
            control1_x = start_x + rng.uniform(-90.0, 90.0)
            control1_y = start_y + (end_y - start_y) * 0.33
            control2_x = end_x + rng.uniform(-100.0, 100.0)
            control2_y = start_y + (end_y - start_y) * 0.68
            command = (
                f"M {start_x:.2f} {start_y:.2f} C {control1_x:.2f} {control1_y:.2f} "
                f"{control2_x:.2f} {control2_y:.2f} {end_x:.2f} {end_y:.2f}"
            )
            river_fragments.append(
                f'<g class="river-path" data-region-id="{xml_text(region_id)}" data-index="{river_index}">'
                f'<path d="{command}" class="river-underlay"/>'
                f'<path d="{command}" class="river-line"/>'
                f'</g>'
            )

        label_fragments.append(
            f'<g class="region-label" transform="translate({center[0]:.2f} {center[1]:.2f})">'
            f'<rect x="-188" y="-49" width="376" height="94" rx="30" '
            f'fill="{palette["paperLight"]}" fill-opacity="0.62" stroke="{palette["ink"]}" '
            f'stroke-opacity="0.22" stroke-width="3"/>'
            f'<text y="-7" text-anchor="middle" class="region-name">{title}</text>'
            f'<text y="25" text-anchor="middle" class="region-count">{location_count} LOC · {anchor_count} ANCHOR</text>'
            f'</g>'
        )

    if len(mountain_fragments) < expected["minimumMountainSymbols"]:
        raise RuntimeError("generated mountain symbol count is below the required minimum")
    if len(forest_fragments) < expected["minimumForestSymbols"]:
        raise RuntimeError("generated forest symbol count is below the required minimum")
    if len(river_fragments) < expected["minimumRiverPaths"]:
        raise RuntimeError("generated river path count is below the required minimum")
    if len(route_fragments) != expected["routeCorridors"]:
        raise RuntimeError("generated route corridor count does not match the contract")

    grid = skeleton["locationDensityGrid"]
    grid_size = int(grid["size"])
    extent = size - inset * 2
    cell_size = extent / grid_size
    density_fragments: list[str] = []
    for count, column, row in top_density_cells(grid["rows"]):
        x = inset + (column + 0.5) * cell_size
        y = inset + (row + 0.5) * cell_size
        radius = 20 + min(76, math.sqrt(count) * 11)
        opacity = min(0.12, 0.022 + count / 700)
        density_fragments.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" '
            f'fill="{palette["ink"]}" fill-opacity="{opacity:.4f}" class="density-bloom" '
            f'data-location-count="{count}"/>'
        )

    anchor_fragments: list[str] = []
    for anchor in sorted(anchors, key=lambda row: str(row["locationId"])):
        x, y = project_anchor(anchor, size, inset)
        anchor_fragments.append(
            f'<g class="confirmed-anchor" transform="translate({x:.2f} {y:.2f})" '
            f'data-location-id="{xml_text(anchor["locationId"])}">'
            f'<circle r="12"/><circle r="4" class="anchor-core"/>'
            f'<title>{xml_text(anchor["title"])}</title></g>'
        )

    unassigned_fragments: list[str] = []
    for guide in skeleton["unassignedLocationGuides"]:
        x, y = project(guide, size, inset)
        label = guide.get("title") or guide["locationId"]
        unassigned_fragments.append(
            f'<g class="unassigned-guide" transform="translate({x:.2f} {y:.2f})" '
            f'data-location-id="{xml_text(guide["locationId"])}">'
            f'<path d="M 0 -17 L 17 0 L 0 17 L -17 0 Z"/>'
            f'<title>{xml_text(label)} — pending region classification</title></g>'
        )

    metadata = xml_text(
        json.dumps(
            {
                "strategy": "fully-original-authored-visual-base",
                "stage": "original-terrain-and-coastline-art",
                "generatedAt": trigger["requestedAt"],
                "sourceSkeleton": inputs["skeletonPath"],
                "sourceCompositionManifest": inputs["compositionManifestPath"],
                "thirdPartyRasterUsed": False,
                "thirdPartyVectorUsed": False,
                "officialTerrainClaimed": False,
                "finalBaseApproved": False,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="4096" height="4096" viewBox="0 0 4096 4096"
     role="img" aria-labelledby="title description" data-atlas-asset="original-terrain-coastline-v1">
  <title id="title">Atlas Original Terrain and Coastline V1</title>
  <desc id="description">Repository-owned editable terrain art draft with authored coastlines, mountains, forests, rivers and route corridors. These layers are original visual composition, not official game terrain or a calibrated final base.</desc>
  <metadata>{metadata}</metadata>
  <defs>
    <linearGradient id="oceanGradient" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{palette['ocean']}"/>
      <stop offset="0.55" stop-color="#131c20"/>
      <stop offset="1" stop-color="{palette['oceanDeep']}"/>
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
      <feTurbulence type="fractalNoise" baseFrequency="0.008 0.03" numOctaves="2" seed="71" result="noise"/>
      <feColorMatrix in="noise" values="0.24 0 0 0 0.62  0 0.22 0 0 0.55  0 0 0.18 0 0.45  0 0 0 0.15 0" result="grain"/>
      <feBlend in="SourceGraphic" in2="grain" mode="multiply"/>
    </filter>
    <mask id="landMask" maskUnits="userSpaceOnUse" x="0" y="0" width="4096" height="4096">
      <rect width="4096" height="4096" fill="black"/>
      {''.join(connector_masks)}
      {''.join(land_masks)}
    </mask>
    <style>
      .coastline-ink {{ fill:none; stroke:{palette['ink']}; stroke-width:18; stroke-linejoin:round; stroke-linecap:round; opacity:.92; }}
      .coastline-light {{ fill:none; stroke:{palette['paperLight']}; stroke-width:5; stroke-linejoin:round; stroke-linecap:round; opacity:.55; }}
      .coast-hachure {{ fill:none; stroke:{palette['brass']}; stroke-width:3; stroke-linecap:round; opacity:.42; }}
      .contour {{ fill:none; stroke:{palette['ink']}; stroke-linecap:round; stroke-linejoin:round; }}
      .contour-middle {{ stroke-width:4; stroke-opacity:.18; stroke-dasharray:10 17; }}
      .contour-inner {{ stroke-width:3; stroke-opacity:.11; stroke-dasharray:4 13; }}
      .mountain-symbol path {{ fill:none; stroke:{palette['mountainInk']}; stroke-width:6; stroke-linecap:round; stroke-linejoin:round; opacity:.78; }}
      .mountain-symbol .mountain-highlight {{ stroke:{palette['paperLight']}; stroke-width:3; opacity:.6; }}
      .mountain-symbol .mountain-base {{ stroke-width:3; opacity:.38; }}
      .forest-symbol path:first-child {{ fill:{palette['forest']}; fill-opacity:.66; stroke:{palette['forestDark']}; stroke-width:4; stroke-linejoin:round; }}
      .forest-symbol .tree-trunk {{ fill:none; stroke:{palette['forestDark']}; stroke-width:5; stroke-linecap:round; }}
      .river-underlay {{ fill:none; stroke:{palette['paperLight']}; stroke-width:13; stroke-linecap:round; opacity:.55; }}
      .river-line {{ fill:none; stroke:{palette['river']}; stroke-width:7; stroke-linecap:round; opacity:.88; }}
      .route-underlay {{ fill:none; stroke:{palette['paperLight']}; stroke-width:13; stroke-linecap:round; opacity:.48; }}
      .route-line {{ fill:none; stroke:{palette['brass']}; stroke-width:6; stroke-linecap:round; stroke-dasharray:18 20; opacity:.7; }}
      .region-name {{ font-family:Georgia,'Times New Roman',serif; font-size:29px; font-weight:700; letter-spacing:6px; fill:{palette['ink']}; }}
      .region-count {{ font-family:Arial,sans-serif; font-size:14px; font-weight:700; letter-spacing:2.5px; fill:{palette['softInk']}; }}
      .confirmed-anchor > circle:first-of-type {{ fill:{palette['vermilion']}; fill-opacity:.24; stroke:{palette['vermilion']}; stroke-width:5; }}
      .confirmed-anchor .anchor-core {{ fill:{palette['paperLight']}; stroke:{palette['vermilion']}; stroke-width:3; }}
      .unassigned-guide path {{ fill:none; stroke:{palette['brass']}; stroke-width:6; stroke-dasharray:7 6; }}
      .draft-title {{ font-family:Georgia,'Times New Roman',serif; font-size:55px; font-weight:700; letter-spacing:11px; fill:{palette['paperLight']}; }}
      .draft-subtitle {{ font-family:Arial,sans-serif; font-size:19px; font-weight:700; letter-spacing:7px; fill:{palette['brass']}; }}
      .legend {{ font-family:Arial,sans-serif; font-size:17px; letter-spacing:1.8px; fill:{palette['paperLight']}; }}
    </style>
  </defs>

  <rect width="4096" height="4096" fill="url(#oceanGradient)"/>
  <rect width="4096" height="4096" fill="url(#oceanLines)" opacity="0.72"/>
  <g id="title-block" transform="translate(120 105)">
    <rect width="1360" height="178" rx="32" fill="#070b0d" fill-opacity="0.84" stroke="{palette['brass']}" stroke-opacity="0.5" stroke-width="3"/>
    <text x="42" y="75" class="draft-title">ATLAS</text>
    <text x="44" y="125" class="draft-subtitle">ORIGINAL TERRAIN &amp; COASTLINE · V1</text>
  </g>

  <g id="original-land-silhouette" filter="url(#paperGrain)">
    <g id="land-connectors">{''.join(connector_underlays)}</g>
    <g id="land-region-underlays">{''.join(land_underlays)}</g>
  </g>
  <g id="density-composition" mask="url(#landMask)">{''.join(density_fragments)}</g>
  <g id="regional-masses">{''.join(region_washes_fragments)}</g>
  <g id="authored-route-corridors" mask="url(#landMask)">{''.join(route_fragments)}</g>
  <g id="authored-forests" mask="url(#landMask)">{''.join(forest_fragments)}</g>
  <g id="authored-mountains" mask="url(#landMask)">{''.join(mountain_fragments)}</g>
  <g id="authored-rivers" mask="url(#landMask)">{''.join(river_fragments)}</g>
  <g id="regional-contours">{''.join(contour_fragments)}</g>
  <g id="authored-coastline">{''.join(coastline_fragments)}{''.join(coastline_hachures)}</g>
  <g id="region-labels">{''.join(label_fragments)}</g>
  <g id="confirmed-anchor-guides">{''.join(anchor_fragments)}</g>
  <g id="unassigned-location-guides">{''.join(unassigned_fragments)}</g>

  <g id="legend" transform="translate(120 3760)">
    <rect width="1840" height="222" rx="28" fill="#070b0d" fill-opacity="0.86" stroke="{palette['brass']}" stroke-opacity="0.58" stroke-width="3"/>
    <text x="44" y="56" class="legend">AUTHORED TERRAIN DRAFT · NOT OFFICIAL GAME TOPOGRAPHY</text>
    <text x="44" y="102" class="legend">MOUNTAINS · {len(mountain_fragments)}   FORESTS · {len(forest_fragments)}   RIVERS · {len(river_fragments)}</text>
    <text x="44" y="148" class="legend">ROUTE CORRIDORS · {len(route_fragments)}   COAST HACHURES · {len(coastline_hachures)}</text>
    <text x="44" y="194" class="legend">CONFIRMED ALIGNMENT ANCHORS · 50   UNASSIGNED GUIDES · 5</text>
  </g>
</svg>
'''

    output_svg_path.parent.mkdir(parents=True, exist_ok=True)
    output_svg_path.write_text(svg, encoding="utf-8")
    digest = sha256(output_svg_path)

    manifest = {
        "schemaVersion": 1,
        "generatedAt": trigger["requestedAt"],
        "status": "original-terrain-coastline-draft-ready",
        "stage": "original-terrain-and-coastline-art",
        "asset": {
            "path": outputs["svgPath"],
            "format": "svg",
            "width": width,
            "height": height,
            "sizeBytes": output_svg_path.stat().st_size,
            "sha256": digest,
            "editableSource": True,
            "repositoryOwned": True,
        },
        "sourceHashes": {
            inputs["planPath"]: sha256(plan_path),
            inputs["skeletonPath"]: sha256(skeleton_path),
            inputs["compositionManifestPath"]: sha256(composition_manifest_path),
            composition_manifest["asset"]["path"]: sha256(composition_svg_path),
            inputs["progressPath"]: sha256(progress_path),
        },
        "counts": {
            "locations": counts["locations"],
            "regionAssignedLocations": counts["regionAssignedLocations"],
            "unassignedLocations": counts["unassignedLocations"],
            "regions": counts["regions"],
            "confirmedAnchors": counts["confirmedAnchors"],
            "adjacencyEdges": counts["regionAdjacencyEdges"],
            "mountainSymbols": len(mountain_fragments),
            "forestSymbols": len(forest_fragments),
            "riverPaths": len(river_fragments),
            "routeCorridors": len(route_fragments),
            "coastlineRegionPaths": len(records),
            "coastlineHachures": len(coastline_hachures),
            "densityBlooms": len(density_fragments),
        },
        "authorship": {
            "strategy": "fully-original-authored-visual-base",
            "thirdPartyRasterUsed": False,
            "thirdPartyVectorUsed": False,
            "regionsJsonGeometryUsed": False,
            "legacyRenderBaseRead": False,
            "regionalCompositionSvgParsedForGeometry": False,
            "externalImages": 0,
            "externalFonts": 0,
            "embeddedRasterImages": 0,
            "proceduralSvgDefinitionsOnly": True,
        },
        "claims": {
            "officialTerrain": False,
            "officialCoastline": False,
            "officialRiverNetwork": False,
            "officialRoadNetwork": False,
            "finalBaseApproved": False,
            "finalCanvasFrozen": False,
            "pixelCalibrationComplete": False,
        },
        "nextAction": "review terrain and coastline draft, refine labels and iconography, then prepare final canvas freeze candidate",
    }
    write_json(output_manifest_path, manifest)

    authored = progress["stageGates"]["finalOriginalUltraHdBase"]["authoredBase"]
    authored.update(
        {
            "status": "terrain_coastline_draft_ready",
            "terrainCoastlinePath": outputs["svgPath"],
            "terrainCoastlineManifestPath": outputs["manifestPath"],
            "terrainCoastlineSha256": digest,
            "terrainCoastlineDimensions": {"width": width, "height": height},
            "terrainLayerCounts": {
                "mountains": len(mountain_fragments),
                "forests": len(forest_fragments),
                "rivers": len(river_fragments),
                "routes": len(route_fragments),
                "coastlineHachures": len(coastline_hachures),
            },
            "editableSourceFormat": "svg",
            "finalCanvasFrozen": False,
            "nextStage": "original_labels_icons_and_final_canvas_review",
        }
    )
    progress["generatedAt"] = trigger["requestedAt"]
    progress.setdefault("originalAuthoredBase", {}).update(
        {
            "skeletonStatus": "ready",
            "regionalCompositionStatus": "draft_ready",
            "terrainCoastlineStatus": "draft_ready",
            "terrainCoastlinePath": outputs["svgPath"],
            "terrainCoastlineManifestPath": outputs["manifestPath"],
            "nextAction": "review terrain/coastline art and continue labels, icons and final-canvas preparation",
        }
    )
    progress["stageGates"]["coordinateAndOverlayCalibration"]["pixelTransformStatus"] = (
        "blocked_pending_original_authored_final_canvas"
    )
    progress["stageGates"]["coordinateAndOverlayCalibration"]["blockingReason"] = (
        "pixel calibration begins only after the original authored final canvas is reviewed and frozen"
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
