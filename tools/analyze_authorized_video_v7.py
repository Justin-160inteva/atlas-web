#!/usr/bin/env python3
"""Multipart authorized-video analyzer with truthful 60-second download telemetry."""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import analyze_authorized_video_v6 as v6

runner = v6.v5.runner
emit_runtime_progress = v6.emit_runtime_progress


def _job() -> dict[str, Any]:
    if len(sys.argv) != 2:
        return {}
    try:
        return json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _emit_download(job: dict[str, Any], *, downloaded: int, total: int, segment_downloaded: int,
                   segment_total: int, segment_index: int, segment_count: int,
                   started_at: float, force: bool = False) -> None:
    elapsed = max(0.001, time.monotonic() - started_at)
    speed = downloaded / elapsed
    eta = (total - downloaded) / speed if speed > 0 and total > downloaded else 0
    ratio = downloaded / total if total > 0 else 0
    emit_runtime_progress(
        job,
        stage="download",
        progress_percent=2 + ratio * 6,
        message=f"正在下载第 {segment_index}/{segment_count} 个分片 · {downloaded / 1048576:.1f} MB · {speed / 1048576:.2f} MB/s",
        sampled_frames=0,
        target_frames=int(job.get("maxSamples") or 1),
        state="running",
        metrics={
            "downloadedBytes": downloaded,
            "totalBytes": total,
            "segmentDownloadedBytes": segment_downloaded,
            "segmentTotalBytes": segment_total,
            "segmentIndex": segment_index,
            "segmentCount": segment_count,
            "speedBytesPerSecond": speed,
            "etaSeconds": eta,
        },
        force=force,
    )


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
    total_bytes = sum(declared_sizes)
    downloaded_total = 0
    started_at = time.monotonic()
    downloaded_paths: list[pathlib.Path] = []

    for zero_index, segment in enumerate(segments):
        segment_index = zero_index + 1
        segment_total = declared_sizes[zero_index]
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
                        if total_bytes <= 0:
                            total_bytes = sum(declared_sizes[:zero_index]) + header_total + sum(declared_sizes[zero_index + 1:])
                    with target.open("wb") as handle:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if not chunk:
                                continue
                            handle.write(chunk)
                            size = len(chunk)
                            segment_downloaded += size
                            current_total = downloaded_total + segment_downloaded
                            _emit_download(
                                job,
                                downloaded=current_total,
                                total=total_bytes,
                                segment_downloaded=segment_downloaded,
                                segment_total=segment_total,
                                segment_index=segment_index,
                                segment_count=len(segments),
                                started_at=started_at,
                            )
                if target.stat().st_size < 1024:
                    raise RuntimeError("Downloaded media part is unexpectedly small")
                downloaded_total += target.stat().st_size
                downloaded_paths.append(target)
                _emit_download(
                    job,
                    downloaded=downloaded_total,
                    total=max(total_bytes, downloaded_total),
                    segment_downloaded=target.stat().st_size,
                    segment_total=max(segment_total, target.stat().st_size),
                    segment_index=segment_index,
                    segment_count=len(segments),
                    started_at=started_at,
                    force=True,
                )
                break
            except Exception as exc:
                last_error = repr(exc)
                target.unlink(missing_ok=True)
        else:
            raise RuntimeError(f"Unable to download page {page_number} media part {zero_index}: {last_error}")

    output = workdir / f"source-p{page_number:03d}.mp4"
    emit_runtime_progress(
        job,
        stage="remuxing",
        progress_percent=8,
        message=f"下载完成，共 {downloaded_total / 1048576:.1f} MB，正在媒体转封装",
        metrics={
            "downloadedBytes": downloaded_total,
            "totalBytes": max(total_bytes, downloaded_total),
            "segmentIndex": len(segments),
            "segmentCount": len(segments),
            "speedBytesPerSecond": downloaded_total / max(0.001, time.monotonic() - started_at),
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
