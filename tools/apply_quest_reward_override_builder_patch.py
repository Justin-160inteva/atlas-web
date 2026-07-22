#!/usr/bin/env python3
"""Integrate point-specific reward evidence overrides into the catalog builder."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tools/build_reward_summary_catalog.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")

    path_old = '''SOURCES_PATH = ROOT / "data/rewards/reward-research-sources.json"
CATALOG_PATH = ROOT / "data/rewards/reward-summary-catalog.json"
'''
    path_new = '''SOURCES_PATH = ROOT / "data/rewards/reward-research-sources.json"
POINT_OVERRIDES_PATH = ROOT / "data/rewards/reward-point-evidence-overrides.json"
CATALOG_PATH = ROOT / "data/rewards/reward-summary-catalog.json"
'''
    if "POINT_OVERRIDES_PATH" not in text:
        text = replace_once(text, path_old, path_new, "insert override path")

    start = text.index("def build_record(\n")
    end_marker = "    return record, audit\n"
    end = text.index(end_marker, start) + len(end_marker)
    old_function = text[start:end]
    new_function = '''def build_record(
    location: dict[str, Any],
    lexicon: dict[str, Any],
    external_pages: list[ExternalPage],
    maximum_distance: int,
    generated_at: str,
    point_overrides: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    description_reward_lines = extract_reward_lines(
        str(location.get("description") or ""),
        str(location.get("category_id") or ""),
    )
    override = point_overrides.get(location["id"])
    override_applied = bool(not description_reward_lines and override and override.get("rewardLines"))
    reward_lines = (
        list(description_reward_lines)
        if description_reward_lines
        else list(override.get("rewardLines", [])) if override_applied else []
    )
    evidence_mode = (
        "location_description"
        if description_reward_lines
        else str(override.get("evidenceMode") or "point_specific_override") if override_applied
        else "none"
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
    if description_reward_lines and primary:
        sources.append(primary)
    if override_applied:
        sources.extend(dict(source) for source in override.get("sources", []))
    sources.extend(cross_sources)

    # Keep unique source records while preserving stable evidence order.
    unique_sources: list[dict[str, Any]] = []
    seen_source_ids: set[str] = set()
    for source in sources:
        source_id = str(source.get("sourceId") or source.get("locator") or "")
        if not source_id or source_id in seen_source_ids:
            continue
        seen_source_ids.add(source_id)
        unique_sources.append(source)
    sources = unique_sources

    if not reward_lines:
        status = "unresolved"
        confidence = 0.0
        summary = "奖励尚未确认"
    elif override_applied:
        independent_sources = len({str(source.get("sourceId") or source.get("locator")) for source in sources})
        if independent_sources >= 2:
            status = "multi_source_confirmed"
            confidence = 0.92
            summary = "获得" + "、".join(reward_phrase(reward) for reward in parsed)
        else:
            status = "high_confidence_inference"
            confidence = float(override.get("confidence", 0.88))
            summary = "获得" + "、".join(reward_phrase(reward) for reward in parsed) + "（高置信推断）"
    elif cross_sources:
        status = "multi_source_confirmed"
        confidence = 0.92
        summary = "获得" + "、".join(reward_phrase(reward) for reward in parsed)
    else:
        status = "high_confidence_inference"
        confidence = 0.82 if not unknown_names else 0.78
        summary = "获得" + "、".join(reward_phrase(reward) for reward in parsed) + "（高置信推断）"

    review_method = "atlas_reward_builder_v2_point_override" if override_applied else "atlas_reward_builder_v1"
    change_reason = (
        "同名任务详情页的明确Reward字段已作为点位级独立证据导入；单一攻略来源保持高置信推断。"
        if override_applied
        else "从地点原始奖励字段提取，按简体中文术语标准化，并使用独立公开来源进行保守交叉核对。"
    )
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
            "method": review_method,
            "reviewer": None,
            "changeReasonZhCN": change_reason,
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
        "pointOverrideApplied": override_applied,
        "evidenceMode": evidence_mode,
    }
    return record, audit
'''
    text = text[:start] + new_function + text[end:]

    load_old = '''    registry = load_json(SOURCES_PATH)

    if len(locations) != 3430:
'''
    load_new = '''    registry = load_json(SOURCES_PATH)
    point_override_document = load_json(POINT_OVERRIDES_PATH) if POINT_OVERRIDES_PATH.exists() else {"records": {}}
    point_overrides = point_override_document.get("records", {})

    if not isinstance(point_overrides, dict):
        raise ValueError("Point evidence overrides must use a records object")
    if len(locations) != 3430:
'''
    if load_new not in text:
        text = replace_once(text, load_old, load_new, "load point overrides")

    call_old = '''            record, row = build_record(location, lexicon, external_pages, maximum_distance, generated_at)
'''
    call_new = '''            record, row = build_record(
                location,
                lexicon,
                external_pages,
                maximum_distance,
                generated_at,
                point_overrides,
            )
'''
    if call_new not in text:
        text = replace_once(text, call_old, call_new, "pass point overrides")

    count_old = '''    external_match_locations = sum(1 for row in audit_rows if row["externalMatchCount"])
    unknown_tokens = Counter(token for row in audit_rows for token in row["unknownTokens"])
'''
    count_new = '''    external_match_locations = sum(1 for row in audit_rows if row["externalMatchCount"])
    point_override_locations = sum(1 for row in audit_rows if row.get("pointOverrideApplied"))
    unknown_tokens = Counter(token for row in audit_rows for token in row["unknownTokens"])
'''
    if count_new not in text:
        text = replace_once(text, count_old, count_new, "count point overrides")

    audit_old = '''        "externalMatchLocations": external_match_locations,
        "provisionalTranslationCount": provisional_count,
'''
    audit_new = '''        "externalMatchLocations": external_match_locations,
        "pointOverrideLocations": point_override_locations,
        "pointOverrideSource": POINT_OVERRIDES_PATH.relative_to(ROOT).as_posix() if POINT_OVERRIDES_PATH.exists() else None,
        "provisionalTranslationCount": provisional_count,
'''
    if audit_new not in text:
        text = replace_once(text, audit_old, audit_new, "publish override audit")

    invariant_old = '''            "allSummariesPresent": all(record["summaryZhCN"] for record in records),
        },
'''
    invariant_new = '''            "allSummariesPresent": all(record["summaryZhCN"] for record in records),
            "allPointOverridesApplied": all(
                catalog["records"].get(location_id, {}).get("status") != "unresolved"
                for location_id in point_overrides
            ),
            "singleSourcePointOverridesStayInference": all(
                len(override.get("sources", [])) != 1
                or catalog["records"].get(location_id, {}).get("status") == "high_confidence_inference"
                for location_id, override in point_overrides.items()
            ),
        },
'''
    if invariant_new not in text:
        text = replace_once(text, invariant_old, invariant_new, "add override invariants")

    index_old = '''    index["translationLexicon"] = LEXICON_PATH.relative_to(ROOT).as_posix()
    index["coverage"] = {
'''
    index_new = '''    index["translationLexicon"] = LEXICON_PATH.relative_to(ROOT).as_posix()
    index["pointEvidenceOverrides"] = POINT_OVERRIDES_PATH.relative_to(ROOT).as_posix() if POINT_OVERRIDES_PATH.exists() else None
    index["coverage"] = {
'''
    if index_new not in text:
        text = replace_once(text, index_old, index_new, "register point overrides")

    TARGET.write_text(text, encoding="utf-8")
    print("Applied point-specific quest reward override integration patch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
