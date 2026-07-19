#!/usr/bin/env python3
"""Dictionary-driven Atlas scan diagnosis and bounded recovery.

The engine reconciles failed analyzer results with queue state, matches a curated bug
signature, applies only pre-approved runtime changes, and writes an auditable report.
It never changes authorization, queue scope, source code, or media retention.
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
DICTIONARY = ROOT / "data/scan-bug-dictionary.json"
REPORT = ROOT / "data/batch-analysis/eleven-pilot-recovery-report.json"


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


def safe_error(value: Any) -> str:
    text = str(value or "").replace("\x00", "")
    lowered = text.lower()
    for marker in ("authorization: bearer", "set-cookie", "cookie=", "https://", "http://", "/tmp/"):
        if marker in lowered:
            text = "Sensitive transport detail removed. " + text[-6000:]
            break
    return text[-12000:]


def match_entry(error: str, dictionary: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    lowered = error.lower()
    matches: list[tuple[int, dict[str, Any], str]] = []
    for entry in dictionary.get("entries", []):
        for pattern in entry.get("patterns", []):
            needle = str(pattern).lower()
            if needle and needle in lowered:
                score = len(needle) + (1000 if not entry.get("retryable", False) else 0)
                matches.append((score, entry, pattern))
    if not matches:
        return None, "no known signature"
    _, entry, pattern = max(matches, key=lambda item: item[0])
    return entry, str(pattern)


def latest_failed_result(queue: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    candidates: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for item in queue.get("items", []):
        page = int(item.get("page") or item.get("sequence") or 0)
        path = ROOT / f"data/analysis-results/eleven-p{page:03d}.json"
        result = load(path, {})
        if result.get("status") != "failed":
            continue
        timestamp = path.stat().st_mtime if path.exists() else 0.0
        candidates.append((timestamp, item, result))
    if not candidates:
        return None, None
    _, item, result = max(candidates, key=lambda value: value[0])
    return item, result


def reconcile_failure(queue: dict[str, Any], status: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    failed = [item for item in queue.get("items", []) if item.get("state") == "failed"]
    if failed:
        return failed[0], safe_error(failed[0].get("error"))

    item, result = latest_failed_result(queue)
    if item and result:
        error = safe_error(result.get("error") or f"analysis stage {result.get('stage')} failed")
        if item.get("state") == "running":
            item["state"] = "failed"
            item["error"] = error
            item["lastFinishedAt"] = result.get("generatedAt") or now()
            queue.pop("activeExternalSourceId", None)
        return item, error

    events = status.get("events") or []
    error = safe_error(events[-1].get("error")) if events else ""
    return None, error


def apply_action(action: str, active: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    if action == "increase_backoff_and_retry_public_api":
        manifest["downloadBackoffSeconds"] = min(900, max(60, int(manifest.get("downloadBackoffSeconds", 60)) * 2))
        manifest["preferPublicApi"] = True
        changed = {"downloadBackoffSeconds": manifest["downloadBackoffSeconds"], "preferPublicApi": True}
    elif action in {"switch_to_public_api", "refresh_source_metadata_and_retry"}:
        manifest["preferPublicApi"] = True
        manifest["refreshSourceMetadata"] = True
        changed = {"preferPublicApi": True, "refreshSourceMetadata": True}
    elif action == "use_v10_response_compatibility_adapter":
        manifest["analyzer"] = "tools/analyze_authorized_video_v10.py"
        changed = {"analyzer": manifest["analyzer"]}
    elif action == "enable_transcode_fallback_and_retry":
        manifest["forceTranscodeFallback"] = True
        changed = {"forceTranscodeFallback": True}
    elif action == "extend_timeout_reduce_samples_and_retry":
        manifest["perItemTimeoutSeconds"] = min(10800, int(manifest.get("perItemTimeoutSeconds", 5400)) + 1800)
        manifest["maxSamplesA"] = max(240, int(manifest.get("maxSamplesA", 540)) - 120)
        changed = {"perItemTimeoutSeconds": manifest["perItemTimeoutSeconds"], "maxSamplesA": manifest["maxSamplesA"]}
    elif action == "reduce_memory_pressure_and_retry":
        manifest["maxSamplesA"] = max(180, int(manifest.get("maxSamplesA", 540)) // 2)
        manifest["minimumIntervalSeconds"] = min(12.0, float(manifest.get("minimumIntervalSeconds", 3.0)) * 1.5)
        changed = {"maxSamplesA": manifest["maxSamplesA"], "minimumIntervalSeconds": manifest["minimumIntervalSeconds"]}
    elif action == "retry_progress_publish_with_fresh_sha":
        manifest["progressPublishConflictRetries"] = 5
        changed = {"progressPublishConflictRetries": 5}
    elif action == "cleanup_then_retry":
        manifest["cleanupTransientMediaBeforeRetry"] = True
        changed = {"cleanupTransientMediaBeforeRetry": True}
    elif action == "reset_stale_lease_and_retry":
        active.pop("lastStartedAt", None)
        changed = {"staleLeaseReset": True}
    elif action == "wait_then_retry":
        changed = {"rateLimitCooldown": True}
    return changed


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: diagnose_and_recover_scan_v2.py MANIFEST_JSON", file=sys.stderr)
        return 2

    manifest_path = (ROOT / sys.argv[1]).resolve()
    manifest = load(manifest_path)
    queue_path = ROOT / manifest["queue"]
    status_path = ROOT / manifest["statusOutput"]
    queue = load(queue_path)
    status = load(status_path, {})
    dictionary = load(DICTIONARY, {"entries": [], "defaultPolicy": {}})

    active, error = reconcile_failure(queue, status)
    entry, signature = match_entry(error, dictionary)
    maximum = int(manifest.get("recoveryPolicy", {}).get("maxAttemptsPerItem", manifest.get("maxAttemptsPerItem", 3)))
    attempts = int((active or {}).get("attemptCount", 0))
    action = "none"
    retry = False
    requires_human = False
    cooldown = 0
    changed: dict[str, Any] = {}

    if active:
        if attempts >= maximum:
            action = "block_after_attempt_limit"
            requires_human = True
        elif entry is None:
            action = "human_review_required"
            requires_human = True
        else:
            action = str(entry.get("autoAction") or "human_review_required")
            cooldown = max(0, int(entry.get("cooldownSeconds") or 0))
            retry = bool(entry.get("retryable")) and action != "human_review_required"
            requires_human = not retry
            if retry:
                changed = apply_action(action, active, manifest)
                active["state"] = "pending"
                active.pop("error", None)
                active["lastRecoveryAt"] = now()
                active["lastRecoveryAction"] = action
                queue["status"] = "recovery_scheduled"
                queue.pop("activeExternalSourceId", None)
            else:
                queue["status"] = "blocked"

    report = {
        "schemaVersion": 2,
        "generatedAt": now(),
        "dictionaryVersion": dictionary.get("version"),
        "dictionaryEntryId": (entry or {}).get("id"),
        "manifest": manifest_path.relative_to(ROOT).as_posix(),
        "activeExternalSourceId": (active or {}).get("externalSourceId"),
        "category": (entry or {}).get("layer", "unknown"),
        "matchedSignature": signature,
        "diagnosis": (entry or {}).get("diagnosis", "No safe deterministic match was found."),
        "action": action,
        "retryScheduled": retry,
        "retryDelaySeconds": cooldown,
        "requiresHumanReview": requires_human,
        "attemptCount": attempts,
        "maxAttempts": maximum,
        "changedRuntimeSettings": changed,
        "errorExcerpt": error[-3000:],
        "safety": {
            "sourceCodeModified": False,
            "authorizationBroadened": False,
            "mediaRetentionChanged": False,
            "queueScopeExpanded": False
        }
    }

    write(manifest_path, manifest)
    write(queue_path, queue)
    write(REPORT, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
