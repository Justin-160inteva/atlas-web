#!/usr/bin/env python3
"""Apply a narrowly bounded parser patch for explicit Legendary Chest reward lines.

The patch remains restricted to the explicit Legendary Chest category. It accepts only
complete "proper name - legendary type" lines, normalizes one known source typo, strips
list bullets, and never derives a reward from category alone.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'tools/build_reward_summary_catalog.py'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new, 1)


def main() -> int:
    text = TARGET.read_text(encoding='utf-8')

    base_constants = '''HEADING_LINE = re.compile(r"^\\*\\*[^*]+:\\*\\*$")
LATIN = re.compile(r"[A-Za-z]")
'''
    first_version_constants = '''HEADING_LINE = re.compile(r"^\\*\\*[^*]+:\\*\\*$")
INLINE_LEGENDARY_REWARD = re.compile(
    r"^(?P<name>[^\\n]{2,140}?)\\s+-\\s+(?P<descriptor>Legendary\\s+(?:Amulet|Trinket|Armor|Armour|Headgear|Helmet|Katana|Tanto|Kusarigama|Naginata|Kanabo|Teppo|Bow|Weapon|Outfit|Gear))$",
    re.IGNORECASE,
)
UNKNOWN_REWARD_PLACEHOLDERS = {"?", "??", "TBD", "Unknown"}
LATIN = re.compile(r"[A-Za-z]")
'''
    upgraded_constants = '''HEADING_LINE = re.compile(r"^\\*\\*[^*]+:\\*\\*$")
INLINE_LEGENDARY_REWARD = re.compile(
    r"^(?P<name>[^\\n]{2,140}?)\\s+-\\s+(?P<descriptor>Leg(?:endary|edary)\\s+[A-Za-z][A-Za-z /-]{1,60})$",
    re.IGNORECASE,
)
UNKNOWN_REWARD_PLACEHOLDERS = {"?", "??", "TBD", "Unknown"}
LATIN = re.compile(r"[A-Za-z]")
'''
    if first_version_constants in text:
        text = replace_once(text, first_version_constants, upgraded_constants, 'upgrade inline legendary regex')
    elif 'Leg(?:endary|edary)' not in text:
        text = replace_once(text, base_constants, upgraded_constants, 'install inline legendary regex')

    original_function = '''def extract_reward_lines(description: str) -> list[str]:
    if not description:
        return []
    match = REWARD_SECTION.search(description)
    if not match:
        return []
    lines: list[str] = []
    for raw in match.group(1).splitlines():
        raw = raw.strip()
        if not raw or HEADING_LINE.match(raw):
            continue
        raw = re.sub(r"^[\\-•*]+\\s*", "", raw)
        cleaned = clean_markdown(raw)
        if cleaned and cleaned not in {"?", "??", "TBD", "Unknown"}:
            lines.append(cleaned)
    return lines
'''
    upgraded_function = '''def extract_reward_lines(description: str, category_id: str | None = None) -> list[str]:
    if not description:
        return []

    lines: list[str] = []
    match = REWARD_SECTION.search(description)
    if match:
        for raw in match.group(1).splitlines():
            raw = raw.strip()
            if not raw or HEADING_LINE.match(raw):
                continue
            raw = re.sub(r"^[\\-•*]+\\s*", "", raw)
            cleaned = clean_markdown(raw)
            if cleaned and cleaned not in UNKNOWN_REWARD_PLACEHOLDERS:
                lines.append(cleaned)

    # MapGenie Legendary Chest records commonly store the explicit reward as a
    # standalone "Proper Name - Legendary Type" line instead of a Rewards block.
    # Apply this fallback only to the explicit Legendary Chest category.
    if not lines and "legendary-chest" in str(category_id or "").lower():
        for raw in description.splitlines():
            cleaned = re.sub(r"^[\\-•*]+\\s*", "", clean_markdown(raw.strip()))
            if not cleaned or cleaned in UNKNOWN_REWARD_PLACEHOLDERS:
                continue
            inline = INLINE_LEGENDARY_REWARD.fullmatch(cleaned)
            if not inline:
                continue
            name = inline.group("name").strip()
            descriptor = re.sub(
                r"^Legedary\\b",
                "Legendary",
                inline.group("descriptor").strip(),
                flags=re.IGNORECASE,
            )
            if name in UNKNOWN_REWARD_PLACEHOLDERS or name.startswith("??"):
                continue
            lines.append(f"{name} - {descriptor}")

    return list(dict.fromkeys(lines))
'''
    first_version_function = '''def extract_reward_lines(description: str, category_id: str | None = None) -> list[str]:
    if not description:
        return []

    lines: list[str] = []
    match = REWARD_SECTION.search(description)
    if match:
        for raw in match.group(1).splitlines():
            raw = raw.strip()
            if not raw or HEADING_LINE.match(raw):
                continue
            raw = re.sub(r"^[\\-•*]+\\s*", "", raw)
            cleaned = clean_markdown(raw)
            if cleaned and cleaned not in UNKNOWN_REWARD_PLACEHOLDERS:
                lines.append(cleaned)

    # MapGenie legendary-chest records commonly store the explicit reward as a
    # standalone "Proper Name - Legendary Type" line instead of a Rewards block.
    # Apply this fallback only to the explicit Legendary Chest category.
    if not lines and "legendary-chest" in str(category_id or "").lower():
        for raw in description.splitlines():
            cleaned = clean_markdown(raw.strip())
            if not cleaned or cleaned in UNKNOWN_REWARD_PLACEHOLDERS:
                continue
            inline = INLINE_LEGENDARY_REWARD.fullmatch(cleaned)
            if not inline:
                continue
            name = inline.group("name").strip()
            descriptor = inline.group("descriptor").strip()
            if name in UNKNOWN_REWARD_PLACEHOLDERS or name.startswith("??"):
                continue
            lines.append(f"{name} - {descriptor}")

    return list(dict.fromkeys(lines))
'''
    if original_function in text:
        text = replace_once(text, original_function, upgraded_function, 'install reward extractor')
    elif first_version_function in text:
        text = replace_once(text, first_version_function, upgraded_function, 'upgrade reward extractor')
    elif upgraded_function not in text:
        raise RuntimeError('reward extractor was neither original, first-version, nor upgraded')

    original_call = '''    reward_lines = extract_reward_lines(str(location.get("description") or ""))
'''
    upgraded_call = '''    reward_lines = extract_reward_lines(
        str(location.get("description") or ""),
        str(location.get("category_id") or ""),
    )
'''
    if original_call in text:
        text = replace_once(text, original_call, upgraded_call, 'pass category into reward extractor')
    elif upgraded_call not in text:
        raise RuntimeError('build_record reward extractor call was neither original nor upgraded')

    bo_keyword = '''    ("legendary bo", "weapon"),
'''
    katana_keyword = '''    ("katana", "weapon"),
'''
    if bo_keyword not in text:
        text = replace_once(text, katana_keyword, bo_keyword + katana_keyword, 'add bo weapon type')

    TARGET.write_text(text, encoding='utf-8')
    print('Applied expanded explicit Legendary Chest reward parser patch.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
