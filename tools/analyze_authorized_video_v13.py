#!/usr/bin/env python3
"""Atlas v13 analyzer with signed metadata and resumable CDN rotation.

v13 bypasses the rate-limited public video webpage.  It verifies the BVID/page/CID
already stored in the authorized queue, requests WBI-signed player metadata, chooses a
bounded analysis-quality DASH stream, and resumes partial bytes across API-provided CDN
backups.  Legacy progressive metadata is retained only as a final direct-API fallback.
Original media and frame pixels remain transient.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import time
import urllib.parse
from typing import Any

import analyze_authorized_video_v12 as v12
import bilibili_transport_v13 as transport


v11 = v12.v11
v9 = v11.v9
runner = v11.runner
MIB = v11.MIB


def _settings() -> dict[str, Any]:
    return v11._settings()


def _job() -> dict[str, Any]:
    return v11._job()


def _api_get_json(url: str) -> dict[str, Any]:
    with runner.requests.get(
        url,
        headers=runner.HEADERS,
        impersonate="chrome",
        timeout=30,
    ) as response:
        response.raise_for_status()
        payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(
            f"Bilibili API code={payload.get('code')} message={payload.get('message')}"
        )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("Bilibili API returned no data object")
    return data


def _wbi_play_metadata(bvid: str, cid: int, *, refresh_index: int) -> dict[str, Any]:
    nav = _api_get_json("https://api.bilibili.com/x/web-interface/nav")
    mixin_key = transport.extract_mixin_key(nav)
    params: dict[str, Any] = {
        "bvid": bvid,
        "cid": cid,
        "qn": 32,
        "fnval": 4048,
        "fourk": 0,
        "try_look": 1,
        **transport.fingerprint_params(f"{bvid}:{cid}:{refresh_index}:{time.time_ns()}"),
    }
    endpoint = transport.signed_url(
        "https://api.bilibili.com/x/player/wbi/playurl",
        params,
        mixin_key,
    )
    return _api_get_json(endpoint)


def _legacy_play_metadata(bvid: str, cid: int) -> dict[str, Any]:
    query = urllib.parse.urlencode({
        "bvid": bvid,
        "cid": cid,
        "qn": 32,
        "fnver": 0,
        "fnval": 0,
        "fourk": 0,
    })
    return _api_get_json(f"https://api.bilibili.com/x/player/playurl?{query}")


def _download_stream(
    stream: dict[str, Any],
    target: pathlib.Path,
    *,
    heartbeat: v9.DownloadHeartbeat,
    downloaded_before: int,
    segment_index: int,
    settings: dict[str, Any],
) -> tuple[int, list[str]]:
    declared = max(0, int(stream.get("declaredSize") or 0))
    if declared and target.exists() and target.stat().st_size == declared and declared >= 1024:
        return declared, []
    if declared and target.exists() and target.stat().st_size > declared:
        target.unlink(missing_ok=True)

    workers = max(2, min(8, int(settings.get("maxRangeWorkers", 4))))
    threshold = max(8 * MIB, int(settings.get("parallelRangeThresholdBytes", 24 * MIB)))
    chunk_size = max(MIB, min(8 * MIB, int(settings.get("chunkSizeBytes", 4 * MIB))))
    retries = max(1, min(4, int(settings.get("rangeRetriesPerCdn", 2))))
    diagnostics: list[str] = []

    for candidate_index, candidate in enumerate(stream.get("candidates") or [], start=1):
        range_ok = False
        actual_size = declared
        try:
            range_ok, probed_size = v11._range_probe(str(candidate), declared)
            if probed_size:
                actual_size = probed_size
                declared = probed_size
        except Exception as exc:
            diagnostics.append(
                f"cdn-{candidate_index}-probe:{transport.redact_diagnostic(type(exc).__name__ + ':' + str(exc))}"
            )

        existing = target.stat().st_size if target.exists() else 0
        heartbeat.update(
            downloaded_bytes=downloaded_before + existing,
            segment_downloaded_bytes=existing,
            segment_total_bytes=actual_size,
            segment_index=segment_index,
        )

        try:
            if (
                range_ok
                and existing == 0
                and actual_size >= threshold
                and settings.get("adaptiveParallelRanges", True)
            ):
                try:
                    v11._parallel_range_download(
                        str(candidate),
                        target,
                        total_size=actual_size,
                        heartbeat=heartbeat,
                        downloaded_before=downloaded_before,
                        segment_index=segment_index,
                        workers=workers,
                        chunk_size=chunk_size,
                        retries=retries,
                    )
                except Exception as exc:
                    diagnostics.append(
                        f"cdn-{candidate_index}-range:{transport.redact_diagnostic(type(exc).__name__ + ':' + str(exc))}"
                    )
                    target.unlink(missing_ok=True)
                    v11._single_stream_resume(
                        str(candidate),
                        target,
                        expected_size=actual_size,
                        heartbeat=heartbeat,
                        downloaded_before=downloaded_before,
                        segment_index=segment_index,
                        chunk_size=chunk_size,
                        retries=retries,
                    )
            else:
                v11._single_stream_resume(
                    str(candidate),
                    target,
                    expected_size=actual_size,
                    heartbeat=heartbeat,
                    downloaded_before=downloaded_before,
                    segment_index=segment_index,
                    chunk_size=chunk_size,
                    retries=retries,
                )

            size = target.stat().st_size if target.exists() else 0
            if size < 1024:
                raise RuntimeError("Downloaded media stream is unexpectedly small")
            if actual_size and size != actual_size:
                raise RuntimeError("content-length mismatch after CDN failover")
            return size, diagnostics
        except Exception as exc:
            # Keep a valid partial target. The next API-provided CDN can resume it.
            diagnostics.append(
                f"cdn-{candidate_index}-transfer:{transport.redact_diagnostic(type(exc).__name__ + ':' + str(exc))}"
            )

    raise RuntimeError("all API-provided CDN candidates failed: " + " | ".join(diagnostics[-8:]))


def _download_plan(
    plan: dict[str, Any],
    workdir: pathlib.Path,
    *,
    page_number: int,
    settings: dict[str, Any],
) -> tuple[list[pathlib.Path], int, float]:
    streams = plan.get("streams") or []
    declared_sizes = [max(0, int(stream.get("declaredSize") or 0)) for stream in streams]
    heartbeat_seconds = max(20, min(60, int(settings.get("heartbeatSeconds", 30))))
    v9.HEARTBEAT_SECONDS = float(heartbeat_seconds)
    v9.SPEED_WINDOW_SECONDS = float(max(30, int(settings.get("speedWindowSeconds", 60))))
    heartbeat = v9.DownloadHeartbeat(_job(), total_bytes=sum(declared_sizes), segment_count=len(streams))
    heartbeat.start()
    downloaded_total = 0
    paths: list[pathlib.Path] = []

    try:
        for zero_index, stream in enumerate(streams):
            extension = str(stream.get("extension") or "media")
            target = workdir / f"p{page_number:03d}-v13-part-{zero_index:03d}.{extension}"
            size, _diagnostics = _download_stream(
                stream,
                target,
                heartbeat=heartbeat,
                downloaded_before=downloaded_total,
                segment_index=zero_index + 1,
                settings=settings,
            )
            downloaded_total += size
            declared_sizes[zero_index] = max(declared_sizes[zero_index], size)
            paths.append(target)
            heartbeat.update(
                downloaded_bytes=downloaded_total,
                total_bytes=max(sum(declared_sizes), downloaded_total),
                segment_downloaded_bytes=size,
                segment_total_bytes=size,
                segment_index=zero_index + 1,
            )
            heartbeat.publish(force=True)
    finally:
        heartbeat.stop()
    return paths, downloaded_total, max(0.001, time.monotonic() - heartbeat.started_at)


def _remux(
    paths: list[pathlib.Path],
    workdir: pathlib.Path,
    *,
    page_number: int,
) -> pathlib.Path:
    output = workdir / f"source-p{page_number:03d}-v13.mp4"
    output.unlink(missing_ok=True)
    if len(paths) == 1:
        command = ["ffmpeg", "-y", "-i", str(paths[0]), "-map", "0:v:0", "-c", "copy", str(output)]
    else:
        concat_file = workdir / "v13-parts.txt"
        concat_file.write_text(
            "".join(f"file '{path.as_posix()}'\n" for path in paths),
            encoding="utf-8",
        )
        command = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-map", "0:v:0", "-c", "copy", str(output),
        ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not output.exists() or output.stat().st_size < 1024:
        raise RuntimeError(transport.redact_diagnostic(result.stderr or "ffmpeg remux failed"))
    return output


def direct_bilibili_download(url: str, workdir: pathlib.Path) -> pathlib.Path:
    job = _job()
    settings = _settings()
    bvid, page_number, cid = transport.validate_job_identity(job, url)
    runner.HEADERS["Referer"] = f"https://www.bilibili.com/video/{bvid}"
    max_height = max(240, min(720, int(settings.get("analysisVideoMaxHeight", 480))))
    prefer_backups = bool(settings.get("preferBackupUrlOnRepeated412", True))
    refresh_passes = max(1, min(3, int(settings.get("metadataRefreshPasses", 2))))
    routes: list[tuple[str, Any]] = [
        (f"wbi-signed-dash-refresh-{index + 1}", lambda index=index: _wbi_play_metadata(bvid, cid, refresh_index=index))
        for index in range(refresh_passes)
    ]
    if settings.get("allowLegacyProgressiveFallback", True):
        routes.append(("legacy-progressive-api", lambda: _legacy_play_metadata(bvid, cid)))

    failures: list[str] = []
    for route_name, metadata_loader in routes:
        try:
            play = metadata_loader()
            plan = transport.build_media_plan(
                play,
                max_height=max_height,
                prefer_backups=prefer_backups,
            )
            paths, downloaded_total, elapsed = _download_plan(
                plan,
                workdir,
                page_number=page_number,
                settings=settings,
            )
            v9.emit_runtime_progress(
                job,
                stage="remuxing",
                progress_percent=8,
                message=f"新传输路径下载完成，共 {downloaded_total / MIB:.1f} MB，正在媒体转封装",
                metrics={
                    "downloadedBytes": downloaded_total,
                    "totalBytes": downloaded_total,
                    "segmentIndex": len(paths),
                    "segmentCount": len(paths),
                    "speedBytesPerSecond": downloaded_total / elapsed,
                    "averageSpeedBytesPerSecond": downloaded_total / elapsed,
                    "downloadElapsedSeconds": elapsed,
                    "stalledSeconds": 0,
                    "transferMode": "wbi-signed-cdn-rotation-resume",
                    "metadataRoute": route_name,
                    "maxRangeWorkers": max(2, min(8, int(settings.get("maxRangeWorkers", 4)))),
                },
                force=True,
            )
            return _remux(paths, workdir, page_number=page_number)
        except Exception as exc:
            failures.append(
                f"{route_name}:{transport.redact_diagnostic(type(exc).__name__ + ':' + str(exc))}"
            )

    raise RuntimeError("v13 metadata/CDN routes exhausted: " + " | ".join(failures[-6:]))


def download_with_fallbacks(
    url: str,
    workdir: pathlib.Path,
) -> tuple[pathlib.Path, list[dict[str, Any]]]:
    """Use direct API routes only; do not re-enter the HTTP-412 webpage extractor."""
    try:
        path = direct_bilibili_download(url, workdir)
        return path, [{
            "strategy": "wbi-signed-api-cdn-rotation",
            "success": True,
            "diagnostic": "verified CID + signed play metadata + resumable CDN failover",
        }]
    except Exception as exc:
        attempts = [{
            "strategy": "wbi-signed-api-cdn-rotation",
            "success": False,
            "diagnostic": transport.redact_diagnostic(type(exc).__name__ + ":" + str(exc)),
        }]
        raise RuntimeError(json.dumps(attempts, ensure_ascii=False)) from None


runner.direct_bilibili_download = direct_bilibili_download
runner.download_with_fallbacks = download_with_fallbacks


if __name__ == "__main__":
    raise SystemExit(v9.v6.main())
