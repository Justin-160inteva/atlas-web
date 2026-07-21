#!/usr/bin/env python3
"""Audit the Atlas scan, monitor, heartbeat, data center, and P25-P35 serial execution stack."""
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
    supervisor_source = read_text("tools/supervise_runtime_heartbeat.py")
    publisher = read_text("tools/publish_runtime_progress.py")
    publisher_v2 = read_text("tools/publish_runtime_progress_v2.py")
    analyzer_v11 = read_text("tools/analyze_authorized_video_v11.py")
    analyzer_v12 = read_text("tools/analyze_authorized_video_v12.py")
    analyzer_v13 = read_text("tools/analyze_authorized_video_v13.py")
    transport_v13 = read_text("tools/bilibili_transport_v13.py")
    transport_smoke = read_text("tools/bilibili_transport_smoke.py")
    orchestrator = read_text("tools/run_scan_with_auto_recovery.py")
    orchestrator_v2 = read_text("tools/run_scan_with_auto_recovery_v2.py")
    marker_runtime = read_text("atlas-ui-fix-0931.js")
    controls_runtime = read_text("atlas-controls-0938.js")
    settings_runtime = read_text("atlas-settings.js")
    settings_css = read_text("atlas-settings.css")
    evidence_css = read_text("evidence-studio.css")
    data_center_matrix = read_text("tools/data_center_contract_smoke.mjs")

    entries = bugs.get("entries", [])
    ids = [entry.get("id") for entry in entries]
    required_layers = {"source-download", "source-metadata", "identity", "http-client", "network", "media", "analysis", "runner", "progress-publish", "orchestration", "heartbeat", "safety"}
    check("dictionary_size", len(entries) >= 27, f"{len(entries)} entries")
    check("dictionary_unique", len(ids) == len(set(ids)), "unique IDs")
    check("dictionary_complete", all(entry.get("patterns") and entry.get("autoAction") for entry in entries), "patterns and actions present")
    check("dictionary_layers", required_layers <= {entry.get("layer") for entry in entries}, "required layers present")
    check("cooldowns_bounded", next(entry for entry in entries if entry["id"] == "bilibili-http-412")["cooldownSeconds"] <= 45 and next(entry for entry in entries if entry["id"] == "bilibili-http-429")["cooldownSeconds"] <= 120, "network cooldowns bounded")

    invariants = release.get("invariants", {})
    release_version = str(release.get("version", ""))
    next_full_audit = str(invariants.get("nextRequiredFullAuditVersion", ""))
    full_audit_expected = release_version == next_full_audit
    check("release_version", release_version.startswith("0.9.4."), f"Alpha {release_version}")
    check("release_audit_cycle", invariants.get("requireFullAuditAtThisRelease") is full_audit_expected and next_full_audit == "0.9.4.11", f"Alpha {release_version}; next mandatory audit is {next_full_audit}")
    check("release_matrices", all(invariants.get(key) == 500 for key in ("requiredHeartbeatMatrixChecks", "requiredBrowserMatrixChecks", "requiredDataCenterMatrixChecks", "requiredSerialQueueOrderChecks", "requiredMonitorBatchAuthorityChecks", "requiredQueueSchemaChecks")), "six exact 500-check gates")
    check("release_monitor_contract", invariants.get("singleMonitorController") is True and invariants.get("durableScanStateAlwaysWins") is True and invariants.get("monitorBatchIdentityMustMatch") is True, "single batch-authoritative monitor")
    check("release_serial11_contract", invariants.get("heartbeatSupervisorMaximumQueueItems") == 11 and invariants.get("scanMaximumConcurrentDownloads") == 1 and invariants.get("scanAutoContinueAfterDurableSuccess") is True, "eleven queued, one active, auto continue")
    check("release_transport_contract", invariants.get("requiredSourceTransportChecks") == 96 and invariants.get("sourceTransportUsesSignedWbi") is True and invariants.get("sourceTransportBypassesVideoWebpage") is True and invariants.get("sourceTransportPreservesCdnResume") is True, "signed WBI direct API with resumable CDN rotation")
    check("release_marker_contract", invariants.get("markerSelectionUsesScaleOnly") is True and invariants.get("markerSelectionDecorationLayers") == 0 and invariants.get("markerSelectedScale") == 1.28 and invariants.get("markerSelectionDurationMs") == 190 and invariants.get("markerTipAnchorStable") is True, "anchored scale-only marker selection")
    check("release_marker_runtime", all(token in marker_runtime for token in ("selectionUsesScaleOnly:true", "selectionDecorationLayers:0", "tipAnchorStable:true", "SELECTION_DURATION=190", "SELECTED_SCALE=1.28")) and "ctx.ellipse(" not in marker_runtime and "radius+4.2" not in marker_runtime, "no legacy selection rings or ornaments")
    check("release_settings_icon", invariants.get("settingsIconDesign") == "radial-eight" and "dataset.iconDesign='radial-eight'" in controls_runtime, "simplified radial settings icon")
    check("release_data_center_owner", release.get("runtimeOwners", {}).get("dataEvidenceCenter") == "atlas-settings.js" and release.get("runtimeOwners", {}).get("evidenceDataEngine") == "atlas-evidence-studio.js", "one shell owner and one evidence data engine")
    check("release_data_center_contract", invariants.get("singleDataEvidenceCenter") is True and invariants.get("dataEvidenceCenterViews") == 2 and invariants.get("legacyEvidencePanelStandalone") is False, "one data and evidence center with two views")
    check("release_data_center_runtime", all(token in settings_runtime for token in ('id="settingsPanel"', 'data-center-tab="database"', 'data-center-tab="evidence"', 'id="settingsEvidenceHost"', "host.appendChild(panel)", "legacyClose.hidden=true", "MONITOR_VERSION='0.6.1'")) and 'id="openEvidenceLab"' not in settings_runtime, "legacy evidence workspace is embedded under one controller")
    check("release_data_center_css", all(token in settings_css for token in (".atlas-data-center", ".data-center-tabs", ".data-center-metrics", ".atlas-quality-performance .settings-panel")) and all(token in evidence_css for token in (".settings-evidence-host .evidence-panel", ".settings-evidence-host .evidence-panel>header{display:none}", ".settings-evidence-host .evidence-panel.open{display:block")), "responsive frosted center and embedded evidence workspace")
    check("release_data_center_matrix", "Expected exactly 500 data center checks" in data_center_matrix and "staticValues.length!==50" in data_center_matrix and "totalChecks!==500" in data_center_matrix, "dedicated exact-500 data center matrix")

    items = queue.get("items", [])
    sequences = [item.get("sequence") for item in items]
    status_items = {item.get("externalSourceId"): item for item in status.get("items", [])}
    catalog_by_id = {item["id"]: item for item in catalog.get("items", [])}
    queue_id = queue.get("queueId")
    status_id = status.get("batchId")
    terminal_status = status.get("complete") is True and status.get("summary", {}).get("imported") == status.get("summary", {}).get("total") == 11
    queue_projection_complete = queue.get("status") == "complete" and all(item.get("state") == "imported" for item in items)
    authority = queue.get("authority", {})
    terminal_projection_coherent = authority.get("terminal") is terminal_status or (terminal_status and queue_projection_complete)

    check("queue_exact_eleven", len(items) == queue.get("maximumQueueItems") == manifest.get("maximumQueueItems") == 11, "exactly eleven bounded items")
    check("queue_unique", len({item.get("externalSourceId") for item in items}) == 11, "eleven unique sources")
    check("queue_chronological", sequences == EXPECTED_PAGES, f"sequence={sequences}")
    check("queue_no_skips", queue.get("skippedAlreadyImportedPages") == [], "P25-P35 all included")
    check("queue_region", all(item.get("regionGuess") == queue.get("pilotRegion") for item in items), "bounded batch label")
    check("queue_serial", queue.get("maximumConcurrentItems") == 1 and sum(item.get("state") in {"running", "recovery"} for item in items) <= 1, "maximum one active item")
    check("queue_auto_continue", queue.get("autoContinueAfterDurableSuccess") is True, "durable-success continuation")
    check("queue_status_batch_identity", queue_id == status_id == EXPECTED_BATCH, f"queue={queue_id}, status={status_id}")
    check("queue_authority", authority.get("owner") == "data/batch-analysis/eleven-pilot-scan-status.json" and authority.get("protectFromCatalogRegeneration") is True and authority.get("batchId") == EXPECTED_BATCH and terminal_projection_coherent, "durable status authority wins over a stale terminal projection")
    check("status_coherent", status.get("summary", {}).get("total") == len(items) and status.get("authorizationId") == queue.get("authorizationId") and len(status_items) == 11, "status matches queue")

    catalog_coherent = True
    catalog_lagged: list[str] = []
    for item in items:
        external_id = item.get("externalSourceId")
        entry = catalog_by_id.get(external_id, {})
        catalog_state = entry.get("analysisStatus")
        status_state = status_items.get(external_id, {}).get("state")
        if item.get("state") == "imported":
            durable_imported = status_state == "imported" and terminal_status
            catalog_coherent = catalog_coherent and (catalog_state == "imported" or durable_imported)
            if catalog_state != "imported" and durable_imported:
                catalog_lagged.append(str(external_id))
        else:
            catalog_coherent = catalog_coherent and catalog_state != "imported"
    check("queue_catalog_state", catalog_coherent, f"durable status wins; catalog lagged={len(catalog_lagged)}")
    check("catalog_lag_is_bounded", len(catalog_lagged) <= 11, f"lagged projections={len(catalog_lagged)}")

    check("manifest_batch", manifest.get("id") == EXPECTED_BATCH and manifest.get("pilotRegion") == queue.get("pilotRegion"), "manifest targets P25-P35")
    check("manifest_serial", manifest.get("maxItemsPerRun") == 1 and manifest.get("maximumConcurrentDownloads") == 1, "one item per run")
    check("manifest_auto_continue", manifest.get("autoContinueAfterDurableSuccess") is True, "auto continuation enabled")
    check("heartbeat_telemetry", manifest.get("runtimeHeartbeat", {}).get("minimumIntervalSeconds") == 30 and manifest.get("downloadTelemetry", {}).get("intervalSeconds") == 30, "30-second heartbeat and telemetry")
    check("v13_adapter", manifest.get("analyzer", "").endswith("analyze_authorized_video_v13.py") and "analyze_authorized_video_v12" in analyzer_v13 and "bilibili_transport_v13" in analyzer_v13, "v13 analyzer selected")
    check("adaptive_ranges", "ThreadPoolExecutor" in analyzer_v11 and manifest.get("downloadOptimization", {}).get("adaptiveParallelRanges") is True, "bounded range transfer")
    check("download_policy", manifest.get("downloadOptimization", {}).get("noArtificialRateLimit") is True and 2 <= int(manifest.get("downloadOptimization", {}).get("maxRangeWorkers", 0)) <= 4, "no artificial cap, bounded workers")
    check("wbi_metadata", all(token in analyzer_v13 + transport_v13 for token in ("x/player/wbi/playurl", "extract_mixin_key", "sign_wbi_params", "verified catalog CID")) and manifest.get("downloadOptimization", {}).get("bypassPublicVideoWebpage") is True, "signed metadata bypasses the blocked webpage")
    check("cdn_rotation_resume", all(token in analyzer_v13 + transport_v13 for token in ("stream_candidates", "Keep a valid partial target", "backupUrl")) and manifest.get("downloadOptimization", {}).get("preservePartialAcrossCdnCandidates") is True, "partial bytes survive API-provided CDN failover")
    check("retention", manifest.get("retention", {}).get("originalVideo") is False and manifest.get("retention", {}).get("framePixels") is False, "no retained media pixels")

    check("workflow_capacity", "len(items)==queue['maximumQueueItems']==manifest['maximumQueueItems']==11" in workflow, "eleven-item workflow gate")
    check("workflow_serial", "Scan exactly one item" in workflow and "maximumConcurrentDownloads" in workflow, "one active scan")
    check("workflow_catalog_state", "if item.get('state')=='imported'" in workflow and "catalog_state=='imported'" in workflow, "catalog state remains coherent after each run")
    check("workflow_400_gate", "400/400 eleven-item serial integrity and privacy checks passed" in workflow, "400-round scan gate")
    check("workflow_auto_continue", "Continue with exactly one next item after durable success" in workflow and "steps.decision.outputs.progressed == 'true'" in workflow, "next run only after durable success")

    check("monitor_poll", all(token in monitor for token in ("RAW_POLL_MS", "API_POLL_MS", "APPLY_TICK_MS")) and all(value in monitor for value in ("5000", "180000", "1000")), "5s raw, 180s API, 1s UI")
    check("monitor_thresholds", all(token in monitor for token in ("HEARTBEAT_EXPECTED", "HEARTBEAT_WARN", "HEARTBEAT_FAIL")) and all(value in monitor for value in ("30", "75", "150")), "heartbeat thresholds")
    check("monitor_version", "VERSION = '0.6.1'" in monitor and "scan-monitor.js?v=0.6.1" in monitor_html, "monitor v0.6.1")
    check("monitor_single_controller", "scan-monitor-live-bridge" not in monitor_html and not (ROOT / "scan-monitor-live-bridge.js").exists(), "one monitor controller")
    check("monitor_durable_priority", "durable.state !== 'imported'" in monitor and "批次权威状态优先" in monitor_html, "durable state wins")
    check("monitor_batch_authority", all(token in monitor for token in ("chooseDurableBatch", "completedStatus", "batchKey", "批次冲突已自动隔离")), "mismatched legacy queues are isolated")
    check("monitor_cache", "monitor-v11" in worker and "scan-monitor-live-bridge" not in worker, "single-monitor cache")

    policy = supervisor_config.get("policy", {})
    check("supervisor_capacity", supervisor_config.get("maximumQueueItems") == 11 and "len(queue['items'])==11" in supervisor_workflow, "eleven-item supervisor gate")
    check("supervisor_serial", policy.get("oneItemPerRun") is True and policy.get("maximumConcurrentDownloads") == 1, "one-item supervisor policy")
    check("supervisor_auto_continue", policy.get("automaticContinuationAfterDurableSuccess") is True, "supervisor continuation policy")
    check("supervisor_thresholds", supervisor_config.get("staleAfterSeconds") == 90 and supervisor_config.get("hardStaleAfterSeconds") == 180, "90/180-second thresholds")
    check("supervisor_dedup", supervisor_config.get("resumeCooldownSeconds") == 360 and policy.get("deduplicateResumeRequests") is True and "resume_permitted" in supervisor_source, "resume deduplication")
    check("supervisor_durable", policy.get("durableStateAlwaysWins") is True and "stale_terminal_heartbeat" in supervisor_source, "durable reconciliation")
    check("supervisor_safety", all(token in supervisor_source for token in ("sourceCodeModified", "authorizationBroadened", "queueScopeExpanded", "mediaRetentionChanged")), "bounded repair safety")

    check("publisher_conflict", "error.code not in {409, 422}" in publisher and "ATLAS_PROGRESS_CONFLICT_RETRIES" in publisher, "fresh-SHA conflict retry")
    check("telemetry_preservation", "PRESERVE_STAGES" in publisher_v2 and "telemetryMeasuredAt" in publisher_v2, "same-item telemetry preserved")
    check("same_job_recovery", "diagnose_and_recover_scan_v2.py" in orchestrator and "analyze_authorized_video_v13.py" in orchestrator_v2, "same-job bounded recovery")
    check("success_projection", "publish_durable_projection(queue)" in orchestrator and "clear_stale_recovery(queue)" in orchestrator, "success projects next item")

    recovery = load_module("tools/diagnose_and_recover_scan_v2.py", "atlas_recovery_p25_p35_test")
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

    base_publisher = load_module("tools/publish_runtime_progress.py", "atlas_publisher_p25_p35_test")
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
    transport_result = subprocess.run(
        [sys.executable, "tools/bilibili_transport_smoke.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    check("transport_gate", transport_result.returncode == 0 and "96/96" in transport_result.stdout and "expected 96 checks" in transport_smoke, "96 deterministic source-transport checks")
    media = [path for pattern in ("*.mp4", "*.m4a", "*.webm", "*.flv") for path in ROOT.rglob(pattern)]
    check("repository_media_clean", not media, f"media files={len(media)}")
    check("release_assets_exist", all((ROOT / path).exists() for path in release.get("releaseAssets", [])), "all release assets exist")

    passed = sum(item["passed"] for item in checks)
    report = {
        "schemaVersion": 10,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "pass" if passed == len(checks) else "fail",
        "summary": {"total": len(checks), "passed": passed, "failed": len(checks) - passed},
        "dictionaryVersion": bugs.get("version"),
        "release": release.get("version"),
        "queueItems": len(items),
        "maximumConcurrentItems": queue.get("maximumConcurrentItems"),
        "batchId": queue_id,
        "catalogProjectionLag": catalog_lagged,
        "checks": checks,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
