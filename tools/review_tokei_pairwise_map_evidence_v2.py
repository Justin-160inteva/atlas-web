#!/usr/bin/env python3
"""Binary v2 review for the targeted Tokei/Takahara map geometry.

This version removes candidate-ID generation from the model response. Each model only answers
whether the visibly west/left shrine marker is Tokei Shrine. The program maps a positive answer
to the fixed target ID, preventing a model from describing Tokei correctly while emitting the
neighbor ID in a separate field.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import review_tokei_pairwise_map_evidence as base

STRATEGY_VERSION = 2


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE | re.DOTALL)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("model response contains no JSON object")
    value = json.loads(cleaned[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("model response root is not an object")
    return value


def request_binary_review(model: str, image_path: Path, token: str) -> dict[str, Any]:
    image_url = "data:image/jpeg;base64," + base64.b64encode(image_path.read_bytes()).decode("ascii")
    prompt = """Perform a strict visual-geospatial review. Return JSON only:
{
  "isTokeiWestMarker": true | false,
  "confidence": number from 0 to 1,
  "observations": [string],
  "reasonZhCN": string
}

Panel A at 16.75s shows shrine markers on the north-up Kii map.
Panel B at 17.75s directly identifies the selected circular marker as 高原熊野神社,
Takahara Kumano Shrine.

Candidate geometry:
- Tokei Shrine is the only listed Kii shrine west/left of Takahara.
- Kumano Hongu Taisha, Kumano Nachi Taisha, Kamikura Shrine and Kumano Hayatama Taisha
  are all east/right of Takahara.

Question: Is the distinct shrine marker immediately west/left of the selected Takahara marker
uniquely Tokei Shrine?

Rules:
- Answer true only when the west/left marker is visibly distinct and map orientation plus the
  candidate geometry make the assignment unique.
- Ignore the creator's yellow chapter caption.
- Do not output any candidate ID or shrine name in a separate field.
- Use confidence >=0.92 only for direct, unique evidence; otherwise answer false.
"""
    payload = {
        "model": model,
        "temperature": 0.0,
        "max_tokens": 700,
        "messages": [
            {"role": "system", "content": "Be conservative and follow the exact binary JSON schema."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            },
        ],
    }
    request = urllib.request.Request(
        base.ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=75) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {error.code}: {detail}") from error
    value = parse_json_object(body["choices"][0]["message"]["content"])
    is_tokei = value.get("isTokeiWestMarker") is True
    confidence = round(max(0.0, min(1.0, float(value.get("confidence") or 0.0))), 4)
    confirmed = is_tokei and confidence >= base.MINIMUM_CONFIDENCE
    return {
        "model": model,
        "reviewedAt": base.now(),
        "verdict": "confirmed" if confirmed else "unresolved",
        "selectedLocationId": base.TARGET_ID if confirmed else None,
        "confidence": confidence,
        "binaryAnswer": is_tokei,
        "observations": [str(item) for item in value.get("observations", []) if str(item).strip()][:8],
        "reasonZhCN": str(value.get("reasonZhCN") or "").strip(),
        "reviewSchema": "binary-tokei-west-marker-v2",
    }


def reusable_packet(row: dict[str, Any], model: str) -> bool:
    if row.get("model") != model:
        return False
    verdict = row.get("verdict")
    selected = row.get("selectedLocationId")
    confidence = float(row.get("confidence") or 0.0)
    if verdict == "confirmed":
        return selected == base.TARGET_ID and confidence >= base.MINIMUM_CONFIDENCE
    return verdict == "unresolved" and selected is None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--output", default=str(base.DEFAULT_OUTPUT))
    args = parser.parse_args()

    video = Path(args.video).resolve()
    work_dir = Path(args.work_dir).resolve()
    output = Path(args.output).resolve()
    composite_path, composite = base.build_composite(video, work_dir)
    fingerprint = base.sha256_bytes((composite["sha256"] + base.TARGET_ID + base.NEIGHBOR_ID).encode("utf-8"))

    existing_packets: dict[str, dict[str, Any]] = {}
    if output.is_file():
        try:
            previous = json.loads(output.read_text(encoding="utf-8"))
            if previous.get("evidenceFingerprint") == fingerprint:
                for row in previous.get("reviewPackets", []):
                    model = row.get("model")
                    if model in base.MODELS and reusable_packet(row, model):
                        existing_packets[model] = row
        except (OSError, ValueError, TypeError, KeyError):
            existing_packets = {}

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required")

    packets: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    requested: list[str] = []
    reused: list[str] = []
    for model in base.MODELS:
        if model in existing_packets:
            packets.append(existing_packets[model])
            reused.append(model)
            continue
        requested.append(model)
        try:
            packets.append(request_binary_review(model, composite_path, token))
        except Exception as error:
            errors.append({"model": model, "error": str(error)[:1000]})
        time.sleep(3)

    by_model = {row["model"]: row for row in packets}
    complete = all(model in by_model for model in base.MODELS)
    confirmed = complete and all(
        by_model[model]["verdict"] == "confirmed"
        and by_model[model]["selectedLocationId"] == base.TARGET_ID
        and float(by_model[model]["confidence"]) >= base.MINIMUM_CONFIDENCE
        for model in base.MODELS
    )
    result = {
        "schemaVersion": 1,
        "reviewStrategyVersion": STRATEGY_VERSION,
        "generatedAt": base.now(),
        "status": "confirmed" if confirmed else ("complete-unresolved" if complete else "partial-review"),
        "stage": "tokei-pairwise-two-model-binary-geometry-review-v2",
        "evidenceFingerprint": fingerprint,
        "target": {
            "locationId": base.TARGET_ID,
            "title": "Tokei Shrine",
            "directNeighborLocationId": base.NEIGHBOR_ID,
            "directNeighborTitle": "Takahara Kumano Shrine",
        },
        "policy": {
            "models": list(base.MODELS),
            "minimumConfidencePerModel": base.MINIMUM_CONFIDENCE,
            "requireTwoIndependentModels": True,
            "binaryModelOutput": True,
            "programmaticTargetIdMapping": True,
            "coordinatesAssigned": False,
            "canonicalAnchorModified": False,
        },
        "counts": {
            "successfulModels": len(packets),
            "failedModels": len(errors),
            "requestedModelsThisRun": len(requested),
            "reusedModelsThisRun": len(reused),
        },
        "reviewPackets": packets,
        "errors": errors,
        "composite": composite,
        "privacy": {
            "repositoryContainsPixels": False,
            "transientCompositeDeletedByWorkflow": True,
        },
    }
    base.write_json(output, result)
    print(json.dumps({"status": result["status"], "counts": result["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
