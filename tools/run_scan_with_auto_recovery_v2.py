#!/usr/bin/env python3
"""Run persistent technical recovery with telemetry preservation and strict serial order."""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

import run_scan_with_auto_recovery as base
from publish_runtime_progress_v2 import emit

base.emit_runtime_progress = emit
_original_run = base.run
_original_invoke_autonomous_repair = base.invoke_autonomous_repair
REQUIRED_QUEUE_FIELDS = (
    "externalSourceId", "sequence", "page", "title", "url", "bvid", "cid",
    "durationSeconds", "scanClass", "mapUtility", "priority", "partTitle",
)


def _write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    temporary = pathlib.Path(str(path) + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def invoke_autonomous_repair(manifest_arg: str, queue: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Keep invoking bounded AI repair for technical failures until one patch passes.

    Each individual patch remains restricted by the allowlist, changed-file/line budgets,
    validation tests, authorization scope, serial queue order and transient-media policy.
    Authorization, identity, privacy, retention or queue-scope failures still stop.
    """
    policy = base.load(base.AUTONOMY_POLICY_PATH, {})
    execution = policy.get("execution", {})
    if not execution.get("retryUntilResolvedForTechnicalFailures"):
        return _original_invoke_autonomous_repair(manifest_arg, queue)
    if not policy.get("enabled") or not execution.get("allowAiSourcePatch"):
        return False, {"outcome": "disabled"}
    head = base.earliest_unresolved(queue)
    if not head:
        return False, {"outcome": "no_unresolved_item"}

    hard_minutes = max(1, min(10, int(policy.get("timeBudget", {}).get("hardMaximumMinutes", 10))))
    result = base.run(
        [sys.executable, "tools/scan_autonomous_repair.py", manifest_arg, "--repair-only"],
        hard_minutes * 60,
    )
    report = base.load(base.AUTO_REPAIR_PATH, {"outcome": "missing_report"})
    report["controllerReturnCode"] = result.returncode
    report["controllerOutput"] = base.safe_output(result.stdout + "\n" + result.stderr)
    report["persistentTechnicalRetry"] = True
    report["repairPassesCompleted"] = int(head.get("autonomousRepairPasses", 0))
    report["configuredRepairPasses"] = int(execution.get("maximumAiRepairPassesPerItem", 20))
    repaired = result.returncode == 0 and report.get("outcome") == "repaired"
    if repaired:
        manifest = base.load((base.ROOT / manifest_arg).resolve(), {})
        queue_after = base.load(base.ROOT / manifest["queue"], queue)
        base.publish_recovery(queue_after, report)
    base.write(base.AUTO_REPAIR_PATH, report)
    return repaired, report


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


def _heartbeat_retryable(item: dict[str, Any]) -> bool:
    """Return true only for the stale-heartbeat failure written by the supervisor."""
    error = str(item.get("error") or "").lower()
    action = str(item.get("lastRecoveryAction") or "")
    return (
        error.startswith("heartbeat supervisor: no heartbeat for")
        or action in {
            "reset_lease_and_retry",
            "reset_stale_lease_and_retry",
            "resume_pending_item",
            "publish_terminal_projection_and_resume_pending",
        }
    )


def normalize_queue(queue: dict[str, Any]) -> bool:
    """Make only the earliest safe non-imported item claimable."""
    items = queue.get("items", [])
    if any(item.get("state") in {"running", "recovery"} for item in items):
        return False
    for item in items:
        state = item.get("state", "pending")
        if state == "imported":
            continue
        if state == "queued" or (state == "failed" and _heartbeat_retryable(item)):
            item["state"] = "pending"
            item.pop("error", None)
            item.pop("lastFinishedAt", None)
            queue["status"] = "recovery_scheduled" if state == "failed" else "queued"
            queue.pop("activeExternalSourceId", None)
            return True
        return False
    return False


def synchronize_terminal_authority(queue: dict[str, Any], manifest: dict[str, Any]) -> bool:
    """Keep durable authority metadata aligned with the actual bounded queue state."""
    items = queue.get("items", [])
    complete = bool(items) and all(item.get("state") == "imported" for item in items)
    authority = queue.setdefault("authority", {})
    changed = False
    expected_batch = manifest.get("id") or queue.get("queueId")
    expected = {
        "owner": "data/batch-analysis/eleven-pilot-scan-status.json",
        "batchId": expected_batch,
        "terminal": complete,
        "protectFromCatalogRegeneration": True,
    }
    for key, value in expected.items():
        if authority.get(key) != value:
            authority[key] = value
            changed = True
    expected_status = "complete" if complete else queue.get("status")
    if queue.get("status") != expected_status:
        queue["status"] = expected_status
        changed = True
    if complete and "activeExternalSourceId" in queue:
        queue.pop("activeExternalSourceId", None)
        changed = True
    return changed


def prepare_queue(manifest_arg: str) -> bool:
    """Hydrate queue metadata, synchronize authority, and make one item claimable."""
    manifest_path = (base.ROOT / manifest_arg).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    queue_path = base.ROOT / manifest["queue"]
    catalog_path = base.ROOT / manifest["catalog"]
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    changed = hydrate_queue_from_catalog(queue, catalog)
    changed = synchronize_terminal_authority(queue, manifest) or changed
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
            if str(manifest.get("analyzer", "")).endswith((
                "analyze_authorized_video_v11.py",
                "analyze_authorized_video_v12.py",
                "analyze_authorized_video_v13.py",
            )):
                manifest["analyzer"] = "tools/analyze_authorized_video_v14.py"
                manifest.setdefault("compatibilityFixes", {})["preserveDownloadTelemetryAcrossStages"] = True
                manifest["compatibilityFixes"]["wbiSignedPlayerMetadata"] = True
                manifest["compatibilityFixes"]["apiProvidedCdnRotation"] = True
                manifest["compatibilityFixes"]["generatedTimestampRecovery"] = True
                manifest["compatibilityFixes"]["pixelFormatNormalization"] = True
                _write_json(path, manifest)
        except Exception:
            pass
    return result


base.run = run
base.invoke_autonomous_repair = invoke_autonomous_repair

if __name__ == "__main__":
    if len(sys.argv) > 1:
        prepare_queue(sys.argv[1])
    raise SystemExit(base.main())
