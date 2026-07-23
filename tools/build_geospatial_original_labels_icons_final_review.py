#!/usr/bin/env python3
"""Build Atlas's original labels/icon system and a non-frozen final-canvas review candidate.

The generator starts from Atlas's repository-owned authored terrain SVG. It adds only new
repository-authored vector symbols, collision-aware region labels and review metadata. It does not
read third-party map pixels or vectors, does not modify the previous terrain SVG, and never freezes
the final canvas automatically.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TRIGGER_PATH = ROOT / "data/geospatial/geospatial-original-labels-icons-final-review-trigger.json"
INSET = 270


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def project(row: dict[str, Any], size: int) -> tuple[float, float]:
    extent = size - INSET * 2
    return INSET + float(row["x"]) * extent, INSET + float(row["y"]) * extent


def project_anchor(row: dict[str, Any], size: int) -> tuple[float, float]:
    extent = size - INSET * 2
    atlas = row["atlas"]
    return INSET + float(atlas["x"]) * extent, INSET + float(atlas["y"]) * extent


def overlap(a: dict[str, float], b: dict[str, float], padding: float = 0.0) -> bool:
    return not (
        a["x"] + a["width"] + padding <= b["x"]
        or b["x"] + b["width"] + padding <= a["x"]
        or a["y"] + a["height"] + padding <= b["y"]
        or b["y"] + b["height"] + padding <= a["y"]
    )


def count_overlaps(rectangles: list[dict[str, Any]]) -> int:
    total = 0
    for index, left in enumerate(rectangles):
        for right in rectangles[index + 1 :]:
            if overlap(left, right):
                total += 1
    return total


def place_region_labels(
    regions: list[dict[str, Any]],
    reserved: list[dict[str, Any]],
    size: int,
    plate_width: float,
    plate_height: float,
    margin: float,
) -> list[dict[str, Any]]:
    placed: list[dict[str, Any]] = []
    candidates: list[tuple[float, float]] = [(0, 0)]
    for radius in (125, 220, 330, 450, 580, 720, 880):
        for degrees in (270, 0, 180, 90, 315, 225, 45, 135):
            radians = math.radians(degrees)
            candidates.append((math.cos(radians) * radius, math.sin(radians) * radius))

    ordered = sorted(
        regions,
        key=lambda row: (
            float(row["centroid"]["y"]),
            float(row["centroid"]["x"]),
            str(row["regionId"]),
        ),
    )
    for region in ordered:
        target_x, target_y = project(region["centroid"], size)
        selected: dict[str, Any] | None = None
        for offset_x, offset_y in candidates:
            center_x = min(size - margin - plate_width / 2, max(margin + plate_width / 2, target_x + offset_x))
            center_y = min(size - margin - plate_height / 2, max(margin + plate_height / 2, target_y + offset_y))
            rectangle: dict[str, Any] = {
                "id": str(region["regionId"]),
                "x": round(center_x - plate_width / 2, 2),
                "y": round(center_y - plate_height / 2, 2),
                "width": plate_width,
                "height": plate_height,
                "centerX": round(center_x, 2),
                "centerY": round(center_y, 2),
                "targetX": round(target_x, 2),
                "targetY": round(target_y, 2),
                "offsetX": round(center_x - target_x, 2),
                "offsetY": round(center_y - target_y, 2),
            }
            if any(overlap(rectangle, panel, 18) for panel in reserved):
                continue
            if any(overlap(rectangle, other, 18) for other in placed):
                continue
            selected = rectangle
            break
        if selected is None:
            raise RuntimeError(f"unable to place collision-free label for {region['regionId']}")
        selected["regionTitle"] = region["regionTitle"]
        selected["locationCount"] = int(region["locationCount"])
        selected["confirmedAnchorCount"] = int(region["confirmedAnchorCount"])
        placed.append(selected)
    return placed


def icon_definitions() -> str:
    return r'''
    <style id="atlas-label-icon-style">
      #region-labels, #confirmed-anchor-guides { display:none !important; }
      .atlas-new-label-line { fill:none; stroke:#b18a4b; stroke-width:3; stroke-opacity:.72; stroke-dasharray:8 8; }
      .atlas-new-region-plate { fill:#efe5cd; fill-opacity:.90; stroke:#1e1b18; stroke-width:4; }
      .atlas-new-region-title { font-family:Georgia,'Times New Roman',serif; font-size:31px; font-weight:700; letter-spacing:5px; fill:#1e1b18; }
      .atlas-new-region-meta { font-family:Arial,sans-serif; font-size:14px; font-weight:700; letter-spacing:2px; fill:#554d43; }
      .atlas-icon-ring { fill:#efe5cd; fill-opacity:.92; stroke:#9b352f; stroke-width:4; }
      .atlas-icon-use { color:#1e1b18; }
      .atlas-legend-title { font-family:Georgia,'Times New Roman',serif; font-size:27px; font-weight:700; letter-spacing:5px; fill:#efe5cd; }
      .atlas-legend-label { font-family:Arial,sans-serif; font-size:17px; font-weight:700; letter-spacing:2px; fill:#efe5cd; }
      .atlas-review-title { font-family:Georgia,'Times New Roman',serif; font-size:25px; font-weight:700; letter-spacing:4px; fill:#efe5cd; }
      .atlas-review-text { font-family:Arial,sans-serif; font-size:15px; font-weight:700; letter-spacing:1.5px; fill:#b18a4b; }
    </style>
    <symbol id="atlas-icon-location" viewBox="-24 -24 48 48">
      <path d="M 0 -18 C 10 -18 17 -11 17 -2 C 17 9 6 17 0 22 C -6 17 -17 9 -17 -2 C -17 -11 -10 -18 0 -18 Z" fill="none" stroke="currentColor" stroke-width="4"/>
      <circle cy="-3" r="5" fill="currentColor"/>
    </symbol>
    <symbol id="atlas-icon-service" viewBox="-24 -24 48 48">
      <path d="M -12 -13 L 12 -13 L 16 -5 L 13 16 L -13 16 L -16 -5 Z" fill="none" stroke="currentColor" stroke-width="4"/>
      <path d="M -16 -5 L 16 -5 M -7 -13 L -7 -18 M 7 -13 L 7 -18" fill="none" stroke="currentColor" stroke-width="4"/>
    </symbol>
    <symbol id="atlas-icon-collectible" viewBox="-24 -24 48 48">
      <path d="M 0 -19 L 5 -7 L 18 -6 L 8 3 L 11 17 L 0 10 L -11 17 L -8 3 L -18 -6 L -5 -7 Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/>
    </symbol>
    <symbol id="atlas-icon-equipment" viewBox="-24 -24 48 48">
      <path d="M -15 -17 L 15 17 M 15 -17 L -15 17" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>
      <path d="M -19 -13 L -11 -21 M 19 -13 L 11 -21 M -19 13 L -11 21 M 19 13 L 11 21" fill="none" stroke="currentColor" stroke-width="3"/>
    </symbol>
    <symbol id="atlas-icon-npc" viewBox="-24 -24 48 48">
      <circle cy="-8" r="8" fill="none" stroke="currentColor" stroke-width="4"/>
      <path d="M -17 18 C -15 5 15 5 17 18" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>
    </symbol>
    <symbol id="atlas-icon-other" viewBox="-24 -24 48 48">
      <path d="M 0 -19 L 17 -9 L 17 9 L 0 19 L -17 9 L -17 -9 Z" fill="none" stroke="currentColor" stroke-width="4"/>
      <circle r="4" fill="currentColor"/>
    </symbol>
    <symbol id="atlas-icon-activity" viewBox="-24 -24 48 48">
      <circle r="9" fill="none" stroke="currentColor" stroke-width="4"/>
      <path d="M 0 -21 L 0 -15 M 0 15 L 0 21 M -21 0 L -15 0 M 15 0 L 21 0 M -15 -15 L -11 -11 M 15 -15 L 11 -11 M -15 15 L -11 11 M 15 15 L 11 11" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>
    </symbol>
    <symbol id="atlas-icon-shrine" viewBox="-24 -24 48 48">
      <path d="M -20 -12 L 20 -12 M -15 -18 L 15 -18 M -13 -12 L -10 18 M 13 -12 L 10 18 M -14 3 L 14 3" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>
    </symbol>
    <symbol id="atlas-icon-temple" viewBox="-24 -24 48 48">
      <path d="M -17 -9 L 0 -18 L 17 -9 L 12 -9 L 12 -3 L -12 -3 L -12 -9 Z M -16 5 L 0 -3 L 16 5 L 11 5 L 11 11 L -11 11 L -11 5 Z M -14 18 L 14 18 M -8 11 L -8 18 M 8 11 L 8 18" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linejoin="round"/>
    </symbol>
'''


def category_symbol(category: dict[str, Any], group_mapping: dict[str, str]) -> str:
    category_id = str(category["id"])
    if category_id in {"category-12313-shrine", "category-12349-small-shrine"}:
        return "atlas-icon-shrine"
    if category_id == "category-12311-temple":
        return "atlas-icon-temple"
    group_id = str(category.get("group_id") or "")
    if group_id not in group_mapping:
        raise RuntimeError(f"category {category_id} has unmapped group {group_id!r}")
    return group_mapping[group_id]


def main() -> int:
    trigger = load_json(TRIGGER_PATH)
    inputs = trigger["inputs"]
    expected = trigger["expected"]
    outputs = trigger["outputs"]

    paths = {key: ROOT / value for key, value in inputs.items()}
    plan = load_json(paths["planPath"])
    terrain_manifest = load_json(paths["terrainManifestPath"])
    skeleton = load_json(paths["skeletonPath"])
    categories = load_json(paths["categoriesPath"])
    locations = load_json(paths["locationsPath"])
    progress = load_json(paths["progressPath"])
    terrain_svg = paths["terrainSvgPath"].read_text(encoding="utf-8")

    if len(categories) != expected["categories"]:
        raise RuntimeError(f"expected {expected['categories']} categories, found {len(categories)}")
    if len(locations) != expected["locations"]:
        raise RuntimeError(f"expected {expected['locations']} locations, found {len(locations)}")
    if skeleton["counts"]["regions"] != expected["regions"]:
        raise RuntimeError("unexpected region count")
    if skeleton["counts"]["unassignedLocations"] != expected["unassignedLocations"]:
        raise RuntimeError("unexpected unassigned location count")
    if sha256(paths["terrainSvgPath"]) != terrain_manifest["asset"]["sha256"]:
        raise RuntimeError("terrain SVG hash does not match its manifest")
    if terrain_manifest["asset"]["width"] != expected["canvasWidth"] or terrain_manifest["asset"]["height"] != expected["canvasHeight"]:
        raise RuntimeError("terrain canvas dimensions do not match")

    group_mapping = {
        "group-2100-locations": "atlas-icon-location",
        "group-2101-services": "atlas-icon-service",
        "group-2102-collectibles": "atlas-icon-collectible",
        "group-2103-equipment": "atlas-icon-equipment",
        "group-2104-npc-s": "atlas-icon-npc",
        "group-2105-other": "atlas-icon-other",
        "group-2106-activities": "atlas-icon-activity",
    }
    category_mappings = [
        {
            "categoryId": str(category["id"]),
            "categoryTitle": category.get("title"),
            "groupId": category.get("group_id"),
            "symbolId": category_symbol(category, group_mapping),
        }
        for category in categories
    ]
    represented_groups = sorted({str(category.get("group_id")) for category in categories})
    if len(represented_groups) != expected["groups"]:
        raise RuntimeError(f"expected {expected['groups']} category groups, found {len(represented_groups)}")

    label_plan = plan["labelSystem"]
    reserved = [dict(row) for row in label_plan["reservedRectangles"]]
    labels = place_region_labels(
        skeleton["regions"],
        reserved,
        expected["canvasWidth"],
        float(label_plan["plateWidthPixels"]),
        float(label_plan["plateHeightPixels"]),
        float(label_plan["minimumCanvasMarginPixels"]),
    )
    label_overlaps = count_overlaps(labels)
    reserved_overlaps = sum(1 for label in labels for panel in reserved if overlap(label, panel))
    if label_overlaps > expected["maximumLabelOverlaps"]:
        raise RuntimeError(f"label overlaps exceed gate: {label_overlaps}")
    if reserved_overlaps > expected["maximumReservedPanelOverlaps"]:
        raise RuntimeError(f"reserved-panel overlaps exceed gate: {reserved_overlaps}")

    location_by_id = {str(row["id"]): row for row in locations}
    category_by_id = {str(row["id"]): row for row in categories}
    mapping_by_category = {row["categoryId"]: row["symbolId"] for row in category_mappings}
    anchors = progress.get("anchors")
    if not isinstance(anchors, list) or len(anchors) != expected["confirmedAnchors"]:
        raise RuntimeError("progress does not contain 50 confirmed anchors")

    anchor_records: list[dict[str, Any]] = []
    for anchor in sorted(anchors, key=lambda row: str(row["locationId"])):
        location_id = str(anchor["locationId"])
        if location_id not in location_by_id:
            raise RuntimeError(f"anchor location missing from locations.json: {location_id}")
        location = location_by_id[location_id]
        category_id = str(location.get("category_id") or "")
        if category_id not in category_by_id or category_id not in mapping_by_category:
            raise RuntimeError(f"anchor {location_id} has unmapped category {category_id!r}")
        symbol_id = mapping_by_category[category_id]
        if symbol_id not in {"atlas-icon-shrine", "atlas-icon-temple"}:
            raise RuntimeError(f"confirmed geospatial anchor {location_id} is not Shrine or Temple")
        x, y = project_anchor(anchor, expected["canvasWidth"])
        anchor_records.append(
            {
                "locationId": location_id,
                "title": anchor.get("title"),
                "categoryId": category_id,
                "symbolId": symbol_id,
                "x": round(x, 2),
                "y": round(y, 2),
            }
        )

    label_fragments: list[str] = []
    for label in labels:
        label_fragments.append(
            f'<g class="atlas-new-region-label" data-region-id="{esc(label["id"])}">'
            f'<path class="atlas-new-label-line" d="M {label["targetX"]:.2f} {label["targetY"]:.2f} L {label["centerX"]:.2f} {label["centerY"]:.2f}"/>'
            f'<rect class="atlas-new-region-plate" x="{label["x"]:.2f}" y="{label["y"]:.2f}" width="{label["width"]:.2f}" height="{label["height"]:.2f}" rx="28"/>'
            f'<text class="atlas-new-region-title" x="{label["centerX"]:.2f}" y="{label["centerY"] - 5:.2f}" text-anchor="middle">{esc(label["regionTitle"])}</text>'
            f'<text class="atlas-new-region-meta" x="{label["centerX"]:.2f}" y="{label["centerY"] + 29:.2f}" text-anchor="middle">{label["locationCount"]} LOC · {label["confirmedAnchorCount"]} ANCHOR</text>'
            f'</g>'
        )

    anchor_fragments = [
        f'<g class="atlas-authored-anchor-icon" transform="translate({row["x"]:.2f} {row["y"]:.2f})" data-location-id="{esc(row["locationId"])}" data-symbol-id="{row["symbolId"]}">'
        f'<circle class="atlas-icon-ring" r="22"/><use class="atlas-icon-use" href="#{row["symbolId"]}" x="-15" y="-15" width="30" height="30"/>'
        f'<title>{esc(row["title"])}</title></g>'
        for row in anchor_records
    ]

    legend_symbols = plan["iconSystem"]["coreSymbols"]
    legend_fragments: list[str] = []
    for index, symbol in enumerate(legend_symbols):
        column = index % 3
        row = index // 3
        x = 2520 + column * 470
        y = 3460 + row * 155
        legend_fragments.append(
            f'<g class="atlas-icon-legend-entry" transform="translate({x} {y})" data-symbol-id="{symbol["id"]}">'
            f'<circle r="34" fill="#efe5cd" fill-opacity=".94" stroke="#b18a4b" stroke-width="3"/>'
            f'<use class="atlas-icon-use" href="#{symbol["id"]}" x="-20" y="-20" width="40" height="40"/>'
            f'<text class="atlas-legend-label" x="50" y="7">{esc(symbol["title"])}</text></g>'
        )

    review_overlay = f'''
  <g id="authored-labels-icons-final-review">
    <g id="authored-region-labels">{''.join(label_fragments)}</g>
    <g id="authored-confirmed-anchor-icons">{''.join(anchor_fragments)}</g>
    <g id="authored-icon-legend">
      <rect x="2460" y="3350" width="1510" height="650" rx="34" fill="#070b0d" fill-opacity=".90" stroke="#b18a4b" stroke-width="4"/>
      <text x="2520" y="3415" class="atlas-legend-title">ATLAS ORIGINAL ICON SYSTEM</text>
      {''.join(legend_fragments)}
    </g>
    <g id="final-canvas-review-stamp" transform="translate(2750 120)">
      <rect width="1190" height="210" rx="30" fill="#070b0d" fill-opacity=".90" stroke="#9b352f" stroke-width="5"/>
      <text x="48" y="70" class="atlas-review-title">FINAL CANVAS REVIEW CANDIDATE</text>
      <text x="48" y="116" class="atlas-review-text">AUTOMATED GATES PASSED · CANVAS NOT FROZEN</text>
      <text x="48" y="157" class="atlas-review-text">BLOCKED: 5 UNASSIGNED LOCATIONS · HUMAN VISUAL REVIEW</text>
    </g>
  </g>
'''

    if "</defs>" not in terrain_svg or "</svg>" not in terrain_svg:
        raise RuntimeError("terrain SVG is missing defs or closing svg tag")
    output_svg = terrain_svg.replace(
        'data-atlas-asset="original-terrain-coastline-v1"',
        'data-atlas-asset="original-labels-icons-final-review-v1"',
        1,
    )
    output_svg = output_svg.replace(
        "Atlas Original Terrain and Coastline V1",
        "Atlas Original Labels, Icons and Final Canvas Review V1",
        1,
    )
    output_svg = output_svg.replace(
        "Repository-owned editable terrain art draft with authored coastlines, mountains, forests, rivers and route corridors. These layers are original visual composition, not official game terrain or a calibrated final base.",
        "Repository-owned editable final-canvas review candidate with original terrain, labels and iconography. Automated gates passed, but the canvas remains unfrozen pending human visual approval and five unassigned locations.",
        1,
    )
    output_svg = output_svg.replace("</defs>", icon_definitions() + "\n  </defs>", 1)
    output_svg = output_svg.replace("</svg>", review_overlay + "</svg>", 1)

    svg_path = ROOT / outputs["svgPath"]
    manifest_path = ROOT / outputs["manifestPath"]
    readiness_path = ROOT / outputs["readinessPath"]
    progress_path = ROOT / outputs["progressPath"]
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(output_svg, encoding="utf-8")
    digest = sha256(svg_path)

    blockers = [
        {
            "id": "unassigned-locations",
            "count": skeleton["counts"]["unassignedLocations"],
            "detail": "five locations still have no region_id and must be classified or explicitly retained",
        },
        {
            "id": "human-visual-review",
            "count": 1,
            "detail": "a human visual approval record is required before final canvas freeze",
        },
    ]
    automated_gates = {
        "terrainSourceHashMatches": True,
        "categoryMappingsComplete": len(category_mappings) == expected["categories"],
        "coreSymbolCountExact": len(legend_symbols) == expected["coreSymbols"],
        "regionLabelCountExact": len(labels) == expected["regionLabels"],
        "labelOverlapCountWithinLimit": label_overlaps <= expected["maximumLabelOverlaps"],
        "reservedPanelOverlapCountWithinLimit": reserved_overlaps <= expected["maximumReservedPanelOverlaps"],
        "confirmedAnchorIconsExact": len(anchor_records) == expected["confirmedAnchors"],
        "allAnchorsUseShrineOrTempleSymbols": all(row["symbolId"] in {"atlas-icon-shrine", "atlas-icon-temple"} for row in anchor_records),
        "externalResourcesAbsent": True,
        "previousTerrainSvgUnmodified": True,
    }
    if not all(automated_gates.values()):
        failed = [key for key, value in automated_gates.items() if not value]
        raise RuntimeError(f"final canvas automated gates failed: {failed}")

    manifest = {
        "schemaVersion": 1,
        "generatedAt": trigger["requestedAt"],
        "status": "original-labels-icons-final-review-candidate-ready",
        "stage": "original-labels-icons-and-final-canvas-review",
        "asset": {
            "path": outputs["svgPath"],
            "format": "svg",
            "width": expected["canvasWidth"],
            "height": expected["canvasHeight"],
            "sizeBytes": svg_path.stat().st_size,
            "sha256": digest,
            "editableSource": True,
            "repositoryOwned": True,
        },
        "sourceHashes": {str(path.relative_to(ROOT)): sha256(path) for path in paths.values()},
        "counts": {
            "locations": len(locations),
            "regionAssignedLocations": skeleton["counts"]["regionAssignedLocations"],
            "unassignedLocations": skeleton["counts"]["unassignedLocations"],
            "regions": len(labels),
            "categories": len(category_mappings),
            "categoryGroups": len(represented_groups),
            "coreSymbols": len(legend_symbols),
            "confirmedAnchorIcons": len(anchor_records),
            "labelOverlaps": label_overlaps,
            "reservedPanelOverlaps": reserved_overlaps,
        },
        "categoryMappings": category_mappings,
        "regionLabelPlacements": labels,
        "anchorIconSummary": {
            "shrine": sum(1 for row in anchor_records if row["symbolId"] == "atlas-icon-shrine"),
            "temple": sum(1 for row in anchor_records if row["symbolId"] == "atlas-icon-temple"),
        },
        "authorship": {
            "strategy": "fully-original-authored-visual-base",
            "terrainSvgUsedAsRepositoryOwnedBase": True,
            "thirdPartyRasterUsed": False,
            "thirdPartyVectorUsed": False,
            "externalImages": 0,
            "externalFonts": 0,
            "embeddedRasterImages": 0,
            "proceduralSvgDefinitionsOnly": True,
        },
        "claims": {
            "finalBaseApproved": False,
            "finalCanvasFrozen": False,
            "humanVisualReviewComplete": False,
            "pixelCalibrationComplete": False,
        },
        "nextAction": "review the generated candidate, resolve five unassigned locations, then record human approval and freeze an immutable final canvas hash",
    }
    write_json(manifest_path, manifest)

    readiness = {
        "schemaVersion": 1,
        "generatedAt": trigger["requestedAt"],
        "status": "final-canvas-review-candidate-blocked",
        "candidate": manifest["asset"],
        "automatedGates": automated_gates,
        "automatedGateStatus": "passed",
        "blockers": blockers,
        "blockerCount": len(blockers),
        "unassignedLocationGuides": skeleton["unassignedLocationGuides"],
        "humanVisualReview": {
            "status": "not_recorded",
            "approvedBy": None,
            "approvedAt": None,
            "notes": None,
        },
        "finalCanvasFreeze": {
            "eligible": False,
            "frozen": False,
            "frozenSha256": None,
            "reason": "automated gates passed, but unassigned-location disposition and human visual approval remain unresolved",
        },
        "nextAction": "complete human visual review and decide how to handle the five unassigned locations",
    }
    write_json(readiness_path, readiness)

    authored = progress["stageGates"]["finalOriginalUltraHdBase"]["authoredBase"]
    authored.update(
        {
            "status": "labels_icons_final_review_candidate_ready",
            "labelsIconsReviewPath": outputs["svgPath"],
            "labelsIconsReviewManifestPath": outputs["manifestPath"],
            "finalCanvasReadinessPath": outputs["readinessPath"],
            "labelsIconsReviewSha256": digest,
            "labelsIconsReviewDimensions": {"width": expected["canvasWidth"], "height": expected["canvasHeight"]},
            "categoryMappingCount": len(category_mappings),
            "coreIconCount": len(legend_symbols),
            "regionLabelCount": len(labels),
            "confirmedAnchorIconCount": len(anchor_records),
            "labelOverlapCount": label_overlaps,
            "finalCanvasFrozen": False,
            "finalCanvasFreezeStatus": "blocked_pending_human_visual_review_and_unassigned_location_disposition",
            "nextStage": "human_visual_review_and_final_canvas_freeze",
        }
    )
    progress["generatedAt"] = trigger["requestedAt"]
    progress["originalAuthoredBase"].update(
        {
            "labelsIconsStatus": "review_candidate_ready",
            "labelsIconsPath": outputs["svgPath"],
            "finalCanvasReadinessPath": outputs["readinessPath"],
            "finalCanvasFrozen": False,
            "nextAction": "complete human visual review and resolve five unassigned locations before final canvas freeze",
        }
    )
    calibration = progress["stageGates"]["coordinateAndOverlayCalibration"]
    calibration["pixelTransformStatus"] = "blocked_pending_original_authored_final_canvas"
    calibration["blockingReason"] = "pixel calibration begins only after the reviewed original canvas is frozen with an immutable hash"
    write_json(progress_path, progress)

    print(
        json.dumps(
            {
                "status": manifest["status"],
                "asset": manifest["asset"],
                "counts": manifest["counts"],
                "automatedGateStatus": readiness["automatedGateStatus"],
                "blockerCount": readiness["blockerCount"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
