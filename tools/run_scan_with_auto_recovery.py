#!/usr/bin/env python3
"""Run one queue item with deterministic recovery and bounded autonomous AI repair.

The earliest durable non-imported queue item always owns execution order. Known safe
failures use dictionary recovery first. When deterministic recovery cannot continue, the
preauthorized AI repair controller may modify only allowlisted pipeline files, run fast
safety tests, and retry the same item without asking for confirmation. Authorization,
queue scope, serial execution, and media-retention invariants remain protected.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any

from publish_runtime_progress import emit as emit_runtime_progress

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data/batch-analysis/eleven-pilot-orchestration-report.json"
RECOVERY_PATH = ROOT / "data/batch-analysis/eleven-pilot-recovery-report.json"
AUTO_REPAIR_PATH = ROOT / "data/batch-analysis/scan-autonomous-repair-report.json"
DICTIONARY_PATH = ROOT / "data/scan-bug-dictionary.json"
AUTONOMY_POLICY_PATH = ROOT / "data/scan-autonomy-policy.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: pathlib.Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def safe_output(value: str) -> str:
    text = str(value or "").replace("\x00", "")
    text = re.sub(r"https?://\S+", "[url-redacted]", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)(authorization|cookie|token|secret)\s*[:=]\s*\S+", r"\1=[redacted]", text)
    text = re.sub(r"/tmp/\S+", "[temporary-path-redacted]", text)
    return text[-3000:]


def run(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def item_job(item: dict[str, Any]) -> dict[str, Any]:
    page = int(item.get("page") or item.get("sequence") or 0)
    return load(ROOT / f"data/analysis-jobs/eleven-p{page:03d}.json", {})


def recovery_job(queue: dict[str, Any], recovery: dict[str, Any]) -> dict[str, Any]:
    external_id = recovery.get("activeExternalSourceId") or recovery.get("targetExternalSourceId")
    item = next((entry for entry in queue.get("items", []) if entry.get("externalSourceId") == external_id), None)
    return item_job(item) if item else {}


def publish_recovery(queue: dict[str, Any], recovery: dict[str, Any], *, terminal: bool = False) -> None:
    job = recovery_job(queue, recovery)
    if not job:
        return
    action = str(recovery.get("action") or recovery.get("outcome") or "none")
    entry = str(recovery.get("dictionaryEntryId") or recovery.get("category") or "autonomous-repair")
    delay = max(0, int(recovery.get("retryDelaySeconds") or 0))
    if terminal:
        state = "blocked"
        message = f"自动调查完成：{entry}；安全边界阻止继续修改，问题保持可见"
    elif recovery.get("outcome") == "repaired":
        state = "recovery"
        message = "AI自动修复已通过快速质量门禁；正在重试当前导入项"
    else:
        state = "recovery"
        suffix = f"，{delay}秒安全冷却后重试" if delay else "，立即重新尝试"
        message = f"自动调查完成：{entry}；执行 {action}{suffix}"
    emit_runtime_progress(
        job,
        stage="recovery",
        progress_percent=2,
        message=message,
        sampled_frames=0,
        target_frames=int(job.get("maxSamples") or 1),
        state=state,
        force=True,
    )


def clear_stale_recovery(queue: dict[str, Any]) -> None:
    recovery = load(RECOVERY_PATH, {})
    external_id = recovery.get("activeExternalSourceId")
    item = next((entry for entry in queue.get("items", []) if entry.get("externalSourceId") == external_id), None)
    if not item or item.get("state") != "imported":
        return
    dictionary = load(DICTIONARY_PATH, {})
    write(RECOVERY_PATH, {
        "schemaVersion": 6,
        "generatedAt": now(),
        "dictionaryVersion": dictionary.get("version"),
        "dictionaryEntryId": "runtime-heartbeat-terminal-stale",
        "manifest": recovery.get("manifest", "data/batch-analysis/eleven-pilot-scan-manifest.json"),
        "activeExternalSourceId": external_id,
        "category": "resolved",
        "matchedSignature": recovery.get("matchedSignature", "durable import confirmed"),
        "diagnosis": "Durable queue state confirms that the previously failed item was imported successfully.",
        "action": "none",
        "retryScheduled": False,
        "retryDelaySeconds": 0,
        "requiresHumanReview": False,
        "attemptCount": int(item.get("attemptCount", 0)),
        "maxAttempts": int(recovery.get("maxAttempts", 3)),
        "changedRuntimeSettings": {},
        "resolution": "durable_import_confirmed",
        "safety": {
            "sourceCodeModified": False,
            "authorizationBroadened": False,
            "mediaRetentionChanged": False,
            "queueScopeExpanded": False,
        },
    })


def publish_durable_projection(queue: dict[str, Any]) -> None:
    items = queue.get("items", [])
    pending = next((entry for entry in items if entry.get("state", "pending") in {"pending", "queued", "failed"}), None)
    if pending:
        job = item_job(pending)
        if job:
            page = pending.get("page") or pending.get("sequence") or "—"
            emit_runtime_progress(
                job,
                stage="queued",
                progress_percent=0,
                message=f"上一任务已持久化；P{page} 已排队，等待下一工作流领取",
                sampled_frames=0,
                target_frames=int(job.get("maxSamples") or 1),
                state="queued",
                force=True,
            )
        return
    imported = [entry for entry in items if entry.get("state") == "imported"]
    if imported:
        job = item_job(imported[-1])
        if job:
            emit_runtime_progress(
                job,
                stage="complete",
                progress_percent=100,
                message="当前有界批次已全部完成并持久化",
                sampled_frames=int(job.get("maxSamples") or 0),
                target_frames=int(job.get("maxSamples") or 1),
                state="complete",
                force=True,
            )


def earliest_unresolved(queue: dict[str, Any]) -> dict[str, Any] | None:
    return next((item for item in queue.get("items", []) if item.get("state", "pending") != "imported"), None)


def invoke_autonomous_repair(manifest_arg: str, queue: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    policy = load(AUTONOMY_POLICY_PATH, {})
    if not policy.get("enabled") or not policy.get("execution", {}).get("allowAiSourcePatch"):
        return False, {"outcome": "disabled"}
    head = earliest_unresolved(queue)
    if not head:
        return False, {"outcome": "no_unresolved_item"}
    maximum_passes = int(policy.get("execution", {}).get("maximumAiRepairPassesPerItem", 2))
    if int(head.get("autonomousRepairPasses", 0)) >= maximum_passes:
        return False, {"outcome": "repair_pass_limit"}
    hard_minutes = max(1, min(10, int(policy.get("timeBudget", {}).get("hardMaximumMinutes", 10))))
    result = run([sys.executable, "tools/scan_autonomous_repair.py", manifest_arg, "--repair-only"], hard_minutes * 60)
    report = load(AUTO_REPAIR_PATH, {"outcome": "missing_report"})
    report["controllerReturnCode"] = result.returncode
    report["controllerOutput"] = safe_output(result.stdout + "\n" + result.stderr)
    repaired = result.returncode == 0 and report.get("outcome") == "repaired"
    if repaired:
        queue_after = load(ROOT / load((ROOT / manifest_arg).resolve())["queue"], queue)
        publish_recovery(queue_after, report)
    return repaired, report


def preflight_failed_head(manifest_arg: str, queue_path: pathlib.Path) -> tuple[bool, str, dict[str, Any]]:
    """Diagnose and, when necessary, autonomously repair the earliest failed item."""
    queue = load(queue_path, {"items": []})
    head = earliest_unresolved(queue)
    if not head or head.get("state") != "failed":
        return True, "none", {}

    diagnosis = run([sys.executable, "tools/diagnose_and_recover_scan_v2.py", manifest_arg], 180)
    recovery = load(RECOVERY_PATH, {})
    queue = load(queue_path, queue)
    if recovery.get("activeExternalSourceId") != head.get("externalSourceId"):
        return False, "diagnosis_target_mismatch", recovery

    if not recovery.get("retryScheduled"):
        repaired, auto_report = invoke_autonomous_repair(manifest_arg, queue)
        if repaired:
            return True, "autonomous_repair_ready", auto_report
        publish_recovery(queue, recovery, terminal=True)
        state = "protected_failure" if recovery.get("action") == "protected_failure" else "unrecoverable"
        return False, state, {**recovery, "autonomousRepair": auto_report}

    publish_recovery(queue, recovery)
    delay = min(900, max(0, int(recovery.get("retryDelaySeconds") or 0)))
    if delay:
        print(f"safe preflight recovery cooldown: {delay} seconds", flush=True)
        time.sleep(delay)
    return diagnosis.returncode == 0, "retry_prepared", recovery


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: run_scan_with_auto_recovery.py MANIFEST_JSON", file=sys.stderr)
        return 2

    manifest_arg = sys.argv[1]
    manifest_path = (ROOT / manifest_arg).resolve()
    initial_manifest = load(manifest_path)
    queue_path = ROOT / initial_manifest["queue"]
    configured_attempts = max(1, int(initial_manifest.get("recoveryPolicy", {}).get("maxAttemptsPerItem", 3)))
    autonomy = load(AUTONOMY_POLICY_PATH, {})
    extra_repair_cycles = int(autonomy.get("execution", {}).get("maximumAiRepairPassesPerItem", 0)) if autonomy.get("enabled") else 0
    max_cycles = min(5, configured_attempts + extra_repair_cycles)
    cycles: list[dict[str, Any]] = []
    final_state = "unknown"

    for cycle in range(1, max_cycles + 1):
        prepared, preflight_state, preflight = preflight_failed_head(manifest_arg, queue_path)
        if not prepared:
            cycles.append({
                "cycle": cycle,
                "startedAt": now(),
                "finishedAt": now(),
                "preflightState": preflight_state,
                "dictionaryEntryId": preflight.get("dictionaryEntryId"),
                "action": preflight.get("action"),
                "retryScheduled": preflight.get("retryScheduled"),
                "requiresHumanReview": preflight.get("requiresHumanReview"),
                "autonomousRepair": preflight.get("autonomousRepair"),
            })
            final_state = preflight_state
            break

        manifest = load(manifest_path)
        started = now()
        timeout = int(manifest.get("perItemTimeoutSeconds", 5400)) + 300
        scanner = run([sys.executable, "tools/scan_catalog_queue_v2.py", manifest_arg], timeout)
        queue = load(queue_path, {"items": []})
        failed = [item for item in queue.get("items", []) if item.get("state") == "failed"]
        imported = sum(item.get("state") == "imported" for item in queue.get("items", []))
        running = sum(item.get("state") == "running" for item in queue.get("items", []))
        cycle_report: dict[str, Any] = {
            "cycle": cycle,
            "startedAt": started,
            "finishedAt": now(),
            "preflightState": preflight_state,
            "preflightDictionaryEntryId": preflight.get("dictionaryEntryId"),
            "preflightAutonomousOutcome": preflight.get("outcome"),
            "scannerReturnCode": scanner.returncode,
            "scannerTimeoutSeconds": timeout,
            "imported": imported,
            "failed": len(failed),
            "running": running,
            "scannerOutput": safe_output(scanner.stdout + "\n" + scanner.stderr),
        }

        if not failed:
            clear_stale_recovery(queue)
            publish_durable_projection(queue)
            final_state = "scan_completed_or_progressed"
            cycles.append(cycle_report)
            break

        diagnosis = run([sys.executable, "tools/diagnose_and_recover_scan_v2.py", manifest_arg], 180)
        recovery = load(RECOVERY_PATH, {})
        queue = load(queue_path, queue)
        cycle_report["diagnosisReturnCode"] = diagnosis.returncode
        cycle_report["dictionaryEntryId"] = recovery.get("dictionaryEntryId")
        cycle_report["action"] = recovery.get("action")
        cycle_report["retryScheduled"] = recovery.get("retryScheduled")
        cycle_report["requiresHumanReview"] = recovery.get("requiresHumanReview")

        if not recovery.get("retryScheduled"):
            repaired, auto_report = invoke_autonomous_repair(manifest_arg, queue)
            cycle_report["autonomousRepair"] = auto_report
            cycles.append(cycle_report)
            if repaired:
                final_state = "autonomous_repair_retrying"
                continue
            publish_recovery(queue, recovery, terminal=True)
            final_state = "protected_failure" if recovery.get("action") == "protected_failure" else "unrecoverable"
            break

        cycles.append(cycle_report)
        publish_recovery(queue, recovery)
        delay = min(900, max(0, int(recovery.get("retryDelaySeconds") or 0)))
        if delay:
            print(f"safe recovery cooldown: {delay} seconds", flush=True)
            time.sleep(delay)
        final_state = "retrying"
    else:
        final_state = "attempt_limit_reached"

    source_modified = any((entry.get("autonomousRepair") or {}).get("outcome") == "repaired" for entry in cycles)
    report = {
        "schemaVersion": 4,
        "generatedAt": now(),
        "manifest": manifest_arg,
        "dictionary": "data/scan-bug-dictionary.json",
        "autonomyPolicy": "data/scan-autonomy-policy.json",
        "finalState": final_state,
        "cycles": cycles,
        "performance": {
            "targetRepairMinutes": int(autonomy.get("timeBudget", {}).get("targetMinutes", 5)),
            "maximumRepairMinutes": int(autonomy.get("timeBudget", {}).get("hardMaximumMinutes", 10)),
            "deterministicRecoveryFirst": True,
        },
        "safety": {
            "maximumCycles": max_cycles,
            "strictEarliestUnresolvedOrder": True,
            "sourceCodeModifiedAutomatically": source_modified,
            "authorizationBroadened": False,
            "mediaRetentionChanged": False,
            "queueScopeExpanded": False,
            "confirmationRequired": False,
        },
    }
    write(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False))
    failure_states = {"protected_failure", "unrecoverable", "attempt_limit_reached", "diagnosis_target_mismatch"}
    return 1 if final_state in failure_states else 0


if __name__ == "__main__":
    raise SystemExit(main())
