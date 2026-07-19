#!/usr/bin/env python3
"""Run one queue item with immediate dictionary-driven investigation and retry.

A failure is diagnosed in the same GitHub Actions job. Safe deterministic failures are
retried after their prescribed cooldown; unsafe or unknown failures stop for review.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any

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


def run(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: run_scan_with_auto_recovery.py MANIFEST_JSON", file=sys.stderr)
        return 2

    manifest_arg = sys.argv[1]
    manifest_path = (ROOT / manifest_arg).resolve()
    manifest = load(manifest_path)
    queue_path = ROOT / manifest["queue"]
    max_attempts = max(1, int(manifest.get("recoveryPolicy", {}).get("maxAttemptsPerItem", 3)))
    cycles: list[dict[str, Any]] = []
    final_state = "unknown"

    for cycle in range(1, max_attempts + 1):
        started = now()
        scanner = run([sys.executable, "tools/scan_catalog_queue_v2.py", manifest_arg], int(manifest.get("perItemTimeoutSeconds", 5400)) + 300)
        queue = load(queue_path, {"items": []})
        failed = [item for item in queue.get("items", []) if item.get("state") == "failed"]
        imported = sum(item.get("state") == "imported" for item in queue.get("items", []))
        running = sum(item.get("state") == "running" for item in queue.get("items", []))
        cycle_report: dict[str, Any] = {
            "cycle": cycle,
            "startedAt": started,
            "finishedAt": now(),
            "scannerReturnCode": scanner.returncode,
            "imported": imported,
            "failed": len(failed),
            "running": running,
            "scannerOutput": (scanner.stdout + "\n" + scanner.stderr)[-3000:]
        }

        if not failed:
            final_state = "scan_completed_or_progressed"
            cycles.append(cycle_report)
            break

        diagnosis = run([sys.executable, "tools/diagnose_and_recover_scan_v2.py", manifest_arg], 180)
        recovery = load(RECOVERY_PATH, {})
        cycle_report["diagnosisReturnCode"] = diagnosis.returncode
        cycle_report["dictionaryEntryId"] = recovery.get("dictionaryEntryId")
        cycle_report["action"] = recovery.get("action")
        cycle_report["retryScheduled"] = recovery.get("retryScheduled")
        cycle_report["requiresHumanReview"] = recovery.get("requiresHumanReview")
        cycles.append(cycle_report)

        if not recovery.get("retryScheduled"):
            final_state = "human_review_required" if recovery.get("requiresHumanReview") else "unrecoverable"
            break

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
