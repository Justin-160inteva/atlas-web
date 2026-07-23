#!/usr/bin/env python3
"""Extract variable-size one-day review artifacts for Sakai correction scans."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "data/geospatial/geospatial-2p5d-sakai-correction-scan-plan.json"
TIMESTAMPS_PATH = ROOT / "data/geospatial/geospatial-2p5d-sakai-correction-timestamp-plan.json"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_frame(capture: cv2.VideoCapture, seconds: float) -> np.ndarray:
    capture.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000.0)
    ok, frame = capture.read()
    if not ok or frame is None:
        raise RuntimeError(f"failed to read frame at {seconds:.3f}s")
    return frame


def label_frame(frame: np.ndarray, row: dict[str, Any], scan_id: str, index: int) -> np.ndarray:
    output = frame.copy()
    height, width = output.shape[:2]
    overlay = output.copy()
    cv2.rectangle(overlay, (0, height - 52), (width, height), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.70, output, 0.30, 0, output)
    seconds = float(row["time"])
    minutes = int(seconds // 60)
    remainder = seconds - minutes * 60
    window = str(row.get("windowId") or row.get("durationSegment") or "-")
    text = f"{scan_id}  {minutes:02d}:{remainder:05.2f}  {row['bucket']}  {window}  #{index:03d}"
    cv2.putText(output, text, (12, height - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (248, 248, 248), 1, cv2.LINE_AA)
    return output


def make_sheet(images: list[np.ndarray], columns: int, rows: int, width: int, height: int) -> np.ndarray:
    canvas = np.zeros((rows * height, columns * width, 3), dtype=np.uint8)
    for index, image in enumerate(images[: columns * rows]):
        row = index // columns
        column = index % columns
        canvas[row * height : (row + 1) * height, column * width : (column + 1) * width] = image
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--scan-id", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    plan = load(PLAN_PATH)
    timestamps = load(TIMESTAMPS_PATH)
    scan = next((row for row in timestamps["jobs"] if row["id"] == args.scan_id), None)
    if scan is None:
        raise RuntimeError(f"scan ID is not in timestamp plan: {args.scan_id}")

    extraction = plan["extraction"]
    frame_width = int(extraction["frameWidth"])
    frame_height = int(extraction["frameHeight"])
    columns = int(extraction["contactSheetColumns"])
    rows = int(extraction["contactSheetRows"])
    jpeg_quality = int(extraction["jpegQuality"])
    expected_frames = int(scan["frameCount"])
    expected_sheets = int(scan["contactSheetCount"])

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
    expected_duration = float(scan["durationSeconds"])
    tolerance = max(8.0, expected_duration * 0.015)
    if abs(duration - expected_duration) > tolerance:
        raise RuntimeError(f"downloaded duration mismatch: {duration:.3f} vs {expected_duration:.3f}")

    images: list[np.ndarray] = []
    records: list[dict[str, Any]] = []
    for index, row in enumerate(scan["timestamps"], start=1):
        seconds = float(row["time"])
        raw = read_frame(capture, seconds)
        resized = cv2.resize(raw, (frame_width, frame_height), interpolation=cv2.INTER_AREA)
        labeled = label_frame(resized, row, args.scan_id, index)
        filename = f"{args.scan_id}-{index:03d}-{seconds:010.3f}.jpg"
        path = frames_dir / filename
        if not cv2.imwrite(str(path), labeled, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]):
            raise RuntimeError(f"failed to write {path}")
        images.append(labeled)
        records.append({
            "index": index,
            "time": round(seconds, 3),
            "bucket": row["bucket"],
            "windowId": row.get("windowId"),
            "durationSegment": row.get("durationSegment"),
            "filename": f"frames/{filename}",
        })
    capture.release()
    if len(records) != expected_frames:
        raise RuntimeError(f"frame count mismatch: {len(records)}/{expected_frames}")

    per_sheet = columns * rows
    sheet_records: list[dict[str, Any]] = []
    for sheet_index in range(math.ceil(len(images) / per_sheet)):
        start = sheet_index * per_sheet
        sheet = make_sheet(images[start : start + per_sheet], columns, rows, frame_width, frame_height)
        filename = f"{args.scan_id}-sheet-{sheet_index + 1:02d}.jpg"
        path = sheets_dir / filename
        if not cv2.imwrite(str(path), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88]):
            raise RuntimeError(f"failed to write {path}")
        sheet_records.append({
            "sheet": sheet_index + 1,
            "filename": f"contact-sheets/{filename}",
            "firstFrameIndex": start + 1,
            "lastFrameIndex": min(len(images), start + per_sheet),
        })
    if len(sheet_records) != expected_sheets:
        raise RuntimeError(f"contact sheet count mismatch: {len(sheet_records)}/{expected_sheets}")

    manifest = {
        "schemaVersion": 1,
        "status": "correction-artifact-ready",
        "stage": plan["stage"],
        "runId": args.run_id,
        "scanId": args.scan_id,
        "sourceJobId": scan["sourceJobId"],
        "authorizationId": plan["authorizationId"],
        "strategy": scan["strategy"],
        "source": {
            "jobPath": scan["jobPath"],
            "resultPath": scan["resultPath"],
            "page": scan["page"],
            "cid": scan["cid"],
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
            "artifactRetentionDays": int(extraction["artifactRetentionDays"]),
            "originalVideoIncludedInArtifact": False,
        },
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": manifest["status"],
        "scanId": args.scan_id,
        "frames": len(records),
        "contactSheets": len(sheet_records),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
