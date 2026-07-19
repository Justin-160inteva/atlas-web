#!/usr/bin/env python3
"""Executable audit for the Atlas v12 adaptive scan and realtime monitor stack."""
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
    bridge = read_text("scan-monitor-live-bridge.js")
    monitor_html = read_text("scan-monitor.html")
    worker = read_text("sw.js")
    publisher = read_text("tools/publish_runtime_progress.py")
    publisher_v2 = read_text("tools/publish_runtime_progress_v2.py")
    analyzer_v11 = read_text("tools/analyze_authorized_video_v11.py")
    analyzer_v12 = read_text("tools/analyze_authorized_video_v12.py")
    workflow = read_text(".github/workflows/scan-eleven-pilot-v2.yml")
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

    check("heartbeat_30_seconds", manifest.get("runtimeHeartbeat", {}).get("minimumIntervalSeconds") == 30, "30-second worker heartbeat")
    check("telemetry_30_seconds", manifest.get("downloadTelemetry", {}).get("intervalSeconds") == 30, "30-second download telemetry")
    check("v12_adapter", manifest.get("analyzer", "").endswith("analyze_authorized_video_v12.py") and "analyze_authorized_video_v11" in analyzer_v12, "v12 analyzer selected")
    check("adaptive_ranges", "ThreadPoolExecutor" in analyzer_v11 and "Range" in analyzer_v11 and manifest.get("downloadOptimization", {}).get("adaptiveParallelRanges") is True, "bounded HTTP range transfer")
    check("no_rate_limit", manifest.get("downloadOptimization", {}).get("noArtificialRateLimit") is True, "no artificial bandwidth cap")
    check("range_workers", 2 <= int(manifest.get("downloadOptimization", {}).get("maxRangeWorkers", 0)) <= 4, "bounded parallel workers")
    check("range_resume", "rangeRetries" in analyzer_v11 and "fallbackToResumableSingleStream" in json.dumps(manifest), "range resume and single-stream fallback")
    check("balanced_sampling", all(token in analyzer_v11 for token in ("balanced-high", "balanced", "fast-review", "qualitySpeedPolicy")), "catalog-aware sample profiles")
    check("bounded_queue", 1 <= len(queue.get("items", [])) <= 3 and manifest.get("maxItemsPerRun") == 1, "one item per run")
    check("retention", manifest.get("retention", {}).get("originalVideo") is False and manifest.get("retention", {}).get("framePixels") is False, "no retained media pixels")

    check("monitor_poll", "POLL_MS=10000" in monitor and "RAW_POLL=5000" in bridge and "APPLY_TICK=1000" in bridge, "10s core, 5s raw, 1s projection")
    check("monitor_thresholds", "heartbeatAge<=75" in bridge and "heartbeatAge>150" in bridge, "30/75/150-second monitor thresholds")
    check("monitor_versions", "VERSION='0.2.1'" in bridge and "scan-monitor-live-bridge.js?v=0.2.1" in monitor_html, "realtime bridge version coherent")
    check("monitor_authoritative_api", "API_POLL=65000" in bridge and "GitHub Contents API" in bridge, "bounded authoritative API calibration")
    check("monitor_projection", "MAX_PROJECT=35" in bridge and "实时估算" in bridge and "最近实测" in bridge, "clearly labelled short projection")
    check("monitor_recovery_retention", "telemetryMeasuredAt" in bridge and "保留最后下载实测" in bridge, "recovery does not zero last measured telemetry")
    check("monitor_cache", "monitor-v10" in worker and "scan-monitor-live-bridge.js" in worker, "cache generation v10")

    check("publisher_conflict_logic", "error.code not in {409, 422}" in publisher and "ATLAS_PROGRESS_CONFLICT_RETRIES" in publisher, "fresh-SHA conflict retry")
    check("telemetry_preservation", "PRESERVE_STAGES" in publisher_v2 and "telemetryMeasuredAt" in publisher_v2 and "externalSourceId" in publisher_v2, "same-item metrics preserved across stages")
    check("same_job_recovery", "run_scan_with_auto_recovery_v2.py" in workflow and "diagnose_and_recover_scan_v2.py" in read_text("tools/run_scan_with_auto_recovery.py"), "same-job diagnosis")
    check("v12_recovery_normalization", "analyze_authorized_video_v12.py" in orchestrator_v2 and "diagnose_and_recover_scan_v2.py" in orchestrator_v2, "retries remain on v12")
    check("generic_region", "all(item['regionGuess']==region" in workflow and "len(queue['items'])==3" not in workflow, "not hard-coded to one region")
    check("live_recovery", "publish_recovery(queue, recovery)" in read_text("tools/run_scan_with_auto_recovery.py"), "live recovery state published")

    recovery = load_module("tools/diagnose_and_recover_scan_v2.py", "atlas_recovery_v3_test")
    examples = {
        "HTTP Error 412: Precondition Failed": "bilibili-http-412",
        "curl: (18) end of response with bytes missing": "curl-transport",
        "range request was not honored": "range-not-supported",
        "content-length mismatch after resumed transfer": "download-truncated",
        "409 Conflict sha does not match": "github-contents-conflict",
        "CID mismatch": "multipart-page-identity",
    }
    for message, expected in examples.items():
        matched, _ = recovery.match_entry(message, bugs)
        check(f"match_{expected}", matched and matched.get("id") == expected, message)

    sample_manifest = {"downloadBackoffSeconds": 900, "preferPublicApi": False, "recoveryPolicy": {"fastCooldownCapSeconds": 180}, "downloadOptimization": {}}
    changed = recovery.apply_action("fast_backoff_public_api_and_adaptive_range", {"attemptCount": 2}, sample_manifest)
    check("action_412", sample_manifest["downloadBackoffSeconds"] == 90 and sample_manifest["preferPublicApi"] is True and changed.get("adaptiveParallelRanges") is True, "fast public API plus adaptive ranges")

    sample_manifest = {"downloadOptimization": {}}
    changed = recovery.apply_action("fallback_resumable_single_stream", {"attemptCount": 1}, sample_manifest)
    check("action_range_fallback", changed.get("adaptiveParallelRanges") is False and changed.get("fallbackToResumableSingleStream") is True, "single-stream fallback")

    sample_manifest = {"forceTranscodeFallback": False}
    recovery.apply_action("enable_transcode_fallback_and_retry", {}, sample_manifest)
    check("action_media", sample_manifest["forceTranscodeFallback"] is True, "transcode fallback")

    sample_manifest = {"perItemTimeoutSeconds": 5400, "maxSamplesA": 540, "maxSamplesDefault": 360}
    recovery.apply_action("extend_timeout_reduce_samples_and_retry", {}, sample_manifest)
    check("action_timeout", sample_manifest == {"perItemTimeoutSeconds": 6600, "maxSamplesA": 480, "maxSamplesDefault": 300}, "timeout quality/speed recovery")

    base_publisher = load_module("tools/publish_runtime_progress.py", "atlas_publisher_v3_test")
    calls = {"put": 0}
    base_publisher._current_sha = lambda *_args, **_kwargs: "sha"
    base_publisher.time.sleep = lambda _seconds: None
    base_publisher.random.uniform = lambda _a, _b: 0.0
    base_publisher.os.getenv = lambda key, default="": {
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

    base_publisher._github_request = fake_request
    published = base_publisher._publish_github({"stage": "audit", "progressPercent": 1})
    check("publisher_409_simulation", published is True and calls["put"] == 2, "first conflict recovered on second write")

    media = []
    for pattern in ("*.mp4", "*.m4a", "*.webm", "*.flv"):
        media.extend(ROOT.rglob(pattern))
    check("repository_media_clean", not media, f"media files={len(media)}")

    passed = sum(item["passed"] for item in checks)
    report = {
        "schemaVersion": 3,
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
