#!/usr/bin/env python3
"""Review targeted Tokei/Takahara map evidence with two independent vision models.

The script extracts two transient frames from the authorized shrine video:
- 16.75s: full Kii map with shrine markers visible;
- 17.75s: the same map state with a direct popup identifying the selected marker as
  Takahara Kumano Shrine (高原熊野神社).

Only a compact review composite is sent to GitHub Models. Repository output contains
text, hashes, timestamps and reviewer decisions only; no image or video pixels.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data/geospatial/tokei-pairwise-map-review.json"
ENDPOINT = "https://models.github.ai/inference/chat/completions"
MODELS = ("openai/gpt-4.1-mini", "openai/gpt-4o-mini")
MINIMUM_CONFIDENCE = 0.92
TARGET_ID = "location-mapgenie-438414"
NEIGHBOR_ID = "location-mapgenie-437477"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def extract_frame(capture: cv2.VideoCapture, fps: float, second: float) -> np.ndarray:
    capture.set(cv2.CAP_PROP_POS_FRAMES, round(second * fps))
    ok, frame = capture.read()
    if not ok or frame is None:
        raise RuntimeError(f"unable to read frame at {second:.3f}s")
    return frame


def build_composite(video: Path, output_dir: Path) -> tuple[Path, dict[str, Any]]:
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError("unable to open authorized shrine video")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    try:
        frame_a = extract_frame(capture, fps, 16.75)
        frame_b = extract_frame(capture, fps, 17.75)
    finally:
        capture.release()

    panels: list[np.ndarray] = []
    for label, frame in (("A 16.75s markers", frame_a), ("B 17.75s direct Takahara popup", frame_b)):
        height, width = frame.shape[:2]
        crop = frame[int(height * 0.08):int(height * 0.92), int(width * 0.02):int(width * 0.98)]
        scale = min(620 / crop.shape[1], 440 / crop.shape[0])
        resized = cv2.resize(
            crop,
            (max(1, round(crop.shape[1] * scale)), max(1, round(crop.shape[0] * scale))),
            interpolation=cv2.INTER_AREA,
        )
        panel = np.zeros((500, 640, 3), dtype=np.uint8)
        x = (640 - resized.shape[1]) // 2
        y = 42 + (440 - resized.shape[0]) // 2
        panel[y:y + resized.shape[0], x:x + resized.shape[1]] = resized
        cv2.putText(panel, label, (16, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (245, 245, 245), 2, cv2.LINE_AA)
        panels.append(panel)

    composite = np.concatenate(panels, axis=1)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "tokei-pairwise-review-composite.jpg"
    if not cv2.imwrite(str(path), composite, [cv2.IMWRITE_JPEG_QUALITY, 88]):
        raise RuntimeError("unable to write review composite")
    data = path.read_bytes()
    return path, {
        "filename": path.name,
        "sha256": sha256_bytes(data),
        "width": int(composite.shape[1]),
        "height": int(composite.shape[0]),
        "sourceTimesSeconds": [16.75, 17.75],
    }


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE | re.DOTALL)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("model response contains no JSON object")
    value = json.loads(cleaned[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("model response root is not an object")
    return value


def request_review(model: str, image_path: Path, token: str) -> dict[str, Any]:
    image_url = "data:image/jpeg;base64," + base64.b64encode(image_path.read_bytes()).decode("ascii")
    prompt = """You are performing a strict geospatial evidence review for Assassin's Creed Shadows.
Return JSON only with this exact shape:
{
  "verdict": "confirmed" | "unresolved",
  "selectedLocationId": string | null,
  "confidence": number from 0 to 1,
  "observations": [string],
  "reasonZhCN": string
}

Evidence:
- Panel A (16.75s) shows the Kii regional game map with shrine icons.
- Panel B (17.75s) shows a direct popup reading 高原熊野神社, so the selected circular shrine marker is Takahara Kumano Shrine, candidate location-mapgenie-437477.
- Candidate normalized Atlas positions in the same north-up map system:
  * Tokei Shrine, location-mapgenie-438414: (0.597490, 0.054553)
  * Takahara Kumano Shrine, location-mapgenie-437477: (0.670354, 0.070095)
  * Kumano Hongu Taisha: (0.774966, 0.125092)
  * Kumano Nachi Taisha: (0.861682, 0.068492)
  * Kamikura Shrine: (0.954181, 0.113815)
  * Kumano Hayatama Taisha: (0.959751, 0.137589)
