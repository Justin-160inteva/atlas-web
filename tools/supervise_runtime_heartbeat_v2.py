#!/usr/bin/env python3
"""Persistent technical-retry overlay for the Atlas heartbeat supervisor.

The base supervisor remains authoritative for durable-state reconciliation. This overlay only
changes the old attempt-limit terminal branch for stale technical execution: it releases the
single stale lease and schedules the same authorized item again. Protected authorization,
identity, privacy, retention and queue-scope failures are not changed here.
"""
from __future__ import annotations

import sys
from typing import Any

import supervise_runtime_heartbeat as base

_original_evaluate = base.evaluate


def evaluate(
    config: dict[str, Any],
    manifest: dict[str, Any],
    queue: dict[str, Any],
    status: dict[str, Any],
    runtime: dict[str, Any],
    dictionary: dict[str, Any],
    previous: dict[str, Any],
    now,
):
    report, updated_queue, runtime_projection = _original_evaluate(
        config, manifest, queue, status, runtime, dictionary, previous, now
    )
    policy = config.get("policy", {})
    if report.get("decision") != "attempt_limit_reached" or not policy.get("retryTechnicalFailuresUntilResolved"):
        return report, updated_queue, runtime_projection

    items = updated_queue.get("items", [])
    runtime_id = runtime.get("externalSourceId")
    target = next((item for item in items if item.get("externalSourceId") == runtime_id), None)
    if target is None:
        target = next((item for item in items if item.get("state", "pending") in {"pending", "queued", "failed"}), None)
    if target is None:
        return report, updated_queue, runtime_projection

    age = report.get("heartbeatAgeSeconds") or 0
    stage = str(runtime.get("stage") or "unknown")
    target["state"] = "failed"
    target["error"] = f"heartbeat supervisor: no heartbeat for {age}s at stage {stage}; persistent technical retry enabled"
    target["lastFinishedAt"] = base.iso(now)
    target["persistentRetryRequested"] = True
    updated_queue["status"] = "retryable_failure"
    updated_queue["updatedAt"] = base.iso(now)
    updated_queue.pop("activeExternalSourceId", None)

    target_id = target.get("externalSourceId")
    cooldown = max(5, int(config.get("resumeCooldownSeconds", 60)))
    resume, suppressed = base.resume_permitted(previous, target_id, now, cooldown)
    runtime_projection = base.projection(
        target,
        state="queued",
        stage="queued",
        progress=0,
        message="技术故障尚未解决；已释放旧心跳并继续自动诊断、AI修复和重试",
        now=now,
        runtime=runtime,
    )
    report.update({
        "decision": "persistent_technical_retry",
        "dictionaryEntryId": "runtime-heartbeat-hard-stale",
        "dictionaryEntryKnown": True,
        "diagnosis": f"heartbeat remained stale after the previous attempt budget at stage={stage}; persistent technical retry is enabled",
        "repair": "release_stale_lease_and_continue_ai_repair",
        "resumeWorkflow": resume,
        "resumeSuppressedByCooldown": suppressed,
        "resumeTargetExternalSourceId": target_id,
        "lastResumeRequestedAt": base.iso(now) if resume else previous.get("lastResumeRequestedAt"),
        "resumeCooldownSeconds": cooldown,
        "projectionWritten": True,
        "queueChanged": True,
        "persistentTechnicalRetry": True,
    })
    return report, updated_queue, runtime_projection


base.evaluate = evaluate

if __name__ == "__main__":
    raise SystemExit(base.main())
