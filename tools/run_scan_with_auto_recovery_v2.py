#!/usr/bin/env python3
"""Run bounded recovery with telemetry preservation, v12 normalization, and strict queue order."""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

import run_scan_with_auto_recovery as base
from publish_runtime_progress_v2 import emit

base.emit_runtime_progress = emit
_original_run = base.run


def _write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    temporary = pathlib.Path(str(path) + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def normalize_queue(queue: dict[str, Any]) -> bool:
    """Convert only the earliest non-imported queued item to pending.

    Returns True when a transition was applied. No transition is allowed while any item
    is already running or recovering, which preserves the one-download-at-a-time rule.
    """
    items = queue.get("items", [])
    if any(item.get("state") in {"running", "recovery"} for item in items):
        return False
    for item in items:
        state = item.get("state", "pending")
        if state == "imported":
            continue
        if state == "queued":
            item["state"] = "pending"
            queue["status"] = "queued"
            queue.pop("activeExternalSourceId", None)
            return True
        return False
    return False


def normalize_first_queued_item(manifest_arg: str) -> bool:
    """Allow the scanner to claim the earliest supervisor-projected queued item."""
    manifest_path = (base.ROOT / manifest_arg).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    queue_path = base.ROOT / manifest["queue"]
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    changed = normalize_queue(queue)
    if changed:
        _write_json(queue_path, queue)
    return changed


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
