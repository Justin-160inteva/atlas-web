#!/usr/bin/env python3
"""Audit authorized video and geospatial evidence for the first Atlas 2.5D pilot tile.

This tool does not infer building, road, water or terrain geometry. It only measures
repository evidence, selects a candidate region/tile, and records gaps that require
additional authorized video coverage before reconstruction.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "data/geospatial/geospatial-2p5d-pilot-coverage-audit-plan.json"
AUDIT_PATH = ROOT / "data/geospatial/geospatial-2p5d-pilot-coverage-audit.json"
BRIEF_PATH = ROOT / "data/geospatial/geospatial-2p5d-pilot-video-authorization-brief.json"
GRID_SIZE = 16


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalized(value: Any) -> str:
    text = str(value or "").lower().replace("·", " ")
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", text)


def bounded_strings(value: Any, *, depth: int = 0) -> list[str]:
    """Extract useful textual metadata without traversing numeric descriptor matrices."""
    if depth > 6:
        return []
    if isinstance(value, str):
        return [value] if len(value) <= 2000 else []
    if isinstance(value, dict):
        output: list[str] = []
        ignored = {"descriptors", "clearFrameTimes", "histogram", "samples", "frames", "numericFeatures"}
        for key, item in value.items():
            if str(key) in ignored:
                continue
            output.extend(bounded_strings(item, depth=depth + 1))
        return output
    if isinstance(value, list):
        output: list[str] = []
        for item in value[:500]:
            output.extend(bounded_strings(item, depth=depth + 1))
        return output
    return []


def alias_match(text: str, aliases: list[str]) -> bool:
    normalized_text = normalized(text)
    return any(normalized(alias) and normalized(alias) in normalized_text for alias in aliases)


def category_family(title: str) -> str:
    token = normalized(title)
    if token in {
        "castle", "fort", "hostilelandmark", "kakurega", "landmark", "subregion", "viewpoint",
        "shrine", "temple", "smallshrine", "kofun",
    }:
        return "building-or-landmark"
    if token in {"gearvendor", "ornamentvendor", "porttrader"}:
        return "service-or-settlement"
    if token in {"quest", "target"}:
        return "quest-or-character"
    if token in {
        "hiddentrail", "horsearchery", "kata", "kujikiri", "rift",
    }:
        return "activity-or-route"
    if token in {"chest", "legendarychest", "stockpile", "keys", "kurakey", "weaponpart"}:
        return "loot-or-equipment"
    return "collectible-or-other"


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def score_region(
    *,
    explicit_videos: list[dict[str, Any]],
    locations: list[dict[str, Any]],
    anchor_count: int,
    category_titles: dict[str, str],
    weights: dict[str, float],
) -> dict[str, Any]:
    duration_minutes = sum(float((row.get("media") or {}).get("durationSeconds") or 0) for row in explicit_videos) / 60.0
    kept_frames = sum(int((row.get("scan") or {}).get("kept") or 0) for row in explicit_videos)
    video_count = len(explicit_videos)
    video_evidence = 100.0 * (
        0.55 * clamp(video_count / 3.0)
        + 0.25 * clamp(duration_minutes / 120.0)
        + 0.20 * clamp(kept_frames / 600.0)
    )

    category_ids = {str(row.get("category_id") or "") for row in locations if row.get("category_id")}
    category_count = len(category_ids)
    geospatial = 100.0 * (
        0.40 * clamp(len(locations) / 500.0)
        + 0.35 * clamp(anchor_count / 5.0)
        + 0.25 * clamp(category_count / 12.0)
    )

    family_counts = Counter(category_family(category_titles.get(category_id, category_id)) for category_id in category_ids)
    structural_count = sum(
        1 for row in locations
        if category_family(category_titles.get(str(row.get("category_id") or ""), "")) == "building-or-landmark"
    )
    represented_families = len([name for name, count in family_counts.items() if count > 0])
    scene_diversity = 100.0 * (
        0.45 * clamp(represented_families / 6.0)
        + 0.35 * clamp(structural_count / 40.0)
        + 0.20 * clamp(category_count / 20.0)
    )

    total = (
        video_evidence * float(weights["authorizedVideoEvidence"])
        + geospatial * float(weights["geospatialReadiness"])
        + scene_diversity * float(weights["sceneDiversity"])
    )
    return {
        "total": round(total, 3),
        "authorizedVideoEvidence": round(video_evidence, 3),
        "geospatialReadiness": round(geospatial, 3),
        "sceneDiversity": round(scene_diversity, 3),
        "metrics": {
            "explicitAuthorizedVideos": video_count,
            "explicitAuthorizedDurationMinutes": round(duration_minutes, 3),
            "keptNumericDescriptorSamples": kept_frames,
            "locations": len(locations),
            "confirmedAnchors": anchor_count,
            "distinctCategories": category_count,
            "structuralLocations": structural_count,
            "representedSceneFamilies": represented_families,
            "sceneFamilyCounts": dict(sorted(family_counts.items())),
        },
    }


def choose_tile(
    region_locations: list[dict[str, Any]],
    anchors: list[dict[str, Any]],
    category_titles: dict[str, str],
) -> dict[str, Any] | None:
    if not region_locations:
        return None
    anchor_ids = {str(row.get("locationId")) for row in anchors}
    cells: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in region_locations:
        try:
            x = clamp(float(row["atlas_x"]))
            y = clamp(float(row["atlas_y"]))
        except (KeyError, TypeError, ValueError):
            continue
        column = min(GRID_SIZE - 1, int(x * GRID_SIZE))
        grid_row = min(GRID_SIZE - 1, int(y * GRID_SIZE))
        cells[(column, grid_row)].append(row)

    candidates: list[tuple[float, int, int, list[dict[str, Any]], dict[str, Any]]] = []
    for (column, grid_row), rows in cells.items():
        category_ids = {str(row.get("category_id") or "") for row in rows if row.get("category_id")}
        families = {category_family(category_titles.get(category_id, category_id)) for category_id in category_ids}
        cell_anchor_count = sum(1 for row in rows if str(row.get("id")) in anchor_ids)
        structural = sum(
            1 for row in rows
            if category_family(category_titles.get(str(row.get("category_id") or ""), "")) == "building-or-landmark"
        )
        score = len(rows) + 4 * len(category_ids) + 8 * len(families) + 12 * cell_anchor_count + 3 * structural
        metadata = {
            "locationCount": len(rows),
            "distinctCategories": len(category_ids),
            "sceneFamilies": sorted(families),
            "confirmedAnchorCount": cell_anchor_count,
            "structuralLocationCount": structural,
        }
        candidates.append((score, column, grid_row, rows, metadata))

    candidates.sort(key=lambda item: (-item[0], -item[4]["confirmedAnchorCount"], -item[4]["distinctCategories"], item[2], item[1]))
    score, column, grid_row, rows, metadata = candidates[0]
    x0 = column / GRID_SIZE
    y0 = grid_row / GRID_SIZE
    x1 = (column + 1) / GRID_SIZE
    y1 = (grid_row + 1) / GRID_SIZE
    summaries = []
    for row in sorted(rows, key=lambda item: str(item.get("title") or item.get("id") or ""))[:40]:
        category_id = str(row.get("category_id") or "")
        summaries.append({
            "locationId": row.get("id"),
            "title": row.get("title"),
            "categoryId": category_id,
            "categoryTitle": category_titles.get(category_id),
            "atlas": {"x": row.get("atlas_x"), "y": row.get("atlas_y")},
            "confirmedAnchor": str(row.get("id")) in anchor_ids,
        })
    return {
        "grid": {"size": GRID_SIZE, "column": column, "row": grid_row},
        "normalizedBounds": {"minX": x0, "minY": y0, "maxX": x1, "maxY": y1},
        "selectionScore": round(score, 3),
        **metadata,
        "sampleLocations": summaries,
    }


def main() -> int:
    plan = load(PLAN_PATH)
    inputs = {name: ROOT / path for name, path in plan["inputs"].items()}
    regions = load(inputs["regions"])
    locations = load(inputs["locations"])
    categories = load(inputs["categories"])
    analysis_index = load(inputs["analysisIndex"])
    progress = load(inputs["geospatialProgress"])

    category_titles = {str(row.get("id")): str(row.get("title") or row.get("id")) for row in categories}
    region_titles = {str(row.get("id")): str(row.get("title") or row.get("id")) for row in regions}
    target_regions = {region_id: title for region_id, title in region_titles.items() if title in plan["regionAliases"]}
    if len(target_regions) != 10:
        raise RuntimeError(f"expected 10 target regions, found {len(target_regions)}: {sorted(target_regions.values())}")

    locations_by_region: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in locations:
        region_id = str(row.get("region_id") or "")
        if region_id in target_regions:
            locations_by_region[region_id].append(row)

    anchors = progress.get("anchors") or []
    anchors_by_region: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for anchor in anchors:
        region_id = str(anchor.get("regionId") or anchor.get("region_id") or "")
        if not region_id:
            location_id = str(anchor.get("locationId") or "")
            location = next((row for row in locations if str(row.get("id")) == location_id), None)
            if location:
                region_id = str(location.get("region_id") or "")
        if region_id in target_regions:
            anchors_by_region[region_id].append(anchor)

    imported_items = [
        row for row in analysis_index.get("items", [])
        if row.get("status") == "imported" and row.get("authorizationId")
    ]
    evidence_by_region: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unmatched_items: list[dict[str, Any]] = []
    for item in imported_items:
        searchable = [str(item.get("title") or "")]
        result_path = ROOT / str(item.get("resultPath") or "")
        if result_path.is_file():
            try:
                searchable.extend(bounded_strings(load(result_path)))
            except (OSError, json.JSONDecodeError):
                pass
        joined = "\n".join(searchable)
        matched_titles = [title for title, aliases in plan["regionAliases"].items() if alias_match(joined, aliases)]
        compact = {
            "jobId": item.get("jobId"),
            "externalSourceId": item.get("externalSourceId"),
            "authorizationId": item.get("authorizationId"),
            "author": item.get("author"),
            "title": item.get("title"),
            "resultPath": item.get("resultPath"),
            "media": item.get("media"),
            "scan": item.get("scan"),
            "matchedRegions": matched_titles,
        }
        if not matched_titles:
            unmatched_items.append(compact)
        for title in matched_titles:
            evidence_by_region[title].append(compact)

    rows: list[dict[str, Any]] = []
    requirements = plan["pilotRequirements"]
    for region_id, title in sorted(target_regions.items(), key=lambda item: item[1]):
        region_locations = locations_by_region[region_id]
        region_anchors = anchors_by_region[region_id]
        videos = evidence_by_region.get(title, [])
        scoring = score_region(
            explicit_videos=videos,
            locations=region_locations,
            anchor_count=len(region_anchors),
            category_titles=category_titles,
            weights=plan["weights"],
        )
        metrics = scoring["metrics"]
        hard_gates = {
            "explicitAuthorizedVideos": metrics["explicitAuthorizedVideos"] >= int(requirements["minimumExplicitAuthorizedVideos"]),
            "confirmedAnchors": metrics["confirmedAnchors"] >= int(requirements["minimumConfirmedAnchors"]),
            "locationCount": metrics["locations"] >= int(requirements["minimumLocationCount"]),
            "distinctCategories": metrics["distinctCategories"] >= int(requirements["minimumDistinctCategories"]),
        }
        rows.append({
            "regionId": region_id,
            "regionTitle": title,
            "score": scoring,
            "hardGates": hard_gates,
            "eligibleForPilotSelection": all(hard_gates.values()),
            "authorizedVideoEvidence": videos,
        })

    eligible = [row for row in rows if row["eligibleForPilotSelection"]]
    eligible.sort(key=lambda row: (-float(row["score"]["total"]), row["regionTitle"]))
    selected = eligible[0] if eligible else max(rows, key=lambda row: float(row["score"]["total"]))
    selected_id = str(selected["regionId"])
    selected_tile = choose_tile(locations_by_region[selected_id], anchors_by_region[selected_id], category_titles)

    gap_flags = {
        "buildingFootprints": "not-derived-from-current-numeric-analysis",
        "roadTopology": "not-derived-from-current-numeric-analysis",
        "waterAndCoastGeometry": "not-derived-from-current-numeric-analysis",
        "terrainElevation": "not-derived-from-current-numeric-analysis",
        "vegetationDistribution": "not-derived-from-current-numeric-analysis",
        "cameraPoseAndScale": "not-derived-from-current-numeric-analysis",
    }
    status = "pilot-region-selected-evidence-gaps-recorded" if selected["eligibleForPilotSelection"] else "no-region-passes-pilot-hard-gates"
    generated_at = utc_now()
    audit = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "status": status,
        "stage": plan["stage"],
        "sourceHashes": {str(path.relative_to(ROOT)): sha256(path) for path in inputs.values()},
        "counts": {
            "regions": len(rows),
            "locations": len(locations),
            "categories": len(categories),
            "analysisIndexItems": len(analysis_index.get("items", [])),
            "importedAuthorizedAnalysisItems": len(imported_items),
            "regionMatchedAuthorizedAnalysisItems": len({row["externalSourceId"] for values in evidence_by_region.values() for row in values}),
            "unmatchedAuthorizedAnalysisItems": len(unmatched_items),
            "confirmedAnchors": len(anchors),
        },
        "scoringWeights": plan["weights"],
        "regions": sorted(rows, key=lambda row: (-float(row["score"]["total"]), row["regionTitle"])),
        "selection": {
            "regionId": selected_id,
            "regionTitle": selected["regionTitle"],
            "eligible": selected["eligibleForPilotSelection"],
            "score": selected["score"],
            "tile": selected_tile,
            "geometryStatus": "not-modeled",
            "visualStatus": "not-started",
        },
        "evidenceGaps": gap_flags,
        "unmatchedAuthorizedAnalysisItems": unmatched_items,
        "safety": {
            "officialMapGeometryExtracted": False,
            "thirdPartyPixelsRetained": False,
            "unsupportedGeometryInferred": False,
            "existingCoordinatesModified": False,
            "pilotModelGenerated": False,
        },
        "nextAction": "review selected tile, then search for and authorize videos that resolve its building, road, water, terrain and camera-pose evidence gaps",
    }
    write(AUDIT_PATH, audit)

    selected_title = str(selected["regionTitle"])
    queries = [
        f"Assassin's Creed Shadows {selected_title} full exploration walkthrough",
        f"刺客信条 影 {selected_title} 全探索 攻略",
        f"Assassin's Creed Shadows {selected_title} castle shrine temple viewpoint",
        f"刺客信条影 {selected_title} 城堡 神社 寺庙 鸟瞰",
        f"Assassin's Creed Shadows {selected_title} roads villages coast river",
    ]
    brief = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "status": "authorization-search-brief-ready",
        "selectedRegion": {"id": selected_id, "title": selected_title},
        "selectedTile": selected_tile,
        "existingAuthorizedVideos": selected["authorizedVideoEvidence"],
        "requiredEvidence": [
            {
                "type": "building-layout",
                "need": "high or elevated views showing individual roofs, yards, walls and entrances",
                "priority": "critical",
            },
            {
                "type": "road-topology",
                "need": "continuous traversal through main roads, side roads, bridges and settlement entrances",
                "priority": "critical",
            },
            {
                "type": "water-and-coast",
                "need": "clear shoreline, river, lake, canal, harbor or bridge relationships when present in the tile",
                "priority": "critical",
            },
            {
                "type": "terrain-and-vegetation",
                "need": "wide views revealing ridges, slopes, fields, forests and elevation transitions",
                "priority": "high",
            },
            {
                "type": "camera-calibration",
                "need": "repeated landmarks from multiple directions or a map-to-world transition for relative scale",
                "priority": "high",
            },
        ],
        "internetSearchQueries": queries,
        "authorizationRequestMustCover": [
            "download and transiently scan the authorized video",
            "extract timestamps and numeric/structural evidence",
            "use observed spatial relationships for an original 2D/2.5D reconstruction",
            "publish only original reconstruction and evidence metadata, not source video frames",
        ],
        "doNotStartModelingUntil": [
            "at least one authorized video explicitly covers the selected tile",
            "building and road evidence are sufficient for a bounded sample",
            "water/terrain gaps are either resolved or explicitly excluded from the sample scope",
        ],
    }
    write(BRIEF_PATH, brief)
    print(json.dumps({
        "status": audit["status"],
        "selectedRegion": audit["selection"]["regionTitle"],
        "selectedScore": audit["selection"]["score"]["total"],
        "selectedTile": audit["selection"]["tile"],
        "authorizedAnalyses": audit["counts"]["importedAuthorizedAnalysisItems"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
