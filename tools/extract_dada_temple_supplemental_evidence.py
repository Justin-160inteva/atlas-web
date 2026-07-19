#!/usr/bin/env python3
"""Extract dense transient evidence around unresolved Dada temple positions.

The repository receives only timestamps, dimensions and hashes. JPEG pixels are
written to a temporary workflow artifact and deleted from the runner afterward.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/geospatial/dada-temples-36-supplemental-evidence-manifest.json"

WINDOWS = [
    {"target": "position-02-root-tower", "videoPositions": [2], "start": 21.0, "end": 30.0, "candidateIds": ["location-mapgenie-436442", "location-mapgenie-436455"]},
    {"target": "positions-04-05-koyasan-saika", "videoPositions": [4, 5], "start": 35.0, "end": 52.0, "candidateIds": ["location-mapgenie-436436", "location-mapgenie-436455", "location-mapgenie-436387"]},
    {"target": "position-10-tennoji", "videoPositions": [10], "start": 78.0, "end": 88.0, "candidateIds": ["location-mapgenie-434396"]},
    {"target": "position-30-miidera", "videoPositions": [30], "start": 214.0, "end": 226.0, "candidateIds": ["location-mapgenie-435055"]},
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    video = Path(args.video)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError("unable to open supplemental evidence video")
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = frame_count / fps if fps > 0 else 0.0
    if abs(duration - 259.799) > 3:
        raise RuntimeError(f"unexpected video duration: {duration}")

    rows = []
    sheets = []
    for window_index, window in enumerate(WINDOWS, start=1):
        window_frames = []
        time_value = float(window["start"])
        frame_index = 0
        while time_value <= float(window["end"]) + 1e-9:
            cap.set(cv2.CAP_PROP_POS_MSEC, time_value * 1000.0)
            ok, frame = cap.read()
            if not ok or frame is None:
                raise RuntimeError(f"failed reading frame at {time_value:.3f}s")
            filename = f"window-{window_index:02d}-{window['target']}-{frame_index:03d}-{time_value:.3f}s.jpg"
            path = output / filename
            if not cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92]):
                raise RuntimeError(f"failed writing {filename}")
            row = {
                "window": window_index,
                "target": window["target"],
                "videoPositions": window["videoPositions"],
                "timeSeconds": round(time_value, 3),
                "filename": filename,
                "sha256": sha256(path),
                "width": int(frame.shape[1]),
                "height": int(frame.shape[0]),
            }
            rows.append(row)
            window_frames.append((time_value, frame))
            frame_index += 1
            time_value += 0.5

        thumb_width, thumb_height = 384, 216
        cols = 4
        sheet_rows = (len(window_frames) + cols - 1) // cols
        sheet = np.zeros((sheet_rows * (thumb_height + 32), cols * thumb_width, 3), dtype=np.uint8)
        for index, (timestamp, frame) in enumerate(window_frames):
            thumb = cv2.resize(frame, (thumb_width, thumb_height), interpolation=cv2.INTER_AREA)
            y = (index // cols) * (thumb_height + 32)
            x = (index % cols) * thumb_width
            sheet[y:y + thumb_height, x:x + thumb_width] = thumb
            cv2.putText(sheet, f"{timestamp:.1f}s", (x + 8, y + thumb_height + 23), cv2.FONT_HERSHEY_SIMPLEX, .65, (255, 255, 255), 1, cv2.LINE_AA)
        sheet_filename = f"supplemental-contact-sheet-{window_index:02d}-{window['target']}.jpg"
        sheet_path = output / sheet_filename
        cv2.imwrite(str(sheet_path), sheet, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        sheets.append({
            "window": window_index,
            "target": window["target"],
            "filename": sheet_filename,
            "sha256": sha256(sheet_path),
            "frameCount": len(window_frames),
        })

    cap.release()
    manifest = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "status": "artifact-upload-pending",
        "runId": str(args.run_id),
        "artifactName": args.artifact_name,
        "artifactRetentionDays": 1,
        "source": {
            "bvid": "BV19EXYYWEdv",
            "title": "〖刺客信条影 新手攻略〗03 寺庙全收集（36个位置）",
            "authorizationId": "auth-dada-20260718",
            "downloadedDurationSeconds": round(duration, 3),
            "transientVideoSha256": sha256(video),
        },
        "windows": WINDOWS,
        "extraction": {
            "intervalSeconds": 0.5,
            "frameCount": len(rows),
            "contactSheetCount": len(sheets),
            "frames": rows,
            "contactSheets": sheets,
        },
        "privacy": {
            "repositoryContainsPixels": False,
            "artifactContainsTransientPixels": True,
            "originalVideoRetained": False,
            "framePixelsRetainedAfterWorkflow": False,
        },
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"frames": len(rows), "sheets": len(sheets)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
