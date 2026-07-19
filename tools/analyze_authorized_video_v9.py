#!/usr/bin/env python3
"""Multipart authorized-video analyzer with independent 60-second download heartbeats.

The download ticker keeps publishing a sanitized heartbeat even when the network stream
has not yielded a new chunk. Public telemetry contains byte counts, rolling speed,
segment progress, ETA, and stall age only; it never contains media URLs or local paths.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import threading
import time
from collections import deque
from typing import Any
from urllib.parse import parse_qs, urlparse

import analyze_authorized_video_v6 as v6

runner = v6.v5.runner
emit_runtime_progress = v6.emit_runtime_progress
MIB = 1024 * 1024
HEARTBEAT_SECONDS = 60.0
SPEED_WINDOW_SECONDS = 120.0


def _job() -> dict[str, Any]:
    if len(sys.argv) != 2:
        return {}
    try:
        return json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    except Exception:
        return {}


class DownloadHeartbeat:
    def __init__(self, job: dict[str, Any], *, total_bytes: int, segment_count: int) -> None:
        self.job = job
        self.started_at = time.monotonic()
        self.total_bytes = max(0, int(total_bytes))
        self.downloaded_bytes = 0
        self.segment_downloaded_bytes = 0
        self.segment_total_bytes = 0
        self.segment_index = 1 if segment_count else 0
        self.segment_count = max(0, int(segment_count))
        self.last_byte_at = self.started_at
        self.heartbeat_sequence = 0
        self.points: deque[tuple[float, int]] = deque([(self.started_at, 0)], maxlen=512)
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._ticker, name="atlas-download-heartbeat", daemon=True)

    def start(self) -> None:
        self.publish(force=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=30)

    def update(self, *, downloaded_bytes: int, total_bytes: int | None = None,
               segment_downloaded_bytes: int | None = None,
               segment_total_bytes: int | None = None,
               segment_index: int | None = None) -> None:
        now = time.monotonic()
        with self.lock:
            downloaded = max(0, int(downloaded_bytes))
            if downloaded > self.downloaded_bytes:
                self.last_byte_at = now
            self.downloaded_bytes = downloaded
            if total_bytes is not None:
                self.total_bytes = max(0, int(total_bytes))
            if segment_downloaded_bytes is not None:
                self.segment_downloaded_bytes = max(0, int(segment_downloaded_bytes))
            if segment_total_bytes is not None:
                self.segment_total_bytes = max(0, int(segment_total_bytes))
            if segment_index is not None:
                self.segment_index = max(0, int(segment_index))
            self.points.append((now, downloaded))
            cutoff = now - SPEED_WINDOW_SECONDS
            while len(self.points) > 2 and self.points[1][0] < cutoff:
                self.points.popleft()

    def _snapshot(self) -> dict[str, float | int]:
        now = time.monotonic()
        with self.lock:
            downloaded = self.downloaded_bytes
            total = self.total_bytes
            segment_downloaded = self.segment_downloaded_bytes
            segment_total = self.segment_total_bytes
            segment_index = self.segment_index
            segment_count = self.segment_count
            last_byte_at = self.last_byte_at
            points = list(self.points)
            self.heartbeat_sequence += 1
            sequence = self.heartbeat_sequence

        oldest_time, oldest_bytes = points[0]
        window_seconds = max(0.001, now - oldest_time)
        rolling_speed = max(0.0, (downloaded - oldest_bytes) / window_seconds)
        elapsed = max(0.001, now - self.started_at)
        average_speed = downloaded / elapsed
        eta = (total - downloaded) / rolling_speed if rolling_speed > 0 and total > downloaded else 0.0
        return {
            "downloadedBytes": downloaded,
            "totalBytes": total,
            "segmentDownloadedBytes": segment_downloaded,
            "segmentTotalBytes": segment_total,
            "segmentIndex": segment_index,
            "segmentCount": segment_count,
            "speedBytesPerSecond": rolling_speed,
            "averageSpeedBytesPerSecond": average_speed,
            "etaSeconds": eta,
            "downloadElapsedSeconds": elapsed,
            "speedWindowSeconds": window_seconds,
            "stalledSeconds": max(0.0, now - last_byte_at),
            "heartbeatSequence": sequence,
        }

    def publish(self, *, force: bool) -> None:
        metrics = self._snapshot()
        downloaded = int(metrics["downloadedBytes"])
        total = int(metrics["totalBytes"])
        ratio = downloaded / total if total > 0 else 0.0
        segment_index = int(metrics["segmentIndex"])
        segment_count = int(metrics["segmentCount"])
        speed = float(metrics["speedBytesPerSecond"])
        stalled = float(metrics["stalledSeconds"])
        if stalled >= HEARTBEAT_SECONDS and speed <= 0:
            activity = f"最近 {int(stalled)} 秒未收到新数据，连接仍在等待"
        else:
            activity = f"滚动速度 {speed / MIB:.2f} MB/s"
        emit_runtime_progress(
            self.job,
            stage="download",
            progress_percent=2 + ratio * 6,
            message=(
                f"正在下载第 {segment_index}/{segment_count} 个分片 · "
                f"{downloaded / MIB:.1f} MB · {activity}"
            ),
            sampled_frames=0,
            target_frames=int(self.job.get("maxSamples") or 1),
            state="running",
            metrics=metrics,
            force=force,
        )

    def _ticker(self) -> None:
        while not self.stop_event.wait(HEARTBEAT_SECONDS):
            try:
                self.publish(force=True)
            except Exception as error:
                print(f"download heartbeat warning: {type(error).__name__}", flush=True)


def direct_bilibili_download(url: str, workdir: pathlib.Path) -> pathlib.Path:
    job = _job()
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
    downloaded_total = 0
    downloaded_paths: list[pathlib.Path] = []
    heartbeat = DownloadHeartbeat(job, total_bytes=sum(declared_sizes), segment_count=len(segments))
    heartbeat.start()

    try:
        for zero_index, segment in enumerate(segments):
            segment_index = zero_index + 1
            segment_total = declared_sizes[zero_index]
            heartbeat.update(
                downloaded_bytes=downloaded_total,
                total_bytes=sum(declared_sizes),
                segment_downloaded_bytes=0,
                segment_total_bytes=segment_total,
                segment_index=segment_index,
            )
            candidates = [segment.get("url"), *(segment.get("backup_url") or [])]
            last_error = "no media URL"
            for candidate in filter(None, candidates):
                target = workdir / f"p{page_number:03d}-part-{zero_index:03d}.flv"
                target.unlink(missing_ok=True)
                segment_downloaded = 0
                try:
                    with runner.requests.get(
                        str(candidate), headers=runner.HEADERS, impersonate="chrome", stream=True, timeout=90
                    ) as response:
                        response.raise_for_status()
                        header_total = int(response.headers.get("content-length") or 0)
                        if header_total > 0:
                            segment_total = header_total
                            declared_sizes[zero_index] = header_total
                        heartbeat.update(
                            downloaded_bytes=downloaded_total,
                            total_bytes=sum(declared_sizes),
                            segment_downloaded_bytes=0,
                            segment_total_bytes=segment_total,
                            segment_index=segment_index,
                        )
                        with target.open("wb") as handle:
                            for chunk in response.iter_content(chunk_size=MIB):
                                if not chunk:
                                    continue
                                handle.write(chunk)
                                segment_downloaded += len(chunk)
                                heartbeat.update(
                                    downloaded_bytes=downloaded_total + segment_downloaded,
                                    total_bytes=sum(declared_sizes),
                                    segment_downloaded_bytes=segment_downloaded,
                                    segment_total_bytes=segment_total,
                                    segment_index=segment_index,
                                )
                    if target.stat().st_size < 1024:
                        raise RuntimeError("Downloaded media part is unexpectedly small")
                    downloaded_total += target.stat().st_size
                    downloaded_paths.append(target)
                    heartbeat.update(
                        downloaded_bytes=downloaded_total,
                        total_bytes=max(sum(declared_sizes), downloaded_total),
                        segment_downloaded_bytes=target.stat().st_size,
                        segment_total_bytes=max(segment_total, target.stat().st_size),
                        segment_index=segment_index,
                    )
                    heartbeat.publish(force=True)
                    break
                except Exception as exc:
                    last_error = repr(exc)
                    target.unlink(missing_ok=True)
                    heartbeat.update(
                        downloaded_bytes=downloaded_total,
                        total_bytes=sum(declared_sizes),
                        segment_downloaded_bytes=0,
                        segment_total_bytes=segment_total,
                        segment_index=segment_index,
                    )
            else:
                raise RuntimeError(f"Unable to download page {page_number} media part {zero_index}: {last_error}")
    finally:
        heartbeat.stop()

    output = workdir / f"source-p{page_number:03d}.mp4"
    elapsed = max(0.001, time.monotonic() - heartbeat.started_at)
    emit_runtime_progress(
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
    raise SystemExit(v6.main())
