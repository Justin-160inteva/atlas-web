#!/usr/bin/env python3
"""Patch numeric progression reward parsing for EXP and Mastery Level fields."""
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

    regex_old = '''NUMBER_ONLY_REWARD = re.compile(
    r"^(\d[\d,]*(?:\.\d+)?)\s+(XP|Mastery Points?|Knowledge Points?|Experience Points?)$",
    re.IGNORECASE,
)
'''
    regex_new = '''NUMBER_ONLY_REWARD = re.compile(
    r"^(\d[\d,]*(?:\.\d+)?)\s+(XP|EXP|Mastery Points?|Mastery Levels?|Knowledge Points?|Experience Points?)$",
    re.IGNORECASE,
)
'''
    if regex_new not in text:
        text = replace_once(text, regex_old, regex_new, "expand numeric progression regex")

    keywords_old = '''    ("experience", "experience"),
    (" xp", "experience"),
    ("mastery point", "skill_point"),
'''
    keywords_new = '''    ("experience", "experience"),
    (" exp", "experience"),
    (" xp", "experience"),
    ("mastery point", "skill_point"),
    ("mastery level", "mastery_level"),
'''
    if keywords_new not in text:
        text = replace_once(text, keywords_old, keywords_new, "add EXP and mastery-level types")

    labels_old = '''    "skill_point": "技能点",
    "knowledge_point": "知识点",
    "experience": "经验值",
'''
    labels_new = '''    "skill_point": "技能点",
    "mastery_level": "精通等级",
    "knowledge_point": "知识点",
    "experience": "经验值",
'''
    if labels_new not in text:
        text = replace_once(text, labels_old, labels_new, "add mastery-level label")

    units_old = '''    "skill_point": "个",
    "knowledge_point": "个",
'''
    units_new = '''    "skill_point": "个",
    "mastery_level": "级",
    "knowledge_point": "个",
'''
    if units_new not in text:
        text = replace_once(text, units_old, units_new, "add mastery-level unit")

    numeric_types_old = '''    if reward_type in {"experience", "skill_point", "knowledge_point"}:
        name_zh = TYPE_LABELS[reward_type]
'''
    numeric_types_new = '''    if reward_type in {"experience", "skill_point", "mastery_level", "knowledge_point"}:
        name_zh = TYPE_LABELS[reward_type]
'''
    if numeric_types_new not in text:
        text = replace_once(text, numeric_types_old, numeric_types_new, "treat mastery level as progression")

    phrase_old = '''    if quantity is not None:
        quantity_text = f"{quantity:,}" if isinstance(quantity, int) else str(quantity)
        unit = UNIT_LABELS.get(reward_type, "件")
        if reward_type in {"experience", "skill_point", "knowledge_point"}:
            return f"{quantity_text} {unit}{name}"
        return f"{quantity_text} {unit}{name}"
'''
    phrase_new = '''    if quantity is not None:
        quantity_text = f"{quantity:,}" if isinstance(quantity, int) else str(quantity)
        unit = UNIT_LABELS.get(reward_type, "件")
        if reward_type == "mastery_level":
            return f"精通等级提升 {quantity_text} 级"
        if reward_type in {"experience", "skill_point", "knowledge_point"}:
            return f"{quantity_text} {unit}{name}"
        return f"{quantity_text} {unit}{name}"
'''
    if phrase_new not in text:
        text = replace_once(text, phrase_old, phrase_new, "format mastery-level reward")

    TARGET.write_text(text, encoding="utf-8")
    print("Applied EXP and Mastery Level numeric reward parser patch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
