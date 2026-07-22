#!/usr/bin/env python3
"""Translate unresolved reward proper names into standard Simplified Chinese.

This process changes translation text only. It never changes reward quantity, type,
location association, or evidence status. The original English name remains in every
reward record and every generated translation has an auditable method record.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "data/rewards/reward-translation-research-policy.json"
CATALOG_PATH = ROOT / "data/rewards/reward-summary-catalog.json"
LOCATIONS_PATH = ROOT / "data/locations.json"
QUEUE_PATH = ROOT / "data/rewards/reward-research-queue.json"
LEXICON_PATH = ROOT / "data/rewards/reward-translation-lexicon-zh-CN.json"
EVIDENCE_PATH = ROOT / "data/rewards/reward-translation-evidence.json"
STATE_PATH = ROOT / "data/rewards/reward-translation-research-state.json"

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
LATIN = re.compile(r"[A-Za-z]")
FENCED_JSON = re.compile(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def candidate_required(reward: dict[str, Any], exact_names: dict[str, str]) -> bool:
    original = str(reward.get("nameOriginal") or "").strip()
    if not original or original in exact_names:
        return False
    current = str(reward.get("nameZhCN") or "")
    notes = str(reward.get("notesZhCN") or "")
    return (
        "具体名称待核对" in current
        or current.endswith("（暂译）")
        or "规则化暂译" in notes
        or "中文译名待核对" in notes
    )


def collect_candidates(catalog: dict[str, Any], locations: list[dict[str, Any]], queue: dict[str, Any], exact_names: dict[str, str]) -> list[dict[str, Any]]:
    location_titles = {str(item.get("id")): str(item.get("title") or "") for item in locations}
    priority_by_location = {str(item.get("locationId")): int(item.get("priority") or 0) for item in queue.get("items", [])}
    grouped: dict[str, dict[str, Any]] = {}
    records = catalog.get("records", {})
    iterable = records.values() if isinstance(records, dict) else records
    for record in iterable:
        location_id = str(record.get("locationId") or "")
        for reward in record.get("rewards", []):
            if not candidate_required(reward, exact_names):
                continue
            original = str(reward.get("nameOriginal") or "").strip()
            entry = grouped.setdefault(original, {"original": original, "frequency": 0, "priority": 0, "types": set(), "rarities": set(), "locations": []})
            entry["frequency"] += 1
            entry["priority"] = max(entry["priority"], priority_by_location.get(location_id, 0))
            if reward.get("type"):
                entry["types"].add(str(reward["type"]))
            if reward.get("rarity"):
                entry["rarities"].add(str(reward["rarity"]))
            title = location_titles.get(location_id)
            if title and title not in entry["locations"] and len(entry["locations"]) < 4:
                entry["locations"].append(title)
    result = [{
        "original": entry["original"],
        "frequency": entry["frequency"],
        "priority": entry["priority"],
        "types": sorted(entry["types"]),
        "rarities": sorted(entry["rarities"]),
        "locations": entry["locations"],
    } for entry in grouped.values()]
    result.sort(key=lambda item: (-item["priority"], -item["frequency"], item["original"].lower()))
    return result


def parse_model_content(content: str) -> dict[str, Any]:
    match = FENCED_JSON.search(content)
    return json.loads(match.group(1) if match else content)


def call_model(policy: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    token = os.environ.get("ATLAS_REWARD_TRANSLATION_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GitHub Models token is unavailable")
    model = policy["model"]
    compact = [{"original": item["original"], "types": item["types"], "rarities": item["rarities"], "locations": item["locations"]} for item in candidates]
    system = (
        "你是《刺客信条：影》奖励名称的简体中文本地化编辑。只翻译奖励专名，不改变奖励类型、数量、稀有度、地点或证据状态。"
        "输出必须是严格JSON。译名必须自然、规范、适合游戏界面；优先采用历史人物、地名和日语词的通行中文写法。"
        "不要声称译名来自官方。zhCN中不要保留英文字母，也不要额外添加传奇、武器、护甲等类型词。"
    )
    user = json.dumps({
        "task": "translate_reward_proper_names",
        "rules": policy["translationRules"],
        "input": compact,
        "requiredOutput": {"translations": [{"original": "必须与输入完全一致", "zhCN": "标准简体中文专名", "confidence": 0.85, "reasonZhCN": "一句话说明译法，不声称官方"}]},
    }, ensure_ascii=False)
    payload = json.dumps({
        "model": model["id"],
        "temperature": model.get("temperature", 0.1),
        "max_tokens": int(model.get("maximumOutputTokens", 3200)),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
    }, ensure_ascii=False).encode("utf-8")
    timeout = int(policy["batch"].get("requestTimeoutSeconds", 120))
    last_error: Exception | None = None
    for attempt in range(1, 4):
        request = urllib.request.Request(model["endpoint"], data=payload, method="POST", headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            return parse_model_content(body["choices"][0]["message"]["content"])
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(attempt * 4)
    raise RuntimeError(f"GitHub Models translation failed after retries: {last_error}")


def validate_translation(original: str, value: dict[str, Any], maximum_chars: int) -> dict[str, Any]:
    if str(value.get("original") or "") != original:
        raise ValueError(f"model changed original name: {original}")
    zh_cn = re.sub(r"\s+", "", str(value.get("zhCN") or "").strip())
    if not zh_cn or not CJK.search(zh_cn):
        raise ValueError(f"translation has no Chinese characters: {original}")
    if LATIN.search(zh_cn):
        raise ValueError(f"translation retained Latin letters: {original} -> {zh_cn}")
    if len(zh_cn) > maximum_chars:
        raise ValueError(f"translation is too long: {original} -> {zh_cn}")
    if any(token in zh_cn for token in ("暂译", "待核对", "未知", "官方")):
        raise ValueError(f"translation contains status wording: {original} -> {zh_cn}")
    confidence = max(0.0, min(1.0, float(value.get("confidence", 0.75))))
    reason = str(value.get("reasonZhCN") or "采用语义本地化并保留原文供复核。").strip()
    return {"zhCN": zh_cn, "confidence": confidence, "reasonZhCN": reason[:180]}


def main() -> int:
    policy = load_json(POLICY_PATH, {})
    if not policy.get("enabled"):
        print("Reward translation research is disabled.")
        return 0
    catalog = load_json(CATALOG_PATH, {})
    locations = load_json(LOCATIONS_PATH, [])
    queue = load_json(QUEUE_PATH, {"items": []})
    lexicon = load_json(LEXICON_PATH, {})
    evidence = load_json(EVIDENCE_PATH, {"schemaVersion": 1, "release": "0.9.4.8", "locale": "zh-CN", "translations": {}})
    exact_names = lexicon.setdefault("exactNames", {})
    translations = evidence.setdefault("translations", {})
    generated_at = now_iso()
    candidates_before = collect_candidates(catalog, locations, queue, exact_names)
    maximum = int(policy["batch"].get("maximumNamesPerRun", 100))
    request_size = int(policy["batch"].get("namesPerModelRequest", 20))
    selected = candidates_before[:maximum]
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for offset in range(0, len(selected), request_size):
        chunk = selected[offset:offset + request_size]
        response = call_model(policy, chunk)
        by_original = {str(item.get("original") or ""): item for item in response.get("translations", []) if isinstance(item, dict)}
        for candidate in chunk:
            original = candidate["original"]
            try:
                if original not in by_original:
                    raise ValueError("model omitted translation")
                checked = validate_translation(original, by_original[original], int(policy["translationRules"].get("maximumChineseNameCharacters", 40)))
                exact_names[original] = checked["zhCN"]
                translations[original] = {
                    "original": original,
                    "zhCN": checked["zhCN"],
                    "method": "github_models_standard_zh_cn",
                    "model": policy["model"]["id"],
                    "generatedAt": generated_at,
                    "confidence": checked["confidence"],
                    "reasonZhCN": checked["reasonZhCN"],
                    "officialConfirmed": False,
                    "standardSimplifiedChinese": True,
                    "sourceContexts": {"types": candidate["types"], "rarities": candidate["rarities"], "locations": candidate["locations"], "occurrenceCount": candidate["frequency"]},
                }
                accepted.append({"original": original, "zhCN": checked["zhCN"], "confidence": checked["confidence"]})
            except (ValueError, TypeError) as exc:
                rejected.append({"original": original, "error": str(exc)})

    lexicon["updatedAt"] = generated_at
    evidence["generatedAt"] = generated_at
    evidence["translationCount"] = len(translations)
    evidence["noticeZhCN"] = "这些映射用于标准简体中文显示，不代表育碧官方译名；奖励原文和证据等级始终保留。"
    write_json(LEXICON_PATH, lexicon)
    write_json(EVIDENCE_PATH, evidence)
    remaining = collect_candidates(catalog, locations, queue, exact_names)
    state = {
        "schemaVersion": 1,
        "release": "0.9.4.8",
        "generatedAt": generated_at,
        "status": "complete" if not remaining else "in_progress",
        "candidateNamesBeforeRun": len(candidates_before),
        "selectedThisRun": len(selected),
        "acceptedThisRun": len(accepted),
        "rejectedThisRun": len(rejected),
        "remainingCandidateNames": len(remaining),
        "totalRegisteredStandardTranslations": len(translations),
        "accepted": accepted,
        "rejected": rejected,
        "nextNames": [item["original"] for item in remaining[:20]],
        "safety": {"rewardQuantitiesChanged": False, "rewardTypesChanged": False, "locationAssociationsChanged": False, "evidenceStatusesChangedByTranslation": False, "officialTranslationClaimed": False},
    }
    write_json(STATE_PATH, state)
    print(json.dumps({"accepted": len(accepted), "rejected": len(rejected), "remaining": len(remaining), "registered": len(translations)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
