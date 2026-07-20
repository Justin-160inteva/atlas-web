#!/usr/bin/env python3
"""Audit Atlas scan safety, serial execution, watchdog health and v14 transport."""
from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
import urllib.error
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/batch-analysis/scan-system-health.json"
EXPECTED_PAGES = list(range(25, 36))
EXPECTED_BATCH = "eleven-production-p025-p035-v1"


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
    publisher = read_text("tools/publish_runtime_progress.py")
    publisher_v2 = read_text("tools/publish_runtime_progress_v2.py")
    analyzer_v11 = read_text("tools/analyze_authorized_video_v11.py")
    analyzer_v13 = read_text("tools/analyze_authorized_video_v13.py")
    analyzer_v14 = read_text("tools/analyze_authorized_video_v14.py")
    transport_v13 = read_text("tools/bilibili_transport_v13.py")
    resume_v14 = read_text("tools/resumable_transport_v14.py")
    smoke_v14 = read_text("tools/bilibili_transport_v14_smoke.py")
    orchestrator = read_text("tools/run_scan_with_auto_recovery.py")
    orchestrator_v2 = read_text("tools/run_scan_with_auto_recovery_v2.py")

    entries = bugs.get("entries", [])
    ids = [entry.get("id") for entry in entries]
    required_layers = {
        "source-download", "source-metadata", "identity", "http-client", "network",
        "media", "analysis", "runner", "progress-publish", "orchestration",
        "heartbeat", "safety",
    }
    check("dictionary_size", len(entries) >= 27, f"{len(entries)} entries")
    check("dictionary_unique", len(ids) == len(set(ids)), "unique IDs")
    check("dictionary_complete", all(entry.get("patterns") and entry.get("autoAction") for entry in entries), "patterns and actions present")
    check("dictionary_layers", required_layers <= {entry.get("layer") for entry in entries}, "required layers present")
    check("cooldowns_bounded", next(entry for entry in entries if entry["id"] == "bilibili-http-412")["cooldownSeconds"] <= 45 and next(entry for entry in entries if entry["id"] == "bilibili-http-429")["cooldownSeconds"] <= 120, "network cooldowns bounded")

    invariants = release.get("invariants", {})
    check("release_version", release.get("version") == "0.9.4.8", "Alpha 0.9.4.8")
    check("release_audit_cycle", invariants.get("requireFullAuditAtThisRelease") is True and invariants.get("nextRequiredFullAuditVersion") == "0.9.4.11", "audit cadence preserved")
    check("release_matrices", all(invariants.get(key) == 500 for key in ("requiredHeartbeatMatrixChecks", "requiredBrowserMatrixChecks", "requiredDataCenterMatrixChecks", "requiredSerialQueueOrderChecks", "requiredMonitorBatchAuthorityChecks", "requiredQueueSchemaChecks")), "six exact 500-check gates")
    check("release_serial11_contract", invariants.get("heartbeatSupervisorMaximumQueueItems") == 11 and invariants.get("scanMaximumConcurrentDownloads") == 1 and invariants.get("scanAutoContinueAfterDurableSuccess") is True, "eleven queued, one active")
    check("release_transport_contract", invariants.get("requiredSourceTransportChecks") == 128 and invariants.get("sourceTransportUsesSignedWbi") is True and invariants.get("sourceTransportPreservesCdnResume") is True, "128-check signed WBI transport")
    check("release_transport_v14_contract", all(invariants.get(key) is True for key in ("sourceTransportRequiresExactContentRange", "sourceTransportSafeRestartsIgnoredRanges", "sourceTransportValidatesResponseBodyLength", "sourceTransportSynchronizesDurableBytes")), "v14 byte-safety invariants")
    check("validation_review_contract", invariants.get("perReleaseValidationReviewRequired") is True and invariants.get("skipUnrelatedValidationMatrices") is True, "watchdog and test-speed review retained")

    items = queue.get("items", [])
    status_items = {item.get("externalSourceId"): item for item in status.get("items", [])}
    catalog_by_id = {item.get("id"): item for item in catalog.get("items", [])}
    sequences = [item.get("sequence") for item in items]
    check("queue_exact_eleven", len(items) == queue.get("maximumQueueItems") == manifest.get("maximumQueueItems") == 11, "exactly eleven bounded items")
    check("queue_unique", len({item.get("externalSourceId") for item in items}) == 11, "eleven unique sources")
    check("queue_chronological", sequences == EXPECTED_PAGES, f"sequence={sequences}")
    check("queue_serial", queue.get("maximumConcurrentItems") == 1 and sum(item.get("state") in {"running", "recovery"} for item in items) <= 1, "maximum one active item")
    check("queue_auto_continue", queue.get("autoContinueAfterDurableSuccess") is True, "durable-success continuation")
    check("queue_status_batch_identity", queue.get("queueId") == status.get("batchId") == EXPECTED_BATCH, "batch identity coherent")
    check("queue_authorization_identity", queue.get("authorizationId") == status.get("authorizationId") == catalog.get("authorizationId"), "authorization coherent")
    check("queue_region", all(item.get("regionGuess") == queue.get("pilotRegion") for item in items), "bounded batch label")
    check("queue_no_skips", queue.get("skippedAlreadyImportedPages") == [], "P25-P35 all included")
    check("status_coherent", status.get("summary", {}).get("total") == len(items) and len(status_items) == 11, "status matches queue")
    check("queue_catalog_projection", all((catalog_by_id.get(item.get("externalSourceId"), {}).get("analysisStatus") == "imported") == (item.get("state") == "imported") for item in items), "catalog projection matches durable queue")

    allowed = {"pending", "queued", "running", "recovery", "failed", "imported"}
    for expected_page, item in zip(EXPECTED_PAGES, items):
        external_id = item.get("externalSourceId")
        check(
            f"queue_item_{expected_page}",
            item.get("sequence") == expected_page
            and external_id in catalog_by_id
            and external_id in status_items
            and item.get("state", "pending") in allowed,
            f"P{expected_page} identity/state coherent",
        )

    optimization = manifest.get("downloadOptimization", {})
    fixes = manifest.get("compatibilityFixes", {})
    check("manifest_batch", manifest.get("id") == EXPECTED_BATCH and manifest.get("pilotRegion") == queue.get("pilotRegion"), "manifest targets P25-P35")
    check("manifest_serial", manifest.get("maxItemsPerRun") == 1 and manifest.get("maximumConcurrentDownloads") == 1, "one item per run")
    check("manifest_auto_continue", manifest.get("autoContinueAfterDurableSuccess") is True, "auto continuation enabled")
    check("heartbeat_telemetry", manifest.get("runtimeHeartbeat", {}).get("minimumIntervalSeconds") == 30 and manifest.get("downloadTelemetry", {}).get("intervalSeconds") == 30, "30-second heartbeat")
    check("v13_adapter", "import analyze_authorized_video_v13 as v13" in analyzer_v14 and "bilibili_transport_v13" in analyzer_v13, "v14 safely extends verified v13 identity/metadata path")
    check("v14_adapter", manifest.get("analyzer", "").endswith("analyze_authorized_video_v14.py") and "_single_stream_resume_v14" in analyzer_v14, "v14 analyzer selected")
    check("adaptive_ranges", "ThreadPoolExecutor" in analyzer_v11 and optimization.get("adaptiveParallelRanges") is True, "bounded range transfer")
    check("download_policy", optimization.get("noArtificialRateLimit") is True and 2 <= int(optimization.get("maxRangeWorkers", 0)) <= 4, "no artificial cap, bounded workers")
    check("wbi_metadata", all(token in analyzer_v13 + transport_v13 for token in ("x/player/wbi/playurl", "extract_mixin_key", "sign_wbi_params", "verified catalog CID")), "signed metadata bypasses blocked webpage")
    check("cdn_rotation_resume", all(token in analyzer_v13 + transport_v13 for token in ("stream_candidates", "Keep a valid partial target", "backupUrl")) and optimization.get("preservePartialAcrossCdnCandidates") is True, "partial bytes survive CDN failover")
    check("strict_content_range", fixes.get("strictContentRangeResume") is True and optimization.get("requireExactContentRangeStart") is True and "range_start == offset" in resume_v14, "append only at exact offset")
    check("safe_restart", fixes.get("safeRestartOnIgnoredRange") is True and optimization.get("safeRestartWhenRangeIgnored") is True and 'mode = "wb"' in resume_v14 and "target.unlink" in analyzer_v14, "ignored ranges overwrite residue")
    check("body_length_validation", fixes.get("midStreamTruncationRecovery") is True and optimization.get("validateResponseBodyLength") is True and "expected_payload_bytes" in resume_v14, "truncated bodies stay retryable")
    check("durable_chunk_accounting", fixes.get("durableChunkAccounting") is True and optimization.get("synchronizeChunkAccounting") is True and "target.stat().st_size" in analyzer_v14, "heartbeat follows durable bytes")
    check("retention", manifest.get("retention", {}).get("originalVideo") is False and manifest.get("retention", {}).get("framePixels") is False, "no retained media pixels")

    check("workflow_capacity", "len(items)==queue['maximumQueueItems']==manifest['maximumQueueItems']==11" in workflow, "eleven-item workflow gate")
    check("workflow_serial", "Scan exactly one item" in workflow and "maximumConcurrentDownloads" in workflow, "one active scan")
    check("workflow_transport_gate", "128-check byte-accurate" in workflow and "bilibili_transport_v14_smoke.py" in workflow, "v14 gate runs before media transfer")
    check("workflow_v14_compile", all(path in workflow for path in ("resumable_transport_v14.py", "analyze_authorized_video_v14.py", "bilibili_transport_v14_smoke.py")), "v14 stack compiled")
    check("workflow_privacy_gate", "400/400 eleven-item serial integrity and privacy checks passed" in workflow, "400-round runtime gate")
    check("workflow_auto_continue", "Continue with exactly one next item after durable success" in workflow and "steps.decision.outputs.progressed == 'true'" in workflow, "next run only after durable success")
    check("orchestrator_v14", "analyze_authorized_video_v14.py" in orchestrator_v2 and "strictContentRangeResume" in orchestrator_v2, "recovery cannot downgrade transport")
    check("analyzer_entrypoint", "raise SystemExit(v9.v6.main())" in analyzer_v14 and "runner.download_with_fallbacks" in analyzer_v14, "established analyzer entrypoint retained")

    check("monitor_poll", all(token in monitor for token in ("RAW_POLL_MS", "API_POLL_MS", "APPLY_TICK_MS")) and all(value in monitor for value in ("5000", "180000", "1000")), "5s raw, 180s API, 1s UI")
    check("monitor_thresholds", all(token in monitor for token in ("HEARTBEAT_EXPECTED", "HEARTBEAT_WARN", "HEARTBEAT_FAIL")) and all(value in monitor for value in ("30", "75", "150")), "heartbeat thresholds")
    check("monitor_version", "VERSION = '0.6.1'" in monitor and "scan-monitor.js?v=0.6.1" in monitor_html, "monitor v0.6.1")
    check("monitor_single_controller", "scan-monitor-live-bridge" not in monitor_html and "scan-monitor-live-bridge" not in worker, "single monitor owner")
    check("supervisor_capacity", supervisor_config.get("maximumQueueItems") == 11 and "len(queue['items'])==11" in supervisor_workflow, "eleven-item supervisor gate")
    check("supervisor_serial", supervisor_config.get("policy", {}).get("oneItemPerRun") is True and supervisor_config.get("policy", {}).get("maximumConcurrentDownloads") == 1, "one-item watchdog policy")
    check("telemetry_preservation", "PRESERVE_STAGES" in publisher_v2 and "telemetryMeasuredAt" in publisher_v2, "same-item telemetry preserved")
    check("same_job_recovery", "diagnose_and_recover_scan_v2.py" in orchestrator and "analyze_authorized_video_v14.py" in orchestrator_v2, "same-job bounded recovery")
    check("publisher_conflict_contract", "error.code not in {409, 422}" in publisher and "ATLAS_PROGRESS_CONFLICT_RETRIES" in publisher, "fresh-SHA conflict retry")

    base_publisher = load_module("tools/publish_runtime_progress.py", "atlas_publisher_v14_audit")
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
        del credential, body
        if method == "PUT":
            calls["put"] += 1
            if calls["put"] == 1:
                raise urllib.error.HTTPError(url, 409, "Conflict", hdrs=None, fp=None)
        return {}

    base_publisher._github_request = fake_request
    check("publisher_409_simulation", base_publisher._publish_github({"stage": "audit", "progressPercent": 1}) is True and calls["put"] == 2, "first conflict recovered")

    recovery = load_module("tools/diagnose_and_recover_scan_v2.py", "atlas_recovery_v14_audit")
    examples = {
        "HTTP Error 412: Precondition Failed": "bilibili-http-412",
        "HTTP Error 503: Service Unavailable": "bilibili-http-5xx",
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

    transport_result = subprocess.run(
        [sys.executable, "tools/bilibili_transport_v14_smoke.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    check("transport_gate", transport_result.returncode == 0 and "128/128" in transport_result.stdout and "expected 32 v14 checks" in smoke_v14, "128 deterministic source-transport checks")
    media = [path for pattern in ("*.mp4", "*.m4a", "*.webm", "*.flv") for path in ROOT.rglob(pattern)]
    check("repository_media_clean", not media, f"media files={len(media)}")
    check("release_assets_exist", all((ROOT / path).exists() for path in release.get("releaseAssets", [])), "all release assets exist")

    if len(checks) != 78:
        raise AssertionError(f"expected 78 audit checks, executed {len(checks)}")
    passed = sum(item["passed"] for item in checks)
    report = {
        "schemaVersion": 11,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "pass" if passed == len(checks) else "fail",
        "summary": {"total": len(checks), "passed": passed, "failed": len(checks) - passed},
        "dictionaryVersion": bugs.get("version"),
        "release": release.get("version"),
        "queueItems": len(items),
        "maximumConcurrentItems": queue.get("maximumConcurrentItems"),
        "batchId": queue.get("queueId"),
        "checks": checks,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
