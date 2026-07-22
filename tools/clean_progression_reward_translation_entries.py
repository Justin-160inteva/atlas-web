#!/usr/bin/env python3
"""Remove numeric progression rewards that were mistakenly registered as proper names."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEXICON_PATH = ROOT / "data/rewards/reward-translation-lexicon-zh-CN.json"
EVIDENCE_PATH = ROOT / "data/rewards/reward-translation-evidence.json"

NUMERIC_PROGRESSION = re.compile(
    r"(?i)^\d[\d,]*(?:\.\d+)?\s+(?:XP|EXP|Mastery Points?|Mastery Levels?|Knowledge Points?|Experience Points?)$"
)
GENERIC_PROGRESSION = re.compile(r"(?i)^(?:XP|EXP|Mastery Points?|Mastery Levels?|Knowledge Points?|Experience Points?)$")


def main() -> int:
    lexicon = json.loads(LEXICON_PATH.read_text(encoding="utf-8"))
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    exact = lexicon.setdefault("exactNames", {})
    translations = evidence.setdefault("translations", {})

    removed = sorted({
        key for key in set(exact) | set(translations)
        if NUMERIC_PROGRESSION.fullmatch(str(key).strip())
        or GENERIC_PROGRESSION.fullmatch(str(key).strip())
    })
    for key in removed:
        exact.pop(key, None)
        translations.pop(key, None)

    evidence["translationCount"] = len(translations)
    LEXICON_PATH.write_text(json.dumps(lexicon, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    EVIDENCE_PATH.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"removed": removed, "remainingTranslations": len(translations)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
