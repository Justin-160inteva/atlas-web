#!/usr/bin/env python3
"""Resolve 达达猪 sequence 08 by reusing the proven sequence-06 resolver engine.

Only constants and output paths are changed. No media is downloaded in this stage.
"""
from __future__ import annotations

import sys
from pathlib import Path

import resolve_dada_sequence06 as resolver

resolver.SEQUENCE = 8
resolver.TOPIC = "古坟试炼"
resolver.EXPECTED_DURATION = 125
resolver.DURATION_TOLERANCE = 2
resolver.OLD_WRONG_BVID = "BV1A5P9z7EGM"
resolver.REPORT_PATH = resolver.ROOT / "data/batch-analysis/dada-sequence-08-resolution.json"

if __name__ == "__main__":
    sys.exit(resolver.main())
