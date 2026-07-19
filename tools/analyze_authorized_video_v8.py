#!/usr/bin/env python3
"""Enforce one public download heartbeat at least every 60 seconds."""
from __future__ import annotations

import time

import analyze_authorized_video_v7 as v7

_original_emit_download = v7._emit_download
_last_forced_at = 0.0


def emit_download_every_minute(*args, force: bool = False, **kwargs):
    global _last_forced_at
    now = time.monotonic()
    minute_due = _last_forced_at == 0.0 or now - _last_forced_at >= 60.0
    effective_force = force or minute_due
    result = _original_emit_download(*args, force=effective_force, **kwargs)
    if effective_force:
        _last_forced_at = now
    return result


v7._emit_download = emit_download_every_minute


if __name__ == "__main__":
    raise SystemExit(v7.v6.main())
