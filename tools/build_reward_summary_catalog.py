#!/usr/bin/env python3
"""Build evidence-aware Simplified Chinese reward summaries for all Atlas locations.

The builder is intentionally conservative:
- every location receives exactly one record;
- a single imported community source is never labelled official;
- an independent public source must match both location and named reward before
  a record can be upgraded to multi-source confirmed;
- missing evidence remains unresolved;
- unknown proper-name translations use a Chinese generic description while the
  original name is retained only in the structured evidence record.
"""

from __future__ import annotations

import html
import json
import re
import shutil
import sys
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
LOCATIONS_PATH = ROOT / "data/locations.json"
INDEX_PATH = ROOT / "data/rewards/reward-evidence-index.json"
POLICY_PATH = ROOT / "data/rewards/reward-source-policy.json"
TERMS_PATH = ROOT / "data/rewards/reward-terminology-zh-CN.json"
LEXICON_PATH = ROOT / "data/rewards/reward-translation-lexicon-zh-CN.json"
SOURCES_PATH = ROOT / "data/rewards/reward-research-sources.json"
CATALOG_PATH = ROOT / "data/rewards/reward-summary-catalog.json"
AUDIT_PATH = ROOT / "data/rewards/reward-source-audit.json"
QUEUE_PATH = ROOT / "data/rewards/reward-research-queue.json"
RECORDS_DIR = ROOT / "data/rewards/records"
BATCH_SIZE = 100
RELEASE = "0.9.4.8"

REWARD_SECTION = re.compile(
    r"\*\*Rewards?\s*:\s*\*\*\s*(.*?)(?=\n\s*\n\s*\*\*[^\n]+?:\s*\*\*|\Z)",
    re.IGNORECASE | re.DOTALL,
)
MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
QUANTITY_PREFIX = re.compile(r"^(?:(\d[\d,]*(?:\.\d+)?)\s*[x×]?\s+)(.+)$", re.IGNORECASE)
NUMBER_ONLY_REWARD = re.compile(
    r"^(\d[\d,]*(?:\.\d+)?)\s+(XP|Mastery Points?|Knowledge Points?|Experience Points?)$",
    re.IGNORECASE,
)
HEADING_LINE = re.compile(r"^\*\*[^*]+:\*\*$")
INLINE_LEGENDARY_REWARD = re.compile(
    r"^(?P<name>[^\n]{2,140}?)\s+-\s+(?P<descriptor>Leg(?:endary|edary)\s+[A-Za-z][A-Za-z /-]{1,60})$",
    re.IGNORECASE,
)
UNKNOWN_REWARD_PLACEHOLDERS = {"?", "??", "TBD", "Unknown"}
LATIN = re.compile(r"[A-Za-z]")

TYPE_KEYWORDS: list[tuple[str, str]] = [
    ("experience", "experience"),
    (" xp", "experience"),
    ("mastery point", "skill_point"),
    ("knowledge point", "knowledge_point"),
    ("trinket", "trinket"),
    ("amulet", "trinket"),
    ("engraving", "engraving"),
    ("light armor", "armor"),
    ("heavy armor", "armor"),
    ("armor", "armor"),
    ("armour", "armor"),
    ("headgear", "armor"),
    ("helmet", "armor"),
    ("legendary bo", "weapon"),
    ("katana", "weapon"),
    ("tanto", "weapon"),
    ("kusarigama", "weapon"),
    ("naginata", "weapon"),
    ("kanabo", "weapon"),
    ("teppo", "weapon"),
    ("bow", "weapon"),
    ("weapon", "weapon"),
    ("key", "quest_item"),
    ("scroll", "collectible"),
    ("material", "resource"),
    ("resource", "resource"),
    ("mon", "currency"),
]

