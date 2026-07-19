#!/usr/bin/env python3
"""Completion-aware static and executable audit for the Atlas scan stack."""
from __future__ import annotations

import importlib.util
import json
import pathlib
import urllib.error
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/batch-analysis/scan-system-health.json"


def read_json(path: str) -> Any:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def load_module(path: str, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: Any, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    bugs = read_json("data/scan-bug-dictionary.json")
    manifest = read_json("data/batch-analysis/eleven-pilot-scan-manifest.json")
    queue = read_json("data/batch-analysis/eleven-pilot-scan-queue.json")
    monitor = read_text("scan-monitor.js")
    monitor_html = read_text("scan-monitor.html")
    worker = read_text("sw.js")
    publisher_text = read_text("tools/publish_runtime_progress.py")
    workflow = read_text(".github/workflows/scan-eleven-pilot-v2.yml")
    analyzer = read_text("tools/analyze_authorized_video_v10.py")
    orchestrator = read_text("tools/run_scan_with_auto_recovery.py")

    entries = bugs.get("entries", [])
    ids = [entry.get("id") for entry in entries]
    layers = {entry.get("layer") for entry in entries}
    required_layers = {"source-download", "source-metadata", "identity", "http-client", "network", "media", "analysis", "runner", "progress-publish", "orchestration", "safety"}
    check("dictionary_size", len(entries) >= 18, f"{len(entries)} entries")
    check("dictionary_unique", len(ids) == len(set(ids)), "unique IDs")
    check("dictionary_patterns", all(entry.get("patterns") for entry in entries), "all signatures present")
    check("dictionary_actions", all(entry.get("autoAction") for entry in entries), "all actions present")
    check("dictionary_layers", required_layers <= layers, f"layers={sorted(layers)}")

    check("heartbeat_60_seconds", manifest.get("runtimeHeartbeat", {}).get("minimumIntervalSeconds") == 60, "60-second worker heartbeat")
    check("telemetry_60_seconds", manifest.get("downloadTelemetry", {}).get("intervalSeconds") == 60, "60-second download telemetry")
    check("v10_adapter", manifest.get("analyzer", "").endswith("analyze_authorized_video_v10.py") and "ClosingResponse" in analyzer, "curl response compatibility")
    check("bounded_queue", 1 <= len(queue.get("items", [])) <= 3 and manifest.get("maxItemsPerRun") == 1, "one active item and at most three queued")
    check("retention", manifest.get("retention", {}).get("originalVideo") is False and manifest.get("retention", {}).get("framePixels") is False, "no retained media pixels")

    check("monitor_poll", "const POLL_MS=10000" in monitor and "state.timer=setInterval(refresh,POLL_MS)" in monitor, "single 10-second controller")
    check("monitor_thresholds", "const HEARTBEAT_EXPECTED=60" in monitor and "const HEARTBEAT_WARN=150" in monitor and "const HEARTBEAT_FAIL=180" in monitor, "60/150/180-second thresholds")
    check("monitor_versions", "const VERSION='0.5.0'" in monitor and "scan-monitor.js?v=0.5.0" in monitor_html, "unified monitor version")
    check("monitor_schema", "const validRuntime=" in monitor and "runtimeNewer" in monitor, "runtime schema and monotonic guards")
    check("monitor_completion_priority", "Promise.all([read(paths.status,true),read(paths.queue,true),read(paths.runtime,true)])" in monitor and "finally" in monitor and "state.refreshing=false" in monitor, "core reads cannot remain permanently syncing")
    check("monitor_cache", "monitor-v7" in worker and "./scan-monitor.js" in worker and "scan-monitor-coherence.js" not in worker and "scan-monitor-download.js" not in worker, "cache generation v7 contains only unified controller")

    check("publisher_conflict_logic", "error.code not in {409, 422}" in publisher_text and "ATLAS_PROGRESS_CONFLICT_RETRIES" in publisher_text, "fresh-SHA conflict retry")
    check("same_job_recovery", "run_scan_with_auto_recovery.py" in workflow and "diagnose_and_recover_scan_v2.py" in workflow, "same-job diagnosis")
    check("generic_region", "all(item['regionGuess']==region" in workflow and "len(queue['items'])==3" not in workflow, "not hard-coded to one region")
    check("live_recovery", "publish_recovery(queue, recovery)" in orchestrator and 'state = "recovery"' in orchestrator, "live recovery state published")

    recovery = load_module("tools/diagnose_and_recover_scan_v2.py", "atlas_recovery_test")
    examples = {
        "HTTP Error 412: Precondition Failed": "bilibili-http-412",
        "Response object does not support the context manager protocol": "curl-response-context-manager",
        "Invalid data found when processing input": "ffmpeg-invalid-data",
        "No space left on device": "runner-disk-space",
        "409 Conflict sha does not match": "github-contents-conflict",
        "CID mismatch": "multipart-page-identity",
    }
    for message, expected in examples.items():
        matched, _ = recovery.match_entry(message, bugs)
        check(f"match_{expected}", matched and matched.get("id") == expected, message)

    sample = {"downloadBackoffSeconds": 60, "preferPublicApi": False}
    recovery.apply_action("increase_backoff_and_retry_public_api", {}, sample)
    check("action_412", sample == {"downloadBackoffSeconds": 120, "preferPublicApi": True}, "backoff and API fallback")

    sample = {"analyzer": "tools/analyze_authorized_video_v9.py"}
    recovery.apply_action("use_v10_response_compatibility_adapter", {}, sample)
    check("action_context", sample["analyzer"].endswith("analyze_authorized_video_v10.py"), "v10 compatibility action")

    sample = {"forceTranscodeFallback": False}
    recovery.apply_action("enable_transcode_fallback_and_retry", {}, sample)
    check("action_media", sample["forceTranscodeFallback"] is True, "transcode fallback action")

    sample = {"perItemTimeoutSeconds": 5400, "maxSamplesA": 540}
    recovery.apply_action("extend_timeout_reduce_samples_and_retry", {}, sample)
    check("action_timeout", sample == {"perItemTimeoutSeconds": 7200, "maxSamplesA": 420}, "timeout recovery action")

    sample = {"maxSamplesA": 540, "minimumIntervalSeconds": 3.0}
    recovery.apply_action("reduce_memory_pressure_and_retry", {}, sample)
    check("action_memory", sample == {"maxSamplesA": 270, "minimumIntervalSeconds": 4.5}, "memory recovery action")

    publisher = load_module("tools/publish_runtime_progress.py", "atlas_publisher_test")
    calls = {"put": 0}
    publisher._current_sha = lambda *_args, **_kwargs: "sha"
    publisher.time.sleep = lambda _seconds: None
    publisher.random.uniform = lambda _a, _b: 0.0
    publisher.os.getenv = lambda key, default="": {
        "ATLAS_PROGRESS_TOKEN": "audit",
        "ATLAS_PROGRESS_REPOSITORY": "owner/repo",
        "ATLAS_PROGRESS_BRANCH": "main",
        "ATLAS_PROGRESS_PATH": "progress.json",
        "ATLAS_PROGRESS_CONFLICT_RETRIES": "5",
    }.get(key, default)

    def fake_request(url: str, credential: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> dict[str, Any]:
        if method == "PUT":
            calls["put"] += 1
            if calls["put"] == 1:
                raise urllib.error.HTTPError(url, 409, "Conflict", hdrs=None, fp=None)
        return {}

    publisher._github_request = fake_request
    published = publisher._publish_github({"stage": "audit", "progressPercent": 1})
    check("publisher_409_simulation", published is True and calls["put"] == 2, "first conflict recovered on second write")

    media = []
    for pattern in ("*.mp4", "*.m4a", "*.webm", "*.flv"):
        media.extend(ROOT.rglob(pattern))
    check("repository_media_clean", not media, f"media files={len(media)}")

    passed = sum(item["passed"] for item in checks)
    report = {
        "schemaVersion": 2,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "pass" if passed == len(checks) else "fail",
        "summary": {"total": len(checks), "passed": passed, "failed": len(checks) - passed},
        "dictionaryVersion": bugs.get("version"),
        "checks": checks,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())