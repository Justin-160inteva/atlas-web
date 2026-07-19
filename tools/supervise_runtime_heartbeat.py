#!/usr/bin/env python3
"""Detect stale Atlas runtime heartbeats and apply bounded dictionary repairs.

This supervisor never edits executable source code, authorization, queue scope, or
retention policy. It may reconcile durable queue state, publish a diagnosis, and
request one bounded workflow retry.
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]


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
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except (TypeError, ValueError):
        return None


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: supervise_runtime_heartbeat.py CONFIG", file=sys.stderr)
        return 2

    config = load(ROOT / sys.argv[1])
    manifest = load(ROOT / config["manifest"])
    queue_path = ROOT / manifest["queue"]
    status_path = ROOT / manifest["statusOutput"]
    runtime_path = ROOT / config["runtimeProgress"]
    dictionary = load(ROOT / config["dictionary"])
    queue = load(queue_path)
    status = load(status_path, {})
    runtime = load(runtime_path, {})

    now = datetime.now(timezone.utc)
    stale_after = max(120, int(config.get("staleAfterSeconds", 180)))
    hard_stale_after = max(stale_after, int(config.get("hardStaleAfterSeconds", 420)))
    updated = parse_time(runtime.get("updatedAt"))
    age = int((now - updated).total_seconds()) if updated else 10**9
    runtime_id = runtime.get("externalSourceId")
    item = next((x for x in queue.get("items", []) if x.get("externalSourceId") == runtime_id), None)
    imported = sum(x.get("state") == "imported" for x in queue.get("items", []))
    complete = bool(queue.get("items")) and imported == len(queue.get("items", []))

    decision = "healthy"
    repair = "none"
    resume = False
    dictionary_id = "heartbeat-healthy"
    diagnosis = "runtime heartbeat is fresh"
    changed = False

    if complete:
        decision = "complete"
        dictionary_id = "heartbeat-complete"
        diagnosis = "all bounded queue items are imported"
    elif not runtime or not updated:
        decision = "missing_heartbeat"
        dictionary_id = "runtime-heartbeat-missing"
        diagnosis = "runtime heartbeat file is missing or has no valid timestamp"
        repair = "resume_pending_item"
        resume = True
    elif age <= stale_after:
        decision = "healthy"
    elif runtime.get("state") in {"running", "recovery"}:
        stage = str(runtime.get("stage") or "unknown")
        if item and item.get("state") == "imported":
            decision = "stale_terminal_heartbeat"
            dictionary_id = "runtime-heartbeat-terminal-stale"
            diagnosis = "runtime heartbeat is stale but durable queue already confirms import"
            repair = "publish_terminal_projection"
        elif age >= hard_stale_after:
            decision = "hard_stale"
            dictionary_id = "runtime-heartbeat-hard-stale"
            diagnosis = f"no heartbeat for {age}s while stage={stage}"
            repair = "reset_lease_and_retry"
            resume = True
            if item:
                attempts = int(item.get("attemptCount", 0))
                max_attempts = int(manifest.get("maxAttemptsPerItem", 3))
                if attempts < max_attempts:
                    item["state"] = "failed"
                    item["error"] = f"heartbeat supervisor: no heartbeat for {age}s at stage {stage}"
                    item["lastFinishedAt"] = iso(now)
                    queue["status"] = "retryable_failure"
                    queue.pop("activeExternalSourceId", None)
                    changed = True
                else:
                    resume = False
                    decision = "attempt_limit_reached"
                    repair = "human_review"
        else:
            decision = "soft_stale"
            dictionary_id = "runtime-heartbeat-soft-stale"
            diagnosis = f"heartbeat age {age}s exceeds {stale_after}s but remains below hard threshold"
            repair = "observe_and_recheck"
    else:
        decision = "inactive_stale"
        dictionary_id = "runtime-heartbeat-inactive-stale"
        diagnosis = f"last runtime state={runtime.get('state')} is {age}s old"
        pending = next((x for x in queue.get("items", []) if x.get("state", "pending") in {"pending", "failed"}), None)
        if pending:
            repair = "resume_pending_item"
            resume = True

    known_ids = {entry.get("id") for entry in dictionary.get("entries", [])}
    report = {
        "schemaVersion": 1,
        "generatedAt": iso(now),
        "decision": decision,
        "dictionaryEntryId": dictionary_id,
        "dictionaryEntryKnown": dictionary_id in known_ids,
        "diagnosis": diagnosis,
        "repair": repair,
        "resumeWorkflow": resume,
        "heartbeatAgeSeconds": age if age < 10**9 else None,
        "softThresholdSeconds": stale_after,
        "hardThresholdSeconds": hard_stale_after,
        "runtime": {
            "externalSourceId": runtime_id,
            "page": runtime.get("page"),
            "state": runtime.get("state"),
            "stage": runtime.get("stage"),
            "updatedAt": runtime.get("updatedAt"),
            "heartbeatSequence": runtime.get("heartbeatSequence"),
        },
        "safety": {
            "sourceCodeModified": False,
            "authorizationBroadened": False,
            "queueScopeExpanded": False,
            "mediaRetentionChanged": False,
        },
    }

    if changed:
        queue["updatedAt"] = iso(now)
        write(queue_path, queue)
    write(ROOT / config["reportOutput"], report)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
