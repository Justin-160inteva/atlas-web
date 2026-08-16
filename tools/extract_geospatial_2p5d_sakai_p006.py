#!/usr/bin/env python3
"""Extract a one-day private P06 contact-sheet artifact outside the repository."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    plan = json.loads((ROOT / "data/geospatial/geospatial-2p5d-sakai-p006-scan-plan.json").read_text(encoding="utf-8"))
    timestamps = json.loads((ROOT / plan["outputs"]["timestampPlan"]).read_text(encoding="utf-8"))
    sampling = plan["sampling"]
    output_dir = Path(args.output_dir).resolve()
    if output_dir == ROOT or ROOT in output_dir.parents:
        raise RuntimeError("transient frame output must remain outside the repository")
    frames_dir, sheets_dir = output_dir / "frames", output_dir / "contact-sheets"
    frames_dir.mkdir(parents=True, exist_ok=True)
    sheets_dir.mkdir(parents=True, exist_ok=True)

    capture = cv2.VideoCapture(str(Path(args.video)))
    if not capture.isOpened():
        raise RuntimeError("OpenCV could not open transient P06 video")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if fps > 0 else 0.0
    expected_duration = float(timestamps["source"]["durationSeconds"])
    if abs(duration - expected_duration) > max(8.0, expected_duration * 0.015):
        raise RuntimeError(f"downloaded duration mismatch: {duration:.3f} vs {expected_duration:.3f}")

    width, height = int(sampling["frameWidth"]), int(sampling["frameHeight"])
    images: list[np.ndarray] = []
    records = []
    for index, row in enumerate(timestamps["timestamps"], 1):
        seconds = float(row["time"])
        capture.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
        ok, frame = capture.read()
        if not ok or frame is None:
            raise RuntimeError(f"failed to read P06 frame at {seconds:.3f}s")
        image = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        overlay = image.copy()
        cv2.rectangle(overlay, (0, height - 46), (width, height), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.72, image, 0.28, 0, image)
        label = f"P06 {int(seconds // 60):02d}:{seconds % 60:05.2f} {row['bucket']} #{index:03d}"
        cv2.putText(image, label, (12, height - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (248, 248, 248), 1, cv2.LINE_AA)
        filename = f"p006-{index:03d}-{seconds:010.3f}.jpg"
        if not cv2.imwrite(str(frames_dir / filename), image, [cv2.IMWRITE_JPEG_QUALITY, int(sampling["jpegQuality"])]):
            raise RuntimeError(f"failed to write {filename}")
        images.append(image)
        records.append({"index": index, "time": seconds, "bucket": row["bucket"], "filename": f"frames/{filename}"})
    capture.release()

    columns, rows_per_sheet = int(sampling["contactSheetColumns"]), int(sampling["contactSheetRows"])
    per_sheet = columns * rows_per_sheet
    sheet_records = []
    for sheet_index in range(math.ceil(len(images) / per_sheet)):
        sheet = np.zeros((rows_per_sheet * height, columns * width, 3), dtype=np.uint8)
        for local_index, image in enumerate(images[sheet_index * per_sheet:(sheet_index + 1) * per_sheet]):
            row_index, column_index = divmod(local_index, columns)
            sheet[row_index * height:(row_index + 1) * height, column_index * width:(column_index + 1) * width] = image
        filename = f"p006-contact-sheet-{sheet_index + 1:02d}.jpg"
        if not cv2.imwrite(str(sheets_dir / filename), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88]):
            raise RuntimeError(f"failed to write {filename}")
        sheet_records.append({"sheet": sheet_index + 1, "filename": f"contact-sheets/{filename}", "firstFrameIndex": sheet_index * per_sheet + 1, "lastFrameIndex": min(len(images), (sheet_index + 1) * per_sheet)})
    if len(records) != int(sampling["frameCount"]) or len(sheet_records) != int(sampling["contactSheetCount"]):
        raise RuntimeError("P06 artifact count drifted")

    manifest = {
        "schemaVersion": 1, "status": "p006-private-review-artifact-ready", "stage": plan["stage"],
        "runId": args.run_id, "scanId": plan["source"]["scanId"], "sourceJobId": plan["source"]["jobId"],
        "authorizationId": plan["authorizationId"],
        "source": {"page": plan["source"]["expectedPage"], "cid": plan["source"]["expectedCid"], "expectedDurationSeconds": expected_duration, "downloadedDurationSeconds": round(duration, 3)},
        "extraction": {"frameWidth": width, "frameHeight": height, "frames": records, "contactSheets": sheet_records},
        "privacy": {"repositoryContainsPixels": False, "artifactContainsPrivateLowResolutionFrames": True, "artifactRetentionDays": int(sampling["artifactRetentionDays"]), "originalVideoIncludedInArtifact": False},
        "modeling": {"geometryGenerated": False, "humanReviewRequired": True, "minimumIndependentViewsPerModeledFeature": plan["hardGates"]["minimumIndependentViewsPerModeledFeature"]},
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "frames": len(records), "contactSheets": len(sheet_records)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
