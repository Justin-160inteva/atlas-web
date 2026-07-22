#!/usr/bin/env python3
"""Atlas v14 analyzer with bounded fastest-CDN selection and resilient media normalization.

v14 preserves v13's verified BVID/page/CID identity, WBI-signed metadata,
resumable API-provided CDN failover, transient-media policy, and numeric-only
analysis output. It also validates the remuxed stream and automatically normalizes
broken timestamps, implausible frame rates, missing pixel formats, or empty stream-copy
outputs through one bounded H.264/yuv420p transcode.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import analyze_authorized_video_v13 as v13

runner = v13.runner
transport = v13.transport
MIB = v13.MIB


def _probe_speed(candidate: str, probe_bytes: int, timeout_seconds: int) -> tuple[bool, float]:
    """Return (range-supported, measured bytes/second) for a bounded probe."""
    headers = dict(runner.HEADERS)
    headers.update({
        "Range": f"bytes=0-{probe_bytes - 1}",
        "Accept-Encoding": "identity",
    })
    started = time.monotonic()
    received = 0
    with runner.requests.get(
        candidate,
        headers=headers,
        impersonate="chrome",
        stream=True,
        timeout=timeout_seconds,
    ) as response:
        response.raise_for_status()
        status = int(getattr(response, "status_code", 0) or 0)
        if status not in {200, 206}:
            return False, 0.0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            received += len(chunk)
            if received >= probe_bytes:
                break
    elapsed = max(0.001, time.monotonic() - started)
    return status == 206, (received / elapsed if received else 0.0)


def _ordered_candidates(
    candidates: list[str],
    target: pathlib.Path,
    settings: dict[str, Any],
    declared_size: int,
) -> list[str]:
    """Order fresh transfers by Range capability and measured throughput."""
    if len(candidates) < 2 or not settings.get("cdnSpeedProbeEnabled", True):
        return candidates
    if target.exists() and target.stat().st_size > 0:
        return candidates

    maximum = max(2, min(6, int(settings.get("cdnSpeedProbeCandidates", 4))))
    probe_bytes = max(128 * 1024, min(MIB, int(settings.get("cdnSpeedProbeBytes", 512 * 1024))))
    timeout_seconds = max(3, min(12, int(settings.get("cdnSpeedProbeTimeoutSeconds", 6))))
    sampled = candidates[:maximum]
    results: dict[str, tuple[bool, float]] = {}

    with ThreadPoolExecutor(max_workers=len(sampled), thread_name_prefix="atlas-cdn-probe") as pool:
        futures = {
            pool.submit(_probe_speed, candidate, probe_bytes, timeout_seconds): candidate
            for candidate in sampled
        }
        for future in as_completed(futures):
            candidate = futures[future]
            try:
                range_ok, measured_speed = future.result()
                results[candidate] = (bool(range_ok), max(0.0, float(measured_speed)))
            except Exception:
                results[candidate] = (False, 0.0)

    threshold = max(8 * MIB, int(settings.get("parallelRangeThresholdBytes", 8 * MIB)))
    prefer_range = bool(
        settings.get("adaptiveParallelRanges", True)
        and settings.get("preferRangeCapableCdn", True)
        and declared_size >= threshold
    )
    original_index = {candidate: index for index, candidate in enumerate(candidates)}

    def rank(candidate: str) -> tuple[int, float, int]:
        range_ok, measured_speed = results.get(candidate, (False, 0.0))
        range_priority = 1 if (prefer_range and range_ok) else 0
        return (-range_priority, -measured_speed, original_index[candidate])

    return sorted(candidates, key=rank)


_original_download_stream = v13._download_stream


def _download_stream(
    stream: dict[str, Any],
    target: pathlib.Path,
    *,
    heartbeat: Any,
    downloaded_before: int,
    segment_index: int,
    settings: dict[str, Any],
) -> tuple[int, list[str]]:
    tuned = dict(stream)
    tuned["candidates"] = _ordered_candidates(
        [str(candidate) for candidate in (stream.get("candidates") or [])],
        target,
        settings,
        max(0, int(stream.get("declaredSize") or 0)),
    )
    return _original_download_stream(
        tuned,
        target,
        heartbeat=heartbeat,
        downloaded_before=downloaded_before,
        segment_index=segment_index,
        settings=settings,
    )


def _input_args(paths: list[pathlib.Path], workdir: pathlib.Path) -> list[str]:
    if len(paths) == 1:
        return ["-i", str(paths[0])]
    concat_file = workdir / "v14-parts.txt"
    concat_file.write_text(
        "".join(f"file '{path.as_posix()}'\n" for path in paths),
        encoding="utf-8",
    )
    return ["-f", "concat", "-safe", "0", "-i", str(concat_file)]


def _fraction(value: Any) -> float:
    try:
        numerator, denominator = str(value or "0/1").split("/", 1)
        return float(numerator) / max(1.0, float(denominator))
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def _probe_usable(path: pathlib.Path) -> tuple[bool, str]:
    if not path.exists() or path.stat().st_size < 1024:
        return False, "output is missing or empty"
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=pix_fmt,avg_frame_rate,r_frame_rate,duration,nb_frames",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    if result.returncode != 0:
        return False, transport.redact_diagnostic(result.stderr or "ffprobe failed")
    try:
        stream = (json.loads(result.stdout).get("streams") or [{}])[0]
    except (json.JSONDecodeError, IndexError):
        return False, "ffprobe returned no video stream"
    pix_fmt = str(stream.get("pix_fmt") or "").lower()
    frame_rate = _fraction(stream.get("avg_frame_rate") or stream.get("r_frame_rate"))
    duration = float(stream.get("duration") or 0)
    if pix_fmt in {"", "none", "unknown"}:
        return False, "video pixel format is unspecified"
    if frame_rate <= 0 or frame_rate > 240:
        return False, f"implausible frame rate {frame_rate:.2f} fps"
    if duration <= 0:
        return False, "video duration is zero"
    return True, f"pix_fmt={pix_fmt} fps={frame_rate:.3f} duration={duration:.2f}"


def _run_ffmpeg(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=5400, check=False)


def _remux(
    paths: list[pathlib.Path],
    workdir: pathlib.Path,
    *,
    page_number: int,
) -> pathlib.Path:
    output = workdir / f"source-p{page_number:03d}-v14.mp4"
    output.unlink(missing_ok=True)
    input_args = _input_args(paths, workdir)

    remux_result = _run_ffmpeg([
        "ffmpeg", "-y", "-fflags", "+genpts+discardcorrupt",
        "-analyzeduration", "100M", "-probesize", "100M",
        *input_args,
        "-map", "0:v:0", "-c:v", "copy",
        "-avoid_negative_ts", "make_zero", "-movflags", "+faststart",
        str(output),
    ])
    usable, probe_detail = _probe_usable(output)
    if remux_result.returncode == 0 and usable:
        return output

    output.unlink(missing_ok=True)
    transcode_result = _run_ffmpeg([
        "ffmpeg", "-y", "-fflags", "+genpts+discardcorrupt",
        "-err_detect", "ignore_err", "-analyzeduration", "200M", "-probesize", "200M",
        *input_args,
        "-map", "0:v:0", "-vf", "fps=30,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
        "-vsync", "cfr", "-an", "-threads", "2",
        "-avoid_negative_ts", "make_zero", "-movflags", "+faststart",
        str(output),
    ])
    normalized, normalized_detail = _probe_usable(output)
    if transcode_result.returncode != 0 or not normalized:
        diagnostic = "\n".join([
            "v14 stream-copy validation failed: " + probe_detail,
            transport.redact_diagnostic(remux_result.stderr[-3000:]),
            "v14 normalization validation failed: " + normalized_detail,
            transport.redact_diagnostic(transcode_result.stderr[-3000:]),
        ])
        raise RuntimeError(diagnostic)
    return output


v13._download_stream = _download_stream
v13._remux = _remux
runner.direct_bilibili_download = v13.direct_bilibili_download
runner.download_with_fallbacks = v13.download_with_fallbacks


if __name__ == "__main__":
    raise SystemExit(v13.v9.v6.main())
