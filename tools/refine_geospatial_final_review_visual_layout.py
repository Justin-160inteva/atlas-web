#!/usr/bin/env python3
"""Refine the final-review SVG after generation.

This pass keeps the repository-owned terrain and icon geometry unchanged. It only
moves region label plates away from confirmed anchor icons, updates review-facing
copy, and refreshes hashes in the manifest/readiness/progress records.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SVG_PATH = ROOT / "assets/original-map/atlas-original-labels-icons-final-review-v1.svg"
MANIFEST_PATH = ROOT / "data/geospatial/geospatial-original-labels-icons-final-review-v1.json"
READINESS_PATH = ROOT / "data/geospatial/geospatial-original-final-canvas-readiness.json"
PROGRESS_PATH = ROOT / "data/geospatial/geospatial-progress.json"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def overlap(a: dict[str, float], b: dict[str, float], padding: float = 0.0) -> bool:
    return not (
        a["x"] + a["width"] + padding <= b["x"]
        or b["x"] + b["width"] + padding <= a["x"]
        or a["y"] + a["height"] + padding <= b["y"]
        or b["y"] + b["height"] + padding <= a["y"]
    )


def count_anchor_overlaps(labels: list[dict[str, Any]], anchors: list[dict[str, float]]) -> int:
    return sum(1 for label in labels for anchor in anchors if overlap(label, anchor, 10))


def rebuild_label_group(label: dict[str, Any]) -> str:
    return (
        f'<g class="atlas-new-region-label" data-region-id="{label["id"]}">'
        f'<path class="atlas-new-label-line" d="M {label["targetX"]:.2f} {label["targetY"]:.2f} L {label["centerX"]:.2f} {label["centerY"]:.2f}"/>'
        f'<rect class="atlas-new-region-plate" x="{label["x"]:.2f}" y="{label["y"]:.2f}" width="{label["width"]:.2f}" height="{label["height"]:.2f}" rx="28"/>'
        f'<text class="atlas-new-region-title" x="{label["centerX"]:.2f}" y="{label["centerY"] - 5:.2f}" text-anchor="middle">{label["regionTitle"]}</text>'
        f'<text class="atlas-new-region-meta" x="{label["centerX"]:.2f}" y="{label["centerY"] + 29:.2f}" text-anchor="middle">{label["locationCount"]} LOC · {label["confirmedAnchorCount"]} ANCHOR</text>'
        f'</g>'
    )


def main() -> int:
    svg = SVG_PATH.read_text(encoding="utf-8")
    manifest = load(MANIFEST_PATH)
    readiness = load(READINESS_PATH)
    progress = load(PROGRESS_PATH)

    anchor_matches = re.findall(
        r'class="atlas-authored-anchor-icon"\s+transform="translate\(([0-9.]+) ([0-9.]+)\)"',
        svg,
    )
    if len(anchor_matches) != 50:
        raise RuntimeError(f"expected 50 anchor transforms, found {len(anchor_matches)}")
    anchor_rects = [
        {"x": float(x) - 34.0, "y": float(y) - 34.0, "width": 68.0, "height": 68.0}
        for x, y in anchor_matches
    ]

    labels = [dict(row) for row in manifest["regionLabelPlacements"]]
    reserved = [
        {"x": 90.0, "y": 75.0, "width": 1500.0, "height": 240.0},
        {"x": 2700.0, "y": 85.0, "width": 1260.0, "height": 270.0},
        {"x": 2420.0, "y": 3310.0, "width": 1590.0, "height": 740.0},
    ]
    candidate_offsets: list[tuple[float, float]] = [(0.0, 0.0)]
    for radius in (125, 220, 330, 450, 580, 720, 880, 1040):
        for degrees in (270, 0, 180, 90, 315, 225, 45, 135):
            radians = math.radians(degrees)
            candidate_offsets.append((math.cos(radians) * radius, math.sin(radians) * radius))

    placed: list[dict[str, Any]] = []
    for original in labels:
        target_x = float(original["targetX"])
        target_y = float(original["targetY"])
        width = float(original["width"])
        height = float(original["height"])
        selected: dict[str, Any] | None = None
        for offset_x, offset_y in candidate_offsets:
            center_x = min(4096 - 270 - width / 2, max(270 + width / 2, target_x + offset_x))
            center_y = min(4096 - 270 - height / 2, max(270 + height / 2, target_y + offset_y))
            candidate = dict(original)
            candidate.update({
                "x": round(center_x - width / 2, 2),
                "y": round(center_y - height / 2, 2),
                "centerX": round(center_x, 2),
                "centerY": round(center_y, 2),
                "offsetX": round(center_x - target_x, 2),
                "offsetY": round(center_y - target_y, 2),
            })
            if any(overlap(candidate, panel, 18) for panel in reserved):
                continue
            if any(overlap(candidate, other, 18) for other in placed):
                continue
            if any(overlap(candidate, anchor, 12) for anchor in anchor_rects):
                continue
            selected = candidate
            break
        if selected is None:
            raise RuntimeError(f"unable to place anchor-safe label for {original['id']}")
        placed.append(selected)

    for label in placed:
        pattern = re.compile(
            rf'<g class="atlas-new-region-label" data-region-id="{re.escape(str(label["id"]))}">.*?</g>',
            re.S,
        )
        svg, replacements = pattern.subn(rebuild_label_group(label), svg, count=1)
        if replacements != 1:
            raise RuntimeError(f"unable to replace label group for {label['id']}")

    svg = svg.replace(
        "ORIGINAL TERRAIN &amp; COASTLINE · V1",
        "ORIGINAL MAP · LABELS &amp; ICONS · FINAL REVIEW",
        1,
    )
    svg = svg.replace(
        "Repository-owned editable final-canvas review candidate with original terrain, labels and iconography. Automated gates passed, but the canvas remains unfrozen pending human visual approval and five unassigned locations.",
        "Repository-owned editable final-canvas review candidate with original terrain, labels and iconography. Automated gates and the no-inference global-overlay disposition passed; the canvas remains unfrozen pending human visual approval.",
        1,
    )
    SVG_PATH.write_text(svg, encoding="utf-8")

    anchor_overlap_count = count_anchor_overlaps(placed, anchor_rects)
    if anchor_overlap_count != 0:
        raise RuntimeError(f"anchor-label overlaps remain: {anchor_overlap_count}")

    digest = sha256(SVG_PATH)
    manifest["regionLabelPlacements"] = placed
    manifest["counts"]["anchorLabelOverlaps"] = anchor_overlap_count
    manifest["asset"]["sizeBytes"] = SVG_PATH.stat().st_size
    manifest["asset"]["sha256"] = digest
    manifest["nextAction"] = "complete human visual review, then record approval and freeze the immutable final canvas hash"
    write(MANIFEST_PATH, manifest)

    readiness["candidate"] = manifest["asset"]
    readiness["automatedGates"]["anchorLabelOverlapCountWithinLimit"] = True
    readiness["nextAction"] = "complete human visual review, then record approval and freeze the immutable final canvas hash"
    write(READINESS_PATH, readiness)

    authored = progress["stageGates"]["finalOriginalUltraHdBase"]["authoredBase"]
    authored["labelsIconsReviewSha256"] = digest
    authored["anchorLabelOverlapCount"] = anchor_overlap_count
    progress["originalAuthoredBase"]["nextAction"] = "complete human visual review before final canvas freeze"
    write(PROGRESS_PATH, progress)

    print(json.dumps({
        "status": "visual-layout-refined",
        "regionLabels": len(placed),
        "anchorLabelOverlaps": anchor_overlap_count,
        "sha256": digest,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
