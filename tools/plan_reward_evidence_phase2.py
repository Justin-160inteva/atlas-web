#!/usr/bin/env python3
"""Plan phase-two evidence research for unresolved Atlas reward records.

The planner does not invent rewards or change the catalog. It classifies every unresolved
location by category, region, available source text, and likely evidence strategy, then
writes a bounded priority queue for subsequent official/guide/video/image research.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data/rewards/reward-summary-catalog.json"
LOCATIONS_PATH = ROOT / "data/locations.json"
CATEGORIES_PATH = ROOT / "data/categories.json"
REGIONS_PATH = ROOT / "data/regions.json"
SOURCES_PATH = ROOT / "data/rewards/reward-research-sources.json"
OUTPUT_PATH = ROOT / "data/rewards/reward-evidence-phase2-plan.json"


def load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_lookup(value: Any) -> dict[str, dict[str, Any]]:
    if isinstance(value, dict):
        if isinstance(value.get("items"), list):
            value = value["items"]
        else:
            return {str(key): item if isinstance(item, dict) else {"name": str(item)} for key, item in value.items()}
    if isinstance(value, list):
        result: dict[str, dict[str, Any]] = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            key = item.get("id") or item.get("category_id") or item.get("region_id") or item.get("slug")
            if key is not None:
                result[str(key)] = item
        return result
    return {}


def label(item: dict[str, Any] | None, fallback: str) -> str:
    item = item or {}
    return str(item.get("nameZhCN") or item.get("name_zh") or item.get("name") or item.get("title") or item.get("label") or fallback)


def description_has_reward_text(location: dict[str, Any]) -> bool:
    description = str(location.get("description") or "").lower()
    return "**reward" in description or "rewards:" in description or "reward:" in description


def strategy(category_label: str, title: str, description: str) -> tuple[str, int, list[str]]:
    text = f"{category_label} {title} {description}".lower()
    if any(token in text for token in ("castle", "城", "fort", "堡")):
        return "castle_legendary_chest_crosscheck", 100, ["official_reward_mechanics", "castle", "legendary_chest", "video"]
    if any(token in text for token in ("kofun", "古坟", "tomb")):
        return "kofun_location_reward_crosscheck", 96, ["kofun", "guide", "video"]
    if any(token in text for token in ("legendary chest", "传奇宝箱", "chest")):
        return "legendary_chest_crosscheck", 94, ["legendary_chest", "guide", "video"]
    if any(token in text for token in ("quest", "任务", "contract", "契约", "target", "目标")):
        return "quest_completion_reward_crosscheck", 90, ["quest", "guide", "video"]
    if any(token in text for token in ("sumi-e", "水墨", "painting", "画")):
        return "collectible_identity_and_unlock_crosscheck", 82, ["collectible", "image", "video"]
    if any(token in text for token in ("pet", "动物", "animal", "cub", "pup")):
        return "pet_unlock_crosscheck", 80, ["pet", "image", "video"]
    if any(token in text for token in ("tea bowl", "茶碗", "tea", "茶具")):
        return "tea_collectible_crosscheck", 78, ["collectible", "guide", "image"]
    if any(token in text for token in ("viewpoint", "俯瞰点", "sync", "同步点")):
        return "activity_completion_reward_crosscheck", 68, ["official_mechanics", "guide"]
    if any(token in text for token in ("shrine", "神社", "temple", "寺", "kata", "冥想")):
        return "activity_reward_crosscheck", 72, ["activity", "guide", "video"]
    return "point_specific_external_evidence_required", 50, ["official", "guide", "video", "image"]


def main() -> int:
    catalog = load(CATALOG_PATH, {})
    locations = load(LOCATIONS_PATH, [])
    categories = normalize_lookup(load(CATEGORIES_PATH, []))
    regions = normalize_lookup(load(REGIONS_PATH, []))
    registry = load(SOURCES_PATH, {"sources": []})

    records = catalog.get("records", {})
    if not isinstance(records, dict) or len(records) != 3430:
        raise ValueError("Expected a 3430-record reward catalog")
    location_by_id = {str(item.get("id")): item for item in locations if isinstance(item, dict) and item.get("id")}
    unresolved_ids = [location_id for location_id, record in records.items() if record.get("status") == "unresolved"]

    category_counts: Counter[str] = Counter()
    region_counts: Counter[str] = Counter()
    strategy_counts: Counter[str] = Counter()
    has_description_count = 0
    has_source_location_count = 0
    candidates: list[dict[str, Any]] = []

    for location_id in unresolved_ids:
        record = records[location_id]
        location = location_by_id.get(location_id, {})
        category_id = str(location.get("category_id") or record.get("categoryId") or "uncategorized")
        region_id = str(location.get("region_id") or "unknown-region")
        category_name = label(categories.get(category_id), category_id)
        region_name = label(regions.get(region_id), region_id)
        title = str(location.get("title") or location.get("name") or location_id)
        description = str(location.get("description") or "")
        method, base_priority, evidence_types = strategy(category_name, title, description)
        source_location_id = record.get("sourceLocationId") or (location.get("source") or {}).get("location_id")
        has_description = bool(description.strip())
        has_reward_text = description_has_reward_text(location)

        category_counts[f"{category_id}\t{category_name}"] += 1
        region_counts[f"{region_id}\t{region_name}"] += 1
        strategy_counts[method] += 1
        has_description_count += int(has_description)
        has_source_location_count += int(source_location_id is not None)

        priority = base_priority
        if source_location_id is not None:
            priority += 4
        if has_description:
            priority += 2
        if has_reward_text:
            priority += 8
        candidates.append({
            "locationId": location_id,
            "sourceLocationId": source_location_id,
            "title": title,
            "categoryId": category_id,
            "categoryZhCN": category_name,
            "regionId": region_id,
            "regionZhCN": region_name,
            "priority": priority,
            "strategy": method,
            "desiredEvidenceTypes": evidence_types,
            "hasDescription": has_description,
            "hasRewardText": has_reward_text,
            "currentSummaryZhCN": record.get("summaryZhCN"),
        })

    candidates.sort(key=lambda item: (-item["priority"], item["categoryZhCN"], item["title"], item["locationId"]))
    point_sources = [source for source in registry.get("sources", []) if source.get("pointEvidence")]
    nonpoint_sources = [source for source in registry.get("sources", []) if not source.get("pointEvidence")]

    payload = {
        "schemaVersion": 1,
        "release": "0.9.4.8",
        "generatedAt": now_iso(),
        "targetLocationCount": 3430,
        "unresolvedCount": len(unresolved_ids),
        "resolvedOrInferredCount": 3430 - len(unresolved_ids),
        "unresolvedWithDescription": has_description_count,
        "unresolvedWithSourceLocationId": has_source_location_count,
        "categoryCount": len(category_counts),
        "regionCount": len(region_counts),
        "strategyCounts": dict(strategy_counts.most_common()),
        "topCategories": [
            {"categoryId": key.split("\t", 1)[0], "categoryZhCN": key.split("\t", 1)[1], "unresolved": count}
            for key, count in category_counts.most_common(40)
        ],
        "topRegions": [
            {"regionId": key.split("\t", 1)[0], "regionZhCN": key.split("\t", 1)[1], "unresolved": count}
            for key, count in region_counts.most_common(30)
        ],
        "registeredSources": {
            "pointEvidenceCount": len(point_sources),
            "contextOrTerminologyCount": len(nonpoint_sources),
            "pointEvidenceSourceIds": [source.get("sourceId") for source in point_sources],
        },
        "researchPolicyZhCN": "按具体地点证据优先。只有来源能同时对应地点和奖励时才升级证据状态；类别规律仅用于排序，不直接生成奖励。",
        "nextBatchSize": min(100, len(candidates)),
        "nextBatch": candidates[:100],
        "allCandidates": candidates,
        "invariants": {
            "catalogCountPreserved": len(records) == 3430,
            "unresolvedCountConserved": len(candidates) == len(unresolved_ids),
            "noRewardValuesGenerated": True,
            "noEvidenceStatusChanged": True,
        },
    }
    write(OUTPUT_PATH, payload)
    print(json.dumps({
        "unresolved": len(unresolved_ids),
        "categories": len(category_counts),
        "nextBatch": min(100, len(candidates)),
        "pointSources": len(point_sources),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
