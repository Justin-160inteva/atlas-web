#!/usr/bin/env python3
"""Watch an Atlas scan queue and safely resume only stale or retryable work.

The watchdog never changes source code, authorization, media retention, or queue scope.
It writes a machine-readable decision and optionally resets one stale running lease.
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def load(path: pathlib.Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: watch_and_resume_scan.py WATCHDOG_CONFIG", file=sys.stderr)
        return 2

    config_path = (ROOT / sys.argv[1]).resolve()
    config = load(config_path)
    manifest_path = ROOT / config["manifest"]
    manifest = load(manifest_path)
    queue_path = ROOT / manifest["queue"]
    status_path = ROOT / manifest["statusOutput"]
    queue = load(queue_path)
    status = load(status_path, {})

    stale_after = max(1800, int(config.get("staleAfterSeconds", 7200)))
    max_attempts = max(1, int(manifest.get("recoveryPolicy", {}).get("maxAttemptsPerItem", 3)))
    current = now()
    decision = "no_action"
    reason = "queue is healthy or waiting for an active workflow"
    resume = False
    changed_item: str | None = None

    imported = sum(item.get("state") == "imported" for item in queue.get("items", []))
    if imported == len(queue.get("items", [])):
        decision = "complete"
        reason = "all bounded pilot items are imported"
    else:
        running = [item for item in queue.get("items", []) if item.get("state") == "running"]
        retryable = [
            item for item in queue.get("items", [])
            if item.get("state") == "failed" and int(item.get("attemptCount", 0)) < max_attempts
        ]
        pending = [item for item in queue.get("items", []) if item.get("state", "pending") == "pending"]

        if running:
            item = running[0]
            started = parse_time(item.get("lastStartedAt"))
            age = (current - started).total_seconds() if started else stale_after + 1
            if age >= stale_after:
                item["state"] = "failed"
                item["error"] = f"watchdog recovered stale running lease after {int(age)} seconds"
                item["lastFinishedAt"] = iso(current)
                queue["status"] = "retryable_failure"
                queue.pop("activeExternalSourceId", None)
                decision = "recover_stale_running"
                reason = "running lease exceeded watchdog threshold"
                resume = int(item.get("attemptCount", 0)) < max_attempts
                changed_item = item.get("externalSourceId")
            else:
                decision = "active_not_stale"
                reason = f"active item age {int(age)} seconds is below {stale_after}"
        elif retryable:
            decision = "resume_retryable_failure"
            reason = "a failed item remains below the bounded attempt limit"
            resume = True
            changed_item = retryable[0].get("externalSourceId")
        elif pending:
            status_time = parse_time(status.get("updatedAt"))
            trigger_time = parse_time(config.get("activatedAt"))
            reference = max(filter(None, [status_time, trigger_time]), default=None)
            age = (current - reference).total_seconds() if reference else stale_after + 1
            if age >= stale_after:
                decision = "resume_idle_pending"
                reason = "pending queue has had no durable progress within watchdog threshold"
                resume = True
                changed_item = pending[0].get("externalSourceId")
            else:
                decision = "pending_grace_period"
                reason = f"pending queue is within {stale_after}-second startup grace period"
        else:
            decision = "blocked"
            reason = "no pending or retryable item remains; human review is required"

    queue["updatedAt"] = iso(current)
    write(queue_path, queue)
    report = {
        "schemaVersion": 1,
        "generatedAt": iso(current),
        "decision": decision,
        "reason": reason,
        "resumeWorkflow": resume,
        "changedExternalSourceId": changed_item,
        "staleAfterSeconds": stale_after,
        "safety": {
            "sourceCodeModified": False,
            "authorizationBroadened": False,
            "mediaRetentionChanged": False,
            "queueScopeExpanded": False
        }
    }
    output = ROOT / config.get("reportOutput", "data/batch-analysis/eleven-pilot-watchdog-state.json")
    write(output, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
