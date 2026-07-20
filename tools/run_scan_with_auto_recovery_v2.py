#!/usr/bin/env python3
"""Run bounded recovery with telemetry preservation, v12 normalization, and strict queue order."""
from __future__ import annotations

import json
import pathlib
import sys

import run_scan_with_auto_recovery as base
from publish_runtime_progress_v2 import emit

base.emit_runtime_progress = emit
_original_run = base.run


def _write_json(path: pathlib.Path, value: dict) -> None:
    temporary = pathlib.Path(str(path) + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def normalize_first_queued_item(manifest_arg: str) -> None:
    """Allow the scanner to claim the earliest supervisor-projected queued item.

    scan_catalog_queue_v2 historically selected only pending/failed states. The heartbeat
    supervisor correctly projects the next item as queued. Convert only the earliest
    non-imported queued item to pending immediately before scanner execution, while
    refusing to touch the queue if another item is already running or recovering.
    """
    manifest_path = (base.ROOT / manifest_arg).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    queue_path = base.ROOT / manifest["queue"]
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    items = queue.get("items", [])
    if any(item.get("state") in {"running", "recovery"} for item in items):
        return
    for item in items:
        state = item.get("state", "pending")
        if state == "imported":
            continue
        if state == "queued":
            item["state"] = "pending"
            queue["status"] = "queued"
            queue.pop("activeExternalSourceId", None)
            _write_json(queue_path, queue)
        break


def run(command: list[str], timeout: int):
    result = _original_run(command, timeout)
    if any(part.endswith("diagnose_and_recover_scan_v2.py") for part in command):
        manifest_arg = command[-1]
        path = (base.ROOT / manifest_arg).resolve()
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if str(manifest.get("analyzer", "")).endswith("analyze_authorized_video_v11.py"):
                manifest["analyzer"] = "tools/analyze_authorized_video_v12.py"
                manifest.setdefault("compatibilityFixes", {})["preserveDownloadTelemetryAcrossStages"] = True
                _write_json(path, manifest)
        except Exception:
            pass
    return result


base.run = run

if __name__ == "__main__":
    if len(sys.argv) > 1:
        normalize_first_queued_item(sys.argv[1])
    raise SystemExit(base.main())
