#!/usr/bin/env python3
"""Build point-specific quest reward overrides from exact-title detail diagnostics.

Only explicit Markdown ``**Reward:**`` fields in the matched quest section are accepted.
The script never derives rewards from quest category, order, objectives, or nearby pages.
Ambiguous or conflicting fields are skipped and recorded for review.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC_PATH = ROOT / "data/rewards/reward-quest-detail-diagnostic.json"
OUTPUT_PATH = ROOT / "data/rewards/reward-point-evidence-overrides.json"

REWARD_FIELD = re.compile(r"(?im)^\s*(?:[-*+]\s*)?\*\*Rewards?\s*:\s*\*\*\s*(?P<value>[^\n]+?)\s*$")
UNKNOWN = re.compile(r"(?i)^(?:\?|\?\?|tbd|unknown|none|n/?a|not listed)$")
SAFE_SPLIT = re.compile(r"\s*(?:,|;|\band\b)\s*", re.IGNORECASE)
SPACE = re.compile(r"\s+")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def clean(value: str) -> str:
    value = value.replace("\u00a0", " ").replace("’", "'").replace("–", "-").replace("—", "-")
    return SPACE.sub(" ", value).strip().strip(".,; ")


def split_reward_field(value: str) -> list[str]:
    value = clean(value)
    if not value or UNKNOWN.fullmatch(value):
        return []
    parts = [clean(part) for part in SAFE_SPLIT.split(value)]
    return list(dict.fromkeys(part for part in parts if part and not UNKNOWN.fullmatch(part)))


def extract_detail_fields(detail: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for section in detail.get("sections", []):
        section_text = str(section.get("section") or "")
        for match in REWARD_FIELD.finditer(section_text):
            value = clean(match.group("value"))
            if value and not UNKNOWN.fullmatch(value) and value not in fields:
                fields.append(value)
    return fields


def source_from_detail(detail: dict[str, Any], reward_field: str, captured_at: str) -> dict[str, Any]:
    source_id = str(detail.get("sourceId") or "quest-detail-guide")
    publisher = "PowerPyx" if "powerpyx" in source_id.lower() else "VULKK" if "vulkk" in source_id.lower() else "公开任务攻略"
    return {
        "sourceId": f"quest-detail-{source_id}",
        "sourceType": "guide_article",
        "title": f"《刺客信条：影》任务详情页：{detail.get('label') or '同名任务'}",
        "publisherOrAuthor": publisher,
        "locator": detail.get("url"),
        "capturedAt": captured_at,
        "gameVersion": None,
        "supports": [
            "quest_identity",
            f"reward_field:{reward_field}",
        ],
        "limitationsZhCN": "同名任务详情页明确列出Reward字段；当前仅有一个独立攻略来源，因此保持高置信推断，不标记为多来源确认。",
    }


def main() -> int:
    diagnostic = load_json(DIAGNOSTIC_PATH, {})
    if diagnostic.get("targetCount") != 73:
        raise ValueError("Expected the 73-quest detail diagnostic")

    generated_at = now_iso()
    records: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for row in diagnostic.get("results", []):
        location_id = str(row.get("locationId") or "")
        title = str(row.get("title") or "")
        candidates: list[dict[str, Any]] = []
        for detail in row.get("details", []):
            if not detail.get("fetched"):
                continue
            for field in extract_detail_fields(detail):
                reward_lines = split_reward_field(field)
                if not reward_lines:
                    continue
                candidates.append({
                    "rewardField": field,
                    "rewardLines": reward_lines,
                    "source": source_from_detail(detail, field, diagnostic.get("generatedAt") or generated_at),
                })

        unique: dict[tuple[str, ...], dict[str, Any]] = {}
        for candidate in candidates:
            unique.setdefault(tuple(candidate["rewardLines"]), candidate)

        if not unique:
            skipped.append({
                "locationId": location_id,
                "title": title,
                "reason": "no_strict_reward_field",
            })
            continue
        if len(unique) > 1:
            conflicts.append({
                "locationId": location_id,
                "title": title,
                "type": "conflicting_reward_fields",
                "candidateRewardLines": [list(key) for key in unique],
            })
            continue

        candidate = next(iter(unique.values()))
        records[location_id] = {
            "locationId": location_id,
            "sourceLocationId": row.get("sourceLocationId"),
            "title": title,
            "categoryId": "category-12341-quest",
            "rewardFieldOriginal": candidate["rewardField"],
            "rewardLines": candidate["rewardLines"],
            "status": "high_confidence_inference",
            "confidence": 0.88,
            "evidenceMode": "exact_quest_reward_field",
            "sources": [candidate["source"]],
            "reviewZhCN": "任务标题与详情页章节精确匹配，且同一章节中存在明确Reward字段。",
        }

    payload = {
        "schemaVersion": 1,
        "release": "0.9.4.8",
        "generatedAt": generated_at,
        "sourceDiagnostic": DIAGNOSTIC_PATH.relative_to(ROOT).as_posix(),
        "targetQuestCount": 73,
        "overrideCount": len(records),
        "conflictCount": len(conflicts),
        "skippedCount": len(skipped),
        "records": records,
        "conflicts": conflicts,
        "skipped": skipped,
        "invariants": {
            "onlyQuestCategory": all(row.get("categoryId") == "category-12341-quest" for row in records.values()),
            "allHaveRewardLines": all(bool(row.get("rewardLines")) for row in records.values()),
            "allHaveSingleSource": all(len(row.get("sources", [])) == 1 for row in records.values()),
            "allStayHighConfidenceInference": all(row.get("status") == "high_confidence_inference" for row in records.values()),
            "noUnknownPlaceholders": all(not UNKNOWN.fullmatch(line) for row in records.values() for line in row.get("rewardLines", [])),
            "noConflictsImported": not conflicts,
            "noRewardRecordsModifiedByGenerator": True,
        },
    }
    write_json(OUTPUT_PATH, payload)
    print(json.dumps({
        "overrides": len(records),
        "conflicts": len(conflicts),
        "skipped": len(skipped),
        "titles": [row["title"] for row in records.values()],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
