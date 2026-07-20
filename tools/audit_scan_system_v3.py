#!/usr/bin/env python3
"""Executable full audit for the Atlas v12 scan, monitor, and heartbeat stack."""
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
    release = read_json("release-manifest.json")
    queue = read_json("data/batch-analysis/eleven-pilot-scan-queue.json")
    monitor = read_text("scan-monitor.js")
    monitor_html = read_text("scan-monitor.html")
    worker = read_text("sw.js")
    publisher = read_text("tools/publish_runtime_progress.py")
    publisher_v2 = read_text("tools/publish_runtime_progress_v2.py")
    analyzer_v11 = read_text("tools/analyze_authorized_video_v11.py")
    analyzer_v12 = read_text("tools/analyze_authorized_video_v12.py")
    workflow = read_text(".github/workflows/scan-eleven-pilot-v2.yml")
    supervisor_workflow = read_text(".github/workflows/supervise-eleven-heartbeat.yml")
    supervisor_config = read_json("data/batch-analysis/eleven-heartbeat-supervisor.json")
    supervisor_source = read_text("tools/supervise_runtime_heartbeat.py")
    orchestrator = read_text("tools/run_scan_with_auto_recovery.py")
    orchestrator_v2 = read_text("tools/run_scan_with_auto_recovery_v2.py")

    entries = bugs.get("entries", [])
    ids = [entry.get("id") for entry in entries]
    layers = {entry.get("layer") for entry in entries}
    required_layers = {"source-download", "source-metadata", "identity", "http-client", "network", "media", "analysis", "runner", "progress-publish", "orchestration", "heartbeat", "safety"}
    check("dictionary_size", len(entries) >= 25, f"{len(entries)} entries")
    check("dictionary_unique", len(ids) == len(set(ids)), "unique IDs")
    check("dictionary_patterns", all(entry.get("patterns") for entry in entries), "all signatures present")
    check("dictionary_actions", all(entry.get("autoAction") for entry in entries), "all actions present")
    check("dictionary_layers", required_layers <= layers, f"layers={sorted(layers)}")
    check("fast_412_cooldown", next(entry for entry in entries if entry["id"] == "bilibili-http-412")["cooldownSeconds"] <= 45, "412 cooldown <=45s")
    check("bounded_429_cooldown", next(entry for entry in entries if entry["id"] == "bilibili-http-429")["cooldownSeconds"] <= 120, "429 cooldown <=120s")

    check("release_0945", release.get("version") == "0.9.4.5" and release.get("invariants", {}).get("requireFullAuditAtThisRelease") is True, "Alpha 0.9.4.5 full audit required")
    check("release_heartbeat_matrix", release.get("invariants", {}).get("requiredHeartbeatMatrixChecks") == 500, "exact heartbeat matrix contract")
    check("release_single_monitor", release.get("invariants", {}).get("singleMonitorController") is True, "single monitor owner")
    check("release_durable_priority", release.get("invariants", {}).get("durableScanStateAlwaysWins") is True, "durable state wins")

    check("heartbeat_30_seconds", manifest.get("runtimeHeartbeat", {}).get("minimumIntervalSeconds") == 30, "30-second worker heartbeat")
    check("telemetry_30_seconds", manifest.get("downloadTelemetry", {}).get("intervalSeconds") == 30, "30-second download telemetry")
    check("v12_adapter", manifest.get("analyzer", "").endswith("analyze_authorized_video_v12.py") and "analyze_authorized_video_v11" in analyzer_v12, "v12 analyzer selected")
    check("adaptive_ranges", "ThreadPoolExecutor" in analyzer_v11 and "Range" in analyzer_v11 and manifest.get("downloadOptimization", {}).get("adaptiveParallelRanges") is True, "bounded HTTP range transfer")
    check("no_rate_limit", manifest.get("downloadOptimization", {}).get("noArtificialRateLimit") is True, "no artificial bandwidth cap")
    check("range_workers", 2 <= int(manifest.get("downloadOptimization", {}).get("maxRangeWorkers", 0)) <= 4, "bounded parallel workers")
    check("range_resume", "rangeRetries" in analyzer_v11 and "fallbackToResumableSingleStream" in json.dumps(manifest), "range resume and single-stream fallback")
    check("balanced_sampling", all(token in analyzer_v11 for token in ("balanced-high", "balanced", "fast-review", "qualitySpeedPolicy")), "catalog-aware sample profiles")
    check("bounded_queue", 1 <= len(queue.get("items", [])) <= 5 and manifest.get("maxItemsPerRun") == 1, "up to five queued, one item per run")
    check("retention", manifest.get("retention", {}).get("originalVideo") is False and manifest.get("retention", {}).get("framePixels") is False, "no retained media pixels")

    check("monitor_poll", all(token in monitor for token in ("RAW_POLL_MS=5000", "API_POLL_MS=180000", "APPLY_TICK_MS=1000")), "5s raw, 180s API, 1s UI")
    check("monitor_thresholds", all(token in monitor for token in ("HEARTBEAT_EXPECTED=30", "HEARTBEAT_WARN=75", "HEARTBEAT_FAIL=150")), "30/75/150-second monitor thresholds")
    check("monitor_version", "VERSION='0.6.0'" in monitor and "scan-monitor.js?v=0.6.0" in monitor_html, "monitor v0.6.0 pinned")
    check("monitor_single_controller", "scan-monitor-live-bridge" not in monitor_html and not (ROOT / "scan-monitor-live-bridge.js").exists(), "obsolete competing controller removed")
    check("monitor_authoritative_api", "GitHub Contents API" in monitor and "readApi" in monitor, "bounded authoritative calibration")
    check("monitor_durable_priority", "durable.state!=='imported'" in monitor and "relevantRecovery" in monitor and "持久状态优先" in monitor, "imported state rejects stale runtime")
    check("monitor_terminal_telemetry", "上一任务最终实测" in monitor and "不再作为当前任务心跳" in monitor, "historical telemetry cannot become active heartbeat")
    check("monitor_supervisor_visibility", "eleven-heartbeat-supervisor-state.json" in monitor and "心跳监督" in monitor, "supervisor state is visible")
    check("monitor_cache", "monitor-v11" in worker and "scan-monitor.js" in worker and "scan-monitor-live-bridge" not in worker, "monitor cache generation v11")

    policy = supervisor_config.get("policy", {})
    check("supervisor_thresholds", supervisor_config.get("staleAfterSeconds") == 90 and supervisor_config.get("hardStaleAfterSeconds") == 180, "90/180-second supervisor thresholds")
    check("supervisor_dedup_policy", supervisor_config.get("resumeCooldownSeconds") == 360 and policy.get("deduplicateResumeRequests") is True, "360-second resume deduplication")
    check("supervisor_durable_policy", policy.get("durableStateAlwaysWins") is True and policy.get("terminalProjectionRequired") is True, "durable terminal projection policy")
    check("supervisor_five_item_gate", "1<=len(queue['items'])<=5" in supervisor_workflow, "five-item safety gate")
    check("supervisor_persists_projection", "data/runtime-progress/eleven-pilot-progress.json" in supervisor_workflow and "projectionWritten" in supervisor_workflow, "runtime projection persisted")
    check("supervisor_terminal_logic", "stale_terminal_heartbeat" in supervisor_source and "publish_terminal_projection_and_resume_pending" in supervisor_source, "terminal runtime reconciliation")
    check("supervisor_resume_dedup", "resume_permitted" in supervisor_source and "resumeSuppressedByCooldown" in supervisor_source, "duplicate dispatch suppression")
    check("supervisor_safety", all(token in supervisor_source for token in ("sourceCodeModified", "authorizationBroadened", "queueScopeExpanded", "mediaRetentionChanged")), "repair safety invariants")

    check("publisher_conflict_logic", "error.code not in {409, 422}" in publisher and "ATLAS_PROGRESS_CONFLICT_RETRIES" in publisher, "fresh-SHA conflict retry")
    check("telemetry_preservation", "PRESERVE_STAGES" in publisher_v2 and "telemetryMeasuredAt" in publisher_v2 and "externalSourceId" in publisher_v2, "same-item metrics preserved across stages")
    check("same_job_recovery", "run_scan_with_auto_recovery_v2.py" in workflow and "diagnose_and_recover_scan_v2.py" in orchestrator, "same-job diagnosis")
    check("v12_recovery_normalization", "analyze_authorized_video_v12.py" in orchestrator_v2 and "diagnose_and_recover_scan_v2.py" in orchestrator_v2, "retries remain on v12")
    check("success_projection", "publish_durable_projection(queue)" in orchestrator and "clear_stale_recovery(queue)" in orchestrator, "success clears stale recovery and publishes terminal projection")
    check("generic_region", "all(item['regionGuess']==region" in workflow and "len(queue['items'])==3" not in workflow, "not hard-coded to one region")
    check("live_recovery", "publish_recovery(queue, recovery)" in orchestrator, "live recovery state published")

    recovery = load_module("tools/diagnose_and_recover_scan_v2.py", "atlas_recovery_v4_test")
    examples = {
        "HTTP Error 412: Precondition Failed": "bilibili-http-412",
        "curl: (18) end of response with bytes missing": "curl-transport",
        "range request was not honored": "range-not-supported",
        "content-length mismatch after resumed transfer": "download-truncated",
        "409 Conflict sha does not match": "github-contents-conflict",
        "CID mismatch": "multipart-page-identity",
        "OpenCV could not open the downloaded video": "opencv-open-failure",
    }
    for message, expected in examples.items():
        matched, _ = recovery.match_entry(message, bugs)
        check(f"match_{expected}", matched and matched.get("id") == expected, message)

    sample_manifest = {"downloadBackoffSeconds": 900, "preferPublicApi": False, "recoveryPolicy": {"fastCooldownCapSeconds": 180}, "downloadOptimization": {}}
    changed = recovery.apply_action("fast_backoff_public_api_and_adaptive_range", {"attemptCount": 2}, sample_manifest)
    check("action_412", sample_manifest["downloadBackoffSeconds"] == 40 and sample_manifest["preferPublicApi"] is True and changed.get("adaptiveParallelRanges") is True, "bounded public API plus adaptive ranges")
    sample_manifest = {"downloadOptimization": {}}
    changed = recovery.apply_action("fallback_resumable_single_stream", {"attemptCount": 1}, sample_manifest)
    check("action_range_fallback", changed.get("adaptiveParallelRanges") is False and changed.get("fallbackToResumableSingleStream") is True, "single-stream fallback")
    sample_manifest = {"forceTranscodeFallback": False}
    recovery.apply_action("enable_transcode_fallback_and_retry", {}, sample_manifest)
    check("action_media", sample_manifest["forceTranscodeFallback"] is True, "transcode fallback")
    sample_manifest = {"perItemTimeoutSeconds": 5400, "maxSamplesA": 540, "maxSamplesDefault": 360}
    recovery.apply_action("extend_timeout_reduce_samples_and_retry", {}, sample_manifest)
    check("action_timeout", sample_manifest == {"perItemTimeoutSeconds": 6300, "maxSamplesA": 480, "maxSamplesDefault": 300}, "timeout quality/speed recovery")

    base_publisher = load_module("tools/publish_runtime_progress.py", "atlas_publisher_v4_test")
    calls = {"put": 0}
    base_publisher._current_sha = lambda *_args, **_kwargs: "sha"
    base_publisher.time.sleep = lambda _seconds: None
    base_publisher.random.uniform = lambda _a, _b: 0.0
    base_publisher.os.getenv = lambda key, default="": {"ATLAS_PROGRESS_TOKEN": "audit", "ATLAS_PROGRESS_REPOSITORY": "owner/repo", "ATLAS_PROGRESS_BRANCH": "main", "ATLAS_PROGRESS_PATH": "progress.json", "ATLAS_PROGRESS_CONFLICT_RETRIES": "5"}.get(key, default)

    def fake_request(url: str, credential: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> dict[str, Any]:
        if method == "PUT":
            calls["put"] += 1
            if calls["put"] == 1:
                raise urllib.error.HTTPError(url, 409, "Conflict", hdrs=None, fp=None)
        return {}

    base_publisher._github_request = fake_request
    published = base_publisher._publish_github({"stage": "audit", "progressPercent": 1})
    check("publisher_409_simulation", published is True and calls["put"] == 2, "first conflict recovered on second write")

    media = []
    for pattern in ("*.mp4", "*.m4a", "*.webm", "*.flv"):
        media.extend(ROOT.rglob(pattern))
    check("repository_media_clean", not media, f"media files={len(media)}")
    release_assets = release.get("releaseAssets", [])
    check("release_assets_exist", all((ROOT / path).exists() for path in release_assets), "all release assets exist")

    passed = sum(item["passed"] for item in checks)
    report = {
        "schemaVersion": 4,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "pass" if passed == len(checks) else "fail",
        "summary": {"total": len(checks), "passed": passed, "failed": len(checks) - passed},
        "dictionaryVersion": bugs.get("version"),
        "release": release.get("version"),
        "checks": checks,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
