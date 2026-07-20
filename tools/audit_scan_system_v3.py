#!/usr/bin/env python3
"""Audit the Atlas scan, monitor, and heartbeat stack, including NEXT10 serial execution."""
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
    status = read_json("data/batch-analysis/eleven-pilot-scan-status.json")
    catalog = read_json("data/eleven-game-world-ac-shadows-catalog.json")
    monitor = read_text("scan-monitor.js")
    monitor_html = read_text("scan-monitor.html")
    worker = read_text("sw.js")
    workflow = read_text(".github/workflows/scan-eleven-pilot-v2.yml")
    supervisor_workflow = read_text(".github/workflows/supervise-eleven-heartbeat.yml")
    supervisor_config = read_json("data/batch-analysis/eleven-heartbeat-supervisor.json")
    supervisor_source = read_text("tools/supervise_runtime_heartbeat.py")
    publisher = read_text("tools/publish_runtime_progress.py")
    publisher_v2 = read_text("tools/publish_runtime_progress_v2.py")
    analyzer_v11 = read_text("tools/analyze_authorized_video_v11.py")
    analyzer_v12 = read_text("tools/analyze_authorized_video_v12.py")
    orchestrator = read_text("tools/run_scan_with_auto_recovery.py")
    orchestrator_v2 = read_text("tools/run_scan_with_auto_recovery_v2.py")

    entries = bugs.get("entries", [])
    ids = [entry.get("id") for entry in entries]
    required_layers = {"source-download", "source-metadata", "identity", "http-client", "network", "media", "analysis", "runner", "progress-publish", "orchestration", "heartbeat", "safety"}
    check("dictionary_size", len(entries) >= 25, f"{len(entries)} entries")
    check("dictionary_unique", len(ids) == len(set(ids)), "unique IDs")
    check("dictionary_complete", all(entry.get("patterns") and entry.get("autoAction") for entry in entries), "patterns and actions present")
    check("dictionary_layers", required_layers <= {entry.get("layer") for entry in entries}, "required layers present")
    check("cooldowns_bounded", next(entry for entry in entries if entry["id"] == "bilibili-http-412")["cooldownSeconds"] <= 45 and next(entry for entry in entries if entry["id"] == "bilibili-http-429")["cooldownSeconds"] <= 120, "network cooldowns bounded")

    invariants = release.get("invariants", {})
    check("release_version", release.get("version") == "0.9.4.5", "Alpha 0.9.4.5")
    check("release_full_audit", invariants.get("requireFullAuditAtThisRelease") is True, "full audit required")
    check("release_matrices", invariants.get("requiredHeartbeatMatrixChecks") == 500 and invariants.get("requiredBrowserMatrixChecks") == 500, "two exact 500-check gates")
    check("release_monitor_contract", invariants.get("singleMonitorController") is True and invariants.get("durableScanStateAlwaysWins") is True, "single durable monitor")
    check("release_next10_contract", invariants.get("heartbeatSupervisorMaximumQueueItems") == 10 and invariants.get("scanMaximumConcurrentDownloads") == 1 and invariants.get("scanAutoContinueAfterDurableSuccess") is True, "ten queued, one active, auto continue")

    items = queue.get("items", [])
    sequences = [item.get("sequence") for item in items]
    catalog_by_id = {item["id"]: item for item in catalog.get("items", [])}
    check("queue_exact_ten", len(items) == queue.get("maximumQueueItems") == manifest.get("maximumQueueItems") == 10, "exactly ten bounded items")
    check("queue_unique", len({item.get("externalSourceId") for item in items}) == 10, "ten unique sources")
    check("queue_chronological", sequences == sorted(sequences), f"sequence={sequences}")
    check("queue_skips_imported", queue.get("skippedAlreadyImportedPages") == [20, 21, 22], "P20-P22 do not consume slots")
    check("queue_region", all(item.get("regionGuess") == queue.get("pilotRegion") for item in items), "bounded batch label")
    check("queue_serial", queue.get("maximumConcurrentItems") == 1 and sum(item.get("state") in {"running", "recovery"} for item in items) <= 1, "maximum one active item")
    check("queue_auto_continue", queue.get("autoContinueAfterDurableSuccess") is True, "durable-success continuation")
    check("status_coherent", status.get("summary", {}).get("total") == len(items) and status.get("authorizationId") == queue.get("authorizationId"), "status matches queue")

    catalog_coherent = True
    for item in items:
        entry = catalog_by_id.get(item.get("externalSourceId"), {})
        catalog_state = entry.get("analysisStatus")
        if item.get("state") == "imported":
            catalog_coherent = catalog_coherent and catalog_state == "imported"
        else:
            catalog_coherent = catalog_coherent and catalog_state != "imported"
    check("queue_catalog_state", catalog_coherent, "imported and pending states agree with catalog")

    check("manifest_serial", manifest.get("maxItemsPerRun") == 1 and manifest.get("maximumConcurrentDownloads") == 1, "one item per run")
    check("manifest_auto_continue", manifest.get("autoContinueAfterDurableSuccess") is True, "auto continuation enabled")
    check("heartbeat_telemetry", manifest.get("runtimeHeartbeat", {}).get("minimumIntervalSeconds") == 30 and manifest.get("downloadTelemetry", {}).get("intervalSeconds") == 30, "30-second heartbeat and telemetry")
    check("v12_adapter", manifest.get("analyzer", "").endswith("analyze_authorized_video_v12.py") and "analyze_authorized_video_v11" in analyzer_v12, "v12 analyzer selected")
    check("adaptive_ranges", "ThreadPoolExecutor" in analyzer_v11 and manifest.get("downloadOptimization", {}).get("adaptiveParallelRanges") is True, "bounded range transfer")
    check("download_policy", manifest.get("downloadOptimization", {}).get("noArtificialRateLimit") is True and 2 <= int(manifest.get("downloadOptimization", {}).get("maxRangeWorkers", 0)) <= 4, "no artificial cap, bounded workers")
    check("retention", manifest.get("retention", {}).get("originalVideo") is False and manifest.get("retention", {}).get("framePixels") is False, "no retained media pixels")

    check("workflow_capacity", "len(items)==queue['maximumQueueItems']==manifest['maximumQueueItems']==10" in workflow, "ten-item workflow gate")
    check("workflow_serial", "Scan exactly one item" in workflow and "maximumConcurrentDownloads" in workflow, "one active scan")
    check("workflow_catalog_state", "if item.get('state')=='imported'" in workflow and "catalog_state=='imported'" in workflow, "catalog state remains coherent after each run")
    check("workflow_400_gate", "400/400 ten-item serial integrity and privacy checks passed" in workflow, "400-round scan gate")
    check("workflow_auto_continue", "Continue with exactly one next item after durable success" in workflow and "steps.decision.outputs.progressed == 'true'" in workflow, "next run only after durable success")

    check("monitor_poll", all(token in monitor for token in ("RAW_POLL_MS=5000", "API_POLL_MS=180000", "APPLY_TICK_MS=1000")), "5s raw, 180s API, 1s UI")
    check("monitor_thresholds", all(token in monitor for token in ("HEARTBEAT_EXPECTED=30", "HEARTBEAT_WARN=75", "HEARTBEAT_FAIL=150")), "heartbeat thresholds")
    check("monitor_version", "VERSION='0.6.0'" in monitor and "scan-monitor.js?v=0.6.0" in monitor_html, "monitor v0.6.0")
    check("monitor_single_controller", "scan-monitor-live-bridge" not in monitor_html and not (ROOT / "scan-monitor-live-bridge.js").exists(), "one monitor controller")
    check("monitor_durable_priority", "durable.state!=='imported'" in monitor and "持久状态优先" in monitor, "durable state wins")
    check("monitor_cache", "monitor-v11" in worker and "scan-monitor-live-bridge" not in worker, "single-monitor cache")

    policy = supervisor_config.get("policy", {})
    check("supervisor_capacity", supervisor_config.get("maximumQueueItems") == 10 and "len(queue['items'])==10" in supervisor_workflow, "ten-item supervisor gate")
    check("supervisor_serial", policy.get("oneItemPerRun") is True and policy.get("maximumConcurrentDownloads") == 1, "one-item supervisor policy")
    check("supervisor_auto_continue", policy.get("automaticContinuationAfterDurableSuccess") is True, "supervisor continuation policy")
    check("supervisor_thresholds", supervisor_config.get("staleAfterSeconds") == 90 and supervisor_config.get("hardStaleAfterSeconds") == 180, "90/180-second thresholds")
    check("supervisor_dedup", supervisor_config.get("resumeCooldownSeconds") == 360 and policy.get("deduplicateResumeRequests") is True and "resume_permitted" in supervisor_source, "resume deduplication")
    check("supervisor_durable", policy.get("durableStateAlwaysWins") is True and "stale_terminal_heartbeat" in supervisor_source, "durable reconciliation")
    check("supervisor_safety", all(token in supervisor_source for token in ("sourceCodeModified", "authorizationBroadened", "queueScopeExpanded", "mediaRetentionChanged")), "bounded repair safety")

    check("publisher_conflict", "error.code not in {409, 422}" in publisher and "ATLAS_PROGRESS_CONFLICT_RETRIES" in publisher, "fresh-SHA conflict retry")
    check("telemetry_preservation", "PRESERVE_STAGES" in publisher_v2 and "telemetryMeasuredAt" in publisher_v2, "same-item telemetry preserved")
    check("same_job_recovery", "diagnose_and_recover_scan_v2.py" in orchestrator and "analyze_authorized_video_v12.py" in orchestrator_v2, "same-job bounded recovery")
    check("success_projection", "publish_durable_projection(queue)" in orchestrator and "clear_stale_recovery(queue)" in orchestrator, "success projects next item")

    recovery = load_module("tools/diagnose_and_recover_scan_v2.py", "atlas_recovery_next10_test")
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

    base_publisher = load_module("tools/publish_runtime_progress.py", "atlas_publisher_next10_test")
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
    check("publisher_409_simulation", base_publisher._publish_github({"stage": "audit", "progressPercent": 1}) is True and calls["put"] == 2, "first conflict recovered")
    media = [path for pattern in ("*.mp4", "*.m4a", "*.webm", "*.flv") for path in ROOT.rglob(pattern)]
    check("repository_media_clean", not media, f"media files={len(media)}")
    check("release_assets_exist", all((ROOT / path).exists() for path in release.get("releaseAssets", [])), "all release assets exist")

    passed = sum(item["passed"] for item in checks)
    report = {
        "schemaVersion": 5,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "pass" if passed == len(checks) else "fail",
        "summary": {"total": len(checks), "passed": passed, "failed": len(checks) - passed},
        "dictionaryVersion": bugs.get("version"),
        "release": release.get("version"),
        "queueItems": len(items),
        "maximumConcurrentItems": queue.get("maximumConcurrentItems"),
        "checks": checks,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
