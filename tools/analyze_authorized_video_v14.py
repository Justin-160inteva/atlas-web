#!/usr/bin/env python3
"""Atlas v14 analyzer with byte-accurate cross-CDN resume and safe restart.

v14 keeps the authorized v13 WBI metadata/CDN path, but replaces the legacy
single-stream writer. Partial bytes are appended only after an exact Content-Range
match; ignored or zero-based range responses overwrite the residue safely. Chunk
accounting is synchronized to the durable file size and incomplete bodies remain
retryable across API-provided CDN candidates.
"""
from __future__ import annotations

import pathlib
import time
from typing import Any

import analyze_authorized_video_v13 as v13
import resumable_transport_v14 as resume_v14

v12 = v13.v12
v11 = v13.v11
v9 = v13.v9
runner = v13.runner
transport = v13.transport


def _heartbeat_update(
    heartbeat: Any,
    target: pathlib.Path,
    *,
    downloaded_before: int,
    segment_index: int,
    total_size: int,
) -> int:
    durable = target.stat().st_size if target.exists() else 0
    heartbeat.update(
        downloaded_bytes=downloaded_before + durable,
        segment_downloaded_bytes=durable,
        segment_total_bytes=max(0, int(total_size or 0)),
        segment_index=segment_index,
    )
    return durable


def _single_stream_resume_v14(
    candidate: str,
    target: pathlib.Path,
    *,
    expected_size: int,
    heartbeat: Any,
    downloaded_before: int,
    segment_index: int,
    chunk_size: int,
    retries: int,
) -> None:
    """Resume one candidate without ever appending a fresh full response to residue."""
    last_error: Exception | None = None
    for attempt in range(max(1, int(retries))):
        requested_offset = target.stat().st_size if target.exists() else 0
        headers = dict(runner.HEADERS)
        headers["Accept-Encoding"] = "identity"
        if requested_offset:
            headers["Range"] = f"bytes={requested_offset}-"

        try:
            with runner.requests.get(
                candidate,
                headers=headers,
                impersonate="chrome",
                stream=True,
                timeout=90,
            ) as response:
                response.raise_for_status()
                plan = resume_v14.plan_response_write(
                    int(getattr(response, "status_code", 0) or 0),
                    response.headers,
                    requested_offset=requested_offset,
                    expected_size=expected_size,
                )
                if plan.restarted:
                    target.unlink(missing_ok=True)

                payload_written = 0
                with target.open(plan.mode) as handle:
                    for chunk in response.iter_content(chunk_size=max(1, int(chunk_size))):
                        if not chunk:
                            continue
                        handle.write(chunk)
                        payload_written += len(chunk)
                        _heartbeat_update(
                            heartbeat,
                            target,
                            downloaded_before=downloaded_before,
                            segment_index=segment_index,
                            total_size=plan.total_size,
                        )

                final_size = _heartbeat_update(
                    heartbeat,
                    target,
                    downloaded_before=downloaded_before,
                    segment_index=segment_index,
                    total_size=plan.total_size,
                )
                resume_v14.validate_completed_transfer(
                    final_size,
                    total_size=plan.total_size,
                    payload_written=payload_written,
                    expected_payload_bytes=plan.expected_payload_bytes,
                )
                return
        except Exception as exc:
            last_error = exc
            if attempt + 1 >= max(1, int(retries)):
                raise
            time.sleep(min(6, 1 + attempt * 2))

    raise RuntimeError("v14 single-stream retry limit reached") from last_error


# v13 resolves this helper dynamically through its v11 module alias.
v11._single_stream_resume = _single_stream_resume_v14

# Keep the established signed metadata, identity, privacy and analyzer entry points.
direct_bilibili_download = v13.direct_bilibili_download
download_with_fallbacks = v13.download_with_fallbacks
runner.direct_bilibili_download = direct_bilibili_download
runner.download_with_fallbacks = download_with_fallbacks


if __name__ == "__main__":
    raise SystemExit(v9.v6.main())
