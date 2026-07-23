#!/usr/bin/env python3
"""Run binary Tokei review and embed the exact 27-shrine catalog proof.

The standalone proof workflow is optional; this wrapper guarantees that the established
Tokei evidence workflow publishes the non-pixel proof inside its existing review result.
"""
from __future__ import annotations

import json
from pathlib import Path

import build_dada_shrine_catalog_completeness_proof as catalog_proof
import review_tokei_pairwise_map_evidence as base
import review_tokei_pairwise_map_evidence_v2 as binary_review


def main() -> int:
    catalog_proof.main()
    review_code = binary_review.main()
    if review_code != 0:
        return review_code

    review_path = base.DEFAULT_OUTPUT
    proof_path = catalog_proof.OUTPUT_PATH
    review = json.loads(review_path.read_text(encoding="utf-8"))
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    review["catalogCompletenessProof"] = proof
    review["catalogCompletenessProofEmbedded"] = True
    review["promotionDecision"] = {
        "allowed": False,
        "reason": "pairwise visual review remains unresolved; catalog proof requires independent review",
    }
    base.write_json(review_path, review)
    print(json.dumps({
        "reviewStatus": review["status"],
        "proofStatus": proof["status"],
        "proofCounts": proof["counts"],
        "uniqueMissing": proof["uniqueSetDifference"]["locationId"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
