#!/usr/bin/env python3
"""Apply the no-inference disposition and final-review visual balance adjustments."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DISPOSITION_PATH = ROOT / "data/geospatial/geospatial-unassigned-location-disposition.json"
READINESS_PATH = ROOT / "data/geospatial/geospatial-original-final-canvas-readiness.json"
MANIFEST_PATH = ROOT / "data/geospatial/geospatial-original-labels-icons-final-review-v1.json"
PROGRESS_PATH = ROOT / "data/geospatial/geospatial-progress.json"
SVG_PATH = ROOT / "assets/original-map/atlas-original-labels-icons-final-review-v1.svg"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    disposition = load(DISPOSITION_PATH)
    readiness = load(READINESS_PATH)
    manifest = load(MANIFEST_PATH)
    progress = load(PROGRESS_PATH)

    if disposition.get("status") != "approved":
        raise RuntimeError("unassigned location disposition is not approved")
    if disposition.get("policy") != "retain_as_global_overlay_without_region_inference":
        raise RuntimeError("unexpected unassigned location policy")
    expected_safety = {
        "regionMembershipInferred": False,
        "coordinatesChanged": False,
        "locationsRemoved": False,
        "globalVisibilityPreserved": True,
    }
    if disposition.get("safety") != expected_safety:
        raise RuntimeError(f"unassigned location safety contract mismatch: {disposition.get('safety')!r}")

    expected_ids = {str(row["locationId"]) for row in readiness["unassignedLocationGuides"]}
    rows = disposition.get("locations")
    if not isinstance(rows, list) or len(rows) != 5:
        raise RuntimeError("disposition must contain exactly five locations")
    actual_ids = {str(row["locationId"]) for row in rows}
    if actual_ids != expected_ids:
        raise RuntimeError(f"disposition IDs do not match readiness guides: {sorted(actual_ids ^ expected_ids)}")
    for row in rows:
        if row.get("disposition") != "retain_global_overlay":
            raise RuntimeError(f"unexpected disposition for {row.get('locationId')}")
        if row.get("regionId") is not None:
            raise RuntimeError(f"region inference is forbidden for {row.get('locationId')}")

    unresolved = [row for row in readiness["blockers"] if row["id"] != "unassigned-locations"]
    if [row["id"] for row in unresolved] != ["human-visual-review"]:
        raise RuntimeError("unexpected blockers after applying unassigned disposition")

    svg = SVG_PATH.read_text(encoding="utf-8")
    old_status = "BLOCKED: 5 UNASSIGNED LOCATIONS · HUMAN VISUAL REVIEW"
    new_status = "UNASSIGNED RETAINED GLOBALLY · BLOCKED: HUMAN VISUAL REVIEW"
    if old_status not in svg:
        raise RuntimeError("expected pre-disposition review status text was not found in SVG")
    svg = svg.replace(old_status, new_status, 1)
    balance_style = r'''
    <style id="atlas-final-review-visual-balance">
      #land-region-underlays path { stroke-width:7px !important; stroke-opacity:.32 !important; }
      .coastline-ink { stroke-width:6px !important; opacity:.36 !important; }
      .coastline-light { stroke-width:2px !important; opacity:.30 !important; }
      .route-underlay { stroke-width:8px !important; opacity:.24 !important; }
      .route-line { stroke-width:4px !important; opacity:.50 !important; stroke-dasharray:14 22 !important; }
    </style>
'''
    if 'id="atlas-final-review-visual-balance"' in svg:
        raise RuntimeError("visual balance style is already present before disposition processing")
    if "</defs>" not in svg:
        raise RuntimeError("SVG defs closing tag is missing")
    svg = svg.replace("</defs>", balance_style + "\n  </defs>", 1)
    SVG_PATH.write_text(svg, encoding="utf-8")
    svg_digest = sha256(SVG_PATH)

    readiness["status"] = "final-canvas-review-candidate-awaiting-human-approval"
    readiness["unassignedLocationDisposition"] = {
        "status": "resolved",
        "path": str(DISPOSITION_PATH.relative_to(ROOT)),
        "policy": disposition["policy"],
        "locationCount": len(rows),
        "regionMembershipInferred": False,
        "globalVisibilityPreserved": True,
    }
    readiness["visualBalanceReview"] = {
        "status": "adjusted_after_rendered_preview",
        "regionUnderlayStrokeWidth": 7,
        "coastlineInkStrokeWidth": 6,
        "routeLineStrokeWidth": 4,
        "purpose": "reduce overlapping internal outlines and preserve terrain/label hierarchy",
    }
    readiness["automatedGates"]["visualBalanceOverridesApplied"] = True
    readiness["blockers"] = unresolved
    readiness["blockerCount"] = len(unresolved)
    readiness["candidate"] = {
        **manifest["asset"],
        "sizeBytes": SVG_PATH.stat().st_size,
        "sha256": svg_digest,
    }
    readiness["finalCanvasFreeze"]["reason"] = (
        "all automated and unassigned-location disposition gates passed; human visual approval remains required"
    )
    readiness["nextAction"] = "complete human visual review, then record approval and freeze the immutable final canvas hash"
    write(READINESS_PATH, readiness)

    manifest["asset"]["sizeBytes"] = SVG_PATH.stat().st_size
    manifest["asset"]["sha256"] = svg_digest
    manifest["unassignedLocationDisposition"] = readiness["unassignedLocationDisposition"]
    manifest["visualReviewAdjustments"] = readiness["visualBalanceReview"]
    manifest["nextAction"] = "complete human visual review, then record approval and freeze the immutable final canvas hash"
    write(MANIFEST_PATH, manifest)

    authored = progress["stageGates"]["finalOriginalUltraHdBase"]["authoredBase"]
    authored["unassignedLocationDispositionPath"] = str(DISPOSITION_PATH.relative_to(ROOT))
    authored["unassignedLocationDispositionStatus"] = "resolved_retained_global_overlay"
    authored["visualBalanceReviewStatus"] = "adjusted_after_rendered_preview"
    authored["labelsIconsReviewSha256"] = svg_digest
    authored["finalCanvasFreezeStatus"] = "blocked_pending_human_visual_review"
    progress["originalAuthoredBase"]["unassignedLocationDispositionStatus"] = "resolved_retained_global_overlay"
    progress["originalAuthoredBase"]["visualBalanceReviewStatus"] = "adjusted_after_rendered_preview"
    progress["originalAuthoredBase"]["nextAction"] = "complete human visual review before final canvas freeze"
    write(PROGRESS_PATH, progress)

    print(json.dumps({
        "status": readiness["status"],
        "resolvedUnassignedLocations": len(rows),
        "visualBalanceReview": readiness["visualBalanceReview"],
        "candidateSha256": svg_digest,
        "remainingBlockers": readiness["blockers"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
