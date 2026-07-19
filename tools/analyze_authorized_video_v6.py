#!/usr/bin/env python3
"""Wrap the resilient multipart analyzer with truthful public progress heartbeats.

The wrapper publishes only sanitized task state. It does not expose cookies, media URLs,
local paths, video bytes, or frame pixels, and heartbeat failures never stop analysis.
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

import analyze_authorized_video_v5 as v5

try:
    from publish_runtime_progress import emit as emit_runtime_progress
except ImportError:
    def emit_runtime_progress(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: analyze_authorized_video_v6.py JOB_JSON", file=sys.stderr)
        return 2

    job_path = pathlib.Path(sys.argv[1])
    job = json.loads(job_path.read_text(encoding="utf-8"))
    output_path = pathlib.Path(job["output"])

    emit_runtime_progress(
        job,
        stage="download",
        progress_percent=2,
        message="已领取任务，正在临时下载授权视频",
        sampled_frames=0,
        target_frames=int(job.get("maxSamples") or 1),
        state="running",
        force=True,
    )

    try:
        return_code = v5.runner.main()
    except Exception:
        emit_runtime_progress(
            job,
            stage="download",
            progress_percent=2,
            message="扫描进程异常退出，正在交给自动诊断器",
            sampled_frames=0,
            target_frames=int(job.get("maxSamples") or 1),
            state="failed",
            force=True,
        )
        raise

    try:
        result = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else {}
    except Exception:
        result = {}

    if result.get("status") == "analyzed":
        scan = result.get("scan") or {}
        media = result.get("media") or {}
        emit_runtime_progress(
            job,
            stage="persisting",
            progress_percent=98,
            message="数值分析已完成，正在写入分析索引与任务状态",
            processed_seconds=float(media.get("durationSeconds") or job.get("durationHintSeconds") or 0),
            sampled_frames=int(scan.get("sampled") or 0),
            target_frames=int(job.get("maxSamples") or 1),
            state="running",
            force=True,
        )
    else:
        failure_stage = str(result.get("stage") or "download")
        emit_runtime_progress(
            job,
            stage=failure_stage,
            progress_percent=2,
            message="本轮扫描失败，正在进入受限自动诊断与恢复",
            sampled_frames=0,
            target_frames=int(job.get("maxSamples") or 1),
            state="failed",
            force=True,
        )

    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
