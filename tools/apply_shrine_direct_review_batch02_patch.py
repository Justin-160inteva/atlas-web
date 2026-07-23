#!/usr/bin/env python3
"""Patch the audited batch-one review tools into an isolated ordinals 9-14 batch-two runner.

The patch is exact and aborts if any source marker changes. It modifies only the runner checkout;
the shared batch-one source remains unchanged in the repository.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "tools/review_dada_shrine_direct_candidates_batch01.py"
RECONCILE = ROOT / "tools/reconcile_dada_shrine_direct_review_batch01.py"

REVIEW_REPLACEMENTS = {
    'DEFAULT_OUTPUT = ROOT / "data/geospatial/dada-shrines-direct-review-batch01.json"':
        'DEFAULT_OUTPUT = ROOT / "data/geospatial/dada-shrines-direct-review-batch02.json"',
    'ORDINALS = tuple(range(1, 9))': 'ORDINALS = tuple(range(9, 15))',
    '"stage": "direct-shrine-popup-independent-review-batch01",':
        '"stage": "direct-shrine-popup-independent-review-batch02",',
}

RECONCILE_REPLACEMENTS = {
    'RESULT_PATH = ROOT / "data/geospatial/dada-shrines-direct-review-batch01.json"':
        'RESULT_PATH = ROOT / "data/geospatial/dada-shrines-direct-review-batch02.json"',
    'if ordinals != list(range(1, 9)):': 'if ordinals != list(range(9, 15)):',
    'result["stage"] = "direct-shrine-popup-independent-review-batch01-programmatic-label-consensus"':
        'result["stage"] = "direct-shrine-popup-independent-review-batch02-programmatic-label-consensus"',
}


def apply(path: Path, replacements: dict[str, str]) -> None:
    source = path.read_text(encoding="utf-8")
    for old, new in replacements.items():
        count = source.count(old)
        if count != 1:
            raise RuntimeError(f"{path.name}: expected one occurrence of {old!r}, found {count}")
        source = source.replace(old, new, 1)
    path.write_text(source, encoding="utf-8")


def main() -> int:
    apply(REVIEW, REVIEW_REPLACEMENTS)
    apply(RECONCILE, RECONCILE_REPLACEMENTS)
    print("Patched direct shrine review tools for ordinals 9-14 (batch 02)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
