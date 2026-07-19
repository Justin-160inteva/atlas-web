#!/usr/bin/env python3
"""Resolve 达达猪 sequence 12 without downloading media.

The proven sequence-06 resolver performs collection, title, duration, author,
and independent video metadata checks. This wrapper supplies sequence-12
constants and corrects the stale-result explanation after applying the result.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import resolve_dada_sequence06 as resolver

resolver.SEQUENCE = 12
resolver.TOPIC = "饕餮之刃"
resolver.EXPECTED_DURATION = 590
resolver.DURATION_TOLERANCE = 2
resolver.OLD_WRONG_BVID = "BV197cjebEXW"
resolver.REPORT_PATH = resolver.ROOT / "data/batch-analysis/dada-sequence-12-resolution.json"


def patch_stale_reason() -> None:
    status_path = resolver.ROOT / "data/batch-analysis/dada-author-catalog-status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    item = next(entry for entry in status["items"] if int(entry.get("sequence") or 0) == 12)
    item["staleReason"] = "Previous analysis used BV197cjebEXW (unrelated Ghost of Tsushima sequence 12 video)"
    temporary = status_path.with_suffix(status_path.suffix + ".tmp")
    temporary.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(status_path)


if __name__ == "__main__":
    result = resolver.main()
    if result == 0 and "--apply" in sys.argv:
        patch_stale_reason()
    raise SystemExit(result)
