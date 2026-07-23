#!/usr/bin/env python3
"""Reduce v2 shrine event payloads without weakening confirmation gates.

Each event remains explicitly labeled and isolated, but only its scene detector-selected
representative frame is sent. This avoids GitHub Models HTTP 413 responses while retaining
all three frame hashes in the persisted evidence manifest for later supplemental review.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tools/review_dada_shrine_scene_segments_v2.py"


def replace_exact(text: str, old: str, new: str, expected: int = 1) -> str:
    count = text.count(old)
    if count == 0 and new in text:
        return text
    if count != expected:
        raise RuntimeError(f"expected {expected} occurrences of {old!r}, found {count}")
    return text.replace(old, new)


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    text = replace_exact(
        text,
        '"text": f"EVENT E{slot:02d}: The next three images belong only to this event, in before / representative / after order.",',
        '"text": f"EVENT E{slot:02d}: The next image is the scene detector-selected representative frame for this event only.",',
    )
    old_block = '''        ordered = sorted(\n            frames_by_slot[slot],\n            key=lambda row: {"before": 0, "representative": 1, "after": 2}.get(str(row["role"]), 9),\n        )\n        if len(ordered) != 3:\n            raise RuntimeError(f"event {slot} does not have exactly three context frames")\n        for row in ordered:\n'''
    new_block = '''        ordered = [row for row in frames_by_slot[slot] if str(row.get("role")) == "representative"]\n        if len(ordered) != 1:\n            raise RuntimeError(f"event {slot} does not have exactly one representative frame")\n        for row in ordered:\n'''
    text = replace_exact(text, old_block, new_block)
    text = replace_exact(
        text,
        '"EVENT文字后紧跟的三张图只属于该EVENT，顺序为before、representative、after。",',
        '"EVENT文字后紧跟的一张图是只属于该EVENT的场景代表帧。",',
    )
    text = replace_exact(
        text,
        '"framesPerEvent": 3,',
        '"framesPerEvent": int(request_config.get("framesPerEvent") or 1),',
    )
    TARGET.write_text(text, encoding="utf-8")
    print("reduced shrine v2 requests to one representative frame per explicitly labeled event")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
