#!/usr/bin/env python3
"""Validate the labels/icon review candidate, no-inference disposition and freeze readiness."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SVG = ROOT / "assets/original-map/atlas-original-labels-icons-final-review-v1.svg"
MANIFEST = ROOT / "data/geospatial/geospatial-original-labels-icons-final-review-v1.json"
READINESS = ROOT / "data/geospatial/geospatial-original-final-canvas-readiness.json"
DISPOSITION = ROOT / "data/geospatial/geospatial-unassigned-location-disposition.json"
PROGRESS = ROOT / "data/geospatial/geospatial-progress.json"
LEGACY = ROOT / "assets/world-map-4096.webp"
TERRAIN = ROOT / "assets/original-map/atlas-original-terrain-coastline-v1.svg"
TERRAIN_MANIFEST = ROOT / "data/geospatial/geospatial-original-terrain-coastline-v1.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    svg = SVG.read_text(encoding="utf-8")
    manifest = load(MANIFEST)
    readiness = load(READINESS)
    disposition = load(DISPOSITION)
    progress = load(PROGRESS)
    svg_digest = digest(SVG)

    assert svg.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert 'width="4096"' in svg and 'height="4096"' in svg
    assert 'viewBox="0 0 4096 4096"' in svg
    assert 'data-atlas-asset="original-labels-icons-final-review-v1"' in svg
    assert '<image' not in svg.lower()
    assert 'data:image/' not in svg.lower()
    assert '@import' not in svg.lower()
    assert not re.search(r'(?:href|src)\s*=\s*["\'](?:https?:|//)', svg, re.I)
    assert not re.search(r'url\(\s*["\']?https?://', svg, re.I)

    required_ids = {
        "authored-labels-icons-final-review",
        "authored-region-labels",
        "authored-confirmed-anchor-icons",
        "authored-icon-legend",
        "final-canvas-review-stamp",
        "atlas-icon-location",
        "atlas-icon-service",
        "atlas-icon-collectible",
        "atlas-icon-equipment",
        "atlas-icon-npc",
        "atlas-icon-other",
        "atlas-icon-activity",
        "atlas-icon-shrine",
        "atlas-icon-temple",
    }
    for identifier in required_ids:
        assert f'id="{identifier}"' in svg
    assert svg.count('<symbol id="atlas-icon-') == 9
    assert svg.count('class="atlas-new-region-label"') == 10
    assert svg.count('class="atlas-authored-anchor-icon"') == 50
    assert svg.count('class="atlas-icon-legend-entry"') == 9
    assert '#region-labels, #confirmed-anchor-guides { display:none !important; }' in svg

    expected_counts = {
        "locations": 3430,
        "regionAssignedLocations": 3425,
        "unassignedLocations": 5,
        "regions": 10,
        "categories": 44,
        "categoryGroups": 7,
        "coreSymbols": 9,
        "confirmedAnchorIcons": 50,
        "labelOverlaps": 0,
        "reservedPanelOverlaps": 0,
    }
    assert manifest["status"] == "original-labels-icons-final-review-candidate-ready"
    assert manifest["asset"] == {
        "path": str(SVG.relative_to(ROOT)),
        "format": "svg",
        "width": 4096,
        "height": 4096,
        "sizeBytes": SVG.stat().st_size,
        "sha256": svg_digest,
        "editableSource": True,
        "repositoryOwned": True,
    }
    assert manifest["counts"] == expected_counts
    assert len(manifest["categoryMappings"]) == 44
    assert len({row["categoryId"] for row in manifest["categoryMappings"]}) == 44
    assert len(manifest["regionLabelPlacements"]) == 10
    assert manifest["anchorIconSummary"]["shrine"] + manifest["anchorIconSummary"]["temple"] == 50
    assert manifest["unassignedLocationDisposition"] == {
        "status": "resolved",
        "path": str(DISPOSITION.relative_to(ROOT)),
        "policy": "retain_as_global_overlay_without_region_inference",
        "locationCount": 5,
        "regionMembershipInferred": False,
        "globalVisibilityPreserved": True,
    }
    assert manifest["authorship"] == {
        "strategy": "fully-original-authored-visual-base",
        "terrainSvgUsedAsRepositoryOwnedBase": True,
        "thirdPartyRasterUsed": False,
        "thirdPartyVectorUsed": False,
        "externalImages": 0,
        "externalFonts": 0,
        "embeddedRasterImages": 0,
        "proceduralSvgDefinitionsOnly": True,
    }
    assert all(value is False for value in manifest["claims"].values())

    expected_safety = {
        "regionMembershipInferred": False,
        "coordinatesChanged": False,
        "locationsRemoved": False,
        "globalVisibilityPreserved": True,
    }
    assert disposition["status"] == "approved"
    assert disposition["policy"] == "retain_as_global_overlay_without_region_inference"
    assert len(disposition["locations"]) == 5
    assert all(row["disposition"] == "retain_global_overlay" and row["regionId"] is None for row in disposition["locations"])
    assert disposition["safety"] == expected_safety

    assert readiness["status"] == "final-canvas-review-candidate-awaiting-human-approval"
    assert readiness["automatedGateStatus"] == "passed"
    assert all(readiness["automatedGates"].values())
    assert readiness["unassignedLocationDisposition"]["status"] == "resolved"
    assert readiness["unassignedLocationDisposition"]["locationCount"] == 5
    assert readiness["unassignedLocationDisposition"]["regionMembershipInferred"] is False
    assert readiness["blockerCount"] == 1
    assert [row["id"] for row in readiness["blockers"]] == ["human-visual-review"]
    assert readiness["humanVisualReview"]["status"] == "not_recorded"
    assert readiness["finalCanvasFreeze"]["eligible"] is False
    assert readiness["finalCanvasFreeze"]["frozen"] is False
    assert readiness["finalCanvasFreeze"]["frozenSha256"] is None

    authored = progress["stageGates"]["finalOriginalUltraHdBase"]["authoredBase"]
    assert authored["status"] == "labels_icons_final_review_candidate_ready"
    assert authored["labelsIconsReviewPath"] == str(SVG.relative_to(ROOT))
    assert authored["labelsIconsReviewManifestPath"] == str(MANIFEST.relative_to(ROOT))
    assert authored["finalCanvasReadinessPath"] == str(READINESS.relative_to(ROOT))
    assert authored["labelsIconsReviewSha256"] == svg_digest
    assert authored["categoryMappingCount"] == 44
    assert authored["coreIconCount"] == 9
    assert authored["regionLabelCount"] == 10
    assert authored["confirmedAnchorIconCount"] == 50
    assert authored["labelOverlapCount"] == 0
    assert authored["unassignedLocationDispositionStatus"] == "resolved_retained_global_overlay"
    assert authored["finalCanvasFrozen"] is False
    assert authored["finalCanvasFreezeStatus"] == "blocked_pending_human_visual_review"
    assert authored["nextStage"] == "human_visual_review_and_final_canvas_freeze"
    assert progress["stageGates"]["coordinateAndOverlayCalibration"]["pixelTransformStatus"] == "blocked_pending_original_authored_final_canvas"

    assert digest(LEGACY) == os.environ["LEGACY_SHA256"]
    assert digest(TERRAIN) == os.environ["TERRAIN_SHA256"]
    assert digest(TERRAIN_MANIFEST) == os.environ["TERRAIN_MANIFEST_SHA256"]
    assert not list((ROOT / "assets/original-map").glob("*.png"))
    assert not list((ROOT / "assets/original-map").glob("*.jpg"))
    assert not list((ROOT / "assets/original-map").glob("*.webp"))

    print(json.dumps({
        "status": manifest["status"],
        "asset": manifest["asset"],
        "counts": manifest["counts"],
        "automatedGateStatus": readiness["automatedGateStatus"],
        "remainingBlockers": readiness["blockers"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
