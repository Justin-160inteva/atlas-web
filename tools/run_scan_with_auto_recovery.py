#!/usr/bin/env python3
"""Run one queue item with immediate dictionary-driven investigation and retry.

A failure is diagnosed in the same GitHub Actions job. Safe deterministic failures are
retried after their prescribed cooldown; unsafe or unknown failures stop for review.
Recovery decisions are published immediately as sanitized runtime progress.
"""
from __future__ import annotations

import json
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
    text = re.sub(r"(?i)(authorization|cookie|token)\s*[:=]\s*\S+", r"\1=[redacted]", text)
    text = re.sub(r"/tmp/\S+", "[temporary-path-redacted]", text)
    return text[-3000:]


def run(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def recovery_job(queue: dict[str, Any], recovery: dict[str, Any]) -> dict[str, Any]:
    external_id = recovery.get("activeExternalSourceId")
    item = next((entry for entry in queue.get("items", []) if entry.get("externalSourceId") == external_id), None)
    if not item:
        return {}
    page = int(item.get("page") or item.get("sequence") or 0)
    return load(ROOT / f"data/analysis-jobs/eleven-p{page:03d}.json", {})


def publish_recovery(queue: dict[str, Any], recovery: dict[str, Any], *, terminal: bool = False) -> None:
    job = recovery_job(queue, recovery)
    if not job:
        return
    action = str(recovery.get("action") or "none")
    entry = str(recovery.get("dictionaryEntryId") or recovery.get("category") or "unknown")
    delay = max(0, int(recovery.get("retryDelaySeconds") or 0))
    if terminal:
        state = "blocked"
        message = f"自动调查完成：{entry}；该问题不允许自动修复，已停止并等待人工检查"
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


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: run_scan_with_auto_recovery.py MANIFEST_JSON", file=sys.stderr)
        return 2

    manifest_arg = sys.argv[1]
    manifest_path = (ROOT / manifest_arg).resolve()
    initial_manifest = load(manifest_path)
    queue_path = ROOT / initial_manifest["queue"]
    max_attempts = max(1, int(initial_manifest.get("recoveryPolicy", {}).get("maxAttemptsPerItem", 3)))
    cycles: list[dict[str, Any]] = []
    final_state = "unknown"

    for cycle in range(1, max_attempts + 1):
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
            "scannerReturnCode": scanner.returncode,
            "scannerTimeoutSeconds": timeout,
            "imported": imported,
            "failed": len(failed),
            "running": running,
            "scannerOutput": safe_output(scanner.stdout + "\n" + scanner.stderr)
        }

        if not failed:
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
        cycles.append(cycle_report)

        if not recovery.get("retryScheduled"):
            publish_recovery(queue, recovery, terminal=True)
            final_state = "human_review_required" if recovery.get("requiresHumanReview") else "unrecoverable"
            break

        publish_recovery(queue, recovery)
        delay = min(900, max(0, int(recovery.get("retryDelaySeconds") or 0)))
        if delay:
            print(f"safe recovery cooldown: {delay} seconds", flush=True)
            time.sleep(delay)
        final_state = "retrying"
    else:
        final_state = "attempt_limit_reached"

    report = {
        "schemaVersion": 1,
        "generatedAt": now(),
        "manifest": manifest_arg,
        "dictionary": "data/scan-bug-dictionary.json",
        "finalState": final_state,
        "cycles": cycles,
        "safety": {
            "maximumCycles": max_attempts,
            "sourceCodeModifiedAutomatically": False,
            "authorizationBroadened": False,
            "mediaRetentionChanged": False,
            "queueScopeExpanded": False
        }
    }
    write(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False))
    return 1 if final_state in {"human_review_required", "unrecoverable", "attempt_limit_reached"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
