#!/usr/bin/env python3
"""Extract private low-resolution review frames from authorized transient media."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_timestamps(sampling: dict, duration: float) -> list[tuple[str | None, float]]:
    windows = sampling.get("windows")
    if not windows:
        count = int(sampling["samples"])
        return [(None, duration * (index + 0.5) / count) for index in range(count)]

    timestamps = []
    for window in windows:
        start = int(window["startSeconds"])
        end = int(window["endSeconds"])
        interval = int(window["intervalSeconds"])
        if start < 0 or end < start or end > duration or interval <= 0:
            raise RuntimeError(f"invalid targeted review window: {window['id']}")
        timestamps.extend((window["id"], float(seconds)) for seconds in range(start, end + 1, interval))
    if len(timestamps) != int(sampling["samples"]):
        raise RuntimeError("targeted review sample count does not match its closed windows")
    return timestamps


def main() -> int:
    import cv2
    import numpy as np

    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--sampling-key",
        choices=("reviewSampling", "targetedDenseSampling"),
        default="reviewSampling",
    )
    args = parser.parse_args()

    job = json.loads(Path(args.job).read_text(encoding="utf-8"))
    sampling = job[args.sampling_key]
    output_dir = Path(args.output_dir).resolve()
    if output_dir == ROOT or ROOT in output_dir.parents:
        raise RuntimeError("private review output must remain outside the repository")

    width = int(sampling["frameWidth"])
    height = int(sampling["frameHeight"])
    sample_count = int(sampling["samples"])
    jpeg_quality = int(sampling["jpegQuality"])
    retention_days = int(sampling["artifactRetentionDays"])
    if width > 640 or height > 360 or sample_count > 400 or jpeg_quality > 75 or retention_days != 1:
        raise RuntimeError("low-resolution review limits were exceeded")

    capture = cv2.VideoCapture(str(Path(args.video)))
    if not capture.isOpened():
        raise RuntimeError("OpenCV could not open transient video")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if fps > 0 else 0.0
    expected_duration = float(job["batch"]["durationSeconds"])
    if abs(duration - expected_duration) > max(8.0, expected_duration * 0.015):
        raise RuntimeError(f"downloaded duration mismatch: {duration:.3f} vs {expected_duration:.3f}")

    frames_dir = output_dir / "frames"
    sheets_dir = output_dir / "contact-sheets"
    frames_dir.mkdir(parents=True, exist_ok=True)
    sheets_dir.mkdir(parents=True, exist_ok=True)
    columns = int(sampling["contactSheetColumns"])
    rows = int(sampling["contactSheetRows"])
    per_sheet = columns * rows
    images: list[np.ndarray] = []
    records = []
    timestamps = build_timestamps(sampling, expected_duration)
    for index, (window_id, seconds) in enumerate(timestamps, 1):
        capture.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
        ok, frame = capture.read()
        if not ok or frame is None:
            raise RuntimeError(f"failed to read frame at {seconds:.3f}s")
        image = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        overlay = image.copy()
        cv2.rectangle(overlay, (0, height - 34), (width, height), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.72, image, 0.28, 0, image)
        label = f"{job['id']} {int(seconds // 60):02d}:{seconds % 60:05.2f} #{index:03d}"
        cv2.putText(image, label, (10, height - 11), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (248, 248, 248), 1, cv2.LINE_AA)
        filename = f"{job['id']}-{index:03d}-{seconds:010.3f}.jpg"
        if not cv2.imwrite(str(frames_dir / filename), image, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]):
            raise RuntimeError(f"failed to write {filename}")
        images.append(image)
        records.append({
            "index": index,
            "windowId": window_id,
            "time": round(seconds, 3),
            "filename": f"frames/{filename}",
        })
    capture.release()

    sheet_records = []
    for sheet_index in range(math.ceil(len(images) / per_sheet)):
        sheet = np.zeros((rows * height, columns * width, 3), dtype=np.uint8)
        subset = images[sheet_index * per_sheet:(sheet_index + 1) * per_sheet]
        for local_index, image in enumerate(subset):
            row_index, column_index = divmod(local_index, columns)
            sheet[row_index * height:(row_index + 1) * height, column_index * width:(column_index + 1) * width] = image
        filename = f"{job['id']}-contact-sheet-{sheet_index + 1:02d}.jpg"
        if not cv2.imwrite(str(sheets_dir / filename), sheet, [cv2.IMWRITE_JPEG_QUALITY, 75]):
            raise RuntimeError(f"failed to write {filename}")
        sheet_records.append({
            "sheet": sheet_index + 1,
            "filename": f"contact-sheets/{filename}",
            "firstFrameIndex": sheet_index * per_sheet + 1,
            "lastFrameIndex": min(len(images), (sheet_index + 1) * per_sheet),
        })

    bvid_match = re.search(r"(BV[0-9A-Za-z]+)", job["url"])
    if not bvid_match:
        raise RuntimeError("job URL contains no BVID")
    manifest = {
        "schemaVersion": 1,
        "status": "private-low-resolution-review-artifact-ready",
        "runId": args.run_id,
        "sourceJobId": job["id"],
        "authorizationId": job["authorizationId"],
        "source": {
            "bvid": bvid_match.group(1),
            "page": job["batch"]["page"],
            "cid": job["batch"]["cid"],
            "expectedDurationSeconds": expected_duration,
            "downloadedDurationSeconds": round(duration, 3),
        },
        "extraction": {
            "samplingKey": args.sampling_key,
            "frameWidth": width,
            "frameHeight": height,
            "windows": sampling.get("windows", []),
            "frames": records,
            "contactSheets": sheet_records,
        },
        "privacy": {
            "repositoryContainsPixels": False,
            "artifactContainsPrivateLowResolutionFrames": True,
            "artifactRetentionDays": retention_days,
            "originalVideoIncludedInArtifact": False,
        },
        "modeling": {
            "geometryGenerated": False,
            "humanReviewRequired": True,
            "requiredGates": ["namedSakaiContext", "repeatedStructure", "coordinateAnchor"],
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": manifest["status"], "frames": len(records), "contactSheets": len(sheet_records)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