- Therefore Tokei is the only listed Kii shrine west/left of Takahara; every other candidate is east/right of it.

Question: Do the visible map-marker geometry and the direct Takahara popup uniquely support that the other shrine marker immediately west/left of the selected Takahara marker is Tokei Shrine?

Rules:
- Confirm only when Panel A visibly contains a distinct shrine marker west/left of the selected Takahara marker seen in Panel B and the candidate geometry makes the assignment unique.
- Do not use the creator's yellow chapter caption as location evidence.
- If orientation, marker identity, or uniqueness is unclear, return unresolved.
- Confirmation must select exactly location-mapgenie-438414 and should use confidence >=0.92 only for genuinely direct, unique evidence.
"""
    payload = {
        "model": model,
        "temperature": 0.0,
        "max_tokens": 900,
        "messages": [
            {"role": "system", "content": "Be conservative. Never infer a location when map evidence is ambiguous."},
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
        ENDPOINT,
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
    content = body["choices"][0]["message"]["content"]
    value = parse_json_object(content)
    verdict = str(value.get("verdict") or "unresolved")
    selected = value.get("selectedLocationId")
    confidence = float(value.get("confidence") or 0.0)
    if verdict not in {"confirmed", "unresolved"}:
        verdict = "unresolved"
    if verdict == "confirmed" and selected != TARGET_ID:
        verdict = "unresolved"
    return {
        "model": model,
        "reviewedAt": now(),
        "verdict": verdict,
        "selectedLocationId": selected if isinstance(selected, str) else None,
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "observations": [str(item) for item in value.get("observations", []) if str(item).strip()][:8],
        "reasonZhCN": str(value.get("reasonZhCN") or "").strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    video = Path(args.video).resolve()
    work_dir = Path(args.work_dir).resolve()
    output = Path(args.output).resolve()
    composite_path, composite = build_composite(video, work_dir)
    fingerprint = sha256_bytes((composite["sha256"] + TARGET_ID + NEIGHBOR_ID).encode("utf-8"))

    existing_packets: dict[str, dict[str, Any]] = {}
    if output.is_file():
        try:
            previous = json.loads(output.read_text(encoding="utf-8"))
            if previous.get("evidenceFingerprint") == fingerprint:
                existing_packets = {
                    row["model"]: row
                    for row in previous.get("reviewPackets", [])
                    if row.get("model") in MODELS and row.get("verdict") in {"confirmed", "unresolved"}
                }
        except (OSError, ValueError, TypeError, KeyError):
            existing_packets = {}

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required")

    packets: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    requested: list[str] = []
    reused: list[str] = []
    for model in MODELS:
        if model in existing_packets:
            packets.append(existing_packets[model])
            reused.append(model)
            continue
        requested.append(model)
        try:
            packets.append(request_review(model, composite_path, token))
        except Exception as error:  # preserve partial review for resumable reruns
            errors.append({"model": model, "error": str(error)[:1000]})
        time.sleep(3)

    by_model = {row["model"]: row for row in packets}
    complete = all(model in by_model for model in MODELS)
    confirmed = complete and all(
        by_model[model]["verdict"] == "confirmed"
        and by_model[model]["selectedLocationId"] == TARGET_ID
        and float(by_model[model]["confidence"]) >= MINIMUM_CONFIDENCE
        for model in MODELS
    )
    result = {
        "schemaVersion": 1,
        "generatedAt": now(),
        "status": "confirmed" if confirmed else ("complete-unresolved" if complete else "partial-review"),
        "stage": "tokei-pairwise-two-model-geometry-review",
        "evidenceFingerprint": fingerprint,
        "target": {
            "locationId": TARGET_ID,
            "title": "Tokei Shrine",
            "directNeighborLocationId": NEIGHBOR_ID,
            "directNeighborTitle": "Takahara Kumano Shrine",
        },
        "policy": {
            "models": list(MODELS),
            "minimumConfidencePerModel": MINIMUM_CONFIDENCE,
            "requireTwoIndependentModels": True,
            "requireDirectTakaharaPopup": True,
            "requireUniqueWestMarkerGeometry": True,
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
    write_json(output, result)
    print(json.dumps({"status": result["status"], "counts": result["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
