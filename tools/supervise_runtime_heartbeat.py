#!/usr/bin/env python3
"""Reconcile Atlas runtime heartbeat with durable queue state and recover bounded work.

Durable queue/status data always wins over a stale runtime projection. The supervisor
may publish a queued/complete projection, release one stale lease, and request one
cooldown-protected workflow resume. It never changes executable source, authorization,
queue scope, or media retention.
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


def projection(item: dict[str, Any], *, state: str, stage: str, progress: float, message: str, now: datetime, runtime: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 5,
        "author": runtime.get("author") or "11的游戏世界",
        "authorizationId": runtime.get("authorizationId"),
        "pilotRegion": item.get("regionGuess") or runtime.get("pilotRegion"),
        "externalSourceId": item.get("externalSourceId"),
        "page": item.get("page") or item.get("sequence"),
        "state": state,
        "stage": stage,
        "progressPercent": progress,
        "processedSeconds": 0.0,
        "durationSeconds": float(item.get("durationSeconds") or 0),
        "sampledFrames": 0,
        "targetFrames": 0,
        "message": message,
        "updatedAt": iso(now),
        "heartbeatSequence": int(runtime.get("heartbeatSequence") or 0) + 1,
        "telemetryPreserved": False,
        "projectionSource": "durable-queue-supervisor",
        "privacy": "Only public, sanitized task progress is stored. No media URLs, cookies, video files, local paths, or frame pixels are included.",
    }


def resume_permitted(previous: dict[str, Any], target_id: str | None, now: datetime, cooldown: int) -> tuple[bool, bool]:
    if not target_id:
        return False, False
    previous_target = previous.get("resumeTargetExternalSourceId")
    previous_at = parse_time(previous.get("lastResumeRequestedAt"))
    if previous_target != target_id or previous_at is None:
        return True, False
    elapsed = (now - previous_at).total_seconds()
    return elapsed >= cooldown, elapsed < cooldown


def evaluate(config: dict[str, Any], manifest: dict[str, Any], queue: dict[str, Any], status: dict[str, Any], runtime: dict[str, Any], dictionary: dict[str, Any], previous: dict[str, Any], now: datetime) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    items = queue.get("items", [])
    imported = [item for item in items if item.get("state") == "imported"]
    pending = next((item for item in items if item.get("state", "pending") in {"pending", "queued", "failed"}), None)
    complete = bool(items) and len(imported) == len(items)
    runtime_id = runtime.get("externalSourceId")
    runtime_item = next((item for item in items if item.get("externalSourceId") == runtime_id), None)
    updated = parse_time(runtime.get("updatedAt"))
    age = int((now - updated).total_seconds()) if updated else 10**9
    soft = max(60, int(config.get("staleAfterSeconds", 90)))
    hard = max(soft, int(config.get("hardStaleAfterSeconds", 180)))
    cooldown = max(60, int(config.get("resumeCooldownSeconds", 360)))
    max_attempts = int(config.get("policy", {}).get("maximumAttemptsPerItem", manifest.get("maxAttemptsPerItem", 3)))

    decision = "healthy"
    dictionary_id = "heartbeat-healthy"
    diagnosis = "runtime heartbeat is fresh"
    repair = "none"
    target = None
    queue_changed = False
    runtime_projection = None

    if complete:
        decision = "complete"
        dictionary_id = "heartbeat-complete"
        diagnosis = "all bounded queue items are durably imported"
        if runtime.get("state") != "complete" and imported:
            last = imported[-1]
            runtime_projection = projection(last, state="complete", stage="complete", progress=100, message="当前有界批次已全部完成并持久化", now=now, runtime=runtime)
            repair = "publish_terminal_projection"
    elif runtime_item and runtime_item.get("state") == "imported":
        decision = "stale_terminal_heartbeat"
        dictionary_id = "runtime-heartbeat-terminal-stale"
        diagnosis = "durable queue confirms the runtime item is imported; stale running state is ignored"
        if pending:
            target = pending
            runtime_projection = projection(pending, state="queued", stage="queued", progress=0, message=f"上一任务已持久化；P{pending.get('page') or pending.get('sequence')} 等待调度", now=now, runtime=runtime)
            repair = "publish_terminal_projection_and_resume_pending"
        else:
            repair = "publish_terminal_projection"
    elif not runtime or not updated:
        decision = "missing_heartbeat"
        dictionary_id = "runtime-heartbeat-missing"
        diagnosis = "runtime heartbeat file is missing or has no valid timestamp"
        if pending:
            target = pending
            runtime_projection = projection(pending, state="queued", stage="queued", progress=0, message=f"P{pending.get('page') or pending.get('sequence')} 等待调度；监督器已重建运行投影", now=now, runtime=runtime)
            repair = "resume_pending_item"
    elif runtime.get("state") == "queued":
        decision = "pending_queued"
        dictionary_id = "runtime-heartbeat-inactive-stale"
        diagnosis = "durable queue has pending work and the runtime projection is queued"
        target = runtime_item if runtime_item and runtime_item.get("state") != "imported" else pending
        repair = "resume_pending_item" if target else "none"
    elif runtime.get("state") in {"running", "recovery"}:
        stage = str(runtime.get("stage") or "unknown")
        if age <= soft:
            decision = "healthy"
        elif age < hard:
            decision = "soft_stale"
            dictionary_id = "runtime-heartbeat-soft-stale"
            diagnosis = f"heartbeat age {age}s exceeds {soft}s but remains below hard threshold"
            repair = "observe_and_recheck"
        else:
            decision = "hard_stale"
            dictionary_id = "runtime-heartbeat-hard-stale"
            diagnosis = f"no heartbeat for {age}s while stage={stage}"
            if runtime_item and int(runtime_item.get("attemptCount", 0)) < max_attempts:
                runtime_item["state"] = "failed"
                runtime_item["error"] = f"heartbeat supervisor: no heartbeat for {age}s at stage {stage}"
                runtime_item["lastFinishedAt"] = iso(now)
                queue["status"] = "retryable_failure"
                queue["updatedAt"] = iso(now)
                queue.pop("activeExternalSourceId", None)
                queue_changed = True
                target = runtime_item
                repair = "reset_lease_and_retry"
                runtime_projection = projection(runtime_item, state="queued", stage="queued", progress=0, message="运行心跳超时；已释放旧租约并安排一次有界重试", now=now, runtime=runtime)
            else:
                decision = "attempt_limit_reached"
                repair = "human_review"
    else:
        decision = "inactive_stale"
        dictionary_id = "runtime-heartbeat-inactive-stale"
        diagnosis = f"last runtime state={runtime.get('state')} is {age}s old while durable work remains"
        if pending:
            target = pending
            repair = "resume_pending_item"
            runtime_projection = projection(pending, state="queued", stage="queued", progress=0, message=f"P{pending.get('page') or pending.get('sequence')} 等待调度；已修复过期运行投影", now=now, runtime=runtime)

    target_id = target.get("externalSourceId") if target else None
    resume, suppressed = resume_permitted(previous, target_id, now, cooldown)
    known_ids = {entry.get("id") for entry in dictionary.get("entries", [])}
    last_resume = iso(now) if resume else (previous.get("lastResumeRequestedAt") if previous.get("resumeTargetExternalSourceId") == target_id else None)
    report = {
        "schemaVersion": 2,
        "generatedAt": iso(now),
        "decision": decision,
        "dictionaryEntryId": dictionary_id,
        "dictionaryEntryKnown": dictionary_id in known_ids or dictionary_id in {"heartbeat-healthy", "heartbeat-complete"},
        "diagnosis": diagnosis,
        "repair": repair,
        "resumeWorkflow": resume,
        "resumeSuppressedByCooldown": suppressed,
        "resumeTargetExternalSourceId": target_id,
        "lastResumeRequestedAt": last_resume,
        "resumeCooldownSeconds": cooldown,
        "heartbeatAgeSeconds": age if age < 10**9 else None,
        "softThresholdSeconds": soft,
        "hardThresholdSeconds": hard,
        "durable": {
            "total": len(items),
            "imported": len(imported),
            "pending": sum(item.get("state", "pending") in {"pending", "queued", "failed"} for item in items),
            "statusUpdatedAt": status.get("updatedAt"),
            "queueUpdatedAt": queue.get("updatedAt"),
        },
        "runtime": {
            "externalSourceId": runtime_id,
            "page": runtime.get("page"),
            "state": runtime.get("state"),
            "stage": runtime.get("stage"),
            "updatedAt": runtime.get("updatedAt"),
            "heartbeatSequence": runtime.get("heartbeatSequence"),
            "durableItemState": runtime_item.get("state") if runtime_item else None,
        },
        "projectionWritten": runtime_projection is not None,
        "queueChanged": queue_changed,
        "safety": {
            "sourceCodeModified": False,
            "authorizationBroadened": False,
            "queueScopeExpanded": False,
            "mediaRetentionChanged": False,
        },
    }
    return report, queue, runtime_projection


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: supervise_runtime_heartbeat.py CONFIG", file=sys.stderr)
        return 2
    config = load(ROOT / sys.argv[1])
    manifest = load(ROOT / config["manifest"])
    queue_path = ROOT / manifest["queue"]
    status_path = ROOT / manifest["statusOutput"]
    runtime_path = ROOT / config["runtimeProgress"]
    report_path = ROOT / config["reportOutput"]
    queue = load(queue_path, {"items": []})
    status = load(status_path, {})
    runtime = load(runtime_path, {})
    dictionary = load(ROOT / config["dictionary"], {"entries": []})
    previous = load(report_path, {})
    report, queue, runtime_projection = evaluate(config, manifest, queue, status, runtime, dictionary, previous, datetime.now(timezone.utc))
    if report["queueChanged"]:
        write(queue_path, queue)
    if runtime_projection is not None:
        write(runtime_path, runtime_projection)
    write(report_path, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
