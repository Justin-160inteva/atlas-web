#!/usr/bin/env python3
"""Detect the 27 shrine presentation segments from the authorized Dada video.

The previous scaffold split the video into equal-duration slots. This detector instead
samples the video densely, measures visual change, and snaps each of the 26 expected
boundaries to the strongest nearby transition. It then extracts three transient context
frames per segment and readable representative contact sheets. Repository outputs contain
only timestamps, scores, hashes and dimensions; source video and pixels remain transient.
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
SEGMENTS_PATH = ROOT / "data/geospatial/dada-shrines-27-scene-segments.json"
MANIFEST_PATH = ROOT / "data/geospatial/dada-shrines-27-scene-evidence-manifest.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe_duration(video: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def dhash(gray: np.ndarray) -> int:
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    bits = small[:, 1:] > small[:, :-1]
    value = 0
    for bit in bits.flatten():
        value = (value << 1) | int(bool(bit))
    return value


def hsv_hist(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256])
    return cv2.normalize(hist, hist).flatten()


def frame_metrics(frame: np.ndarray) -> dict[str, Any]:
    small = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 70, 150)
    return {
        "gray": gray,
        "hash": dhash(gray),
        "hist": hsv_hist(small),
        "sharpness": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        "edgeDensity": float(np.count_nonzero(edges)) / float(edges.size),
        "brightness": float(gray.mean()) / 255.0,
    }


def transition_score(previous: dict[str, Any], current: dict[str, Any]) -> tuple[float, dict[str, float]]:
    mean_abs = float(np.mean(cv2.absdiff(previous["gray"], current["gray"]))) / 255.0
    hash_distance = (int(previous["hash"]) ^ int(current["hash"])).bit_count() / 64.0
    hist_distance = float(cv2.compareHist(previous["hist"].astype(np.float32), current["hist"].astype(np.float32), cv2.HISTCMP_BHATTACHARYYA))
    edge_change = abs(float(previous["edgeDensity"]) - float(current["edgeDensity"]))
    score = 0.50 * mean_abs + 0.25 * hash_distance + 0.20 * hist_distance + 0.05 * min(1.0, edge_change * 8.0)
    return score, {
        "meanAbsoluteDifference": mean_abs,
        "hashDistance": hash_distance,
        "histogramDistance": hist_distance,
        "edgeDensityChange": edge_change,
    }


def sample_video(video: Path, interval: float) -> tuple[list[dict[str, Any]], float, float]:
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError("unable to open downloaded shrine video")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    frame_count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if frame_count > 0 else probe_duration(video)
    step = max(1, int(round(fps * interval)))
    samples: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    frame_index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok or frame is None:
                break
            if frame_index % step:
                frame_index += 1
                continue
            time_seconds = frame_index / fps
            metrics = frame_metrics(frame)
            score = 0.0
            components = {
                "meanAbsoluteDifference": 0.0,
                "hashDistance": 0.0,
                "histogramDistance": 0.0,
                "edgeDensityChange": 0.0,
            }
            if previous is not None:
                score, components = transition_score(previous, metrics)
            samples.append({
                "timeSeconds": round(time_seconds, 3),
                "transitionScore": round(score, 6),
                "sharpness": round(float(metrics["sharpness"]), 4),
                "edgeDensity": round(float(metrics["edgeDensity"]), 6),
                "brightness": round(float(metrics["brightness"]), 6),
                "dhashHex": f"{int(metrics['hash']):016x}",
                "components": {key: round(value, 6) for key, value in components.items()},
            })
            previous = metrics
            frame_index += 1
    finally:
        capture.release()
    if len(samples) < 100:
        raise RuntimeError(f"insufficient dense samples: {len(samples)}")
    return samples, fps, duration


def smooth_scores(samples: list[dict[str, Any]]) -> None:
    raw = [float(row["transitionScore"]) for row in samples]
    for index, row in enumerate(samples):
        left = max(0, index - 1)
        right = min(len(raw), index + 2)
        row["smoothedTransitionScore"] = round(max(raw[left:right]), 6)


def nearest_sample(samples: list[dict[str, Any]], target: float) -> dict[str, Any]:
    return min(samples, key=lambda row: abs(float(row["timeSeconds"]) - target))


def detect_boundaries(samples: list[dict[str, Any]], duration: float, count: int, window_fraction: float) -> list[dict[str, Any]]:
    nominal_span = duration / count
    radius = nominal_span * window_fraction
    global_scores = np.array([float(row["smoothedTransitionScore"]) for row in samples], dtype=np.float64)
    global_median = float(np.median(global_scores))
    global_p90 = float(np.quantile(global_scores, 0.90))
    boundaries: list[dict[str, Any]] = []
    for index in range(1, count):
        nominal = duration * index / count
        local = [
            row for row in samples
            if nominal - radius <= float(row["timeSeconds"]) <= nominal + radius
        ]
        if not local:
            chosen = nearest_sample(samples, nominal)
            local = [chosen]
        chosen = max(local, key=lambda row: (float(row["smoothedTransitionScore"]), float(row["transitionScore"])))
        local_scores = np.array([float(row["smoothedTransitionScore"]) for row in local], dtype=np.float64)
        local_median = float(np.median(local_scores))
        chosen_score = float(chosen["smoothedTransitionScore"])
        prominence = max(0.0, chosen_score - local_median)
        confidence = min(1.0, 0.45 + 0.35 * min(1.0, prominence / max(0.015, global_p90 - global_median)) + 0.20 * min(1.0, chosen_score / max(0.03, global_p90)))
        boundaries.append({
            "boundary": index,
            "nominalTimeSeconds": round(nominal, 3),
            "detectedTimeSeconds": round(float(chosen["timeSeconds"]), 3),
            "offsetSeconds": round(float(chosen["timeSeconds"]) - nominal, 3),
            "searchWindowSeconds": [round(nominal - radius, 3), round(nominal + radius, 3)],
            "transitionScore": round(chosen_score, 6),
            "localMedianScore": round(local_median, 6),
            "prominence": round(prominence, 6),
            "confidence": round(confidence, 4),
            "components": chosen["components"],
        })
    times = [float(row["detectedTimeSeconds"]) for row in boundaries]
    if times != sorted(times) or len(set(times)) != len(times):
        raise RuntimeError("detected boundary sequence is not strictly increasing")
    return boundaries


def build_segments(samples: list[dict[str, Any]], boundaries: list[dict[str, Any]], duration: float, count: int) -> list[dict[str, Any]]:
    cuts = [0.0] + [float(row["detectedTimeSeconds"]) for row in boundaries] + [duration]
    segments: list[dict[str, Any]] = []
    for index in range(count):
        start, end = cuts[index], cuts[index + 1]
        span = end - start
        if span < 2.0:
            raise RuntimeError(f"scene segment {index + 1} is too short: {span:.3f}s")
        interior = [
            row for row in samples
            if start + min(0.8, span * 0.12) <= float(row["timeSeconds"]) <= end - min(0.8, span * 0.12)
        ]
        if not interior:
            interior = [nearest_sample(samples, (start + end) / 2)]
        for row in interior:
            stability = max(0.02, 1.0 - min(0.98, float(row["smoothedTransitionScore"]) * 3.0))
            row["representativeScore"] = math.log1p(max(0.0, float(row["sharpness"]))) * (0.65 + float(row["edgeDensity"])) * stability
        representative = max(interior, key=lambda row: float(row["representativeScore"]))
        rep_time = float(representative["timeSeconds"])
        context_delta = min(1.25, span * 0.18)
        frame_times = {
            "before": max(start + 0.15, rep_time - context_delta),
            "representative": rep_time,
            "after": min(end - 0.15, rep_time + context_delta),
        }
        segments.append({
            "slot": index + 1,
            "startSeconds": round(start, 3),
            "endSeconds": round(end, 3),
            "durationSeconds": round(span, 3),
            "representativeTimeSeconds": round(rep_time, 3),
            "representativeScore": round(float(representative["representativeScore"]), 6),
            "representativeSharpness": float(representative["sharpness"]),
            "representativeTransitionScore": float(representative["smoothedTransitionScore"]),
            "representativeDhashHex": representative["dhashHex"],
            "frameTimes": {role: round(value, 3) for role, value in frame_times.items()},
        })
    for previous, current in zip(segments, segments[1:]):
        distance = (int(previous["representativeDhashHex"], 16) ^ int(current["representativeDhashHex"], 16)).bit_count() / 64.0
        previous["nextRepresentativeHashDistance"] = round(distance, 6)
        current["previousRepresentativeHashDistance"] = round(distance, 6)
    return segments


def extract_frames(video: Path, output_dir: Path, segments: list[dict[str, Any]], start_slot: int, end_slot: int) -> list[dict[str, Any]]:
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError("unable to reopen shrine video for evidence extraction")
    rows: list[dict[str, Any]] = []
    try:
        for segment in segments:
            slot = int(segment["slot"])
            if not start_slot <= slot <= end_slot:
                continue
            for role in ("before", "representative", "after"):
                time_seconds = float(segment["frameTimes"][role])
                capture.set(cv2.CAP_PROP_POS_MSEC, time_seconds * 1000.0)
                ok, frame = capture.read()
                if not ok or frame is None:
                    raise RuntimeError(f"unable to extract scene {slot} {role}")
                target_width = 960
                target_height = max(1, round(frame.shape[0] * target_width / frame.shape[1]))
                frame = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)
                filename = f"scene-{slot:02d}-{role}-{time_seconds:.3f}s.jpg"
                path = output_dir / filename
                if not cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 88]):
                    raise RuntimeError(f"unable to write {filename}")
                rows.append({
                    "slot": slot,
                    "role": role,
                    "timeSeconds": round(time_seconds, 3),
                    "filename": filename,
                    "sha256": sha256(path),
                    "width": int(frame.shape[1]),
                    "height": int(frame.shape[0]),
                })
    finally:
        capture.release()
    return rows


def make_representative_sheets(frame_rows: list[dict[str, Any]], output_dir: Path) -> list[dict[str, Any]]:
    representatives = [row for row in frame_rows if row["role"] == "representative"]
    columns, rows_per_sheet = 2, 4
    width, height, label_height = 720, 405, 44
    per_sheet = columns * rows_per_sheet
    sheets: list[dict[str, Any]] = []
    for sheet_index in range(math.ceil(len(representatives) / per_sheet)):
        batch = representatives[sheet_index * per_sheet:(sheet_index + 1) * per_sheet]
        canvas = np.zeros((rows_per_sheet * (height + label_height), columns * width, 3), dtype=np.uint8)
        for index, row in enumerate(batch):
            image = cv2.imread(str(output_dir / row["filename"]))
            if image is None:
                raise RuntimeError(f"unable to read representative {row['filename']}")
            image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
            grid_y, grid_x = divmod(index, columns)
            x0, y0 = grid_x * width, grid_y * (height + label_height)
            canvas[y0:y0 + height, x0:x0 + width] = image
            cv2.rectangle(canvas, (x0, y0 + height), (x0 + width, y0 + height + label_height), (18, 18, 18), -1)
            label = f"E{row['slot']:02d} representative {row['timeSeconds']:.3f}s"
            cv2.putText(canvas, label, (x0 + 12, y0 + height + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (245, 245, 245), 2, cv2.LINE_AA)
        filename = f"representative-sheet-{sheet_index + 1:02d}.jpg"
        path = output_dir / filename
        if not cv2.imwrite(str(path), canvas, [cv2.IMWRITE_JPEG_QUALITY, 92]):
            raise RuntimeError(f"unable to write {filename}")
        sheets.append({
            "filename": filename,
            "sha256": sha256(path),
            "eventCount": len(batch),
            "firstSlot": batch[0]["slot"],
            "lastSlot": batch[-1]["slot"],
            "width": int(canvas.shape[1]),
            "height": int(canvas.shape[0]),
        })
    return sheets


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--segment-count", type=int, default=27)
    parser.add_argument("--sample-interval", type=float, default=0.25)
    parser.add_argument("--boundary-window-fraction", type=float, default=0.42)
    parser.add_argument("--start-slot", type=int, default=1)
    parser.add_argument("--end-slot", type=int, default=14)
    args = parser.parse_args()

    if args.segment_count != 27:
        raise ValueError("authorized source title requires exactly 27 shrine segments")
    if not (1 <= args.start_slot <= args.end_slot <= args.segment_count):
        raise ValueError("selected slot range must be inside 1..27")
    if not (0.1 <= args.sample_interval <= 1.0):
        raise ValueError("sample interval must be between 0.1 and 1.0 seconds")

    video = Path(args.video).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stage = load(STAGE_PATH)
    result = load(RESULT_PATH)
    expected_duration = float(result["media"]["durationSeconds"])
    actual_duration = probe_duration(video)
    if abs(actual_duration - expected_duration) > 3:
        raise RuntimeError(f"duration mismatch: {actual_duration} vs {expected_duration}")

    samples, fps, sampled_duration = sample_video(video, args.sample_interval)
    smooth_scores(samples)
    boundaries = detect_boundaries(samples, actual_duration, args.segment_count, args.boundary_window_fraction)
    segments = build_segments(samples, boundaries, actual_duration, args.segment_count)
    frame_rows = extract_frames(video, output_dir, segments, args.start_slot, args.end_slot)
    sheets = make_representative_sheets(frame_rows, output_dir)

    selected_segments = [row for row in segments if args.start_slot <= int(row["slot"]) <= args.end_slot]
    evidence_fingerprint = hashlib.sha256(
        json.dumps(
            {
                "bvid": stage["source"]["bvid"],
                "segments": selected_segments,
                "frames": [{"slot": row["slot"], "role": row["role"], "sha256": row["sha256"]} for row in frame_rows],
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    timestamp = now()
    segmentation = {
        "schemaVersion": 1,
        "generatedAt": timestamp,
        "status": "complete",
        "stage": "scene-aware-temporal-segmentation",
        "source": {
            "bvid": stage["source"]["bvid"],
            "title": stage["source"]["title"],
            "authorizationId": stage["source"]["authorizationId"],
            "durationSeconds": round(actual_duration, 3),
        },
        "method": {
            "segmentCount": args.segment_count,
            "sampleIntervalSeconds": args.sample_interval,
            "boundaryWindowFraction": args.boundary_window_fraction,
            "transitionScore": "0.50 grayscale MAD + 0.25 dHash distance + 0.20 HSV histogram distance + 0.05 edge-density change",
            "boundarySelection": "strongest visual-change peak near each expected inter-item boundary",
            "representativeSelection": "highest sharpness/edge/stability score inside each detected segment",
        },
        "counts": {
            "denseSamples": len(samples),
            "boundaries": len(boundaries),
            "segments": len(segments),
            "selectedSegments": len(selected_segments),
        },
        "boundaries": boundaries,
        "segments": segments,
        "quality": {
            "strictlyIncreasingBoundaries": all(
                float(boundaries[index]["detectedTimeSeconds"]) < float(boundaries[index + 1]["detectedTimeSeconds"])
                for index in range(len(boundaries) - 1)
            ),
            "minimumSegmentDurationSeconds": round(min(float(row["durationSeconds"]) for row in segments), 3),
            "maximumSegmentDurationSeconds": round(max(float(row["durationSeconds"]) for row in segments), 3),
            "adjacentRepresentativeHashDistances": [
                row.get("nextRepresentativeHashDistance") for row in segments[:-1]
            ],
            "noCoordinatesAssigned": True,
        },
    }
    manifest = {
        "schemaVersion": 1,
        "generatedAt": timestamp,
        "status": "transient-scene-evidence-ready-for-model-review",
        "runId": str(args.run_id),
        "artifactName": args.artifact_name,
        "evidenceFingerprint": evidence_fingerprint,
        "source": segmentation["source"],
        "segmentationPath": "data/geospatial/dada-shrines-27-scene-segments.json",
        "batch": {
            "startSlot": args.start_slot,
            "endSlot": args.end_slot,
            "targetSlots": len(selected_segments),
        },
        "extraction": {
            "method": "three transient context frames per scene-aware segment; representative-only review sheets",
            "frameCount": len(frame_rows),
            "representativeFrameCount": len([row for row in frame_rows if row["role"] == "representative"]),
            "contactSheetCount": len(sheets),
            "frames": frame_rows,
            "contactSheets": sheets,
        },
        "segments": selected_segments,
        "privacy": {
            "repositoryContainsPixels": False,
            "transientDirectoryContainsPixels": True,
            "videoAndFramesMustBeDeletedBeforeJobExit": True,
        },
    }
    if segmentation["counts"] != {"denseSamples": len(samples), "boundaries": 26, "segments": 27, "selectedSegments": len(selected_segments)}:
        raise RuntimeError(f"unexpected segmentation counts: {segmentation['counts']}")
    if len(frame_rows) != len(selected_segments) * 3:
        raise RuntimeError("expected three transient frames per selected segment")
    if not sheets:
        raise RuntimeError("representative review sheets were not produced")

    write(SEGMENTS_PATH, segmentation)
    write(MANIFEST_PATH, manifest)
    (output_dir / "scene-evidence-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "segments": len(segments),
        "selectedSegments": len(selected_segments),
        "frames": len(frame_rows),
        "representativeSheets": len(sheets),
        "evidenceFingerprint": evidence_fingerprint,
        "fps": round(fps, 4),
        "sampledDurationSeconds": round(sampled_duration, 3),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
