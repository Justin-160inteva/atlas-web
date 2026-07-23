#!/usr/bin/env python3
"""Extract transient frames for Dada shrine geospatial anchor batches.

The repository receives only a non-pixel manifest. Frames stay in a caller-provided
temporary directory and must be deleted by the workflow after model review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
STAGE_PATH = ROOT / "data/geospatial/dada-shrines-27-stage1.json"
RESULT_PATH = ROOT / "data/analysis-results/dada-02.json"
MANIFEST_PATH = ROOT / "data/geospatial/dada-shrines-27-batch01-evidence-manifest.json"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe_duration(video: Path) -> float:
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video),
    ], check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def make_contact_sheets(frame_rows: list[dict[str, Any]], output_dir: Path) -> list[dict[str, Any]]:
    columns, rows = 3, 3
    width, height, label_height = 640, 360, 42
    per_sheet = columns * rows
    sheets: list[dict[str, Any]] = []
    for sheet_index in range(math.ceil(len(frame_rows) / per_sheet)):
        batch = frame_rows[sheet_index * per_sheet:(sheet_index + 1) * per_sheet]
        canvas = np.zeros((rows * (height + label_height), columns * width, 3), dtype=np.uint8)
        for index, row in enumerate(batch):
            image = cv2.imread(str(output_dir / row["filename"]))
            if image is None:
                raise RuntimeError(f"unable to read {row['filename']}")
            image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
            gy, gx = divmod(index, columns)
            x0, y0 = gx * width, gy * (height + label_height)
            canvas[y0:y0 + height, x0:x0 + width] = image
            cv2.rectangle(canvas, (x0, y0 + height), (x0 + width, y0 + height + label_height), (18, 18, 18), -1)
            label = f"S{row['slot']:02d} {row['role']} {row['timeSeconds']:.3f}s"
            cv2.putText(canvas, label, (x0 + 10, y0 + height + 29), cv2.FONT_HERSHEY_SIMPLEX, .72, (245, 245, 245), 2, cv2.LINE_AA)
        filename = f"contact-sheet-{sheet_index + 1:02d}.jpg"
        path = output_dir / filename
        if not cv2.imwrite(str(path), canvas, [cv2.IMWRITE_JPEG_QUALITY, 88]):
            raise RuntimeError(f"unable to write {filename}")
        sheets.append({
            "filename": filename,
            "sha256": sha256(path),
            "frameCount": len(batch),
            "firstSlot": batch[0]["slot"],
            "lastSlot": batch[-1]["slot"],
        })
    return sheets


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--start-slot", type=int, default=1)
    parser.add_argument("--end-slot", type=int, default=14)
    args = parser.parse_args()

    if not (1 <= args.start_slot <= args.end_slot <= 27):
        raise ValueError("slot range must be inside 1..27")
    video = Path(args.video).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stage = load(STAGE_PATH)
    result = load(RESULT_PATH)
    expected_duration = float(result["media"]["durationSeconds"])
    actual_duration = probe_duration(video)
    if abs(actual_duration - expected_duration) > 3:
        raise RuntimeError(f"duration mismatch: {actual_duration} vs {expected_duration}")

    selected_slots = [
        slot for slot in stage["temporalScaffold"]["slots"]
        if args.start_slot <= int(slot["slot"]) <= args.end_slot
    ]
    roles = (("early", .18), ("middle", .50), ("late", .82))
    plan: list[dict[str, Any]] = []
    for slot in selected_slots:
        start = float(slot["startSeconds"])
        end = float(slot["endSeconds"])
        span = end - start
        for role, fraction in roles:
            time_value = min(max(start + span * fraction, .05), max(.05, actual_duration - .05))
            plan.append({"slot": int(slot["slot"]), "role": role, "timeSeconds": round(time_value, 3)})

    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError("unable to open downloaded video")
    frame_rows: list[dict[str, Any]] = []
    try:
        for row in plan:
            capture.set(cv2.CAP_PROP_POS_MSEC, float(row["timeSeconds"]) * 1000.0)
            ok, frame = capture.read()
            if not ok or frame is None:
                raise RuntimeError(f"unable to extract slot {row['slot']} {row['role']}")
            target_width = 768
            target_height = max(1, round(frame.shape[0] * target_width / frame.shape[1]))
            frame = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)
            filename = f"slot-{row['slot']:02d}-{row['role']}-{row['timeSeconds']:.3f}s.jpg"
            path = output_dir / filename
            if not cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 82]):
                raise RuntimeError(f"unable to write {filename}")
            frame_rows.append({
                **row,
                "filename": filename,
                "sha256": sha256(path),
                "width": int(frame.shape[1]),
                "height": int(frame.shape[0]),
                "meanBrightness": round(float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean()) / 255.0, 6),
            })
    finally:
        capture.release()

    sheets = make_contact_sheets(frame_rows, output_dir)
    manifest = {
        "schemaVersion": 1,
        "generatedAt": now(),
        "status": "transient-frames-ready-for-model-review",
        "runId": str(args.run_id),
        "artifactName": args.artifact_name,
        "source": {
            "bvid": stage["source"]["bvid"],
            "title": stage["source"]["title"],
            "authorizationId": stage["source"]["authorizationId"],
            "expectedDurationSeconds": expected_duration,
            "downloadedDurationSeconds": round(actual_duration, 3),
            "transientVideoSha256": sha256(video),
        },
        "batch": {"startSlot": args.start_slot, "endSlot": args.end_slot, "targetSlots": len(selected_slots)},
        "extraction": {
            "method": "three downscaled transient frames per slot at 18%, 50%, and 82%",
            "frameCount": len(frame_rows),
            "contactSheetCount": len(sheets),
            "frames": frame_rows,
            "contactSheets": sheets,
        },
        "privacy": {
            "repositoryContainsPixels": False,
            "transientDirectoryContainsPixels": True,
            "videoAndFramesMustBeDeletedBeforeJobExit": True,
        },
    }
    write(MANIFEST_PATH, manifest)
    (output_dir / "artifact-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"slots": len(selected_slots), "frames": len(frame_rows), "sheets": len(sheets)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
