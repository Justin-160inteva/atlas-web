#!/usr/bin/env python3
"""Shared helpers for targeted Tokei/Takahara map evidence review.

When executed directly this module delegates to the binary v2 reviewer. Keeping the frame
extraction and composite construction here allows v2 to reuse one audited evidence pipeline
while removing candidate-ID generation from model output.
"""
from __future__ import annotations

import hashlib
import json
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
    for label, frame in (
        ("A 16.75s markers", frame_a),
        ("B 17.75s direct Takahara popup", frame_b),
    ):
        height, width = frame.shape[:2]
        crop = frame[
            int(height * 0.08):int(height * 0.92),
            int(width * 0.02):int(width * 0.98),
        ]
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
        cv2.putText(
            panel,
            label,
            (16, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            (245, 245, 245),
            2,
            cv2.LINE_AA,
        )
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


if __name__ == "__main__":
    from review_tokei_pairwise_map_evidence_v2 import main as binary_main

    raise SystemExit(binary_main())
