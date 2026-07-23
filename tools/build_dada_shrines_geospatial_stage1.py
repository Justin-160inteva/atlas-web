#!/usr/bin/env python3
"""Build the non-pixel geospatial scaffold for Dada sequence 02 (27 shrines).

This stage validates the authorized analysis result, indexes every existing Shrine
marker, and creates 27 provisional temporal slots. It deliberately makes no automatic
location assignments; links require transient visual evidence in the next stage.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "data/analysis-results/dada-02.json"
LOCATIONS_PATH = ROOT / "data/locations.json"
CATEGORIES_PATH = ROOT / "data/categories.json"
REGIONS_PATH = ROOT / "data/regions.json"
OUTPUT_PATH = ROOT / "data/geospatial/dada-shrines-27-stage1.json"
JOB_PATH = ROOT / "data/analysis-jobs/dada-shrines-27-geospatial.json"
STATUS_PATH = ROOT / "data/batch-analysis/dada-shrines-27-geospatial-status.json"
EXPECTED_TITLE = "〖刺客信条影 新手攻略〗02 神社全收集（27个位置）"
EXPECTED_BVID = "BV1aFXaYmEDZ"
EXPECTED_SLOTS = 27
EXPECTED_CATEGORY_ID = "category-12313-shrine"
BVID_RE = re.compile(r"BV[0-9A-Za-z]+")
COUNT_RE = re.compile(r"(\d+)\s*个位置")


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


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
        local = [
            row for row in descriptors
            if start <= float(row.get("time") or 0) < end
            or (index == count - 1 and float(row.get("time") or 0) <= end)
        ]
        representative = max(local, key=descriptor_score) if local else nearest_descriptor(descriptors, center)
        local_clear = [
            row for row in clear_frames
            if start <= float(row.get("time") or 0) < end
            or (index == count - 1 and float(row.get("time") or 0) <= end)
        ]
        clear = max(local_clear, key=lambda row: float(row.get("sharpness") or 0)) if local_clear else None
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
                "borrowedFromNearestSlot": not bool(local),
            },
            "bestClearFrameTime": None if clear is None else float(clear.get("time") or 0),
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

    shrine_categories = [item for item in categories if normalized(item.get("title")) == "shrine"]
    if len(shrine_categories) != 1:
        raise RuntimeError(f"expected exactly one Shrine category, found {len(shrine_categories)}")
    shrine_category = shrine_categories[0]
    shrine_category_id = str(shrine_category["id"])
    region_titles = {str(item.get("id")): str(item.get("title") or item.get("id")) for item in regions}
    shrine_locations = [item for item in locations if str(item.get("category_id")) == shrine_category_id]
    shrine_locations.sort(key=lambda item: (
        region_titles.get(str(item.get("region_id")), ""),
        str(item.get("title") or ""),
        str(item.get("id") or ""),
    ))

    candidates = []
    for item in shrine_locations:
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
    checks = {
        "analysisStatusExact": result.get("status") == "analyzed",
        "authorExact": source.get("author") == "不再犹豫的达达猪",
        "titleExact": normalized(title) == normalized(EXPECTED_TITLE),
        "bvidExact": source_bvid == EXPECTED_BVID,
        "claimedShrineCount27": claimed_count == EXPECTED_SLOTS,
        "videoNotRetained": media.get("videoRetained") is False,
        "framePixelsNotRetained": media.get("framePixelsRetained") is False,
        "shrineCategoryExact": shrine_category_id == EXPECTED_CATEGORY_ID,
        "mapShrineCountMatchesCategory": len(candidates) == int(shrine_category.get("reported_location_count") or 0),
        "temporalSlots27": len(slots) == EXPECTED_SLOTS,
        "noAutomaticLocationLinks": all(slot["linkedLocationId"] is None for slot in slots),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(f"Dada shrine stage 1 checks failed: {failed}")

    timestamp = now()
    payload = {
        "schemaVersion": 1,
        "generatedAt": timestamp,
        "stage": "candidate-index-and-temporal-scaffold",
        "status": "ready-for-transient-evidence-extraction",
        "source": {
            "analysisResultPath": "data/analysis-results/dada-02.json",
            "title": title,
            "bvid": source_bvid,
            "durationSeconds": float(media.get("durationSeconds") or 0),
            "authorizationId": source.get("authorizationId"),
            "videoRetained": media.get("videoRetained"),
            "framePixelsRetained": media.get("framePixelsRetained"),
        },
        "counts": {
            "videoClaimedShrines": claimed_count,
            "mapShrineCandidates": len(candidates),
            "temporalSlots": len(slots),
            "linkedSlots": 0,
            "unlinkedSlots": len(slots),
        },
        "shrineCategory": {
            "id": shrine_category_id,
            "title": shrine_category.get("title"),
            "reportedLocationCount": shrine_category.get("reported_location_count"),
        },
        "candidateShrines": candidates,
        "temporalScaffold": {
            "method": "equal-duration provisional slots with descriptor representatives",
            "confidence": "provisional-not-geospatially-linked",
            "slots": slots,
        },
        "noGuessPolicy": {
            "enabled": True,
            "reason": "Numeric descriptors alone cannot identify shrine names or coordinates.",
            "requiredEvidenceBeforeLink": [
                "transient authorized frame containing a readable map popup or location label",
                "candidate identity selected from the 32-item Shrine index",
                "minimum confidence and unique location assignment checks",
            ],
        },
        "nextStage": {
            "name": "transient-shrine-popup-evidence-and-model-review",
            "firstBatchSlots": [1, 14],
            "mayDownloadAuthorizedVideo": True,
            "mayCommitPixels": False,
            "mustDeleteVideoAndFrames": True,
        },
    }
    write(OUTPUT_PATH, payload)
    write(JOB_PATH, {
        "schemaVersion": 1,
        "jobId": "dada-shrines-27-geospatial-v1",
        "status": "stage1-complete-evidence-pending",
        "sourceResultPath": "data/analysis-results/dada-02.json",
        "stage1Path": "data/geospatial/dada-shrines-27-stage1.json",
        "targetSlotCount": EXPECTED_SLOTS,
        "candidateShrineCount": len(candidates),
        "linkedSlotCount": 0,
        "pixelPolicy": "transient artifacts only; no video or frame pixels committed",
        "nextAction": "extract and model-review slots 1-14 with strict direct-label evidence",
        "updatedAt": timestamp,
    })
    write(STATUS_PATH, {
        "schemaVersion": 1,
        "status": "complete",
        "stage": "candidate-index-and-temporal-scaffold",
        "generatedAt": timestamp,
        "checks": checks,
        "counts": payload["counts"],
        "outputPath": "data/geospatial/dada-shrines-27-stage1.json",
        "jobPath": "data/analysis-jobs/dada-shrines-27-geospatial.json",
    })
    print(json.dumps({"status": "complete", "counts": payload["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
