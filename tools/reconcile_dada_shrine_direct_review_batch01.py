#!/usr/bin/env python3
"""Reconcile direct shrine review packets by programmatic visible-label equality.

Vision models transcribe the visible popup title and report confidence. The final match decision is
computed deterministically from the transcription and the expected label, preventing contradictory
boolean fields from blocking otherwise identical direct text evidence.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "data/geospatial/dada-shrines-direct-review-batch01.json"
CANDIDATE_PATH = ROOT / "data/geospatial/dada-shrines-27-anchor-candidates.json"
MODELS = ("openai/gpt-4.1-mini", "openai/gpt-4o-mini")
MINIMUM_CONFIDENCE = 0.92

TRADITIONAL_TO_SIMPLIFIED = str.maketrans({
    "倉": "仓",
    "宮": "宫",
    "國": "国",
    "長": "长",
    "愛": "爱",
    "賀": "贺",
    "狹": "狭",
    "園": "园",
    "總": "总",
    "氣": "气",
    "廣": "广",
    "濱": "滨",
    "關": "关",
    "龍": "龙",
    "龜": "龟",
    "澤": "泽",
    "瀧": "泷",
})


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected object in {path}")
    return value


def write(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).translate(TRADITIONAL_TO_SIMPLIFIED)
    return re.sub(r"[\s\-—_·・,，.。:：;；'\"“”‘’()（）\[\]【】]+", "", normalized).casefold()


def main() -> int:
    result = load(RESULT_PATH)
    package = load(CANDIDATE_PATH)
    if result.get("status") != "complete":
        raise RuntimeError("batch review must be complete before reconciliation")
    candidates = {int(row["ordinal"]): row for row in package["directPopupCandidates"]}
    ordinals = [int(value) for value in result["batch"]["ordinals"]]
    if ordinals != list(range(1, 9)):
        raise RuntimeError("unexpected batch ordinals")

    corrections: list[dict[str, Any]] = []
    model_reviews: dict[str, dict[int, dict[str, Any]]] = {model: {} for model in MODELS}
    for packet in result["reviewPackets"]:
        model = packet["model"]
        if model not in model_reviews:
            raise RuntimeError(f"unexpected model: {model}")
        for review in packet["reviews"]:
            ordinal = int(review["ordinal"])
            expected = candidates[ordinal]["visibleLabelZhCN"]
            visible = str(review.get("visibleLabel") or "")
            model_reported = review.get("matchesExpectedLabel") is True
            programmatic = bool(visible.strip()) and normalize_label(visible) == normalize_label(expected)
            review["modelReportedMatch"] = model_reported
            review["programmaticLabelMatch"] = programmatic
            review["matchesExpectedLabel"] = programmatic
            review["selectedLocationId"] = candidates[ordinal]["locationId"] if programmatic else None
            if model_reported != programmatic:
                review["consistencyCorrection"] = {
                    "reason": "model boolean contradicted its own transcribed visible label",
                    "expectedNormalized": normalize_label(expected),
                    "visibleNormalized": normalize_label(visible),
                }
                corrections.append({
                    "model": model,
                    "ordinal": ordinal,
                    "modelReportedMatch": model_reported,
                    "programmaticLabelMatch": programmatic,
                })
            model_reviews[model][ordinal] = review

    consensus: list[dict[str, Any]] = []
    confirmed = 0
    for ordinal in ordinals:
        reviews = [model_reviews[model].get(ordinal) for model in MODELS]
        if not all(review is not None for review in reviews):
            raise RuntimeError(f"missing complete model review for ordinal {ordinal}")
        accepted = all(
            review["programmaticLabelMatch"] is True
            and review["selectedLocationId"] == candidates[ordinal]["locationId"]
            and float(review["confidence"]) >= MINIMUM_CONFIDENCE
            for review in reviews
        )
        if accepted:
            confirmed += 1
        consensus.append({
            "ordinal": ordinal,
            "event": candidates[ordinal]["event"],
            "expectedLabelZhCN": candidates[ordinal]["visibleLabelZhCN"],
            "locationId": candidates[ordinal]["locationId"],
            "status": "confirmed" if accepted else "unresolved",
            "promotionReady": accepted,
            "reviewers": {model: model_reviews[model][ordinal] for model in MODELS},
        })

    result["schemaVersion"] = 2
    result["reviewStrategyVersion"] = 2
    result["generatedAt"] = now()
    result["stage"] = "direct-shrine-popup-independent-review-batch01-programmatic-label-consensus"
    result["policy"]["programmaticVisibleLabelEquality"] = True
    result["policy"]["modelBooleanControlsMatch"] = False
    result["policy"]["traditionalSimplifiedNormalization"] = True
    result["counts"]["confirmed"] = confirmed
    result["counts"]["unresolved"] = len(ordinals) - confirmed
    result["counts"]["consistencyCorrections"] = len(corrections)
    result["consensus"] = consensus
    result["consistencyCorrections"] = corrections
    write(RESULT_PATH, result)
    print(json.dumps({"confirmed": confirmed, "unresolved": len(ordinals) - confirmed, "corrections": corrections}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
