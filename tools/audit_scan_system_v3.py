#!/usr/bin/env python3
"""Audit scan authority, recovery safety, validation policy, and P33-P35 evidence."""
from __future__ import annotations

import json
import pathlib
import sys
import urllib.error
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/batch-analysis/scan-system-health.json"
sys.path.insert(0, str(ROOT / "tools"))


def read_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def read_text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def pull_request_pushes_are_guarded(workflow):
    for step in workflow.split("\n      - "):
        if "git push" not in step:
            continue
        metadata = step.split("\n        run:", 1)[0]
        if not any(
            guard in metadata
            for guard in (
                "github.event_name != 'pull_request'",
                "github.event_name == 'push' && github.ref == 'refs/heads/main'",
            )
        ):
            return False
    return True


def main():
    checks = []

    def check(name, passed, detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    release = read_json("release-manifest.json")
    queue = read_json("data/batch-analysis/eleven-pilot-scan-queue.json")
    manifest = read_json("data/batch-analysis/eleven-pilot-scan-manifest.json")
    status = read_json("data/batch-analysis/eleven-pilot-scan-status.json")
    trigger = read_json("data/batch-analysis/eleven-pilot-v2-trigger.json")
    supervisor = read_json("data/batch-analysis/eleven-heartbeat-supervisor.json")
    supervisor_state = read_json("data/batch-analysis/eleven-heartbeat-supervisor-state.json")
    recovery_report = read_json("data/batch-analysis/eleven-pilot-recovery-report.json")
    repair_report = read_json("data/batch-analysis/scan-autonomous-repair-report.json")
    autonomy = read_json("data/scan-autonomy-policy.json")
    validation = read_json("data/quality/release-validation-policy.json")
    analysis_index = read_json("data/analysis-index.json")
    eleven_catalog = read_json("data/eleven-game-world-ac-shadows-catalog.json")
    bugs = read_json("data/scan-bug-dictionary.json")
    bootstrap = read_text("atlas-bootstrap.js")
    worker = read_text("sw.js")
    scan_workflow = read_text(".github/workflows/scan-eleven-pilot-v2.yml")
    legacy_scan_workflow = read_text(".github/workflows/scan-eleven-pilot.yml")
    supervisor_workflow = read_text(".github/workflows/supervise-eleven-heartbeat.yml")
    discovery_workflow = read_text(".github/workflows/discover-eleven-author-catalog.yml")
    extras_workflow = read_text(".github/workflows/discover-eleven-account-extras.yml")
    dada_scan_workflow = read_text(".github/workflows/scan-dada-author-catalog.yml")
    observer_workflows = tuple(
        read_text(path)
        for path in (
            ".github/workflows/observe-dada-seq12.yml",
            ".github/workflows/observe-dada-seq14.yml",
            ".github/workflows/observe-dada-seq20.yml",
        )
    )
    pull_request_write_workflows = tuple(
        read_text(path)
        for path in (
            ".github/workflows/analyze-authorized-video.yml",
            ".github/workflows/dada-catalog-quality-audit.yml",
            ".github/workflows/dada-sequence-06-resolution.yml",
            ".github/workflows/dada-sequence-08-resolution.yml",
            ".github/workflows/dada-sequence-12-resolution.yml",
            ".github/workflows/dada-shrines-anchor-batch01.yml",
            ".github/workflows/discover-eleven-account-extras.yml",
            ".github/workflows/reprocess-dada-seq08.yml",
            ".github/workflows/reprocess-dada-verified.yml",
            ".github/workflows/reward-legendary-chest-parser.yml",
            ".github/workflows/reward-quest-detail-diagnostic.yml",
            ".github/workflows/reward-quest-evidence-import.yml",
            ".github/workflows/reward-summary-production.yml",
            ".github/workflows/reward-translation-research.yml",
        )
    )
    discovery = read_text("tools/discover_bilibili_author_catalog.py")
    refiner = read_text("tools/refine_eleven_catalog.py")
    conflict_workflow = read_text(".github/workflows/atlas-conflict-reasoner.yml")
    validation_workflow = read_text(".github/workflows/validate-scan-system.yml")

    cache = release["cacheNamespace"]
    check("cache_namespace", cache in bootstrap and cache in worker, "release, bootstrap and service worker share one cache namespace")
    check("release_assets", all((ROOT / path).exists() for path in release.get("releaseAssets", [])), "all declared release assets exist")
    check("validation_policy_owner", release.get("runtimeOwners", {}).get("releaseValidationPolicy") == "data/quality/release-validation-policy.json", "release declares validation policy")
    check("validation_tiers", set(validation.get("tiers", {})) == {"quick", "standard", "full"}, "quick, standard and full tiers exist")
    check("validation_budget_order", validation["tiers"]["quick"]["heartbeatChecks"] < validation["tiers"]["standard"]["heartbeatChecks"] < validation["tiers"]["full"]["heartbeatChecks"], "risk budgets increase monotonically")
    check("validation_quick_floor", all(validation["tiers"]["quick"][key] >= 200 for key in ("heartbeatChecks", "serialQueueChecks", "queueSchemaChecks", "browserChecks", "monitorAuthorityChecks")), "quick relevant matrices preserve the 200-check floor")
    check("validation_standard_floor", all(validation["tiers"]["standard"][key] >= 300 for key in ("heartbeatChecks", "serialQueueChecks", "queueSchemaChecks", "browserChecks", "monitorAuthorityChecks")), "standard relevant matrices preserve the 300-check floor")
    check("validation_high_risk_full", "full_tier = full_audit or high_risk" in read_text("tools/select_release_validation.py"), "high-risk changes select the 500-check full tier without enabling unrelated matrices")
    check("validation_ipad_coverage", all(path in validation["pathGroups"]["ui"] for path in ("atlas-ipad-canvas-hotfix-0948.js", "atlas-ipad-canvas-hotfix-0948.css", "atlas-ipad-gesture-hotfix-0948.js")) and all(path in validation["pathGroups"]["highRisk"] for path in ("atlas-ipad-canvas-hotfix-0948.js", "atlas-ipad-gesture-hotfix-0948.js")), "iPad canvas and gesture changes always select browser validation at the full tier")
    check("validation_cycle", validation["scheduledFullAudit"]["lastCompletedVersion"] == release["version"] and validation["scheduledFullAudit"]["nextRequiredVersion"] == "0.9.4.11", "0.9.4.8 full audit recorded; next at 0.9.4.11")
    check("workflow_selects_risk", "select_release_validation.py" in conflict_workflow and "run_full_audit" in conflict_workflow and "run_playwright" in conflict_workflow, "CI selects matrices by changed risk")
    main_only_workflows = (scan_workflow, supervisor_workflow, discovery_workflow)
    extras_write_guard = "branches: [main]" in extras_workflow and "if: github.event_name == 'push' && github.ref == 'refs/heads/main'" in extras_workflow and "TARGET_BRANCH: main" in extras_workflow
    dada_scan_guard = "push:\n    branches: [main]" in dada_scan_workflow
    check("write_workflows_main_only", all("if: github.ref == 'refs/heads/main'" in workflow for workflow in main_only_workflows) and extras_write_guard and dada_scan_guard, "catalog, scan, supervisor and account extras writes cannot run from feature branches")
    check("workflow_run_writes_main_only", all("branches: [main]" in workflow for workflow in observer_workflows), "workflow-run observers cannot persist pull-request or feature-branch outcomes to main")
    check("pull_request_persistence_read_only", all(pull_request_pushes_are_guarded(workflow) and "github.head_ref" not in workflow for workflow in pull_request_write_workflows), "pull-request workflows expose diagnostics as artifacts but cannot push commits")
    check("legacy_pilot_terminal_guard", "preflight:" in legacy_scan_workflow and "needs: preflight" in legacy_scan_workflow and "authority.get('terminal')" in legacy_scan_workflow and "contents: read" in legacy_scan_workflow, "legacy regional pilot is read-only unless preflight finds its nonterminal regional queue")
    conflict_persist = conflict_workflow.split("- name: Persist reports on main", 1)[-1]
    check("report_persistence_single_owner", "scan-system-health.json" not in conflict_persist, "scan health is persisted only by its owning workflow")
    check("report_persistence_retries", "git pull --rebase origin main && git push origin HEAD:main" in conflict_workflow, "report persistence rebases when another main writer wins the race")
    check("pr_validation_read_only", "permissions:\n  contents: read" in conflict_workflow and "persist-reports:" in conflict_workflow and "if: github.event_name == 'push' && github.ref == 'refs/heads/main'" in conflict_workflow, "PR conflict validation is read-only and report persistence is isolated to main pushes")
    check("scan_validation_read_only", "permissions:\n  contents: read" in validation_workflow and "persist-health-report:" in validation_workflow and "if: always() && github.event_name == 'push' && github.ref == 'refs/heads/main'" in validation_workflow, "feature-branch scan validation is read-only and health persistence is isolated to main pushes")

    items = queue.get("items", [])
    status_items = status.get("items", [])
    authority = queue.get("authority") or {}
    summary = status.get("summary") or {}
    check("single_authority", queue.get("queueId") == manifest.get("id") == status.get("batchId") == authority.get("batchId"), "queue, manifest, status and authority use one batch id")
    check("terminal_authority", authority.get("terminal") is True and authority.get("protectFromCatalogRegeneration") is True and queue.get("status") == "complete" and status.get("complete") is True, "completed P80 batch is protected")
    check("queue_capacity", len(items) == queue.get("maximumQueueItems") == manifest.get("maximumQueueItems") == supervisor.get("maximumQueueItems") == summary.get("total") == 1, "one authoritative queue item")
    check("queue_identity", [item.get("page") for item in items] == [80] and trigger.get("queuePages") == [80], "P80 is the only active batch page")
    check("queue_complete", all(item.get("state") == "imported" for item in items) and all(item.get("state") == "imported" for item in status_items), "P80 result is durably imported")
    check("single_download", queue.get("maximumConcurrentItems") == manifest.get("maximumConcurrentDownloads") == manifest.get("maxItemsPerRun") == 1, "at most one download")
    check("retention", manifest["retention"]["originalVideo"] is False and manifest["retention"]["framePixels"] is False, "source media and frame pixels are not retained")

    recovery = manifest["recoveryPolicy"]
    policy = supervisor["policy"]
    execution = autonomy["execution"]
    check("bounded_attempts", manifest["maxAttemptsPerItem"] == recovery["maxAttemptsPerItem"] == policy["maximumAttemptsPerItem"] == 3, "technical recovery is capped at three attempts")
    check("unknown_stops", recovery["blockUnknownOrIdentityFailures"] is True and trigger["humanReviewOnUnknownFailure"] is True, "unknown or identity failures stop")
    check("no_persistent_retry", recovery["retryTechnicalFailuresUntilResolved"] is False and policy["retryTechnicalFailuresUntilResolved"] is False and execution["retryUntilResolvedForTechnicalFailures"] is False, "retry-until-resolved disabled")
    check("no_source_patch", recovery["neverModifySourceCodeAutomatically"] is True and execution["allowAiSourcePatch"] is False and autonomy["mandatorySafety"]["neverModifyExecutableSourceAutomatically"] is True, "automation cannot modify executable source")
    check("workflow_no_model", "models: read" not in scan_workflow and "ATLAS_AI_REPAIR_TOKEN" not in scan_workflow and "run_scan_with_auto_recovery_v2.py data/" not in scan_workflow, "scan workflow has no model/source-repair path")
    persist_block = scan_workflow.split("Persist durable data state", 1)[-1].split("Continue with exactly one", 1)[0]
    check("workflow_data_only", "tools/*.py" not in persist_block and "data/scan-autonomy-policy.json" not in persist_block, "scan persistence excludes source and policy files")
    check("bounded_supervisor", "supervise_runtime_heartbeat.py data/" in supervisor_workflow and "supervise_runtime_heartbeat_v2.py data/" not in supervisor_workflow and supervisor["resumeCooldownSeconds"] >= 360, "supervisor uses bounded evaluator with cooldown")
    check("supervisor_terminal_state", supervisor_state["decision"] == "complete" and supervisor_state["resumeWorkflow"] is False and supervisor_state["durable"]["total"] == supervisor_state["durable"]["imported"] == 1, "current supervisor state is terminal P80")
    check("recovery_report_current", recovery_report["activeExternalSourceId"].endswith("p080") and recovery_report["maxAttempts"] == 3 and recovery_report["retryScheduled"] is False, "recovery report matches bounded terminal authority")
    check("repair_report_current", repair_report["outcome"] == "disabled-terminal" and repair_report["queueState"] == "complete" and repair_report["changedFiles"] == [], "autonomous source repair report is disabled and terminal")

    check("catalog_guard_code", "protected_queue" in discovery and "preserved-terminal-authority" in discovery and "protected_queue" in refiner and "preserved-terminal-authority" in refiner, "both catalog generators preserve protected terminal queues")
    check("catalog_guard_workflow", "protectFromCatalogRegeneration" in discovery_workflow and "queue['queueId']==manifest['id']==scan_status['batchId']" in discovery_workflow, "scheduled catalog job verifies authority")
    indexed = {item.get("externalSourceId"): item for item in analysis_index.get("items", [])}
    catalog_items = eleven_catalog.get("items", [])
    imported = sum((indexed.get(item.get("id")) or {}).get("status") == "imported" for item in catalog_items)
    check("catalog_analysis_projection", all(item.get("analysisStatus") == ((indexed.get(item.get("id")) or {}).get("status") if (indexed.get(item.get("id")) or {}).get("status") in {"imported", "failed"} else "pending") for item in catalog_items) and eleven_catalog["catalogStatus"]["analysisImported"] == imported and eleven_catalog["catalogStatus"]["analysisRemaining"] == len(catalog_items) - imported, "catalog analysis state is projected from analysis-index.json")

    triad = []
    for page in (33, 34, 35):
        result = read_json(f"data/analysis-results/eleven-p{page:03d}.json")
        triad.append({"page": page, "status": result.get("status"), "generatedAt": result.get("generatedAt"), "sampled": result.get("scan", {}).get("sampled"), "kept": result.get("scan", {}).get("kept")})
    check("p33_p35_analyzed", all(item["status"] == "analyzed" and item["sampled"] for item in triad), "P33, P34 and P35 all have analysis results")
    timestamps = {item["page"]: item["generatedAt"] for item in triad}
    historical_strict_order = timestamps[33] < timestamps[34] < timestamps[35]
    regression_audit = read_text("data/audits/full-audit-0948-regression-20260722.json")
    check("historical_order_disclosed", not historical_strict_order and "scan-order-regression" in regression_audit and "P34 is running while durable P33 remains failed" in regression_audit, "historical P34-before-P33 regression remains explicit")

    entries = bugs.get("entries", [])
    check("bug_dictionary", len(entries) >= 25 and len({entry.get("id") for entry in entries}) == len(entries), "bug dictionary is nontrivial and unique")
    media = [path for pattern in ("*.mp4", "*.m4a", "*.webm", "*.flv") for path in ROOT.rglob(pattern)]
    check("repository_media_clean", not media, f"media files={len(media)}")

    import publish_runtime_progress as publisher
    calls = {"put": 0}
    publisher._current_sha = lambda *_args, **_kwargs: "sha"
    publisher.time.sleep = lambda _seconds: None
    publisher.random.uniform = lambda _a, _b: 0.0
    publisher.os.getenv = lambda key, default="": {"ATLAS_PROGRESS_TOKEN": "audit", "ATLAS_PROGRESS_REPOSITORY": "owner/repo", "ATLAS_PROGRESS_BRANCH": "main", "ATLAS_PROGRESS_PATH": "progress.json", "ATLAS_PROGRESS_CONFLICT_RETRIES": "5"}.get(key, default)
    def fake_request(url, credential, *, method="GET", body=None):
        if method == "PUT":
            calls["put"] += 1
            if calls["put"] == 1:
                raise urllib.error.HTTPError(url, 409, "Conflict", hdrs=None, fp=None)
        return {}
    publisher._github_request = fake_request
    check("publisher_conflict_retry", publisher._publish_github({"stage": "audit", "progressPercent": 1}) is True and calls["put"] == 2, "fresh-SHA retry recovers one conflict")

    passed = sum(item["passed"] for item in checks)
    report = {
        "schemaVersion": 10,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "pass" if passed == len(checks) else "fail",
        "summary": {"total": len(checks), "passed": passed, "failed": len(checks) - passed},
        "release": release["version"], "batchId": queue.get("queueId"), "queueItems": len(items),
        "historicalTriad": {"strictOrderPassed": historical_strict_order, "results": triad, "disposition": "documented-regression-not-retroactively-rewritten"},
        "validationPolicy": {"revision": validation["revision"], "nextFullAudit": validation["scheduledFullAudit"]["nextRequiredVersion"]},
        "checks": checks,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
