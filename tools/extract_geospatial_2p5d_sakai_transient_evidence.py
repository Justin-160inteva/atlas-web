#!/usr/bin/env python3
"""Extract one-day low-resolution review frames for the Sakai 2.5D pilot.

Pixels are written only to a caller-provided temporary directory. The repository keeps
only timestamp plans and non-pixel manifests.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "data/geospatial/geospatial-2p5d-sakai-pilot-evidence-plan.json"
TIMESTAMP_PLAN_PATH = ROOT / "data/geospatial/geospatial-2p5d-sakai-transient-timestamp-plan.json"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def label_frame(frame: np.ndarray, *, job_id: str, time_value: float, bucket: str, index: int) -> np.ndarray:
    output = frame.copy()
    height, width = output.shape[:2]
    overlay = output.copy()
    cv2.rectangle(overlay, (0, height - 42), (width, height), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.68, output, 0.32, 0, output)
    minutes = int(time_value // 60)
    seconds = time_value - minutes * 60
    text = f"{job_id}  {minutes:02d}:{seconds:05.2f}  {bucket}  #{index:03d}"
    cv2.putText(output, text, (12, height - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (245, 245, 245), 1, cv2.LINE_AA)
    return output


def read_frame(capture: cv2.VideoCapture, time_value: float) -> np.ndarray:
    capture.set(cv2.CAP_PROP_POS_MSEC, time_value * 1000.0)
    ok, frame = capture.read()
    if not ok or frame is None:
        raise RuntimeError(f"failed to read frame at {time_value:.3f}s")
    return frame


def make_sheet(images: list[np.ndarray], *, columns: int, rows: int, cell_width: int, cell_height: int) -> np.ndarray:
    canvas = np.zeros((rows * cell_height, columns * cell_width, 3), dtype=np.uint8)
    for index, image in enumerate(images[: columns * rows]):
        row = index // columns
        column = index % columns
        canvas[row * cell_height : (row + 1) * cell_height, column * cell_width : (column + 1) * cell_width] = image
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    plan = load(PLAN_PATH)
    timestamp_plan = load(TIMESTAMP_PLAN_PATH)
    video_plan = next((row for row in timestamp_plan["videos"] if row["jobId"] == args.job_id), None)
    if video_plan is None:
        raise RuntimeError(f"job is not in timestamp plan: {args.job_id}")

    output_dir = Path(args.output_dir)
    frames_dir = output_dir / "frames"
    sheets_dir = output_dir / "contact-sheets"
    frames_dir.mkdir(parents=True, exist_ok=True)
    sheets_dir.mkdir(parents=True, exist_ok=True)

    capture = cv2.VideoCapture(str(Path(args.video)))
    if not capture.isOpened():
        raise RuntimeError("OpenCV could not open transient video")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    source_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    source_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    duration = frame_count / fps if fps > 0 else 0.0
    expected_duration = float(video_plan.get("durationSeconds") or 0)
    if expected_duration > 0 and abs(duration - expected_duration) > max(8.0, expected_duration * 0.015):
        raise RuntimeError(f"downloaded duration mismatch for {args.job_id}: {duration:.3f} vs {expected_duration:.3f}")

    frame_width = int(plan["extraction"]["frameWidth"])
    frame_height = int(plan["extraction"]["frameHeight"])
    columns = int(plan["extraction"]["contactSheetColumns"])
    rows = int(plan["extraction"]["contactSheetRows"])
    expected_count = int(plan["extraction"]["selectedFramesPerVideo"])
    records: list[dict[str, Any]] = []
    images: list[np.ndarray] = []

    for index, timestamp in enumerate(video_plan["timestamps"], start=1):
        time_value = float(timestamp["time"])
        raw = read_frame(capture, time_value)
        resized = cv2.resize(raw, (frame_width, frame_height), interpolation=cv2.INTER_AREA)
        labeled = label_frame(
            resized,
            job_id=args.job_id,
            time_value=time_value,
            bucket=str(timestamp["bucket"]),
            index=index,
        )
        filename = f"{args.job_id}-{index:03d}-{time_value:010.3f}.jpg"
        path = frames_dir / filename
        if not cv2.imwrite(str(path), labeled, [cv2.IMWRITE_JPEG_QUALITY, 82]):
            raise RuntimeError(f"failed to write transient frame {path}")
        images.append(labeled)
        records.append({
            "index": index,
            "time": round(time_value, 3),
            "bucket": timestamp["bucket"],
            "filename": f"frames/{filename}",
            "sharpness": timestamp.get("sharpness"),
            "edgeDensity": timestamp.get("edgeDensity"),
            "difference": timestamp.get("difference"),
        })
    capture.release()

    if len(records) != expected_count:
        raise RuntimeError(f"expected {expected_count} frames, extracted {len(records)}")

    per_sheet = columns * rows
    sheet_records: list[dict[str, Any]] = []
    for sheet_index in range(math.ceil(len(images) / per_sheet)):
        start = sheet_index * per_sheet
        batch = images[start : start + per_sheet]
        sheet = make_sheet(batch, columns=columns, rows=rows, cell_width=frame_width, cell_height=frame_height)
        filename = f"{args.job_id}-sheet-{sheet_index + 1:02d}.jpg"
        path = sheets_dir / filename
        if not cv2.imwrite(str(path), sheet, [cv2.IMWRITE_JPEG_QUALITY, 86]):
            raise RuntimeError(f"failed to write contact sheet {path}")
        sheet_records.append({
            "sheet": sheet_index + 1,
            "filename": f"contact-sheets/{filename}",
            "firstFrameIndex": start + 1,
            "lastFrameIndex": min(len(images), start + per_sheet),
        })

    expected_sheets = int(plan["extraction"]["contactSheetsPerVideo"])
    if len(sheet_records) != expected_sheets:
        raise RuntimeError(f"expected {expected_sheets} contact sheets, wrote {len(sheet_records)}")

    manifest = {
        "schemaVersion": 1,
        "status": "transient-artifact-ready",
        "stage": plan["stage"],
        "runId": args.run_id,
        "jobId": args.job_id,
        "authorizationId": plan["authorizationId"],
        "pilotScopeId": plan["pilotScope"]["id"],
        "source": {
            "jobPath": video_plan["jobPath"],
            "resultPath": video_plan["resultPath"],
            "page": video_plan["page"],
            "cid": video_plan["cid"],
            "expectedDurationSeconds": expected_duration,
            "downloadedDurationSeconds": round(duration, 3),
            "sourceWidth": source_width,
            "sourceHeight": source_height,
            "fps": round(fps, 3),
        },
        "extraction": {
            "frameWidth": frame_width,
            "frameHeight": frame_height,
            "frames": records,
            "contactSheets": sheet_records,
        },
        "privacy": {
            "repositoryContainsPixels": False,
            "artifactContainsTransientPixels": True,
            "artifactRetentionDays": int(plan["extraction"]["artifactRetentionDays"]),
            "originalVideoIncludedInArtifact": False,
        },
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": manifest["status"],
        "jobId": args.job_id,
        "frames": len(records),
        "contactSheets": len(sheet_records),
        "durationSeconds": manifest["source"]["downloadedDurationSeconds"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
