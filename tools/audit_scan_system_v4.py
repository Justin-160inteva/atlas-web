#!/usr/bin/env python3
"""Audit the active Atlas eleven-item scan batch without hard-coded pages."""
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
    policy = read_json("data/batch-analysis/eleven-production-order-policy.json")
    runtime = read_json("data/runtime-progress/eleven-pilot-progress.json")
    auth = read_json("data/authorizations.json")
    monitor = read_text("scan-monitor.js")
    monitor_html = read_text("scan-monitor.html")
    worker = read_text("sw.js")
    publisher = read_text("tools/publish_runtime_progress.py")
    publisher_v2 = read_text("tools/publish_runtime_progress_v2.py")
    orchestrator = read_text("tools/run_scan_with_auto_recovery.py")
    orchestrator_v2 = read_text("tools/run_scan_with_auto_recovery_v2.py")
    analyzer_path = str(manifest.get("analyzer", ""))
    analyzer = read_text(analyzer_path)
    analyzer_v13 = read_text("tools/analyze_authorized_video_v13.py")
    transport = read_text("tools/bilibili_transport_v13.py")
    transport_smoke = read_text("tools/bilibili_transport_smoke.py")
    implementation = "\n".join((analyzer, analyzer_v13, transport))

    items = list(queue.get("items", []))
    status_items = list(status.get("items", []))
    pages = [int(item.get("page", -1)) for item in items]
    sequences = [int(item.get("sequence", -1)) for item in items]
    expected_pages = list(range(min(pages), min(pages) + 11)) if len(pages) == 11 else []
    expected_sequences = list(range(min(sequences), min(sequences) + 11)) if len(sequences) == 11 else []
    queue_id = str(queue.get("queueId", ""))
    status_id = str(status.get("batchId", ""))
    manifest_id = str(manifest.get("id", ""))
    summary = status.get("summary", {})
    imported = int(summary.get("imported", 0))
    running = int(summary.get("running", 0))
    failed = int(summary.get("failed", 0))
    blocked = int(summary.get("blocked", 0))
    remaining = int(summary.get("remaining", 0))
    terminal = status.get("complete") is True and imported == len(items) == 11
    authority = queue.get("authority", {})
    active_count = sum(item.get("state") in {"running", "recovery"} for item in items)
    catalog_by_id = {entry.get("id"): entry for entry in catalog.get("items", [])}
    opts = manifest.get("downloadOptimization", {})
    parallel_mode = opts.get("adaptiveParallelRanges") is True and "ThreadPoolExecutor" in implementation
    fallback_mode = (
        opts.get("fallbackToResumableSingleStream") is True
        and opts.get("preservePartialAcrossCdnCandidates") is True
        and all(token in implementation for token in ("stream_candidates", "backupUrl"))
    )
    transport_mode = "parallel-ranges" if parallel_mode else "resumable-single-stream" if fallback_mode else "unsupported"

    entries = bugs.get("entries", [])
    ids = [entry.get("id") for entry in entries]
    check("dictionary_size", len(entries) >= 27, f"{len(entries)} entries")
    check("dictionary_unique", len(ids) == len(set(ids)), "unique bug IDs")
    check("dictionary_complete", all(entry.get("patterns") and entry.get("autoAction") for entry in entries), "patterns and actions present")
    check("release_version", str(release.get("version", "")).startswith("0.9.4."), str(release.get("version")))
    check("release_assets_exist", all((ROOT / path).exists() for path in release.get("releaseAssets", [])), "all release assets exist")
    check("release_monitor_owner", release.get("runtimeOwners", {}).get("scanMonitor") == "scan-monitor.js", "single monitor owner")
    check("release_autonomy", release.get("invariants", {}).get("scanAutonomousRepairEnabled") is True, "autonomous repair enabled")

    check("queue_exact_eleven", len(items) == queue.get("maximumQueueItems") == manifest.get("maximumQueueItems") == 11, "exactly eleven items")
    check("queue_unique", len({item.get("externalSourceId") for item in items}) == 11, "unique sources")
    check("queue_chronological", pages == expected_pages, f"pages={pages}")
    check("queue_sequence_slots", sequences == expected_sequences, f"sequences={sequences}")
    check("queue_serial", queue.get("maximumConcurrentItems") == 1 and active_count <= 1 and running <= 1, f"active={active_count}, running={running}")
    check("queue_auto_continue", queue.get("autoContinueAfterDurableSuccess") is True, "automatic continuation")
    check("queue_status_batch_identity", queue_id == status_id == manifest_id, f"queue={queue_id}, status={status_id}, manifest={manifest_id}")
    check("queue_authority", authority.get("owner") == "data/batch-analysis/eleven-pilot-scan-status.json" and authority.get("batchId") == queue_id and authority.get("protectFromCatalogRegeneration") is True and authority.get("terminal") is terminal, f"terminal={terminal}")
    check("status_coherent", len(status_items) == 11 and int(summary.get("total", 0)) == 11 and imported + running + failed + blocked + remaining == 11, f"summary={summary}")
    check("active_item_coherent", (status.get("activeItem") is None) if running == 0 else status.get("activeItem") is not None, f"activeItem={status.get('activeItem')}")
    check("result_paths", all(item.get("state") != "imported" or item.get("resultPath") for item in status_items), "imported items have results")
    check("no_failed_terminal_mix", not terminal or failed == blocked == remaining == running == 0, "terminal state is clean")
    check("catalog_identity", all(item.get("externalSourceId") in catalog_by_id for item in items), "all queue sources exist in catalog")
    check("catalog_authorization", all(catalog_by_id[item.get("externalSourceId")].get("authorizationId") == queue.get("authorizationId") for item in items), "catalog authorization matches")
    check("catalog_pending_or_imported", all(catalog_by_id[item.get("externalSourceId")].get("analysisStatus") in {"pending", "imported"} for item in items), "catalog state is scannable")

    check("manifest_batch", manifest_id == queue_id and manifest.get("pilotRegion") == queue.get("pilotRegion"), f"active batch {manifest_id}")
    check("manifest_serial", manifest.get("maxItemsPerRun") == 1 and manifest.get("maximumConcurrentDownloads") == 1, "one item per run")
    check("manifest_auto_continue", manifest.get("autoContinueAfterDurableSuccess") is True, "auto continuation enabled")
    check("heartbeat_telemetry", manifest.get("runtimeHeartbeat", {}).get("minimumIntervalSeconds") == 30 and manifest.get("downloadTelemetry", {}).get("intervalSeconds") == 30, "30-second telemetry")
    inherited_v13 = analyzer_path.endswith("analyze_authorized_video_v13.py") or (analyzer_path.endswith("analyze_authorized_video_v14.py") and "import analyze_authorized_video_v13 as v13" in analyzer)
    check("v13_adapter", inherited_v13 and "bilibili_transport_v13" in analyzer_v13, analyzer_path)
    check("adaptive_ranges", parallel_mode or fallback_mode, f"supported transport mode={transport_mode}")
    workers = int(opts.get("maxRangeWorkers", 0))
    check("download_policy", opts.get("noArtificialRateLimit") is True and 1 <= workers <= 8, f"workers={workers}")
    check("wbi_metadata", all(token in implementation for token in ("x/player/wbi/playurl", "extract_mixin_key", "sign_wbi_params")), "signed WBI metadata")
    check("cdn_rotation_resume", fallback_mode or (all(token in implementation for token in ("stream_candidates", "backupUrl")) and opts.get("preservePartialAcrossCdnCandidates") is True), "resumable CDN rotation")
    probe_mode = opts.get("cdnSpeedProbeEnabled") is True and opts.get("preferRangeCapableCdn") is True and "_ordered_candidates" in implementation
    check("cdn_probe", probe_mode or fallback_mode, f"cdn selection compatible with {transport_mode}")
    check("retention", manifest.get("retention", {}).get("originalVideo") is False and manifest.get("retention", {}).get("framePixels") is False, "no retained media")

    check("policy_active_batch", policy.get("activeBatch", {}).get("batchId") == queue_id and policy.get("nextPage") == min(pages), "production order targets active batch")
    check("policy_serial", policy.get("queueConstruction", {}).get("maxItemsPerRun") == 1 and policy.get("queueConstruction", {}).get("preserveEpisodeOrder") is True, "chronological serial policy")
    record = next((entry for entry in auth.get("records", []) if entry.get("id") == queue.get("authorizationId")), {})
    scope = record.get("scope", {})
    check("authorization_active", record.get("status") == "active" and record.get("author") == queue.get("author"), "active author authorization")
    check("authorization_scope", scope.get("localDownloadAndAnalysis") is True and scope.get("computerVisionAnalysis") is True, "analysis scope allowed")
    check("runtime_projection", runtime.get("pilotRegion") == queue.get("pilotRegion") and runtime.get("externalSourceId") in {item.get("externalSourceId") for item in items}, "runtime belongs to active batch")

    check("monitor_poll", all(token in monitor for token in ("RAW_POLL_MS", "API_POLL_MS", "APPLY_TICK_MS")) and all(value in monitor for value in ("5000", "180000", "1000")), "monitor cadence")
    check("monitor_thresholds", all(token in monitor for token in ("HEARTBEAT_EXPECTED", "HEARTBEAT_WARN", "HEARTBEAT_FAIL")) and all(value in monitor for value in ("30", "75", "150")), "heartbeat thresholds")
    check("monitor_version", "VERSION = '0.6.1'" in monitor and "scan-monitor.js?v=0.6.1" in monitor_html, "monitor v0.6.1")
    check("monitor_single_controller", "scan-monitor-live-bridge" not in monitor_html and not (ROOT / "scan-monitor-live-bridge.js").exists(), "single controller")
    check("monitor_batch_authority", all(token in monitor for token in ("chooseDurableBatch", "batchKey", "批次冲突已自动隔离")), "batch authority selection")
    check("monitor_cache", f"const CACHE='{release.get('cacheNamespace')}'" in worker, "release cache synchronized")

    check("publisher_conflict", "error.code not in {409, 422}" in publisher and "ATLAS_PROGRESS_CONFLICT_RETRIES" in publisher, "fresh SHA retries")
    check("telemetry_preservation", "PRESERVE_STAGES" in publisher_v2 and "telemetryMeasuredAt" in publisher_v2, "telemetry preserved")
    check("same_job_recovery", "diagnose_and_recover_scan_v2.py" in orchestrator and "analyze_authorized_video" in orchestrator_v2, "same-job recovery")
    check("success_projection", "publish_durable_projection(queue)" in orchestrator and "clear_stale_recovery(queue)" in orchestrator, "durable continuation")

    recovery = load_module("tools/diagnose_and_recover_scan_v2.py", "atlas_recovery_dynamic_test")
    examples = {
        "HTTP Error 412: Precondition Failed": "bilibili-http-412",
        "HTTP Error 503: Service Unavailable": "bilibili-http-5xx",
        "range request was not honored": "range-not-supported",
        "OpenCV could not open the downloaded video": "opencv-open-failure",
    }
    for message, expected in examples.items():
        matched, _ = recovery.match_entry(message, bugs)
        check(f"match_{expected}", matched and matched.get("id") == expected, message)

    base_publisher = load_module("tools/publish_runtime_progress.py", "atlas_publisher_dynamic_test")
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
    check("publisher_409_simulation", base_publisher._publish_github({"stage": "audit", "progressPercent": 1}) is True and calls["put"] == 2, "first conflict recovered")
    transport_result = subprocess.run([sys.executable, "tools/bilibili_transport_smoke.py"], cwd=ROOT, capture_output=True, text=True, check=False)
    check("transport_gate", transport_result.returncode == 0 and "96/96" in transport_result.stdout and "expected 96 checks" in transport_smoke, "96 source transport checks")
    media = [path for pattern in ("*.mp4", "*.m4a", "*.webm", "*.flv") for path in ROOT.rglob(pattern)]
    check("repository_media_clean", not media, f"media files={len(media)}")

    passed = sum(item["passed"] for item in checks)
    report = {
        "schemaVersion": 12,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "pass" if passed == len(checks) else "fail",
        "summary": {"total": len(checks), "passed": passed, "failed": len(checks) - passed},
        "dictionaryVersion": bugs.get("version"),
        "release": release.get("version"),
        "queueItems": len(items),
        "maximumConcurrentItems": queue.get("maximumConcurrentItems"),
        "batchId": queue_id,
        "pageRange": [min(pages), max(pages)] if pages else [],
        "transportMode": transport_mode,
        "checks": checks,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
