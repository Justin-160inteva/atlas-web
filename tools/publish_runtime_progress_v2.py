#!/usr/bin/env python3
"""Compatibility wrapper that preserves the last measured download telemetry.

Recovery, remux, analysis, indexing, cleanup, and persistence heartbeats keep the last
sanitized byte/speed snapshot for the same source item. This prevents the monitor from
showing 0 MB after download has already progressed.
"""
from __future__ import annotations

import json
from typing import Any

import publish_runtime_progress as base

PRESERVE_STAGES = {"recovery", "remuxing", "analysis", "indexing", "cleanup", "persisting"}
METRIC_KEYS = {
    "downloadedBytes", "totalBytes", "segmentDownloadedBytes", "segmentTotalBytes",
    "segmentIndex", "segmentCount", "speedBytesPerSecond", "averageSpeedBytesPerSecond",
    "etaSeconds", "downloadElapsedSeconds", "speedWindowSeconds", "stalledSeconds",
    "heartbeatSequence", "maxRangeWorkers", "transferMode",
}


def _previous(job: dict[str, Any], stage: str) -> tuple[dict[str, Any], str | None]:
    if stage not in PRESERVE_STAGES:
        return {}, None
    path = base._local_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}, None
    if value.get("externalSourceId") != job.get("externalSourceId"):
        return {}, None
    if int(value.get("totalBytes") or 0) <= 0:
        return {}, None
    metrics = {key: value[key] for key in METRIC_KEYS if key in value}
    measured_at = value.get("telemetryMeasuredAt") or value.get("updatedAt")
    return metrics, measured_at


def emit(job: dict[str, Any], *, stage: str, progress_percent: float, message: str,
         processed_seconds: float = 0, sampled_frames: int = 0,
         target_frames: int | None = None, state: str = "running",
         metrics: dict[str, Any] | None = None, force: bool = False) -> dict[str, Any]:
    preserved, measured_at = _previous(job, stage)
    merged = dict(preserved)
    merged.update(metrics or {})
    payload = base.emit(
        job,
        stage=stage,
        progress_percent=progress_percent,
        message=message,
        processed_seconds=processed_seconds,
        sampled_frames=sampled_frames,
        target_frames=target_frames,
        state=state,
        metrics=merged or None,
        force=force,
    )
    if preserved and measured_at:
        payload["telemetryMeasuredAt"] = measured_at
        payload["telemetryPreserved"] = True
        base._write_local(payload)
        try:
            base._publish_github(payload)
        except Exception:
            pass
    return payload
