#!/usr/bin/env python3
"""Diagnose one Atlas scan failure and apply bounded, deterministic recovery actions.

This tool never edits source code and never broadens authorization. It may only adjust
approved queue/manifest runtime parameters, reset a retryable item, or block an item
that requires human review. All decisions are persisted as machine-readable JSON.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: pathlib.Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def normalize_error(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"(?i)cookie[^\n]*", "", text)
    return text[-12000:]


def classify(error: str) -> tuple[str, str]:
    low = error.lower()
    rules = [
        ("http_412", ["http error 412", "status code 412", "blocked by server (412)"]),
        ("http_403", ["http error 403", "status code 403", "forbidden"]),
        ("rate_limit", ["too many requests", "http error 429", "rate limit"]),
        ("timeout", ["timeout after", "timed out", "timeoutexpired"]),
        ("cdn_download", ["unable to download", "curl exited", "media segment", "download produced no usable file"]),
        ("ffmpeg", ["ffmpeg", "remux failed", "invalid data found when processing input"]),
        ("disk_space", ["no space left on device", "disk quota exceeded"]),
        ("memory", ["memoryerror", "out of memory", "killed", "exit code 137"]),
        ("page_identity", ["requested page", "exceeds multipart page count", "no pages"]),
        ("authorization", ["authorization", "permission", "scope"]),
        ("schema", ["keyerror", "valueerror", "assertionerror", "jsondecodeerror"]),
    ]
    for category, needles in rules:
        if any(needle in low for needle in needles):
            return category, next(needle for needle in needles if needle in low)
    return "unknown", "no known signature"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: diagnose_and_recover_scan.py MANIFEST_JSON", file=sys.stderr)
        return 2

    manifest_path = (ROOT / sys.argv[1]).resolve()
    manifest = load(manifest_path)
    queue_path = ROOT / manifest["queue"]
    status_path = ROOT / manifest["statusOutput"]
    queue = load(queue_path)
    status = load(status_path, {})

    failed = [item for item in queue.get("items", []) if item.get("state") == "failed"]
    active = failed[0] if failed else None
    error = normalize_error((active or {}).get("error") or (status.get("events") or [{}])[-1].get("error"))
    category, signature = classify(error)

    policy = manifest.setdefault("recoveryPolicy", {})
    maximum = int(policy.get("maxAttemptsPerItem", manifest.get("maxAttemptsPerItem", 3)))
    action = "none"
    retry = False
    changed: dict[str, Any] = {}
    requires_human = False

    if active:
        attempts = int(active.get("attemptCount", 0))
        if attempts >= maximum:
            action = "block_after_attempt_limit"
            requires_human = True
        elif category in {"http_412", "http_403", "rate_limit", "cdn_download"}:
            manifest["downloadBackoffSeconds"] = min(900, max(60, int(manifest.get("downloadBackoffSeconds", 30)) * 2))
            manifest["preferPublicApi"] = True
            active["state"] = "pending"
            action = "increase_backoff_and_retry_public_api"
            retry = True
            changed = {"downloadBackoffSeconds": manifest["downloadBackoffSeconds"], "preferPublicApi": True}
        elif category == "timeout":
            manifest["perItemTimeoutSeconds"] = min(10800, int(manifest.get("perItemTimeoutSeconds", 5400)) + 1800)
            manifest["maxSamplesA"] = max(240, int(manifest.get("maxSamplesA", 540)) - 120)
            active["state"] = "pending"
            action = "extend_timeout_reduce_samples_and_retry"
            retry = True
            changed = {"perItemTimeoutSeconds": manifest["perItemTimeoutSeconds"], "maxSamplesA": manifest["maxSamplesA"]}
        elif category == "memory":
            manifest["maxSamplesA"] = max(180, int(manifest.get("maxSamplesA", 540)) // 2)
            manifest["minimumIntervalSeconds"] = min(12.0, float(manifest.get("minimumIntervalSeconds", 3.0)) * 1.5)
            active["state"] = "pending"
            action = "reduce_memory_pressure_and_retry"
            retry = True
            changed = {"maxSamplesA": manifest["maxSamplesA"], "minimumIntervalSeconds": manifest["minimumIntervalSeconds"]}
        elif category == "ffmpeg":
            manifest["forceTranscodeFallback"] = True
            active["state"] = "pending"
            action = "enable_transcode_fallback_and_retry"
            retry = True
            changed = {"forceTranscodeFallback": True}
        elif category == "disk_space":
            action = "cleanup_then_retry"
            active["state"] = "pending"
            retry = True
        elif category in {"page_identity", "authorization", "schema", "unknown"}:
            action = "human_review_required"
            requires_human = True

        if retry:
            active.pop("error", None)
            active["lastRecoveryAt"] = now()
            active["lastRecoveryAction"] = action
            queue["status"] = "recovery_scheduled"
        elif requires_human:
            queue["status"] = "blocked"

    report = {
        "schemaVersion": 1,
        "generatedAt": now(),
        "manifest": manifest_path.relative_to(ROOT).as_posix(),
        "activeExternalSourceId": (active or {}).get("externalSourceId"),
        "category": category,
        "matchedSignature": signature,
        "action": action,
        "retryScheduled": retry,
        "requiresHumanReview": requires_human,
        "attemptCount": int((active or {}).get("attemptCount", 0)),
        "maxAttempts": maximum,
        "changedRuntimeSettings": changed,
        "errorExcerpt": error[-3000:],
        "safety": {
            "sourceCodeModified": False,
            "authorizationBroadened": False,
            "mediaRetentionChanged": False,
        },
    }

    write(manifest_path, manifest)
    write(queue_path, queue)
    write(ROOT / "data/batch-analysis/eleven-pilot-recovery-report.json", report)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
