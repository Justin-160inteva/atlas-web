#!/usr/bin/env python3
"""Generate Atlas's first repository-owned editable regional composition SVG.

The composition uses only the original-authored spatial skeleton and confirmed anchor coordinates.
It never reads the legacy render image or regions.json geometry. Ten inset region masses and broad
composition connectors form an original map-like land structure without claiming a final coastline,
terrain model, road network, or calibrated production base.
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
INSET = 270


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project(row: dict[str, Any], size: int) -> tuple[float, float]:
    extent = size - INSET * 2
    return INSET + float(row["x"]) * extent, INSET + float(row["y"]) * extent


def project_anchor(row: dict[str, Any], size: int) -> tuple[float, float]:
    extent = size - INSET * 2
    atlas = row["atlas"]
    return INSET + float(atlas["x"]) * extent, INSET + float(atlas["y"]) * extent


def midpoint(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return (a[0] + b[0]) / 2, (a[1] + b[1]) / 2


def smooth_closed_path(points: list[tuple[float, float]]) -> str:
    if len(points) < 3:
        raise RuntimeError("closed composition path requires at least three points")
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


def xml_text(value: Any) -> str:
    return html.escape(str(value), quote=True)


def slug(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value).strip("-")


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
    progress_path = ROOT / inputs["progressPath"]
    svg_path = ROOT / outputs["svgPath"]
    manifest_path = ROOT / outputs["manifestPath"]

    plan = load_json(plan_path)
    skeleton = load_json(skeleton_path)
    progress = load_json(progress_path)
    width = int(expected["canvasWidth"])
    height = int(expected["canvasHeight"])
    if width != height:
        raise RuntimeError("composition v1 requires a square canvas")
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

    anchors = progress.get("anchors")
    if not isinstance(anchors, list) or len(anchors) != 50:
        raise RuntimeError("progress must contain 50 confirmed anchors")

    palette = plan["artDirection"]["palette"]
    region_washes = [
        "#b88f72", "#7f9b91", "#9b8aa5", "#b5a36f", "#718d9e",
        "#9a786c", "#81956f", "#aa8f63", "#7f7d9e", "#8d9a82",
    ]

    centers: dict[str, tuple[float, float]] = {}
    region_records: list[dict[str, Any]] = []
    for index, region in enumerate(skeleton["regions"]):
        region_id = str(region["regionId"])
        center = project(region["centroid"], size)
        hull = [project(row, size) for row in region["constructionHull"]]
        outer = scaled_points(hull, center, 1.10, size)
        wash = scaled_points(hull, center, 1.035, size)
        middle = scaled_points(hull, center, 0.86, size)
        inner = scaled_points(hull, center, 0.69, size)
        centers[region_id] = center
        region_records.append(
            {
                "region": region,
                "regionId": region_id,
                "slug": slug(region_id),
                "center": center,
                "outerPath": smooth_closed_path(outer),
                "washPath": smooth_closed_path(wash),
                "middlePath": smooth_closed_path(middle),
                "innerPath": smooth_closed_path(inner),
                "fill": region_washes[index % len(region_washes)],
            }
        )

    connector_paths: list[str] = []
    connector_guides: list[str] = []
    for edge in skeleton["compositionAdjacency"]:
        left = centers[edge["fromRegionId"]]
        right = centers[edge["toRegionId"]]
        command = f"M {left[0]:.2f} {left[1]:.2f} L {right[0]:.2f} {right[1]:.2f}"
        connector_paths.append(
            f'<path d="{command}" stroke="url(#landGradient)" stroke-width="118" '
            f'stroke-linecap="round" stroke-opacity="0.98"/>'
        )
        connector_guides.append(
            f'<path d="{command}" class="composition-link" '
            f'data-distance="{float(edge["centroidDistance"]):.8f}"/>'
        )

    land_underlays = [
        f'<path d="{record["outerPath"]}" fill="url(#landGradient)" '
        f'stroke="{palette["ink"]}" stroke-width="17" stroke-linejoin="round"/>'
        for record in region_records
    ]
    mask_regions = [f'<path d="{record["outerPath"]}" fill="white"/>' for record in region_records]
    mask_connectors = [
        path.replace('stroke="url(#landGradient)"', 'stroke="white"').replace('stroke-opacity="0.98"', 'stroke-opacity="1"')
        for path in connector_paths
    ]

    region_wash_fragments: list[str] = []
    contour_fragments: list[str] = []
    label_fragments: list[str] = []
    for record in region_records:
        region = record["region"]
        center = record["center"]
        title = xml_text(region["regionTitle"])
        location_count = int(region["locationCount"])
        anchor_count = int(region["confirmedAnchorCount"])
        region_wash_fragments.append(
            f'<g id="region-{record["slug"]}" class="region-mass" '
            f'data-region-id="{xml_text(record["regionId"])}" data-location-count="{location_count}" '
            f'data-anchor-count="{anchor_count}">'
            f'<path d="{record["washPath"]}" fill="{record["fill"]}" fill-opacity="0.58" '
            f'stroke="{palette["ink"]}" stroke-width="6" stroke-opacity="0.54"/>'
            f'</g>'
        )
        contour_fragments.extend(
            [
                f'<path d="{record["middlePath"]}" class="contour contour-middle"/>',
                f'<path d="{record["innerPath"]}" class="contour contour-inner"/>',
            ]
        )
        label_fragments.append(
            f'<g class="region-label" transform="translate({center[0]:.2f} {center[1]:.2f})">'
            f'<rect x="-185" y="-48" width="370" height="92" rx="30" '
            f'fill="{palette["paperLight"]}" fill-opacity="0.56" stroke="{palette["ink"]}" '
            f'stroke-opacity="0.18" stroke-width="3"/>'
            f'<text y="-7" text-anchor="middle" class="region-name">{title}</text>'
            f'<text y="25" text-anchor="middle" class="region-count">{location_count} LOC · {anchor_count} ANCHOR</text>'
            f'</g>'
        )

    grid = skeleton["locationDensityGrid"]
    grid_size = int(grid["size"])
    extent = size - INSET * 2
    cell_size = extent / grid_size
    density_fragments: list[str] = []
    for count, column, row in top_density_cells(grid["rows"]):
        x = INSET + (column + 0.5) * cell_size
        y = INSET + (row + 0.5) * cell_size
        radius = 22 + min(82, math.sqrt(count) * 12)
        opacity = min(0.16, 0.03 + count / 550)
        density_fragments.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" '
            f'fill="{palette["ink"]}" fill-opacity="{opacity:.4f}" class="density-bloom" '
            f'data-location-count="{count}"/>'
        )

    anchor_fragments: list[str] = []
    for anchor in sorted(anchors, key=lambda row: str(row["locationId"])):
        x, y = project_anchor(anchor, size)
        anchor_fragments.append(
            f'<g class="confirmed-anchor" transform="translate({x:.2f} {y:.2f})" '
            f'data-location-id="{xml_text(anchor["locationId"])}">'
            f'<circle r="12"/><circle r="4" class="anchor-core"/>'
            f'<title>{xml_text(anchor["title"])}</title></g>'
        )

    unassigned_fragments: list[str] = []
    for guide in skeleton["unassignedLocationGuides"]:
        x, y = project(guide, size)
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
                "stage": "original-regional-composition",
                "generatedAt": trigger["requestedAt"],
                "sourceSkeleton": inputs["skeletonPath"],
                "thirdPartyRasterUsed": False,
                "thirdPartyVectorUsed": False,
                "finalBaseApproved": False,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="4096" height="4096" viewBox="0 0 4096 4096"
     role="img" aria-labelledby="title description" data-atlas-asset="original-regional-composition-v1">
  <title id="title">Atlas Original Regional Composition V1</title>
  <desc id="description">Repository-owned editable construction draft made from ten inset region masses, composition connectors and confirmed Atlas anchors. Not a final coastline, terrain map, road map, or calibrated production base.</desc>
  <metadata>{metadata}</metadata>
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
    <mask id="landMask" maskUnits="userSpaceOnUse" x="0" y="0" width="4096" height="4096">
      <rect width="4096" height="4096" fill="black"/>
      {''.join(mask_connectors)}
      {''.join(mask_regions)}
    </mask>
    <style>
      .composition-link {{ fill:none; stroke:{palette['brass']}; stroke-width:6; stroke-opacity:.38; stroke-dasharray:18 24; }}
      .contour {{ fill:none; stroke:{palette['ink']}; stroke-linecap:round; stroke-linejoin:round; }}
      .contour-middle {{ stroke-width:4; stroke-opacity:.23; stroke-dasharray:10 17; }}
      .contour-inner {{ stroke-width:3; stroke-opacity:.14; stroke-dasharray:4 13; }}
      .region-name {{ font-family:Georgia,'Times New Roman',serif; font-size:29px; font-weight:700; letter-spacing:6px; fill:{palette['ink']}; }}
      .region-count {{ font-family:Arial,sans-serif; font-size:14px; font-weight:700; letter-spacing:2.5px; fill:{palette['softInk']}; }}
      .confirmed-anchor > circle:first-of-type {{ fill:{palette['vermilion']}; fill-opacity:.24; stroke:{palette['vermilion']}; stroke-width:5; }}
      .confirmed-anchor .anchor-core {{ fill:{palette['paperLight']}; stroke:{palette['vermilion']}; stroke-width:3; }}
      .unassigned-guide path {{ fill:none; stroke:{palette['brass']}; stroke-width:6; stroke-dasharray:7 6; }}
      .draft-title {{ font-family:Georgia,'Times New Roman',serif; font-size:55px; font-weight:700; letter-spacing:11px; fill:{palette['paperLight']}; }}
      .draft-subtitle {{ font-family:Arial,sans-serif; font-size:19px; font-weight:700; letter-spacing:7px; fill:{palette['brass']}; }}
      .legend {{ font-family:Arial,sans-serif; font-size:18px; letter-spacing:2px; fill:{palette['paperLight']}; }}
    </style>
  </defs>

  <rect width="4096" height="4096" fill="url(#oceanGradient)"/>
  <rect width="4096" height="4096" fill="url(#oceanLines)" opacity="0.72"/>
  <g id="title-block" transform="translate(120 105)">
    <rect width="1240" height="178" rx="32" fill="#070b0d" fill-opacity="0.84" stroke="{palette['brass']}" stroke-opacity="0.5" stroke-width="3"/>
    <text x="42" y="75" class="draft-title">ATLAS</text>
    <text x="44" y="125" class="draft-subtitle">ORIGINAL REGIONAL COMPOSITION · V1</text>
  </g>

  <g id="original-land-silhouette" filter="url(#paperGrain)">
    <g id="land-connectors">{''.join(connector_paths)}</g>
    <g id="land-region-underlays">{''.join(land_underlays)}</g>
  </g>
  <g id="density-composition" mask="url(#landMask)">{''.join(density_fragments)}</g>
  <g id="regional-adjacency">{''.join(connector_guides)}</g>
  <g id="regional-masses">{''.join(region_wash_fragments)}</g>
  <g id="regional-contours">{''.join(contour_fragments)}</g>
  <g id="region-labels">{''.join(label_fragments)}</g>
  <g id="confirmed-anchor-guides">{''.join(anchor_fragments)}</g>
  <g id="unassigned-location-guides">{''.join(unassigned_fragments)}</g>

  <g id="legend" transform="translate(120 3800)">
    <rect width="1450" height="184" rx="28" fill="#070b0d" fill-opacity="0.84" stroke="{palette['brass']}" stroke-opacity="0.58" stroke-width="3"/>
    <circle cx="62" cy="60" r="12" fill="{palette['vermilion']}" fill-opacity="0.35" stroke="{palette['vermilion']}" stroke-width="5"/>
    <text x="98" y="68" class="legend">CONFIRMED ALIGNMENT ANCHOR · 50</text>
    <path d="M 46 126 L 62 110 L 78 126 L 62 142 Z" fill="none" stroke="{palette['brass']}" stroke-width="5" stroke-dasharray="6 5"/>
    <text x="98" y="135" class="legend">UNASSIGNED LOCATION GUIDE · 5</text>
    <text x="790" y="68" class="legend">10 ORIGINAL REGION MASSES</text>
    <text x="790" y="135" class="legend">CONSTRUCTION DRAFT · NOT FINAL TERRAIN</text>
  </g>
</svg>
'''

    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(svg, encoding="utf-8")
    digest = sha256(svg_path)

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
            "sizeBytes": svg_path.stat().st_size,
            "sha256": digest,
            "editableSource": True,
            "repositoryOwned": True,
        },
        "composition": {
            "coordinateInsetPixels": INSET,
            "landModel": "ten smoothed region masses connected by authored composition bands",
            "globalConvexHullUsedAsVisibleLand": False,
            "oceanBorderPreserved": True,
            "densityMarksMaskedToLand": True,
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
        "nextAction": "review inset connected-region composition, classify five unassigned points, then author terrain and coastline detailing",
    }
    write_json(manifest_path, manifest)

    authored = progress["stageGates"]["finalOriginalUltraHdBase"]["authoredBase"]
    authored.update(
        {
            "status": "regional_composition_draft_ready",
            "compositionPath": outputs["svgPath"],
            "compositionManifestPath": outputs["manifestPath"],
            "compositionSha256": digest,
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
    progress["stageGates"]["coordinateAndOverlayCalibration"]["pixelTransformStatus"] = "blocked_pending_original_authored_final_canvas"
    write_json(progress_path, progress)

    print(json.dumps({"status": manifest["status"], "asset": manifest["asset"], "counts": manifest["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
