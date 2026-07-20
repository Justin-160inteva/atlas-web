#!/usr/bin/env python3
"""Adaptive high-throughput Atlas analyzer.

v11 keeps the v10 curl_cffi compatibility layer, adds bounded parallel HTTP range
transfers with automatic resume/fallback, shortens truthful heartbeat intervals, and
selects a quality/speed sampling profile from the verified catalog. Original media and
frame pixels remain transient.
"""
from __future__ import annotations

import json
import math
import pathlib
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import parse_qs, urlparse

import analyze_authorized_video_v10 as v10

v9 = v10.v9
runner = v9.runner
MIB = 1024 * 1024
ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "data/batch-analysis/eleven-pilot-scan-manifest.json"
CATALOG_PATH = ROOT / "data/eleven-game-world-ac-shadows-catalog.json"


def _load(path: pathlib.Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _settings() -> dict[str, Any]:
    manifest = _load(MANIFEST_PATH, {})
    return dict(manifest.get("downloadOptimization") or {})


def _job() -> dict[str, Any]:
    if len(sys.argv) != 2:
        return {}
    return _load(pathlib.Path(sys.argv[1]), {})


def _sampling_profile(job: dict[str, Any]) -> tuple[str, int]:
    catalog = _load(CATALOG_PATH, {"items": []})
    source = next(
        (item for item in catalog.get("items", []) if item.get("id") == job.get("externalSourceId")),
        {},
    )
    scan_class = str(source.get("scanClass") or "B").upper()
    utility = str(source.get("mapUtility") or "")
    configured = max(1, int(job.get("maxSamples") or 360))
    if scan_class == "A":
        return "quality", min(configured, 480)
    if scan_class == "B" and utility == "高":
        return "balanced-high", min(configured, 360)
    if scan_class == "B":
        return "balanced", min(configured, 300)
    return "fast-review", min(configured, 180)


_original_analyze = runner.base.analyze


def balanced_analyze(job: dict[str, Any], video_path: pathlib.Path) -> dict[str, Any]:
    profile, samples = _sampling_profile(job)
    tuned = dict(job)
    tuned["maxSamples"] = samples
    tuned["analysisProfile"] = profile
    report = _original_analyze(tuned, video_path)
    report.setdefault("scan", {})["analysisProfile"] = profile
    report["scan"]["qualitySpeedPolicy"] = {
        "profile": profile,
        "targetSamples": samples,
        "descriptorResolution": "320x180",
        "numericDescriptorsOnly": True,
    }
    return report


runner.base.analyze = balanced_analyze


def _range_probe(candidate: str, declared_size: int) -> tuple[bool, int]:
    headers = dict(runner.HEADERS)
    headers.update({"Range": "bytes=0-0", "Accept-Encoding": "identity"})
    with runner.requests.get(
        candidate,
        headers=headers,
        impersonate="chrome",
        stream=True,
        timeout=30,
    ) as response:
        response.raise_for_status()
        status = int(getattr(response, "status_code", 0) or 0)
        content_range = str(response.headers.get("content-range") or "")
        match = re.search(r"/(\d+)$", content_range)
        total = int(match.group(1)) if match else max(0, int(declared_size))
        return status == 206 and total > 0, total


def _parallel_range_download(
    candidate: str,
    target: pathlib.Path,
    *,
    total_size: int,
    heartbeat: v9.DownloadHeartbeat,
    downloaded_before: int,
    segment_index: int,
    workers: int,
    chunk_size: int,
    retries: int,
) -> None:
    workers = max(2, min(int(workers), 8))
    span = math.ceil(total_size / workers)
    ranges = [
        (index, index * span, min(total_size - 1, (index + 1) * span - 1))
        for index in range(workers)
        if index * span < total_size
    ]
    part_paths = [target.with_name(f"{target.name}.range-{index:02d}.part") for index, _, _ in ranges]
    counts = [0 for _ in ranges]
    lock = threading.Lock()

    def update(index: int, value: int) -> None:
        with lock:
            counts[index] = value
            current = sum(counts)
        heartbeat.update(
            downloaded_bytes=downloaded_before + current,
            segment_downloaded_bytes=current,
            segment_total_bytes=total_size,
            segment_index=segment_index,
        )

    def worker(position: int, start: int, end: int) -> None:
        part = part_paths[position]
        expected = end - start + 1
        for attempt in range(max(1, retries)):
            existing = part.stat().st_size if part.exists() else 0
            if existing >= expected:
                update(position, expected)
                return
            request_start = start + existing
            headers = dict(runner.HEADERS)
            headers.update({"Range": f"bytes={request_start}-{end}", "Accept-Encoding": "identity"})
            try:
                with runner.requests.get(
                    candidate,
                    headers=headers,
                    impersonate="chrome",
                    stream=True,
                    timeout=90,
                ) as response:
                    response.raise_for_status()
                    if int(getattr(response, "status_code", 0) or 0) != 206:
                        raise RuntimeError("range request was not honored")
                    mode = "ab" if existing else "wb"
                    written = existing
                    with part.open(mode) as handle:
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            if not chunk:
                                continue
                            handle.write(chunk)
                            written += len(chunk)
                            update(position, min(written, expected))
                if part.stat().st_size == expected:
                    update(position, expected)
                    return
                raise RuntimeError("range content-length mismatch")
            except Exception:
                if attempt + 1 >= max(1, retries):
                    raise
                time.sleep(min(6, 1 + attempt * 2))
        raise RuntimeError("range retry limit reached")

    try:
        with ThreadPoolExecutor(max_workers=len(ranges), thread_name_prefix="atlas-range") as pool:
            futures = [pool.submit(worker, position, start, end) for position, (_, start, end) in enumerate(ranges)]
            for future in as_completed(futures):
                future.result()
        with target.open("wb") as output:
            for path in part_paths:
                with path.open("rb") as source:
                    while True:
                        chunk = source.read(8 * MIB)
                        if not chunk:
                            break
                        output.write(chunk)
        if target.stat().st_size != total_size:
            raise RuntimeError("parallel range assembly size mismatch")
    finally:
        for part in part_paths:
            part.unlink(missing_ok=True)


def _single_stream_resume(
    candidate: str,
    target: pathlib.Path,
    *,
    expected_size: int,
    heartbeat: v9.DownloadHeartbeat,
    downloaded_before: int,
    segment_index: int,
    chunk_size: int,
    retries: int,
) -> None:
    for attempt in range(max(1, retries)):
        existing = target.stat().st_size if target.exists() else 0
        headers = dict(runner.HEADERS)
        headers["Accept-Encoding"] = "identity"
        if existing:
            headers["Range"] = f"bytes={existing}-"
        try:
            with runner.requests.get(
                candidate,
                headers=headers,
                impersonate="chrome",
                stream=True,
                timeout=90,
            ) as response:
                response.raise_for_status()
                status = int(getattr(response, "status_code", 0) or 0)
                if existing and status != 206:
                    existing = 0
                    target.unlink(missing_ok=True)
                header_total = int(response.headers.get("content-length") or 0)
                total = expected_size or (existing + header_total if header_total else 0)
                mode = "ab" if existing else "wb"
                written = existing
                with target.open(mode) as handle:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if not chunk:
                            continue
                        handle.write(chunk)
                        written += len(chunk)
                        heartbeat.update(
                            downloaded_bytes=downloaded_before + written,
                            segment_downloaded_bytes=written,
                            segment_total_bytes=total,
                            segment_index=segment_index,
                        )
            if target.exists() and target.stat().st_size >= 1024:
                if total and target.stat().st_size != total:
                    raise RuntimeError("content-length mismatch after resumed transfer")
                return
        except Exception:
            if attempt + 1 >= max(1, retries):
                raise
            time.sleep(min(6, 1 + attempt * 2))
    raise RuntimeError("single-stream retry limit reached")


def direct_bilibili_download(url: str, workdir: pathlib.Path) -> pathlib.Path:
    job = _job()
    settings = _settings()
    heartbeat_seconds = max(20, min(60, int(settings.get("heartbeatSeconds", 30))))
    v9.HEARTBEAT_SECONDS = float(heartbeat_seconds)
    v9.SPEED_WINDOW_SECONDS = float(max(30, int(settings.get("speedWindowSeconds", 60))))
    workers = max(2, min(8, int(settings.get("maxRangeWorkers", 4))))
    threshold = max(8 * MIB, int(settings.get("parallelRangeThresholdBytes", 24 * MIB)))
    chunk_size = max(MIB, min(8 * MIB, int(settings.get("chunkSizeBytes", 4 * MIB))))
    retries = max(2, min(5, int(settings.get("rangeRetries", 3))))

    match = re.search(r"(BV[0-9A-Za-z]+)", url)
    if not match:
        raise ValueError("No BV identifier found in Bilibili URL")
    bvid = match.group(1)
    query = parse_qs(urlparse(url).query)
    try:
        page_number = max(1, int((query.get("p") or ["1"])[0]))
    except (TypeError, ValueError):
        page_number = 1

    view = runner.api_get_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}")
    pages = view.get("pages") or []
    if not pages:
        raise RuntimeError("Bilibili view API returned no pages")
    if page_number > len(pages):
        raise RuntimeError(f"Requested page {page_number} exceeds multipart page count {len(pages)}")
    cid = pages[page_number - 1]["cid"]
    play = runner.api_get_json(
        f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn=32&fnver=0&fnval=0&fourk=0"
    )
    segments = play.get("durl") or []
    if not segments:
        raise RuntimeError("Bilibili playurl API returned no progressive media URLs")

    declared_sizes = [max(0, int(segment.get("size") or 0)) for segment in segments]
    heartbeat = v9.DownloadHeartbeat(job, total_bytes=sum(declared_sizes), segment_count=len(segments))
    heartbeat.start()
    downloaded_total = 0
    downloaded_paths: list[pathlib.Path] = []

    try:
        for zero_index, segment in enumerate(segments):
            segment_index = zero_index + 1
            target = workdir / f"p{page_number:03d}-part-{zero_index:03d}.flv"
            candidates = [segment.get("url"), *(segment.get("backup_url") or [])]
            last_error = "no media URL"
            for candidate in filter(None, candidates):
                target.unlink(missing_ok=True)
                declared = declared_sizes[zero_index]
                try:
                    range_ok, actual_size = _range_probe(str(candidate), declared)
                    if actual_size:
                        declared = actual_size
                        declared_sizes[zero_index] = actual_size
                    heartbeat.update(
                        downloaded_bytes=downloaded_total,
                        total_bytes=sum(declared_sizes),
                        segment_downloaded_bytes=0,
                        segment_total_bytes=declared,
                        segment_index=segment_index,
                    )
                    if range_ok and declared >= threshold and settings.get("adaptiveParallelRanges", True):
                        _parallel_range_download(
                            str(candidate), target, total_size=declared, heartbeat=heartbeat,
                            downloaded_before=downloaded_total, segment_index=segment_index,
                            workers=workers, chunk_size=chunk_size, retries=retries,
                        )
                    else:
                        _single_stream_resume(
                            str(candidate), target, expected_size=declared, heartbeat=heartbeat,
                            downloaded_before=downloaded_total, segment_index=segment_index,
                            chunk_size=chunk_size, retries=retries,
                        )
                    if target.stat().st_size < 1024:
                        raise RuntimeError("Downloaded media part is unexpectedly small")
                    downloaded_total += target.stat().st_size
                    downloaded_paths.append(target)
                    heartbeat.update(
                        downloaded_bytes=downloaded_total,
                        total_bytes=max(sum(declared_sizes), downloaded_total),
                        segment_downloaded_bytes=target.stat().st_size,
                        segment_total_bytes=max(declared, target.stat().st_size),
                        segment_index=segment_index,
                    )
                    heartbeat.publish(force=True)
                    break
                except Exception as exc:
                    last_error = repr(exc)
                    target.unlink(missing_ok=True)
            else:
                raise RuntimeError(f"Unable to download page {page_number} media part {zero_index}: {last_error}")
    finally:
        heartbeat.stop()

    output = workdir / f"source-p{page_number:03d}.mp4"
    elapsed = max(0.001, time.monotonic() - heartbeat.started_at)
    v9.emit_runtime_progress(
        job,
        stage="remuxing",
        progress_percent=8,
        message=f"下载完成，共 {downloaded_total / MIB:.1f} MB，正在媒体转封装",
        metrics={
            "downloadedBytes": downloaded_total,
            "totalBytes": max(sum(declared_sizes), downloaded_total),
            "segmentIndex": len(segments),
            "segmentCount": len(segments),
            "speedBytesPerSecond": downloaded_total / elapsed,
            "averageSpeedBytesPerSecond": downloaded_total / elapsed,
            "downloadElapsedSeconds": elapsed,
            "stalledSeconds": 0,
            "transferMode": "adaptive-range-or-resume",
            "maxRangeWorkers": workers,
        },
        force=True,
    )
    if len(downloaded_paths) == 1:
        command = ["ffmpeg", "-y", "-i", str(downloaded_paths[0]), "-c", "copy", str(output)]
    else:
        concat_file = workdir / "parts.txt"
        concat_file.write_text("".join(f"file '{path.as_posix()}'\n" for path in downloaded_paths), encoding="utf-8")
        command = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(output)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not output.exists():
        raise RuntimeError(runner.clean_error(result.stderr or "ffmpeg remux failed"))
    return output


runner.direct_bilibili_download = direct_bilibili_download


if __name__ == "__main__":
    raise SystemExit(v9.v6.main())
