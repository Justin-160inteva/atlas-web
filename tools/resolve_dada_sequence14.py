#!/usr/bin/env python3
"""Resolve 达达猪 sequence 14 without downloading media.

The established resolver checks collection membership, title topic, sequence,
duration, author identity and independent video metadata. This wrapper supplies
sequence-14 constants and records the actual stale source being replaced.
"""
from __future__ import annotations

import json
import sys

import resolve_dada_sequence06 as resolver

resolver.SEQUENCE = 14
resolver.TOPIC = "锁链出血流"
resolver.EXPECTED_DURATION = 414
resolver.DURATION_TOLERANCE = 2
resolver.OLD_WRONG_BVID = "BV1A5P9z7EGM"
resolver.REPORT_PATH = resolver.ROOT / "data/batch-analysis/dada-sequence-14-resolution.json"


def patch_stale_reason() -> None:
    status_path = resolver.ROOT / "data/batch-analysis/dada-author-catalog-status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    item = next(entry for entry in status["items"] if int(entry.get("sequence") or 0) == 14)
    item["staleReason"] = "Previous analysis used BV1A5P9z7EGM (sequence 09 开局配装)"
    temporary = status_path.with_suffix(status_path.suffix + ".tmp")
    temporary.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(status_path)


if __name__ == "__main__":
    result = resolver.main()
    if result == 0 and "--apply" in sys.argv:
        patch_stale_reason()
    raise SystemExit(result)
