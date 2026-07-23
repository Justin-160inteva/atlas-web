#!/usr/bin/env python3
"""Replace the one negative pixel-safety field with a positive invariant.

The patch is intentionally exact and fails if the target source changes or appears more than once.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tools/promote_dada_shrine_direct_review_batch01.py"
OLD = '            "repositoryContainsPixels": False,\n'
NEW = '            "repositoryContainsNoPixels": True,\n'


def main() -> int:
    source = TARGET.read_text(encoding="utf-8")
    count = source.count(OLD)
    if count != 1:
        raise RuntimeError(f"expected one negative pixel safety field, found {count}")
    patched = source.replace(OLD, NEW, 1)
    if patched.count(NEW) != 1:
        raise RuntimeError("positive pixel safety field was not written exactly once")
    TARGET.write_text(patched, encoding="utf-8")
    print("Patched promotion safety invariant: repositoryContainsNoPixels=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
