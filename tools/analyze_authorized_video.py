#!/usr/bin/env python3
"""Download an authorized public video, analyze it transiently, and keep only numeric descriptors.

The original video and extracted frame pixels are never committed to the repository.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np

try:
    from publish_runtime_progress import emit as emit_runtime_progress
except ImportError:  # direct imports outside tools/ keep analysis functional
    def emit_runtime_progress(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def hamming_distance(a: str, b: str) -> float:
    if not a or not b or len(a) != len(b):
        return 1.0
    return sum(x != y for x, y in zip(a, b)) / len(a)


def average_hash(gray: np.ndarray) -> str:
    small = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
    mean = float(small.mean())
    return "".join("1" if value >= mean else "0" for value in small.flatten())


def color_descriptor(frame: np.ndarray) -> list[float]:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [6, 4], [0, 180, 0, 256])
    hist = cv2.normalize(hist, hist).flatten()
    return [round(float(value), 6) for value in hist]


def edge_descriptor(gray: np.ndarray) -> tuple[float, list[float], float]:
    edges = cv2.Canny(gray, 70, 150)
    density = float(np.count_nonzero(edges)) / float(edges.size)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude, angle = cv2.cartToPolar(gx, gy, angleInDegrees=True)
    bins = np.zeros(8, dtype=np.float64)
    indices = (angle / 22.5).astype(np.int32) % 8
    for index in range(8):
        bins[index] = float(magnitude[indices == index].sum())
    total = float(bins.sum()) or 1.0
    normalized = [round(float(value / total), 6) for value in bins]
    dominant = int(np.argmax(bins)) * 22.5
    return density, normalized, dominant


def frame_descriptor(frame: np.ndarray) -> dict[str, Any]:
    scaled = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    edge_density, edge_hist, dominant_angle = edge_descriptor(gray)
    return {
        "hash": average_hash(gray),
        "brightness": round(float(gray.mean() / 255.0), 6),
        "sharpness": round(sharpness, 4),
        "edgeDensity": round(edge_density, 6),
        "edge": edge_hist,
        "dominantAngle": dominant_angle,
        "color": color_descriptor(scaled),
    }


def color_distance(a: list[float], b: list[float]) -> float:
    av = np.asarray(a, dtype=np.float32)
    bv = np.asarray(b, dtype=np.float32)
    if av.shape != bv.shape or av.size == 0:
        return 1.0
    return float(np.linalg.norm(av - bv) / math.sqrt(av.size))


def download_video(url: str, workdir: pathlib.Path) -> pathlib.Path:
    template = str(workdir / "source.%(ext)s")
    command = [
        "yt-dlp",
        "--no-playlist",
        "--no-progress",
        "--quiet",
        "--merge-output-format",
        "mp4",
        "--referer",
        "https://www.bilibili.com/",
        "--user-agent",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "-f",
        "bv*[height<=720]+ba/b[height<=720]/b",
        "-o",
        template,
        "--print",
        "after_move:filepath",
        url,
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("yt-dlp did not return a downloaded file path")
    path = pathlib.Path(lines[-1])
    if not path.exists():
        candidates = list(workdir.glob("source.*"))
        if not candidates:
            raise FileNotFoundError(path)
        path = candidates[0]
    return path


def analyze(job: dict[str, Any], video_path: pathlib.Path) -> dict[str, Any]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError("OpenCV could not open the downloaded video")

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    duration = frame_count / fps if fps > 0 else float(job.get("durationHintSeconds") or 0)
    job["durationHintSeconds"] = round(duration, 3)
    requested_interval = max(0.5, float(job.get("intervalSeconds", 1.0)))
    max_samples = max(1, int(job.get("maxSamples", 480)))
    effective_interval = max(requested_interval, duration / max_samples if duration else requested_interval)

    descriptors: list[dict[str, Any]] = []
    kept = 0
    sampled = 0
    blurred = 0
    duplicates = 0
    previous: dict[str, Any] | None = None
    last_kept_time = -1e9
    time_value = 0.0

    emit_runtime_progress(
        job,
        stage="analysis",
        progress_percent=8,
        message="媒体已就绪，开始抽帧与数值分析",
        processed_seconds=0,
        sampled_frames=0,
        target_frames=max_samples,
        force=True,
    )

    while (duration <= 0 or time_value < duration) and sampled < max_samples:
        capture.set(cv2.CAP_PROP_POS_MSEC, time_value * 1000.0)
        ok, frame = capture.read()
        if not ok:
            break
        sampled += 1
        descriptor = frame_descriptor(frame)
        descriptor["time"] = round(time_value, 3)

        too_soft = descriptor["sharpness"] < float(job.get("minimumSharpness", 18.0))
        duplicate = False
        if previous is not None:
            hash_distance = hamming_distance(descriptor["hash"], previous["hash"])
            chroma_distance = color_distance(descriptor["color"], previous["color"])
            duplicate = (
                hash_distance < float(job.get("duplicateHashDistance", 0.11))
                and chroma_distance < float(job.get("duplicateColorDistance", 0.055))
                and (time_value - last_kept_time) < 12.0
            )
            descriptor["difference"] = round(hash_distance * 0.65 + min(1.0, chroma_distance * 5.0) * 0.35, 6)
        else:
            descriptor["difference"] = 1.0

        if too_soft:
            blurred += 1
        elif duplicate:
            duplicates += 1
        else:
            descriptors.append(descriptor)
            previous = descriptor
            last_kept_time = time_value
            kept += 1

        if sampled == 1 or sampled % 10 == 0:
            ratio = sampled / max_samples if max_samples else 0
            emit_runtime_progress(
                job,
                stage="analysis",
                progress_percent=8 + ratio * 84,
                message=f"正在分析视频画面：已采样 {sampled}/{max_samples} 帧",
                processed_seconds=time_value,
                sampled_frames=sampled,
                target_frames=max_samples,
            )

        time_value += effective_interval

    capture.release()

    emit_runtime_progress(
        job,
        stage="indexing",
        progress_percent=94,
        message=f"数值分析完成：保留 {kept} 帧，正在生成结果索引",
        processed_seconds=min(time_value, duration) if duration > 0 else time_value,
        sampled_frames=sampled,
        target_frames=max_samples,
        force=True,
    )

    clear_frames = sorted(descriptors, key=lambda item: item["sharpness"], reverse=True)[:30]
    report = {
        "schemaVersion": 1,
        "jobId": job["id"],
        "status": "analyzed",
        "generatedAt": utc_now(),
        "source": {
            "author": job["author"],
            "title": job["title"],
            "url": job["url"],
            "platform": job.get("platform", "哔哩哔哩"),
            "authorizationId": job["authorizationId"],
            "externalSourceId": job.get("externalSourceId"),
        },
        "media": {
            "durationSeconds": round(duration, 3),
            "width": width,
            "height": height,
            "fps": round(fps, 3),
            "fileSha256": hashlib.sha256(video_path.read_bytes()).hexdigest(),
            "videoRetained": False,
            "framePixelsRetained": False,
        },
        "scan": {
            "requestedIntervalSeconds": requested_interval,
            "effectiveIntervalSeconds": round(effective_interval, 4),
            "sampled": sampled,
            "kept": kept,
            "blurred": blurred,
            "duplicates": duplicates,
            "keepRatio": round(kept / sampled, 6) if sampled else 0,
        },
        "clearFrameTimes": [
            {"time": item["time"], "sharpness": item["sharpness"], "edgeDensity": item["edgeDensity"]}
            for item in clear_frames
        ],
        "descriptors": descriptors,
        "privacy": "Only numeric visual descriptors and timestamps are committed. Original video and frame pixels are deleted after analysis.",
    }
    return report


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: analyze_authorized_video.py JOB_JSON", file=sys.stderr)
        return 2

    job_path = pathlib.Path(sys.argv[1])
    job = json.loads(job_path.read_text(encoding="utf-8"))
    required = ["id", "url", "author", "title", "authorizationId", "output"]
    missing = [key for key in required if not job.get(key)]
    if missing:
        raise ValueError(f"job is missing required fields: {', '.join(missing)}")

    output = pathlib.Path(job["output"])
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="atlas-authorized-") as directory:
        emit_runtime_progress(job, stage="download", progress_percent=2, message="开始临时下载授权视频", force=True)
        video_path = download_video(job["url"], pathlib.Path(directory))
        report = analyze(job, video_path)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    emit_runtime_progress(job, stage="persisting", progress_percent=98, message="分析结果已生成，等待写入任务状态", force=True)
    print(f"analysis complete: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
