#!/usr/bin/env python3
"""Extract transient full-resolution shrine representative frames for UI calibration.

The output directory is intended only for a one-day GitHub Actions artifact. No pixel file
is written under the repository. A JSON manifest records timestamps and SHA-256 hashes so
that the reviewed calibration frames can be tied back to the existing scene segmentation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
SEGMENTS_PATH = ROOT / "data/geospatial/dada-shrines-27-scene-segments.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--start-slot", type=int, default=1)
    parser.add_argument("--end-slot", type=int, default=14)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    video = Path(args.video).resolve()
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    segmentation = json.loads(SEGMENTS_PATH.read_text(encoding="utf-8"))
    segments = [
        row for row in segmentation["segments"]
        if args.start_slot <= int(row["slot"]) <= args.end_slot
    ]
    if [int(row["slot"]) for row in segments] != list(range(args.start_slot, args.end_slot + 1)):
        raise RuntimeError("selected calibration segments are incomplete")

    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError("unable to open shrine video")
    frames = []
    try:
        for segment in segments:
            slot = int(segment["slot"])
            time_seconds = float(segment["representativeTimeSeconds"])
            capture.set(cv2.CAP_PROP_POS_MSEC, time_seconds * 1000.0)
            ok, frame = capture.read()
            if not ok or frame is None:
                raise RuntimeError(f"unable to extract E{slot:02d} at {time_seconds:.3f}s")
            filename = f"E{slot:02d}-{time_seconds:.3f}s-full.jpg"
            path = output / filename
            if not cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 96]):
                raise RuntimeError(f"unable to write {filename}")
            frames.append({
                "slot": slot,
                "timeSeconds": round(time_seconds, 3),
                "filename": filename,
                "sha256": sha256(path),
                "width": int(frame.shape[1]),
                "height": int(frame.shape[0]),
                "segmentStartSeconds": segment["startSeconds"],
                "segmentEndSeconds": segment["endSeconds"],
            })
    finally:
        capture.release()

    manifest = {
        "schemaVersion": 1,
        "generatedAt": now(),
        "runId": str(args.run_id),
        "status": "transient-popup-calibration-ready",
        "source": segmentation["source"],
        "segmentationGeneratedAt": segmentation["generatedAt"],
        "calibrationPurpose": "locate the fixed on-screen map popup/title region before dense shrine-event detection",
        "frames": frames,
        "privacy": {
            "repositoryContainsPixels": False,
            "artifactContainsTransientPixels": True,
            "artifactRetentionDays": 1,
            "deleteVideoAndFramesBeforeJobExit": True,
        },
    }
    (output / "calibration-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"frames": len(frames), "slots": [row["slot"] for row in frames]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
