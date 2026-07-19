#!/usr/bin/env python3
"""Static and executable health audit for the Atlas scan and monitor stack."""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import urllib.error
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


def module_from(path: str, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record(checks: list[dict[str, Any]], name: str, condition: bool, detail: str) -> None:
    checks.append({"name": name, "passed": bool(condition), "detail": detail})


def main() -> int:
    checks: list[dict[str, Any]] = []
    bugs = load("data/scan-bug-dictionary.json")
    manifest = load("data/batch-analysis/eleven-pilot-scan-manifest.json")
    queue = load("data/batch-analysis/eleven-pilot-scan-queue.json")
    monitor = text("scan-monitor.js")
    monitor_health = text("scan-monitor-health.js")
    monitor_html = text("scan-monitor.html")
    worker = text("sw.js")
    publisher_text = text("tools/publish_runtime_progress.py")
    workflow = text(".github/workflows/scan-eleven-pilot-v2.yml")
    analyzer = text("tools/analyze_authorized_video_v10.py")
    orchestrator = text("tools/run_scan_with_auto_recovery.py")

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

    record(checks, "monitor_fast_poll", "FAST_POLL_MS=10000" in monitor and "CHECK_MS=10000" in monitor_health, "monitor reads every 10 seconds")
    record(checks, "monitor_heartbeat_window", "RUNTIME_FRESH_MS=150000" in monitor and "RUNNING_STALE_MS=180000" in monitor and "EXPECTED_HEARTBEAT_SECONDS=60" in monitor_health, "minute heartbeat has bounded health thresholds")
    record(checks, "monitor_version", "VERSION='0.3.1'" in monitor and "VERSION='0.3.1'" in monitor_health and "scan-monitor.js?v=0.3.1" in monitor_html, "monitor stack uses v0.3.1")
    record(checks, "monitor_schema_guard", "validRuntime" in monitor and "invalid runtime schema" in monitor_health and "schemaVersion>=2" in monitor_health, "malformed runtime payloads are rejected")
    record(checks, "monitor_cache_generation", "monitor-v4" in worker and "scan-monitor-health.js" in worker, "service worker cache generation updated")

    record(checks, "publisher_conflict_retry", "error.code not in {409, 422}" in publisher_text and "ATLAS_PROGRESS_CONFLICT_RETRIES" in publisher_text, "GitHub content conflicts refetch SHA and retry")
    record(checks, "workflow_immediate_recovery", "run_scan_with_auto_recovery.py" in workflow and "diagnose_and_recover_scan_v2.py" in workflow, "failure investigation occurs inside the same job")
    record(checks, "workflow_generic_region", "all(item['regionGuess']==region" in workflow and "len(queue['items'])==3" not in workflow, "workflow is not hard-coded to one region or exactly three items")
    record(checks, "live_recovery_status", "publish_recovery(queue, recovery)" in orchestrator and 'state = "recovery"' in orchestrator, "diagnosis and retry decisions are published immediately")

    recovery = module_from("tools/diagnose_and_recover_scan_v2.py", "atlas_recovery_audit")
    sample_expectations = {
        "HTTP Error 412: Precondition Failed": "bilibili-http-412",
        "Response object does not support the context manager protocol": "curl-response-context-manager",
        "Invalid data found when processing input": "ffmpeg-invalid-data",
        "No space left on device": "runner-disk-space",
        "409 Conflict sha does not match": "github-contents-conflict",
        "CID mismatch": "multipart-page-identity"
    }
    for message, expected in sample_expectations.items():
        chosen, _ = recovery.match_entry(message, bugs)
        record(checks, f"dictionary_sample_{expected}", bool(chosen and chosen.get("id") == expected), message)

    manifest_412 = {"downloadBackoffSeconds": 60, "preferPublicApi": False}
    changed_412 = recovery.apply_action("increase_backoff_and_retry_public_api", {}, manifest_412)
    record(checks, "recovery_action_412", manifest_412["downloadBackoffSeconds"] == 120 and manifest_412["preferPublicApi"] is True and changed_412, "backoff doubled and public API preferred")

    manifest_context = {"analyzer": "tools/analyze_authorized_video_v9.py"}
    recovery.apply_action("use_v10_response_compatibility_adapter", {}, manifest_context)
    record(checks, "recovery_action_context_adapter", manifest_context["analyzer"].endswith("analyze_authorized_video_v10.py"), "v10 adapter selected")

    manifest_media = {"forceTranscodeFallback": False}
    recovery.apply_action("enable_transcode_fallback_and_retry", {}, manifest_media)
    record(checks, "recovery_action_transcode", manifest_media["forceTranscodeFallback"] is True, "transcode fallback enabled")

    manifest_timeout = {"perItemTimeoutSeconds": 5400, "maxSamplesA": 540}
    recovery.apply_action("extend_timeout_reduce_samples_and_retry", {}, manifest_timeout)
    record(checks, "recovery_action_timeout", manifest_timeout["perItemTimeoutSeconds"] == 7200 and manifest_timeout["maxSamplesA"] == 420, "timeout extended and sample pressure reduced")

    manifest_memory = {"maxSamplesA": 540, "minimumIntervalSeconds": 3.0}
    recovery.apply_action("reduce_memory_pressure_and_retry", {}, manifest_memory)
    record(checks, "recovery_action_memory", manifest_memory["maxSamplesA"] == 270 and manifest_memory["minimumIntervalSeconds"] == 4.5, "memory pressure reduced")

    redacted = recovery.safe_error("token=secret https://example.invalid/video /tmp/private-file")
    record(checks, "diagnostic_redaction", "secret" not in redacted and "example.invalid" not in redacted and "private-file" not in redacted, "credentials, URLs, and temporary paths redacted")

    publisher = module_from("tools/publish_runtime_progress.py", "atlas_publisher_audit")
    put_calls = {"count": 0}
    publisher._current_sha = lambda *_args, **_kwargs: "current-sha"
    publisher.time.sleep = lambda _seconds: None
    publisher.random.uniform = lambda _a, _b: 0.0

    def fake_request(url: str, token: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> dict[str, Any]:
        if method == "PUT":
            put_calls["count"] += 1
            if put_calls["count"] == 1:
                raise urllib.error.HTTPError(url, 409, "Conflict", hdrs=None, fp=None)
        return {}

    publisher._github_request = fake_request
    old_env = {key: os.environ.get(key) for key in ("ATLAS_PROGRESS_TOKEN", "ATLAS_PROGRESS_REPOSITORY", "ATLAS_PROGRESS_BRANCH", "ATLAS_PROGRESS_PATH")}
    os.environ.update({"ATLAS_PROGRESS_TOKEN": "audit-token", "ATLAS_PROGRESS_REPOSITORY": "owner/repo", "ATLAS_PROGRESS_BRANCH": "main", "ATLAS_PROGRESS_PATH": "progress.json"})
    try:
        published = publisher._publish_github({"stage": "audit", "progressPercent": 1})
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    record(checks, "publisher_conflict_simulation", published is True and put_calls["count"] == 2, "first 409 conflict recovered on second PUT")

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
