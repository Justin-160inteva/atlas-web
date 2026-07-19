#!/usr/bin/env python3
"""Static and simulated health audit for the Atlas scan and monitor stack."""
from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/batch-analysis/scan-system-health.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: str) -> Any:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def record(checks: list[dict[str, Any]], name: str, condition: bool, detail: str) -> None:
    checks.append({"name": name, "passed": bool(condition), "detail": detail})


def main() -> int:
    checks: list[dict[str, Any]] = []
    bugs = load("data/scan-bug-dictionary.json")
    manifest = load("data/batch-analysis/eleven-pilot-scan-manifest.json")
    queue = load("data/batch-analysis/eleven-pilot-scan-queue.json")
    monitor = text("scan-monitor.js")
    monitor_html = text("scan-monitor.html")
    worker = text("sw.js")
    publisher = text("tools/publish_runtime_progress.py")
    workflow = text(".github/workflows/scan-eleven-pilot-v2.yml")
    analyzer = text("tools/analyze_authorized_video_v10.py")

    entries = bugs.get("entries", [])
    ids = [entry.get("id") for entry in entries]
    record(checks, "bug_dictionary_size", len(entries) >= 18, f"{len(entries)} entries")
    record(checks, "bug_dictionary_unique_ids", len(ids) == len(set(ids)), "all IDs unique")
    record(checks, "bug_dictionary_patterns", all(entry.get("patterns") for entry in entries), "all entries have signatures")
    record(checks, "bug_dictionary_actions", all(entry.get("autoAction") for entry in entries), "all entries have actions")

    required_layers = {"source-download", "source-metadata", "identity", "http-client", "network", "media", "analysis", "runner", "progress-publish", "orchestration", "safety"}
    actual_layers = {entry.get("layer") for entry in entries}
    record(checks, "bug_dictionary_layer_coverage", required_layers <= actual_layers, f"layers={sorted(actual_layers)}")

    record(checks, "minute_heartbeat_manifest", manifest.get("runtimeHeartbeat", {}).get("minimumIntervalSeconds") == 60, "manifest heartbeat is 60 seconds")
    record(checks, "download_telemetry_manifest", manifest.get("downloadTelemetry", {}).get("intervalSeconds") == 60, "download telemetry is 60 seconds")
    record(checks, "v10_compatibility_adapter", manifest.get("analyzer", "").endswith("analyze_authorized_video_v10.py") and "ClosingResponse" in analyzer, "explicit response closing adapter enabled")
    record(checks, "bounded_queue", 1 <= len(queue.get("items", [])) <= 3 and manifest.get("maxItemsPerRun") == 1, "one item per run, at most three queued")
    record(checks, "retention_policy", manifest.get("retention", {}).get("originalVideo") is False and manifest.get("retention", {}).get("framePixels") is False, "media and frame pixels are not retained")

    record(checks, "monitor_fast_poll", "FAST_POLL_MS=10000" in monitor, "monitor reads every 10 seconds")
    record(checks, "monitor_heartbeat_window", "RUNTIME_FRESH_MS=150000" in monitor and "RUNNING_STALE_MS=180000" in monitor, "60-second heartbeat gets bounded freshness windows")
    record(checks, "monitor_version", "version:'0.3.1'" in monitor and "scan-monitor.js?v=0.3.1" in monitor_html, "monitor assets use v0.3.1")
    record(checks, "monitor_cache_generation", "monitor-v4" in worker, "service worker cache generation updated")

    record(checks, "publisher_conflict_retry", "error.code not in {409, 422}" in publisher and "ATLAS_PROGRESS_CONFLICT_RETRIES" in publisher, "GitHub content conflicts refetch SHA and retry")
    record(checks, "workflow_immediate_recovery", "run_scan_with_auto_recovery.py" in workflow and "diagnose_and_recover_scan_v2.py" in workflow, "failure investigation occurs inside the same job")
    record(checks, "workflow_generic_region", "all(item['regionGuess']==region" in workflow and "len(queue['items'])==3" not in workflow, "workflow is not hard-coded to 山城 or exactly three items")

    sample_expectations = {
        "HTTP Error 412: Precondition Failed": "bilibili-http-412",
        "Response object does not support the context manager protocol": "curl-response-context-manager",
        "Invalid data found when processing input": "ffmpeg-invalid-data",
        "No space left on device": "runner-disk-space",
        "409 Conflict sha does not match": "github-contents-conflict",
        "CID mismatch": "multipart-page-identity"
    }
    for message, expected in sample_expectations.items():
        matches = [entry for entry in entries if any(pattern.lower() in message.lower() for pattern in entry.get("patterns", []))]
        chosen = max(matches, key=lambda entry: max(len(pattern) for pattern in entry.get("patterns", []) if pattern.lower() in message.lower()), default=0) if matches else None
        record(checks, f"dictionary_sample_{expected}", bool(chosen and chosen.get("id") == expected), message)

    media = []
    for pattern in ("*.mp4", "*.m4a", "*.webm", "*.flv"):
        media.extend(ROOT.rglob(pattern))
    record(checks, "repository_media_clean", not media, f"media files={len(media)}")

    passed = sum(check["passed"] for check in checks)
    report = {
        "schemaVersion": 1,
        "generatedAt": now(),
        "status": "pass" if passed == len(checks) else "fail",
        "summary": {"total": len(checks), "passed": passed, "failed": len(checks) - passed},
        "dictionaryVersion": bugs.get("version"),
        "checks": checks
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
