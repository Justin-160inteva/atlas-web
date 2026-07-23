#!/usr/bin/env python3
"""Extract transient 12-22s map evidence for the missing Tokei Shrine candidate.

The authorized video shows two nearby shrine markers in Nakahechi Route, then directly
opens one popup as Takahara Kumano Shrine. This extractor preserves dense full-map frames
only in a one-day artifact so reviewers can determine whether the other marker is uniquely
Tokei Shrine. The repository receives only timestamps and hashes; this script assigns no
coordinates or candidate IDs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/geospatial/tokei-pairwise-map-evidence-manifest.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def make_sheets(rows: list[dict], output_dir: Path) -> list[dict]:
    columns, grid_rows = 3, 3
    width, height, label_height = 640, 360, 42
    per_sheet = columns * grid_rows
    sheets = []
    for sheet_index in range(math.ceil(len(rows) / per_sheet)):
        batch = rows[sheet_index * per_sheet:(sheet_index + 1) * per_sheet]
        canvas = np.zeros((grid_rows * (height + label_height), columns * width, 3), dtype=np.uint8)
        for index, row in enumerate(batch):
            image = cv2.imread(str(output_dir / row["filename"]))
            if image is None:
                raise RuntimeError(f"unable to read {row['filename']}")
            image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
            gy, gx = divmod(index, columns)
            x0, y0 = gx * width, gy * (height + label_height)
            canvas[y0:y0 + height, x0:x0 + width] = image
            cv2.rectangle(canvas, (x0, y0 + height), (x0 + width, y0 + height + label_height), (18, 18, 18), -1)
            cv2.putText(
                canvas,
                f"T{row['timeSeconds']:.3f}s",
                (x0 + 12, y0 + height + 29),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (245, 245, 245),
                2,
                cv2.LINE_AA,
            )
        filename = f"tokei-pairwise-sheet-{sheet_index + 1:02d}.jpg"
        path = output_dir / filename
        if not cv2.imwrite(str(path), canvas, [cv2.IMWRITE_JPEG_QUALITY, 93]):
            raise RuntimeError(f"unable to write {filename}")
        sheets.append({
            "filename": filename,
            "sha256": sha256(path),
            "frameCount": len(batch),
            "firstTimeSeconds": batch[0]["timeSeconds"],
            "lastTimeSeconds": batch[-1]["timeSeconds"],
        })
    return sheets


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--start", type=float, default=12.0)
    parser.add_argument("--end", type=float, default=22.0)
    parser.add_argument("--interval", type=float, default=0.25)
    args = parser.parse_args()

    if not (0 <= args.start < args.end and 0.1 <= args.interval <= 1.0):
        raise ValueError("invalid targeted evidence range")
    video = Path(args.video).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError("unable to open authorized shrine video")
    rows = []
    time_value = args.start
    try:
        while time_value <= args.end + 1e-6:
            capture.set(cv2.CAP_PROP_POS_MSEC, time_value * 1000.0)
            ok, frame = capture.read()
            if not ok or frame is None:
                raise RuntimeError(f"unable to extract {time_value:.3f}s")
            filename = f"tokei-{time_value:.3f}s-full.jpg"
            path = output_dir / filename
            if not cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 96]):
                raise RuntimeError(f"unable to write {filename}")
            rows.append({
                "timeSeconds": round(time_value, 3),
                "filename": filename,
                "sha256": sha256(path),
                "width": int(frame.shape[1]),
                "height": int(frame.shape[0]),
            })
            time_value += args.interval
    finally:
        capture.release()

    sheets = make_sheets(rows, output_dir)
    manifest = {
        "schemaVersion": 1,
        "generatedAt": now(),
        "runId": str(args.run_id),
        "status": "transient-targeted-map-evidence-ready",
        "source": {
            "bvid": "BV1aFXaYmEDZ",
            "title": "〖刺客信条影 新手攻略〗02 神社全收集（27个位置）",
            "authorizationId": "auth-dada-20260718",
        },
        "target": {
            "missingCandidateId": "location-mapgenie-438414",
            "missingCandidateTitle": "Tokei Shrine",
            "directlyIdentifiedNeighborId": "location-mapgenie-437477",
            "directlyIdentifiedNeighborTitle": "Takahara Kumano Shrine",
            "reviewQuestion": "Do the map sequence and direct Takahara popup uniquely identify the other nearby shrine marker as Tokei Shrine?",
        },
        "range": {
            "startSeconds": args.start,
            "endSeconds": args.end,
            "intervalSeconds": args.interval,
        },
        "counts": {
            "frames": len(rows),
            "contactSheets": len(sheets),
        },
        "frames": rows,
        "contactSheets": sheets,
        "policy": {
            "coordinatesAssigned": False,
            "candidateAssignmentAllowedInExtractor": False,
            "requiresUniquePairwiseSpatialProof": True,
            "otherwiseRemainUnresolved": True,
        },
        "privacy": {
            "repositoryContainsPixels": False,
            "artifactContainsTransientPixels": True,
            "artifactRetentionDays": 1,
            "deleteVideoAndFramesBeforeJobExit": True,
        },
    }
    if len(rows) != 41 or len(sheets) != 5:
        raise RuntimeError(f"unexpected targeted package size: {len(rows)} frames, {len(sheets)} sheets")
    write(OUTPUT, manifest)
    (output_dir / "tokei-pairwise-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
