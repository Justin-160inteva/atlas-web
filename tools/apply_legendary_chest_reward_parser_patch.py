#!/usr/bin/env python3
"""Apply a narrowly bounded parser patch for explicit legendary-chest reward lines."""
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

    constants_old = '''HEADING_LINE = re.compile(r"^\\*\\*[^*]+:\\*\\*$")
LATIN = re.compile(r"[A-Za-z]")
'''
    constants_new = '''HEADING_LINE = re.compile(r"^\\*\\*[^*]+:\\*\\*$")
INLINE_LEGENDARY_REWARD = re.compile(
    r"^(?P<name>[^\\n]{2,140}?)\\s+-\\s+(?P<descriptor>Legendary\\s+(?:Amulet|Trinket|Armor|Armour|Headgear|Helmet|Katana|Tanto|Kusarigama|Naginata|Kanabo|Teppo|Bow|Weapon|Outfit|Gear))$",
    re.IGNORECASE,
)
UNKNOWN_REWARD_PLACEHOLDERS = {"?", "??", "TBD", "Unknown"}
LATIN = re.compile(r"[A-Za-z]")
'''
    if 'INLINE_LEGENDARY_REWARD' not in text:
        text = replace_once(text, constants_old, constants_new, 'insert inline legendary regex')

    function_old = '''def extract_reward_lines(description: str) -> list[str]:
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
    function_new = '''def extract_reward_lines(description: str, category_id: str | None = None) -> list[str]:
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
    if function_old in text:
        text = replace_once(text, function_old, function_new, 'replace reward extractor')
    elif 'def extract_reward_lines(description: str, category_id:' not in text:
        raise RuntimeError('reward extractor was neither original nor already patched')

    call_old = '''    reward_lines = extract_reward_lines(str(location.get("description") or ""))
'''
    call_new = '''    reward_lines = extract_reward_lines(
        str(location.get("description") or ""),
        str(location.get("category_id") or ""),
    )
'''
    if call_old in text:
        text = replace_once(text, call_old, call_new, 'pass category into reward extractor')
    elif call_new not in text:
        raise RuntimeError('build_record reward extractor call was neither original nor patched')

    TARGET.write_text(text, encoding='utf-8')
    print('Applied explicit Legendary Chest reward parser patch.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
