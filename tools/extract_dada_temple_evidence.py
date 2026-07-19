#!/usr/bin/env python3
"""Extract transient visual evidence for the 36 Dada temple time slots.

Frames and contact sheets are written only to a caller-provided temporary
folder. The repository receives a numeric/hash manifest, never image pixels.
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
STAGE1_PATH = ROOT / "data/geospatial/dada-temples-36-stage1.json"
RESULT_PATH = ROOT / "data/analysis-results/dada-temples-36.json"
MANIFEST_PATH = ROOT / "data/geospatial/dada-temples-36-evidence-manifest.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe_duration(video: Path) -> float:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(completed.stdout.strip())


def frame_plan(stage: dict[str, Any], duration: float) -> list[dict[str, Any]]:
    roles = (("early", 0.22), ("middle", 0.50), ("late", 0.78))
    plan: list[dict[str, Any]] = []
    for slot in stage["temporalScaffold"]["slots"]:
        start = float(slot["startSeconds"])
        end = float(slot["endSeconds"])
        span = end - start
        for role, fraction in roles:
            time_value = min(max(start + span * fraction, 0.05), max(0.05, duration - 0.05))
            plan.append({
                "slot": int(slot["slot"]),
                "role": role,
                "timeSeconds": round(time_value, 3),
            })
    return plan


def make_contact_sheets(frame_rows: list[dict[str, Any]], output_dir: Path) -> list[dict[str, Any]]:
    sheet_rows: list[dict[str, Any]] = []
    columns, rows = 3, 3
    thumb_width, thumb_height = 640, 360
    label_height = 44
    cell_height = thumb_height + label_height
    per_sheet = columns * rows
    for sheet_index in range(math.ceil(len(frame_rows) / per_sheet)):
        batch = frame_rows[sheet_index * per_sheet : (sheet_index + 1) * per_sheet]
        canvas = np.zeros((rows * cell_height, columns * thumb_width, 3), dtype=np.uint8)
        for index, row in enumerate(batch):
            image = cv2.imread(str(output_dir / row["filename"]))
            if image is None:
                raise RuntimeError(f"unable to read extracted frame {row['filename']}")
            image = cv2.resize(image, (thumb_width, thumb_height), interpolation=cv2.INTER_AREA)
            grid_y, grid_x = divmod(index, columns)
            y0, x0 = grid_y * cell_height, grid_x * thumb_width
            canvas[y0 : y0 + thumb_height, x0 : x0 + thumb_width] = image
            cv2.rectangle(canvas, (x0, y0 + thumb_height), (x0 + thumb_width, y0 + cell_height), (20, 20, 20), -1)
            label = f"S{row['slot']:02d} {row['role']}  {row['timeSeconds']:.3f}s"
            cv2.putText(
                canvas,
                label,
                (x0 + 12, y0 + thumb_height + 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (245, 245, 245),
                2,
                cv2.LINE_AA,
            )
        filename = f"contact-sheet-{sheet_index + 1:02d}.jpg"
        path = output_dir / filename
        if not cv2.imwrite(str(path), canvas, [cv2.IMWRITE_JPEG_QUALITY, 92]):
            raise RuntimeError(f"unable to write {filename}")
        sheet_rows.append({
            "filename": filename,
            "sha256": sha256(path),
            "frameCount": len(batch),
            "firstSlot": batch[0]["slot"],
            "lastSlot": batch[-1]["slot"],
            "width": int(canvas.shape[1]),
            "height": int(canvas.shape[0]),
        })
    return sheet_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    video = Path(args.video).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stage = load(STAGE1_PATH)
    result = load(RESULT_PATH)
    expected_duration = float(result["media"]["durationSeconds"])
    actual_duration = probe_duration(video)
    if abs(actual_duration - expected_duration) > 3:
        raise RuntimeError(f"downloaded video duration mismatch: {actual_duration} vs {expected_duration}")
    if stage["counts"]["temporalSlots"] != 36 or stage["counts"]["linkedSlots"] != 0:
        raise RuntimeError("stage 1 is not the expected unlinked 36-slot scaffold")

    plan = frame_plan(stage, actual_duration)
    if len(plan) != 108:
        raise RuntimeError(f"expected 108 evidence frames, got {len(plan)}")

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
            filename = f"slot-{row['slot']:02d}-{row['role']}-{row['timeSeconds']:.3f}s.jpg"
            path = output_dir / filename
            if not cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 94]):
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
    timestamp = now()
    manifest = {
        "schemaVersion": 1,
        "generatedAt": timestamp,
        "status": "artifact-upload-pending",
        "runId": str(args.run_id),
        "artifactName": args.artifact_name,
        "artifactRetentionDays": 1,
        "source": {
            "bvid": stage["source"]["bvid"],
            "title": stage["source"]["title"],
            "authorizationId": stage["source"]["authorizationId"],
            "expectedDurationSeconds": expected_duration,
            "downloadedDurationSeconds": round(actual_duration, 3),
            "transientVideoSha256": sha256(video),
        },
        "extraction": {
            "method": "three frames per provisional slot at 22%, 50%, and 78%",
            "frameCount": len(frame_rows),
            "contactSheetCount": len(sheets),
            "frames": frame_rows,
            "contactSheets": sheets,
        },
        "privacy": {
            "repositoryContainsPixels": False,
            "artifactContainsTransientPixels": True,
            "artifactRetentionDays": 1,
            "videoAndLocalFramesMustBeDeletedAfterUpload": True,
        },
        "reviewStatus": {
            "reviewedFrames": 0,
            "linkedTempleSlots": 0,
            "status": "awaiting-visual-review",
        },
    }
    write(MANIFEST_PATH, manifest)
    (output_dir / "artifact-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"frames": len(frame_rows), "contactSheets": len(sheets), "artifact": args.artifact_name}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
