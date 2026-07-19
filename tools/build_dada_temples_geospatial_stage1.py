#!/usr/bin/env python3
"""Build the first non-pixel geospatial scaffold for Dada sequence 03.

This stage deliberately does not guess which video slot belongs to which temple.
It validates the authorized analysis result, indexes every existing Temple marker,
and creates 36 provisional time slots for later transient visual evidence review.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "data/analysis-results/dada-temples-36.json"
LOCATIONS_PATH = ROOT / "data/locations.json"
CATEGORIES_PATH = ROOT / "data/categories.json"
REGIONS_PATH = ROOT / "data/regions.json"
OUTPUT_PATH = ROOT / "data/geospatial/dada-temples-36-stage1.json"
JOB_PATH = ROOT / "data/analysis-jobs/dada-temples-36-geospatial.json"
STATUS_PATH = ROOT / "data/batch-analysis/dada-temples-36-geospatial-status.json"
EXPECTED_TITLE = "〖刺客信条影 新手攻略〗03 寺庙全收集（36个位置）"
EXPECTED_BVID = "BV19EXYYWEdv"
EXPECTED_SLOTS = 36
BVID_RE = re.compile(r"BV[0-9A-Za-z]+")
COUNT_RE = re.compile(r"(\d+)\s*个位置")


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def normalized(value: Any) -> str:
    text = str(value or "").lower().replace("【", "〖").replace("】", "〗")
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", text)


def nearest_descriptor(descriptors: list[dict[str, Any]], center: float) -> dict[str, Any] | None:
    if not descriptors:
        return None
    return min(descriptors, key=lambda row: abs(float(row.get("time") or 0) - center))


def descriptor_score(row: dict[str, Any]) -> float:
    sharpness = max(0.0, float(row.get("sharpness") or 0))
    edge = max(0.0, float(row.get("edgeDensity") or 0))
    difference = max(0.0, float(row.get("difference") or 0))
    return math.log1p(sharpness) * (0.5 + edge) * (0.5 + difference)


def build_slots(result: dict[str, Any], count: int) -> list[dict[str, Any]]:
    duration = float((result.get("media") or {}).get("durationSeconds") or 0)
    descriptors = sorted(result.get("descriptors") or [], key=lambda row: float(row.get("time") or 0))
    clear_frames = sorted(result.get("clearFrameTimes") or [], key=lambda row: float(row.get("time") or 0))
    slots: list[dict[str, Any]] = []
    for index in range(count):
        start = duration * index / count
        end = duration * (index + 1) / count
        center = (start + end) / 2
        local = [row for row in descriptors if start <= float(row.get("time") or 0) < end or (index == count - 1 and float(row.get("time") or 0) <= end)]
        borrowed = False
        representative = max(local, key=descriptor_score) if local else nearest_descriptor(descriptors, center)
        if not local and representative is not None:
            borrowed = True
        local_clear = [row for row in clear_frames if start <= float(row.get("time") or 0) < end or (index == count - 1 and float(row.get("time") or 0) <= end)]
        clear = max(local_clear, key=lambda row: float(row.get("sharpness") or 0)) if local_clear else None
        nearby_boundary = [row for row in descriptors if abs(float(row.get("time") or 0) - start) <= 3.0]
        transition = max(nearby_boundary, key=lambda row: float(row.get("difference") or 0)) if nearby_boundary else None
        slots.append({
            "slot": index + 1,
            "startSeconds": round(start, 3),
            "endSeconds": round(end, 3),
            "centerSeconds": round(center, 3),
            "descriptorCount": len(local),
            "representativeDescriptor": None if representative is None else {
                "time": float(representative.get("time") or 0),
                "sharpness": float(representative.get("sharpness") or 0),
                "edgeDensity": float(representative.get("edgeDensity") or 0),
                "difference": float(representative.get("difference") or 0),
                "borrowedFromNearestSlot": borrowed,
            },
            "bestClearFrameTime": None if clear is None else float(clear.get("time") or 0),
            "boundaryTransition": None if transition is None else {
                "time": float(transition.get("time") or 0),
                "difference": float(transition.get("difference") or 0),
            },
            "linkedLocationId": None,
            "linkConfidence": "unlinked",
        })
    return slots


def main() -> int:
    result = load(RESULT_PATH)
    locations = load(LOCATIONS_PATH)
    categories = load(CATEGORIES_PATH)
    regions = load(REGIONS_PATH)
    source = result.get("source") or {}
    media = result.get("media") or {}
    title = str(source.get("title") or "")
    source_bvid_match = BVID_RE.search(str(source.get("url") or ""))
    source_bvid = source_bvid_match.group(0) if source_bvid_match else None
    count_match = COUNT_RE.search(title)
    claimed_count = int(count_match.group(1)) if count_match else None

    temple_categories = [item for item in categories if normalized(item.get("title")) == "temple"]
    if len(temple_categories) != 1:
        raise RuntimeError(f"expected exactly one Temple category, found {len(temple_categories)}")
    temple_category = temple_categories[0]
    temple_category_id = str(temple_category["id"])
    region_titles = {str(item.get("id")): str(item.get("title") or item.get("id")) for item in regions}
    temple_locations = [item for item in locations if str(item.get("category_id")) == temple_category_id]
    temple_locations.sort(key=lambda item: (region_titles.get(str(item.get("region_id")), ""), str(item.get("title") or ""), str(item.get("id") or "")))

    candidates = []
    for item in temple_locations:
        source_info = item.get("source") or {}
        candidates.append({
            "locationId": item.get("id"),
            "title": item.get("title"),
            "regionId": item.get("region_id"),
            "regionTitle": region_titles.get(str(item.get("region_id")), str(item.get("region_id") or "Unknown")),
            "atlas": {"x": item.get("atlas_x"), "y": item.get("atlas_y")},
            "sourceLocationId": source_info.get("location_id"),
            "sourceSystem": source_info.get("system"),
            "existingStatus": item.get("status"),
            "existingVerified": bool(item.get("verified")),
        })

    slots = build_slots(result, EXPECTED_SLOTS)
    transition_peaks = sorted(
        [
            {"time": float(row.get("time") or 0), "difference": float(row.get("difference") or 0)}
            for row in result.get("descriptors") or []
            if float(row.get("time") or 0) > 0
        ],
        key=lambda row: (-row["difference"], row["time"]),
    )[:35]

    checks = {
        "analysisStatusExact": result.get("status") == "analyzed",
        "authorExact": source.get("author") == "不再犹豫的达达猪",
        "titleExact": normalized(title) == normalized(EXPECTED_TITLE),
        "bvidExact": source_bvid == EXPECTED_BVID,
        "claimedTempleCount36": claimed_count == EXPECTED_SLOTS,
        "videoNotRetained": media.get("videoRetained") is False,
        "framePixelsNotRetained": media.get("framePixelsRetained") is False,
        "templeCategoryExact": temple_category_id == "category-12311-temple",
        "mapTempleCountMatchesCategory": len(candidates) == int(temple_category.get("reported_location_count") or 0),
        "temporalSlots36": len(slots) == EXPECTED_SLOTS,
        "noAutomaticLocationLinks": all(slot["linkedLocationId"] is None for slot in slots),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(f"Dada temple stage 1 checks failed: {failed}")

    timestamp = now()
    payload = {
        "schemaVersion": 1,
        "generatedAt": timestamp,
        "stage": "candidate-index-and-temporal-scaffold",
        "status": "ready-for-transient-evidence-extraction",
        "source": {
            "analysisResultPath": "data/analysis-results/dada-temples-36.json",
            "title": title,
            "bvid": source_bvid,
            "durationSeconds": float(media.get("durationSeconds") or 0),
            "authorizationId": source.get("authorizationId"),
            "videoRetained": media.get("videoRetained"),
            "framePixelsRetained": media.get("framePixelsRetained"),
        },
        "counts": {
            "videoClaimedTemples": claimed_count,
            "mapTempleCandidates": len(candidates),
            "temporalSlots": len(slots),
            "linkedSlots": 0,
            "unlinkedSlots": len(slots),
        },
        "templeCategory": {
            "id": temple_category_id,
            "title": temple_category.get("title"),
            "reportedLocationCount": temple_category.get("reported_location_count"),
        },
        "candidateTemples": candidates,
        "temporalScaffold": {
            "method": "equal-duration provisional slots with descriptor representatives",
            "confidence": "provisional-not-geospatially-linked",
            "transitionPeaks": transition_peaks,
            "slots": slots,
        },
        "noGuessPolicy": {
            "enabled": True,
            "reason": "Numeric frame descriptors cannot identify temple names or map coordinates by themselves.",
            "requiredEvidenceBeforeLink": [
                "transient authorized video frame containing map or location text",
                "independent exact location identity confirmation",
                "coordinate match against the existing Temple candidate index",
            ],
        },
        "nextStage": {
            "name": "transient-map-and-title-evidence-extraction",
            "mayDownloadAuthorizedVideo": True,
            "mayCommitPixels": False,
            "mustDeleteVideoAndFrames": True,
        },
    }
    write(OUTPUT_PATH, payload)

    job = {
        "schemaVersion": 1,
        "jobId": "dada-temples-36-geospatial-v1",
        "status": "stage1-complete-evidence-pending",
        "sourceResultPath": "data/analysis-results/dada-temples-36.json",
        "stage1Path": "data/geospatial/dada-temples-36-stage1.json",
        "targetSlotCount": EXPECTED_SLOTS,
        "candidateTempleCount": len(candidates),
        "linkedSlotCount": 0,
        "pixelPolicy": "transient artifacts only; no video or frame pixels committed to the repository",
        "nextAction": "extract and review transient map/title evidence for the 36 provisional slots",
        "updatedAt": timestamp,
    }
    write(JOB_PATH, job)

    status = {
        "schemaVersion": 1,
        "status": "complete",
        "stage": "candidate-index-and-temporal-scaffold",
        "generatedAt": timestamp,
        "checks": checks,
        "counts": payload["counts"],
        "outputPath": "data/geospatial/dada-temples-36-stage1.json",
        "jobPath": "data/analysis-jobs/dada-temples-36-geospatial.json",
    }
    write(STATUS_PATH, status)
    print(json.dumps({"status": "complete", "counts": payload["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
