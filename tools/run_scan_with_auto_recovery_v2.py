#!/usr/bin/env python3
"""Run bounded recovery with telemetry preservation, queue hydration, and strict order."""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

import run_scan_with_auto_recovery as base
from publish_runtime_progress_v2 import emit

base.emit_runtime_progress = emit
_original_run = base.run
REQUIRED_QUEUE_FIELDS = (
    "externalSourceId", "sequence", "page", "title", "url", "bvid", "cid",
    "durationSeconds", "scanClass", "mapUtility", "priority", "partTitle",
)


def _write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    temporary = pathlib.Path(str(path) + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def hydrate_queue_from_catalog(queue: dict[str, Any], catalog: dict[str, Any]) -> bool:
    """Fill required queue metadata from the verified authorized catalog.

    The queue scope and ordering are never expanded or changed. Unknown IDs or fields that
    remain missing after hydration stop execution before any media transfer begins.
    """
    catalog_by_id = {item.get("id"): item for item in catalog.get("items", []) if item.get("id")}
    changed = False
    for item in queue.get("items", []):
        external_id = item.get("externalSourceId")
        source = catalog_by_id.get(external_id)
        if not source:
            raise KeyError(f"catalog entry missing for queue item {external_id!r}")
        for field in REQUIRED_QUEUE_FIELDS:
            if item.get(field) in (None, "") and source.get(field) not in (None, ""):
                item[field] = source[field]
                changed = True
        missing = [field for field in REQUIRED_QUEUE_FIELDS if item.get(field) in (None, "")]
        if missing:
            raise KeyError(f"queue item {external_id!r} missing required fields after catalog hydration: {missing}")
    return changed


def normalize_queue(queue: dict[str, Any]) -> bool:
    """Convert only the earliest non-imported queued item to pending."""
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


def prepare_queue(manifest_arg: str) -> bool:
    """Hydrate queue metadata and make the earliest queued item claimable."""
    manifest_path = (base.ROOT / manifest_arg).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    queue_path = base.ROOT / manifest["queue"]
    catalog_path = base.ROOT / manifest["catalog"]
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    changed = hydrate_queue_from_catalog(queue, catalog)
    changed = normalize_queue(queue) or changed
    if changed:
        _write_json(queue_path, queue)
    return changed


def normalize_first_queued_item(manifest_arg: str) -> bool:
    """Compatibility alias retained for ordering tests and older callers."""
    return prepare_queue(manifest_arg)


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
        prepare_queue(sys.argv[1])
    raise SystemExit(base.main())