TYPE_LABELS = {
    "currency": "货币",
    "resource": "资源",
    "gear": "装备",
    "weapon": "武器",
    "armor": "护甲",
    "trinket": "饰品",
    "engraving": "铭刻",
    "skill_point": "技能点",
    "knowledge_point": "知识点",
    "experience": "经验值",
    "ability": "能力",
    "cosmetic": "外观物品",
    "quest_item": "任务物品",
    "collectible": "收集品",
    "service_unlock": "功能解锁",
    "unknown": "奖励",
}

UNIT_LABELS = {
    "experience": "点",
    "skill_point": "个",
    "knowledge_point": "个",
    "currency": "",
    "resource": "份",
    "collectible": "件",
    "quest_item": "件",
    "unknown": "份",
}


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth and data.strip():
            self.parts.append(data)

    def text(self) -> str:
        return " ".join(self.parts)


@dataclass
class Translation:
    text: str
    exact: bool
    provisional: bool
    unknown_tokens: tuple[str, ...]


@dataclass
class ExternalPage:
    source: dict[str, Any]
    text: str
    normalized: str
    fetched: bool
    error: str | None


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def clean_markdown(value: str) -> str:
    value = MARKDOWN_LINK.sub(r"\1", value)
    value = re.sub(r"[`*_]", "", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def extract_reward_lines(description: str, category_id: str | None = None) -> list[str]:
    if not description:
        return []

    lines: list[str] = []
    match = REWARD_SECTION.search(description)
    if match:
        for raw in match.group(1).splitlines():
            raw = raw.strip()
            if not raw or HEADING_LINE.match(raw):
                continue
            raw = re.sub(r"^[\-•*]+\s*", "", raw)
            cleaned = clean_markdown(raw)
            if cleaned and cleaned not in UNKNOWN_REWARD_PLACEHOLDERS:
                lines.append(cleaned)

    # MapGenie Legendary Chest records commonly store the explicit reward as a
    # standalone "Proper Name - Legendary Type" line instead of a Rewards block.
    # Apply this fallback only to the explicit Legendary Chest category.
    if not lines and "legendary-chest" in str(category_id or "").lower():
        for raw in description.splitlines():
            cleaned = re.sub(r"^[\-•*]+\s*", "", clean_markdown(raw.strip()))
            if not cleaned or cleaned in UNKNOWN_REWARD_PLACEHOLDERS:
                continue
            inline = INLINE_LEGENDARY_REWARD.fullmatch(cleaned)
            if not inline:
                continue
            name = inline.group("name").strip()
            descriptor = re.sub(
                r"^Legedary\b",
                "Legendary",
                inline.group("descriptor").strip(),
                flags=re.IGNORECASE,
            )
            if name in UNKNOWN_REWARD_PLACEHOLDERS or name.startswith("??"):
                continue
            lines.append(f"{name} - {descriptor}")

    return list(dict.fromkeys(lines))


def normalize_for_match(value: str) -> str:
    value = html.unescape(value).lower()
    value = value.replace("’", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"[^a-z0-9一-龥]+", " ", value).strip()


def title_variants(title: str) -> list[str]:
    normalized = normalize_for_match(title)
    variants = {normalized}
    for suffix in (" castle", " kofun", " temple", " shrine", " fort", " palace"):
        if normalized.endswith(suffix):
            variants.add(normalized[: -len(suffix)].strip())
    return sorted((item for item in variants if len(item) >= 4), key=len, reverse=True)


def split_words(value: str) -> list[str]:
    value = value.replace("’", "'").replace("-", " ")
    return re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?|\d+", value)


def translate_name(name: str, lexicon: dict[str, Any]) -> Translation:
    exact_names = lexicon.get("exactNames", {})
    if name in exact_names:
        return Translation(exact_names[name], True, False, ())

    stripped = re.sub(r"^Legendary\s+", "", name, flags=re.IGNORECASE).strip()
    if stripped in exact_names:
        return Translation(exact_names[stripped], True, False, ())

    whole = lexicon.get("wholePhrases", {})
    if name in whole:
        return Translation(whole[name], True, False, ())
    if stripped in whole:
        return Translation(whole[stripped], True, False, ())

    tokens = lexicon.get("tokens", {})
    words = split_words(stripped)
    translated: list[str] = []
    unknown: list[str] = []
    possessive = False
    for word in words:
        lower = word.lower()
        if lower.endswith("'s"):
            base = lower[:-2]
            mapped = tokens.get(base)
            if mapped:
                translated.append(mapped)
            else:
                unknown.append(word[:-2])
            possessive = True
            continue
        mapped = tokens.get(lower)
        if mapped:
            if possessive and translated:
                translated.append("之")
                possessive = False
            translated.append(mapped)
        elif word.isdigit():
            translated.append(word)
        else:
            unknown.append(word)

    if words and not unknown and translated:
        text = "".join(translated)
        text = re.sub(r"之之+", "之", text)
        return Translation(text, False, True, ())

    return Translation("具体名称待核对", False, True, tuple(dict.fromkeys(unknown or words)))


def infer_type(value: str) -> str:
    lowered = f" {value.lower()} "
    for keyword, reward_type in TYPE_KEYWORDS:
        if keyword in lowered:
            return reward_type
    return "unknown"


def infer_rarity(value: str) -> str | None:
    lowered = value.lower()
    for rarity in ("legendary", "epic", "rare", "uncommon", "common"):
        if rarity in lowered:
            return rarity
    return None


def parse_reward_line(line: str, lexicon: dict[str, Any]) -> dict[str, Any]:
    original_line = line.strip()
    quantity: float | None = None
    quantity_status = "not_applicable"

    numeric = NUMBER_ONLY_REWARD.match(original_line)
    if numeric:
        quantity = float(numeric.group(1).replace(",", ""))
        descriptor = numeric.group(2)
        reward_type = infer_type(descriptor)
        return {
            "type": reward_type,
            "nameOriginal": descriptor,
            "nameZhCN": TYPE_LABELS[reward_type],
            "quantity": int(quantity) if quantity.is_integer() else quantity,
            "quantityStatus": "exact",
            "rarity": None,
            "notesZhCN": "数量直接来自原始地点资料中的奖励字段。",
            "_translationExact": True,
            "_namedReward": False,
            "_raw": original_line,
        }

    working = original_line
    prefix = QUANTITY_PREFIX.match(working)
    if prefix and not re.match(r"^\d{4}\b", working):
        quantity = float(prefix.group(1).replace(",", ""))
        quantity_status = "exact"
        working = prefix.group(2).strip()

    name_part = working
    descriptor = ""
    if " - " in working:
        name_part, descriptor = [part.strip() for part in working.rsplit(" - ", 1)]

    combined = f"{name_part} {descriptor}".strip()
    reward_type = infer_type(combined)
    rarity = infer_rarity(combined)
    translation = translate_name(name_part, lexicon)

    if reward_type in {"experience", "skill_point", "knowledge_point"}:
        name_zh = TYPE_LABELS[reward_type]
        named = False
    elif translation.text == "具体名称待核对":
        rarity_zh = "传奇" if rarity == "legendary" else ""
        name_zh = f"{rarity_zh}{TYPE_LABELS.get(reward_type, '奖励')}（具体名称待核对）"
        named = True
    else:
        name_zh = translation.text + ("（暂译）" if translation.provisional and not translation.exact else "")
        named = True

    notes: list[str] = []
    if translation.exact:
        notes.append("采用已登记的简体中文名称。")
    elif translation.text == "具体名称待核对":
        notes.append("原文专名已保留在 nameOriginal；前端不显示未经核对的伪官方中文名。")
    else:
        notes.append("中文名称为规则化暂译，后续发现官方简体中文译名时应替换。")
    if descriptor:
        notes.append(f"原始奖励类型：{descriptor}。")

    return {
        "type": reward_type,
        "nameOriginal": name_part or original_line,
        "nameZhCN": name_zh,
        "quantity": int(quantity) if quantity is not None and quantity.is_integer() else quantity,
        "quantityStatus": quantity_status,
        "rarity": rarity,
        "notesZhCN": "".join(notes),
        "_translationExact": translation.exact,
        "_translationProvisional": translation.provisional,
        "_unknownTokens": list(translation.unknown_tokens),
        "_namedReward": named,
        "_raw": original_line,
    }


def reward_phrase(reward: dict[str, Any]) -> str:
    reward_type = reward["type"]
    quantity = reward.get("quantity")
    name = reward["nameZhCN"]
    if quantity is not None:
        quantity_text = f"{quantity:,}" if isinstance(quantity, int) else str(quantity)
        unit = UNIT_LABELS.get(reward_type, "件")
        if reward_type in {"experience", "skill_point", "knowledge_point"}:
            return f"{quantity_text} {unit}{name}"
        return f"{quantity_text} {unit}{name}"
    if reward_type in {"weapon", "armor", "trinket", "gear", "engraving"}:
        label = TYPE_LABELS.get(reward_type, "装备")
        if "具体名称待核对" in name:
            return name
        rarity = "传奇" if reward.get("rarity") == "legendary" else ""
        return f"{rarity}{label}“{name}”"
    return name


def source_for_location(location: dict[str, Any]) -> dict[str, Any] | None:
    source = location.get("source") or {}
    location_id = source.get("location_id")
    if not location_id:
        return None
    return {
        "sourceId": f"mapgenie-{location_id}",
        "sourceType": "community_database",
        "title": "MapGenie《刺客信条：影》互动地图地点记录",
        "publisherOrAuthor": "MapGenie",
        "locator": f"https://mapgenie.io/assassins-creed-shadows/maps/japan?locationIds={location_id}",
        "capturedAt": None,
        "gameVersion": None,
        "supports": ["location_identity", "reward_name", "reward_quantity"],
        "limitationsZhCN": "单一社区数据库来源；原始仓库记录来自已导入的地图数据，尚需官方文本、游戏画面或独立指南复核。",
    }


def fetch_external_pages(registry: dict[str, Any]) -> list[ExternalPage]:
    pages: list[ExternalPage] = []
    for source in registry.get("sources", []):
        if not source.get("pointEvidence"):
            continue
        request = urllib.request.Request(
            source["locator"],
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AtlasRewardEvidence/0.9.4.8; +https://github.com/Justin-160inteva/atlas-web)",
                "Accept-Language": "en-US,en;q=0.8,zh-CN;q=0.5",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = response.read(5_000_000).decode(response.headers.get_content_charset() or "utf-8", errors="replace")
            parser = VisibleTextParser()
            parser.feed(payload)
            text = parser.text()
            pages.append(ExternalPage(source, text, normalize_for_match(text), True, None))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
            pages.append(ExternalPage(source, "", "", False, f"{type(exc).__name__}: {exc}"))
    return pages


def locate_near(text: str, needles_a: Iterable[str], needle_b: str, maximum_distance: int) -> bool:
    b = normalize_for_match(needle_b)
    if len(b) < 3:
        return False
    b_positions = [match.start() for match in re.finditer(re.escape(b), text)]
    if not b_positions:
        return False
    for a in needles_a:
        if len(a) < 4:
            continue
        for match in re.finditer(re.escape(a), text):
            if any(abs(match.start() - b_pos) <= maximum_distance for b_pos in b_positions):
                return True
    return False


def external_matches(
    location: dict[str, Any],
    rewards: list[dict[str, Any]],
    pages: list[ExternalPage],
    maximum_distance: int,
) -> list[dict[str, Any]]:
    named = [reward for reward in rewards if reward.get("_namedReward") and reward.get("nameOriginal")]
    if not named:
        return []
    variants = title_variants(str(location.get("title") or ""))
    matches: list[dict[str, Any]] = []
    for page in pages:
        if not page.fetched:
            continue
        supported_names = [
            reward["nameOriginal"]
            for reward in named
            if locate_near(page.normalized, variants, reward["nameOriginal"], maximum_distance)
        ]
        if not supported_names:
            continue
        matches.append({
            "sourceId": page.source["sourceId"],
            "sourceType": page.source["sourceType"],
            "title": page.source["title"],
            "publisherOrAuthor": page.source["publisherOrAuthor"],
            "locator": page.source["locator"],
            "capturedAt": None,
            "gameVersion": None,
            "supports": ["location_identity", *[f"reward_name:{name}" for name in supported_names]],
            "limitationsZhCN": "自动交叉核对要求地点名与奖励原文名在同一页面的限定文本距离内共同出现；数量仍以可复查来源为准。",
        })
    return matches


def public_reward(reward: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in reward.items() if not key.startswith("_")}


def build_record(
    location: dict[str, Any],
    lexicon: dict[str, Any],
    external_pages: list[ExternalPage],
    maximum_distance: int,
    generated_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    reward_lines = extract_reward_lines(
        str(location.get("description") or ""),
        str(location.get("category_id") or ""),
    )
    parsed = [parse_reward_line(line, lexicon) for line in reward_lines]
    primary = source_for_location(location)
    cross_sources = external_matches(location, parsed, external_pages, maximum_distance)

    conflicts: list[dict[str, Any]] = []
    provisional = [reward for reward in parsed if reward.get("_translationProvisional")]
    unknown_names = [reward for reward in parsed if reward.get("nameZhCN", "").find("具体名称待核对") >= 0]
    if provisional:
        conflicts.append({
            "type": "translation_mismatch",
            "status": "accepted_uncertainty",
            "detailZhCN": "至少一个奖励专名尚无已核对的官方简体中文译名。",
            "resolutionZhCN": "前端使用标准化暂译或中文类别占位；原文名保留在结构化记录中，发现官方译名后再替换。",
        })

    sources: list[dict[str, Any]] = []
    if reward_lines and primary:
        sources.append(primary)
    sources.extend(cross_sources)

    if not reward_lines:
        status = "unresolved"
        confidence = 0.0
        summary = "奖励尚未确认"
    elif cross_sources:
        status = "multi_source_confirmed"
        confidence = 0.92
        summary = "获得" + "、".join(reward_phrase(reward) for reward in parsed)
    else:
        status = "high_confidence_inference"
        confidence = 0.82 if not unknown_names else 0.78
        summary = "获得" + "、".join(reward_phrase(reward) for reward in parsed) + "（高置信推断）"

    record = {
        "locationId": location["id"],
        "sourceLocationId": (location.get("source") or {}).get("location_id"),
        "categoryId": location.get("category_id"),
        "status": status,
        "confidence": confidence,
        "summaryZhCN": summary,
        "rewards": [public_reward(reward) for reward in parsed],
        "sources": sources,
        "conflicts": conflicts,
        "review": {
            "state": "machine_checked",
            "lastReviewedAt": generated_at,
            "method": "atlas_reward_builder_v1",
            "reviewer": None,
            "changeReasonZhCN": "从地点原始奖励字段提取，按简体中文术语标准化，并使用独立公开来源进行保守交叉核对。",
        },
    }
    audit = {
        "rewardLines": reward_lines,
        "hasRewardSection": bool(reward_lines),
        "externalMatchCount": len(cross_sources),
        "translationExact": sum(1 for reward in parsed if reward.get("_translationExact")),
        "translationProvisional": len(provisional),
        "unknownNameCount": len(unknown_names),
        "unknownTokens": sorted({token for reward in parsed for token in reward.get("_unknownTokens", [])}),
    }
    return record, audit


def validate_record(record: dict[str, Any]) -> None:
    required = {"locationId", "status", "confidence", "summaryZhCN", "rewards", "sources", "conflicts", "review"}
    missing = required - record.keys()
    if missing:
        raise ValueError(f"{record.get('locationId')}: missing {sorted(missing)}")
    if record["status"] not in {"official_confirmed", "multi_source_confirmed", "high_confidence_inference", "unresolved"}:
        raise ValueError(f"{record['locationId']}: invalid status")
    if not 0 <= float(record["confidence"]) <= 1:
        raise ValueError(f"{record['locationId']}: invalid confidence")
    if not record["summaryZhCN"]:
        raise ValueError(f"{record['locationId']}: empty summary")
    if record["status"] != "unresolved" and not record["sources"]:
        raise ValueError(f"{record['locationId']}: confirmed/inferred record without source")
    for source in record["sources"]:
        if not source.get("locator") or not source.get("supports"):
            raise ValueError(f"{record['locationId']}: invalid source locator/supports")


def load_locked_records() -> dict[str, dict[str, Any]]:
    if not CATALOG_PATH.exists():
        return {}
    try:
        catalog = load_json(CATALOG_PATH)
    except (json.JSONDecodeError, OSError):
        return {}
    records = catalog.get("records", {})
    return {
        location_id: record
        for location_id, record in records.items()
        if (record.get("review") or {}).get("state") == "locked"
    }


def write_batches(records: list[dict[str, Any]], generated_at: str) -> list[dict[str, Any]]:
    RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    for old in RECORDS_DIR.glob("batch-*.json"):
        old.unlink()
    batches: list[dict[str, Any]] = []
    for offset in range(0, len(records), BATCH_SIZE):
        number = offset // BATCH_SIZE + 1
        chunk = records[offset : offset + BATCH_SIZE]
        batch_id = f"reward-batch-{number:03d}"
        status_counts = Counter(record["status"] for record in chunk)
        payload = {
            "schemaVersion": 1,
            "release": RELEASE,
            "batchId": batch_id,
            "generatedAt": generated_at,
            "recordSchema": "data/rewards/reward-record-schema.json",
            "startIndex": offset + 1,
            "endIndex": offset + len(chunk),
            "recordCount": len(chunk),
            "records": chunk,
        }
        path = RECORDS_DIR / f"batch-{number:03d}.json"
        write_json(path, payload)
        batches.append({
            "id": batch_id,
            "state": "generated",
            "scope": f"地点 {offset + 1}–{offset + len(chunk)} 的奖励证据记录",
            "targetRecords": len(chunk),
            "confirmedRecords": status_counts["official_confirmed"] + status_counts["multi_source_confirmed"] + status_counts["high_confidence_inference"],
            "officialConfirmed": status_counts["official_confirmed"],
            "multiSourceConfirmed": status_counts["multi_source_confirmed"],
            "highConfidenceInference": status_counts["high_confidence_inference"],
            "unresolved": status_counts["unresolved"],
            "path": path.relative_to(ROOT).as_posix(),
        })
    return batches


def main() -> int:
    for path in (LOCATIONS_PATH, INDEX_PATH, POLICY_PATH, TERMS_PATH, LEXICON_PATH, SOURCES_PATH):
        if not path.exists():
            raise FileNotFoundError(path)

    locations = load_json(LOCATIONS_PATH)
    index = load_json(INDEX_PATH)
    policy = load_json(POLICY_PATH)
    terms = load_json(TERMS_PATH)
    lexicon = load_json(LEXICON_PATH)
    registry = load_json(SOURCES_PATH)

    if len(locations) != 3430:
        raise ValueError(f"Expected 3430 locations, got {len(locations)}")
    if len({location.get('id') for location in locations}) != len(locations):
        raise ValueError("Duplicate or missing location IDs")
    if index.get("productionRules", {}).get("batchSizeMaximum") != BATCH_SIZE:
        raise ValueError("Batch size does not match reward production rules")
    if not policy.get("principles", {}).get("requireStandardSimplifiedChinese"):
        raise ValueError("Simplified Chinese policy is not active")
    if terms.get("locale") != "zh-CN" or lexicon.get("locale") != "zh-CN":
        raise ValueError("Reward terminology locale mismatch")

    generated_at = now_iso()
    external_pages = fetch_external_pages(registry)
    maximum_distance = int(registry.get("matchingPolicy", {}).get("maximumNormalizedCharacterDistance", 4500))
    locked = load_locked_records()

    records: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    location_lookup: dict[str, dict[str, Any]] = {}
    for position, location in enumerate(locations, start=1):
        location_id = location["id"]
        location_lookup[location_id] = location
        if location_id in locked:
            record = locked[location_id]
            row = {
                "rewardLines": [],
                "hasRewardSection": bool(record.get("rewards")),
                "externalMatchCount": max(0, len(record.get("sources", [])) - 1),
                "translationExact": 0,
                "translationProvisional": 0,
                "unknownNameCount": 0,
                "unknownTokens": [],
                "locked": True,
            }
        else:
            record, row = build_record(location, lexicon, external_pages, maximum_distance, generated_at)
            row["locked"] = False
        validate_record(record)
        records.append(record)
        audit_rows.append({"position": position, "locationId": location_id, **row})

    if len(records) != 3430 or len({record["locationId"] for record in records}) != 3430:
        raise ValueError("Reward record coverage is not exactly one-to-one")

    status_counts = Counter(record["status"] for record in records)
    review_counts = Counter((record.get("review") or {}).get("state") for record in records)
    conflict_count = sum(1 for record in records for conflict in record["conflicts"] if conflict.get("status") == "open")
    reward_section_count = sum(1 for row in audit_rows if row["hasRewardSection"])
    provisional_count = sum(row["translationProvisional"] for row in audit_rows)
    unknown_name_count = sum(row["unknownNameCount"] for row in audit_rows)
    external_match_locations = sum(1 for row in audit_rows if row["externalMatchCount"])
    unknown_tokens = Counter(token for row in audit_rows for token in row["unknownTokens"])

    batches = write_batches(records, generated_at)
    catalog = {
        "schemaVersion": 1,
        "release": RELEASE,
        "locale": "zh-CN",
        "generatedAt": generated_at,
        "targetLocationCount": 3430,
        "recordCount": len(records),
        "recordSchema": "data/rewards/reward-record-schema.json",
        "sourcePolicy": "data/rewards/reward-source-policy.json",
        "terminology": "data/rewards/reward-terminology-zh-CN.json",
        "translationLexicon": "data/rewards/reward-translation-lexicon-zh-CN.json",
        "coverage": {
            "total": 3430,
            "officialConfirmed": status_counts["official_confirmed"],
            "multiSourceConfirmed": status_counts["multi_source_confirmed"],
            "highConfidenceInference": status_counts["high_confidence_inference"],
            "unresolved": status_counts["unresolved"],
        },
        "records": {record["locationId"]: record for record in records},
    }
    write_json(CATALOG_PATH, catalog)

    source_fetch = [
        {
            "sourceId": page.source["sourceId"],
            "locator": page.source["locator"],
            "fetched": page.fetched,
            "normalizedCharacterCount": len(page.normalized),
            "error": page.error,
        }
        for page in external_pages
    ]
    audit = {
        "schemaVersion": 1,
        "release": RELEASE,
        "generatedAt": generated_at,
        "targetLocationCount": 3430,
        "recordCount": len(records),
        "rewardSectionLocations": reward_section_count,
        "externalMatchLocations": external_match_locations,
        "provisionalTranslationCount": provisional_count,
        "unknownChineseNameCount": unknown_name_count,
        "lockedRecordCount": len(locked),
        "openConflictCount": conflict_count,
        "statusCounts": dict(sorted(status_counts.items())),
        "reviewCounts": dict(sorted((str(key), value) for key, value in review_counts.items())),
        "batchCount": len(batches),
        "maximumBatchSize": max(batch["targetRecords"] for batch in batches),
        "sourceFetch": source_fetch,
        "unknownTokens": [{"token": token, "count": count} for token, count in unknown_tokens.most_common()],
        "invariants": {
            "exactly3430Records": len(records) == 3430,
            "oneRecordPerLocation": len({record["locationId"] for record in records}) == 3430,
            "coverageConserved": sum(status_counts.values()) == 3430,
            "batchLimitRespected": all(batch["targetRecords"] <= BATCH_SIZE for batch in batches),
            "lockedRecordsPreserved": all(catalog["records"][location_id] == record for location_id, record in locked.items()),
            "allNonUnresolvedHaveSources": all(record["status"] == "unresolved" or record["sources"] for record in records),
            "allSummariesPresent": all(record["summaryZhCN"] for record in records),
        },
    }
    write_json(AUDIT_PATH, audit)

    priority_categories = {
        "category-12312-castle": 100,
    }
    queue_items: list[dict[str, Any]] = []
    for record, row in zip(records, audit_rows):
        location = location_lookup[record["locationId"]]
        needs_research = record["status"] == "unresolved" or row["translationProvisional"] or row["unknownNameCount"]
        if not needs_research:
            continue
        priority = priority_categories.get(str(location.get("category_id")), 40)
        if record["status"] != "unresolved":
            priority += 30
        if row["unknownNameCount"]:
            priority += 20
        queue_items.append({
            "locationId": record["locationId"],
            "title": location.get("title"),
            "categoryId": location.get("category_id"),
            "regionId": location.get("region_id"),
            "priority": priority,
            "reason": "奖励中文专名待核对" if row["unknownNameCount"] else "缺少可关联到具体点位的奖励证据",
            "currentStatus": record["status"],
            "sourceLocationId": record.get("sourceLocationId"),
        })
    queue_items.sort(key=lambda item: (-item["priority"], str(item.get("title") or ""), item["locationId"]))
    write_json(QUEUE_PATH, {
        "schemaVersion": 1,
        "release": RELEASE,
        "generatedAt": generated_at,
        "total": len(queue_items),
        "policy": "按证据价值和翻译缺口排序；每次人工或自动研究批次最多处理 100 个点位。",
        "items": queue_items,
    })

    index["compiledCatalog"] = CATALOG_PATH.relative_to(ROOT).as_posix()
    index["sourceAudit"] = AUDIT_PATH.relative_to(ROOT).as_posix()
    index["researchQueue"] = QUEUE_PATH.relative_to(ROOT).as_posix()
    index["researchSources"] = SOURCES_PATH.relative_to(ROOT).as_posix()
    index["translationLexicon"] = LEXICON_PATH.relative_to(ROOT).as_posix()
    index["coverage"] = {
        "total": 3430,
        "officialConfirmed": status_counts["official_confirmed"],
        "multiSourceConfirmed": status_counts["multi_source_confirmed"],
        "highConfidenceInference": status_counts["high_confidence_inference"],
        "unresolved": status_counts["unresolved"],
        "humanReviewed": review_counts["human_reviewed"] + review_counts["locked"],
        "locked": review_counts["locked"],
        "openConflicts": conflict_count,
    }
    index["batches"] = batches
    index["lastGeneratedAt"] = generated_at
    index["noteZhCN"] = "已为 3430 个地点建立一对一奖励记录。单一社区来源只标记为高置信推断；地点与奖励名被独立来源共同匹配后才升级为多来源确认；无可靠证据时保持奖励尚未确认。"
    write_json(INDEX_PATH, index)

    print(
        "Reward summary catalog built: "
        f"total={len(records)} reward_sections={reward_section_count} "
        f"multi={status_counts['multi_source_confirmed']} "
        f"inferred={status_counts['high_confidence_inference']} "
        f"unresolved={status_counts['unresolved']} batches={len(batches)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - fail loudly in CI with useful context.
        print(f"Reward catalog build failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
