#!/usr/bin/env python3
"""Detect stable map-popup events in the authorized 27-shrine video.

Unlike the previous forced 27-way temporal split, this detector samples the complete video
and looks specifically for the dark rectangular map information panel. The top-left creator
chapter overlay is outside the detector region and cannot contaminate popup title review.
Representative popup and title crops are transient; the repository receives only timestamps,
box geometry, hashes and numeric quality metrics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "data/analysis-results/dada-02.json"
OUTPUT_PATH = ROOT / "data/geospatial/dada-shrines-popup-event-census.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def dhash(gray: np.ndarray) -> int:
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    bits = small[:, 1:] > small[:, :-1]
    value = 0
    for bit in bits.flatten():
        value = (value << 1) | int(bool(bit))
    return value


def normalized_title_mask(title: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(title, cv2.COLOR_BGR2GRAY) if title.ndim == 3 else title
    resized = cv2.resize(gray, (256, 64), interpolation=cv2.INTER_AREA)
    blurred = cv2.GaussianBlur(resized, (3, 3), 0)
    _, mask = cv2.threshold(blurred, 142, 255, cv2.THRESH_BINARY)
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)),
        iterations=1,
    )
    return mask


def signature_distance(left: np.ndarray, right: np.ndarray) -> float:
    if left.shape != right.shape:
        right = cv2.resize(right, (left.shape[1], left.shape[0]), interpolation=cv2.INTER_NEAREST)
    return float(np.mean(cv2.absdiff(left, right))) / 255.0


def detect_popup(frame: np.ndarray) -> dict[str, Any] | None:
    height, width = frame.shape[:2]
    x0, x1 = int(width * 0.12), int(width * 0.88)
    y0, y1 = int(height * 0.15), int(height * 0.85)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    roi = gray[y0:y1, x0:x1]
    dark = (roi < 80).astype(np.uint8) * 255
    closed = cv2.morphologyEx(
        dark,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (25, 9)),
        iterations=2,
    )
    cleaned = cv2.morphologyEx(
        closed,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)),
        iterations=1,
    )
    contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[dict[str, Any]] = []
    for contour in contours:
        x, y, box_width, box_height = cv2.boundingRect(contour)
        global_x, global_y = x + x0, y + y0
        area = box_width * box_height
        aspect = box_width / max(1.0, box_height)
        if not (230 <= box_width <= 560 and 90 <= box_height <= 340):
            continue
        if area < 32000 or not (1.15 <= aspect <= 5.2):
            continue
        center_x = global_x + box_width / 2
        center_y = global_y + box_height / 2
        if not (width * 0.25 <= center_x <= width * 0.75):
            continue
        if not (height * 0.17 <= center_y <= height * 0.78):
            continue
        box_mask = dark[y:y + box_height, x:x + box_width]
        dark_density = float(np.count_nonzero(box_mask)) / float(max(1, box_mask.size))
        if dark_density < 0.38:
            continue
        contour_area = float(cv2.contourArea(contour))
        rectangular_fill = contour_area / float(max(1, area))
        score = area * dark_density * (0.70 + 0.30 * min(1.0, rectangular_fill))
        candidates.append({
            "x": global_x,
            "y": global_y,
            "width": box_width,
            "height": box_height,
            "darkDensity": dark_density,
            "rectangularFill": rectangular_fill,
            "score": score,
        })
    if not candidates:
        return None
    chosen = max(candidates, key=lambda row: float(row["score"]))
    x, y = int(chosen["x"]), int(chosen["y"])
    box_width, box_height = int(chosen["width"]), int(chosen["height"])
    popup = frame[y:y + box_height, x:x + box_width]
    title_height = max(42, min(82, round(box_height * 0.30)))
    title = popup[:title_height, :]
    title_mask = normalized_title_mask(title)
    popup_gray = cv2.cvtColor(popup, cv2.COLOR_BGR2GRAY)
    chosen.update({
        "popup": popup,
        "title": title,
        "titleMask": title_mask,
        "titleDhash": dhash(title_mask),
        "popupSharpness": float(cv2.Laplacian(popup_gray, cv2.CV_64F).var()),
        "titleBrightDensity": float(np.count_nonzero(title_mask)) / float(title_mask.size),
    })
    return chosen


def split_events(detections: list[dict[str, Any]], maximum_gap: float, title_change_threshold: float) -> list[list[dict[str, Any]]]:
    if not detections:
        return []
    events: list[list[dict[str, Any]]] = []
    current = [detections[0]]
    reference_mask = detections[0]["titleMask"]
    for row in detections[1:]:
        previous = current[-1]
        gap = float(row["timeSeconds"]) - float(previous["timeSeconds"])
        title_distance = signature_distance(reference_mask, row["titleMask"])
        box_shift = math.hypot(
            float(row["x"]) - float(previous["x"]),
            float(row["y"]) - float(previous["y"]),
        )
        size_change = (
            abs(float(row["width"]) - float(previous["width"]))
            + abs(float(row["height"]) - float(previous["height"]))
        )
        changed = (
            gap > maximum_gap
            or title_distance > title_change_threshold
            or box_shift > 155
            or size_change > 190
        )
        if changed:
            events.append(current)
            current = [row]
            reference_mask = row["titleMask"]
        else:
            current.append(row)
            if len(current) >= 3:
                reference_mask = current[len(current) // 2]["titleMask"]
    events.append(current)
    return events


def make_contact_sheets(event_rows: list[dict[str, Any]], output_dir: Path) -> list[dict[str, Any]]:
    columns, rows = 3, 4
    cell_width, image_height, label_height = 480, 260, 42
    per_sheet = columns * rows
    sheets: list[dict[str, Any]] = []
    for sheet_index in range(math.ceil(len(event_rows) / per_sheet)):
        batch = event_rows[sheet_index * per_sheet:(sheet_index + 1) * per_sheet]
        canvas = np.zeros((rows * (image_height + label_height), columns * cell_width, 3), dtype=np.uint8)
        for index, row in enumerate(batch):
            image = cv2.imread(str(output_dir / row["popupFilename"]))
            if image is None:
                raise RuntimeError(f"unable to read popup crop {row['popupFilename']}")
            scale = min(cell_width / image.shape[1], image_height / image.shape[0])
            resized = cv2.resize(
                image,
                (max(1, round(image.shape[1] * scale)), max(1, round(image.shape[0] * scale))),
                interpolation=cv2.INTER_AREA,
            )
            grid_y, grid_x = divmod(index, columns)
            base_x = grid_x * cell_width
            base_y = grid_y * (image_height + label_height)
            offset_x = base_x + (cell_width - resized.shape[1]) // 2
            offset_y = base_y + (image_height - resized.shape[0]) // 2
            canvas[offset_y:offset_y + resized.shape[0], offset_x:offset_x + resized.shape[1]] = resized
            cv2.rectangle(
                canvas,
                (base_x, base_y + image_height),
                (base_x + cell_width, base_y + image_height + label_height),
                (18, 18, 18),
                -1,
            )
            label = f"P{row['event']:03d} {row['representativeTimeSeconds']:.3f}s n={row['sampleCount']}"
            cv2.putText(
                canvas,
                label,
                (base_x + 10, base_y + image_height + 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.66,
                (245, 245, 245),
                2,
                cv2.LINE_AA,
            )
        filename = f"popup-contact-sheet-{sheet_index + 1:02d}.jpg"
        path = output_dir / filename
        if not cv2.imwrite(str(path), canvas, [cv2.IMWRITE_JPEG_QUALITY, 93]):
            raise RuntimeError(f"unable to write {filename}")
        sheets.append({
            "filename": filename,
            "sha256": sha256(path),
            "eventCount": len(batch),
            "firstEvent": batch[0]["event"],
            "lastEvent": batch[-1]["event"],
        })
    return sheets


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--sample-interval", type=float, default=0.25)
    parser.add_argument("--maximum-gap", type=float, default=0.65)
    parser.add_argument("--title-change-threshold", type=float, default=0.255)
    parser.add_argument("--minimum-samples", type=int, default=2)
    args = parser.parse_args()

    video = Path(args.video).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    expected_duration = float(result["media"]["durationSeconds"])

    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError("unable to open shrine video")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    frame_count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if frame_count else expected_duration
    if abs(duration - expected_duration) > 3:
        raise RuntimeError(f"video duration mismatch: {duration:.3f} vs {expected_duration:.3f}")
    step = max(1, round(fps * args.sample_interval))
    detections: list[dict[str, Any]] = []
    sampled = 0
    frame_index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok or frame is None:
                break
            if frame_index % step:
                frame_index += 1
                continue
            sampled += 1
            time_seconds = frame_index / fps
            detected = detect_popup(frame)
            if detected is not None:
                detected["timeSeconds"] = round(time_seconds, 3)
                detections.append(detected)
            frame_index += 1
    finally:
        capture.release()

    raw_events = split_events(detections, args.maximum_gap, args.title_change_threshold)
    stable_events = [rows for rows in raw_events if len(rows) >= args.minimum_samples]
    event_rows: list[dict[str, Any]] = []
    for event_index, rows in enumerate(stable_events, start=1):
        representative = max(
            rows,
            key=lambda row: (
                float(row["popupSharpness"])
                * (0.65 + float(row["darkDensity"]))
                * (0.65 + min(0.35, float(row["titleBrightDensity"]) * 2.0))
            ),
        )
        popup_filename = f"P{event_index:03d}-{representative['timeSeconds']:.3f}s-popup.jpg"
        title_filename = f"P{event_index:03d}-{representative['timeSeconds']:.3f}s-title.jpg"
        popup_path = output_dir / popup_filename
        title_path = output_dir / title_filename
        if not cv2.imwrite(str(popup_path), representative["popup"], [cv2.IMWRITE_JPEG_QUALITY, 96]):
            raise RuntimeError(f"unable to write {popup_filename}")
        if not cv2.imwrite(str(title_path), representative["title"], [cv2.IMWRITE_JPEG_QUALITY, 98]):
            raise RuntimeError(f"unable to write {title_filename}")
        frame_height, frame_width = 720, 1280
        event_rows.append({
            "event": event_index,
            "startSeconds": round(float(rows[0]["timeSeconds"]), 3),
            "endSeconds": round(float(rows[-1]["timeSeconds"]), 3),
            "durationSeconds": round(float(rows[-1]["timeSeconds"]) - float(rows[0]["timeSeconds"]) + args.sample_interval, 3),
            "sampleCount": len(rows),
            "representativeTimeSeconds": float(representative["timeSeconds"]),
            "box": {
                "x": int(representative["x"]),
                "y": int(representative["y"]),
                "width": int(representative["width"]),
                "height": int(representative["height"]),
            },
            "normalizedBox": {
                "x": round(float(representative["x"]) / frame_width, 6),
                "y": round(float(representative["y"]) / frame_height, 6),
                "width": round(float(representative["width"]) / frame_width, 6),
                "height": round(float(representative["height"]) / frame_height, 6),
            },
            "popupSharpness": round(float(representative["popupSharpness"]), 4),
            "darkDensity": round(float(representative["darkDensity"]), 6),
            "titleBrightDensity": round(float(representative["titleBrightDensity"]), 6),
            "titleDhashHex": f"{int(representative['titleDhash']):016x}",
            "popupFilename": popup_filename,
            "popupSha256": sha256(popup_path),
            "titleFilename": title_filename,
            "titleSha256": sha256(title_path),
        })

    sheets = make_contact_sheets(event_rows, output_dir)
    timestamp = now()
    payload = {
        "schemaVersion": 1,
        "generatedAt": timestamp,
        "status": "popup-event-census-complete",
        "stage": "dense-dark-map-popup-detection",
        "source": {
            "bvid": "BV1aFXaYmEDZ",
            "title": "〖刺客信条影 新手攻略〗02 神社全收集（27个位置）",
            "authorizationId": "auth-dada-20260718",
            "durationSeconds": round(duration, 3),
        },
        "method": {
            "sampleIntervalSeconds": args.sample_interval,
            "maximumDetectionGapSeconds": args.maximum_gap,
            "titleChangeThreshold": args.title_change_threshold,
            "minimumSamplesPerEvent": args.minimum_samples,
            "popupSearchRegion": {"x": [0.12, 0.88], "y": [0.15, 0.85]},
            "excludedCreatorOverlayRegion": "top-left creator chapter caption is outside selected popup rectangle",
            "coordinatesAssigned": False,
        },
        "counts": {
            "sampledFrames": sampled,
            "popupDetections": len(detections),
            "rawEvents": len(raw_events),
            "stableEvents": len(event_rows),
            "contactSheets": len(sheets),
        },
        "events": [{key: value for key, value in row.items() if not key.endswith("Filename")} for row in event_rows],
        "artifactFiles": {
            "eventCrops": [{
                "event": row["event"],
                "popupFilename": row["popupFilename"],
                "popupSha256": row["popupSha256"],
                "titleFilename": row["titleFilename"],
                "titleSha256": row["titleSha256"],
            } for row in event_rows],
            "contactSheets": sheets,
        },
        "privacy": {
            "repositoryContainsPixels": False,
            "artifactContainsTransientPopupPixels": True,
            "artifactRetentionDays": 1,
            "deleteVideoAndCropsBeforeJobExit": True,
        },
    }
    if not (15 <= len(event_rows) <= 80):
        raise RuntimeError(f"unexpected stable popup event count: {len(event_rows)}")
    write(OUTPUT_PATH, payload)
    (output_dir / "popup-event-census-manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
