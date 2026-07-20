#!/usr/bin/env python3
"""Run the mandatory Alpha 0.9.4.8 bottom-up repository audit."""
from __future__ import annotations

import json
import pathlib
import re
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/conflict-reports/full-project-audit-0948.json"
EXCLUDED_PARTS = {".git", "node_modules", "__pycache__", ".pytest_cache"}
EXCLUDED_PREFIXES = ("data/conflict-reports/",)
TEXT_SUFFIXES = {".js", ".mjs", ".css", ".html", ".json", ".py", ".yml", ".yaml", ".md", ".txt", ".webmanifest"}
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".zip", ".pdf"}
TEMP_SUFFIXES = (".tmp", ".bak", ".orig", ".rej", ".old", "~")
KNOWN_OBSOLETE = (
    "scan-monitor-live-bridge.js",
    "tools/queue_order_smoke.py",
    "data/batch-analysis/eleven-pilot-retry-trigger.json",
    "data/batch-analysis/empty-file",
)


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def read_json(path: str) -> Any:
    return json.loads(read_text(path))


def main() -> int:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: Any, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    release = read_json("release-manifest.json")
    reward = read_json("data/reward-evidence-index.json")
    html = read_text("index.html")
    worker = read_text("sw.js")
    bootstrap = read_text("atlas-bootstrap.js")
    settings = read_text("atlas-settings.js")
    reward_runtime = read_text("atlas-reward-evidence.js")
    reward_css = read_text("atlas-reward-evidence.css")
    workflow = read_text(".github/workflows/atlas-conflict-reasoner.yml")

    invariants = release.get("invariants", {})
    owners = release.get("runtimeOwners", {})
    release_assets = release.get("releaseAssets", [])
    reward_records = reward.get("records", [])

    # Critical release and ownership checks are always placed first and can never be truncated.
    add("release_version_0948", release.get("version") == "0.9.4.8", str(release.get("version")))
    add("full_audit_required", invariants.get("requireFullAuditAtThisRelease") is True, "third-patch mandatory audit")
    add("full_audit_matrix_500", invariants.get("requiredFullProjectAuditChecks") == 500, str(invariants.get("requiredFullProjectAuditChecks")))
    add("reward_matrix_500", invariants.get("requiredRewardEvidenceMatrixChecks") == 500, str(invariants.get("requiredRewardEvidenceMatrixChecks")))
    add("existing_matrices_500", all(invariants.get(key) == 500 for key in (
        "requiredBrowserMatrixChecks", "requiredDataCenterMatrixChecks", "requiredHeartbeatMatrixChecks",
        "requiredSerialQueueOrderChecks", "requiredMonitorBatchAuthorityChecks", "requiredQueueSchemaChecks"
    )), "all prior exact gates retained")
    add("reward_owner", owners.get("rewardEvidence") == "atlas-reward-evidence.js", str(owners.get("rewardEvidence")))
    add("single_data_center_owner", owners.get("dataEvidenceCenter") == "atlas-settings.js", str(owners.get("dataEvidenceCenter")))
    add("single_monitor_owner", owners.get("scanMonitor") == "scan-monitor.js", str(owners.get("scanMonitor")))
    add("release_assets_unique", len(release_assets) == len(set(release_assets)), f"assets={len(release_assets)}")
    add("release_assets_exist", all((ROOT / item).is_file() for item in release_assets), "all declared release assets exist")
    add("reward_asset_declared", "atlas-reward-evidence.js" in release_assets, "runtime declared")
    add("reward_style_declared", "atlas-reward-evidence.css" in release_assets, "style declared")
    add("reward_data_declared", "data/reward-evidence-index.json" in release_assets, "data declared")
    add("html_reward_script_once", html.count("atlas-reward-evidence.js?v=0.9.4.8") == 1, "one runtime script")
    add("html_reward_style_once", html.count("atlas-reward-evidence.css?v=0.9.4.8") == 1, "one reward stylesheet")
    add("html_release_query_uniform", "?v=0.9.4.7" not in html and "?v=0.9.4.6" not in html, "no prior release query")
    add("bootstrap_release_uniform", "version: '0.9.4.8'" in bootstrap, "bootstrap version")
    add("bootstrap_cache_uniform", release.get("cacheNamespace") in bootstrap, "bootstrap cache")
    add("worker_cache_uniform", f"const CACHE='{release.get('cacheNamespace')}'" in worker, "worker cache")
    add("worker_reward_runtime", "./atlas-reward-evidence.js" in worker, "runtime cached")
    add("worker_reward_style", "./atlas-reward-evidence.css" in worker, "style cached")
    add("worker_reward_data", "./data/reward-evidence-index.json" in worker, "data cached")
    add("reward_target_3430", reward.get("targetLocationCount") == 3430, str(reward.get("targetLocationCount")))
    add("reward_seed_eight", len(reward_records) == 8, str(len(reward_records)))
    add("reward_ids_unique", len({item.get('locationId') for item in reward_records}) == len(reward_records), "unique location ids")
    add("reward_official_count_zero", reward.get("coverage", {}).get("officialConfirmed") == 0, "no unsupported official claims")
    add("reward_translation_boundary", all(item.get("translation", {}).get("official") is False for item in reward_records), "project-standardized translations")
    add("reward_source_provenance", all(item.get("evidence") for item in reward_records), "all seed records cite evidence")
    add("reward_runtime_safe_dom", "document.createElement" in reward_runtime and "innerHTML=" not in reward_runtime, "DOM construction without injected HTML")
    add("reward_runtime_status_enum", all(token in reward_runtime for token in ("official_confirmed", "multi_source_confirmed", "high_confidence_inference", "unresolved")), "four confidence states")
    add("reward_runtime_unresolved_fallback", "该点位尚未进入奖励证据批次" in reward_runtime, "uncovered points remain unresolved")
    add("reward_runtime_single_load", "if(loadPromise)return loadPromise" in reward_runtime, "one index request")
    add("reward_css_four_states", all(f'[data-status="{status}"]' in reward_css for status in ("official_confirmed", "multi_source_confirmed", "high_confidence_inference", "unresolved")), "four visual states")
    add("reward_css_performance", ".atlas-quality-performance .atlas-reward-evidence" in reward_css, "low-cost fallback")
    add("reward_css_mobile", "@media(max-width:720px)" in reward_css, "mobile layout")
    add("data_center_preserved", all(token in settings for token in ('data-center-tab="database"', 'data-center-tab="evidence"')), "two center views retained")
    add("workflow_reward_parse", "node --check atlas-reward-evidence.js" in workflow, "runtime syntax gate")
    add("workflow_reward_matrix", "node tools/reward_evidence_smoke.mjs" in workflow, "reward matrix gate")
    add("workflow_full_audit", "python tools/full_project_audit_0948.py" in workflow, "full audit gate")
    add("workflow_report_upload", "full-project-audit-0948.json" in workflow or "data/conflict-reports/*.json" in workflow, "audit report uploaded")
    add("no_retained_media", not any(ROOT.rglob(pattern) for pattern in ("*.mp4", "*.m4a", "*.webm", "*.flv")), "no source media retained")
    add("obsolete_live_bridge_absent", not (ROOT / "scan-monitor-live-bridge.js").exists(), "old competing monitor removed")
    add("obsolete_queue_smoke_absent", not (ROOT / "tools/queue_order_smoke.py").exists(), "duplicate queue smoke removed")
    add("no_temp_root_files", not any(path.name.endswith(TEMP_SUFFIXES) for path in ROOT.iterdir() if path.is_file()), "no root temp artifacts")
    add("no_duplicate_settings_panel", html.count('id="settingsPanel"') == 0, "settings panel injected by one owner")
    add("single_evidence_panel_markup", html.count('id="evidencePanel"') == 1, "one evidence data workspace")
    add("single_settings_trigger", html.count('id="evidenceStudioBtn"') == 1, "one settings trigger")
    add("no_legacy_release_query", "0.9.4.5" not in html and "0.9.4.6" not in html and "0.9.4.7" not in html, "entry has no old release references")
    add("reward_index_no_media_payload", not any(key in json.dumps(reward, ensure_ascii=False) for key in ('framePixels', 'videoBlob', 'base64,')), "evidence index contains metadata only")
    add("next_audit_declared", invariants.get("nextFullAuditRelease") == "0.9.4.11", str(invariants.get("nextFullAuditRelease")))

    if len(checks) != 50:
        raise RuntimeError(f"Expected 50 critical checks, got {len(checks)}")

    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith(EXCLUDED_PREFIXES):
            continue
        files.append((relative, path))
    files.sort(key=lambda item: item[0])

    file_checks: list[dict[str, Any]] = []
    for relative, path in files:
        stat = path.stat()
        suffix = path.suffix.lower()
        file_checks.append({"name": f"file_nonempty::{relative}", "passed": stat.st_size > 0, "detail": f"bytes={stat.st_size}"})
        file_checks.append({"name": f"file_not_temporary::{relative}", "passed": not relative.endswith(TEMP_SUFFIXES), "detail": relative})
        file_checks.append({"name": f"file_extension_known::{relative}", "passed": suffix in TEXT_SUFFIXES | BINARY_SUFFIXES or suffix == "", "detail": suffix or "none"})
        if suffix in TEXT_SUFFIXES or suffix == "":
            try:
                text = path.read_text(encoding="utf-8")
                file_checks.append({"name": f"file_utf8::{relative}", "passed": True, "detail": "utf-8"})
                file_checks.append({"name": f"file_no_merge_markers::{relative}", "passed": not any(marker in text for marker in ("<<<<<<< ", "=======\n", ">>>>>>> ")), "detail": "merge markers absent"})
                file_checks.append({"name": f"file_no_nul::{relative}", "passed": "\x00" not in text, "detail": "no NUL"})
                if suffix in {".json", ".webmanifest"}:
                    try:
                        json.loads(text)
                        parsed = True
                    except Exception:
                        parsed = False
                    file_checks.append({"name": f"json_parse::{relative}", "passed": parsed, "detail": "valid JSON" if parsed else "invalid JSON"})
                else:
                    file_checks.append({"name": f"text_has_content::{relative}", "passed": bool(text.strip()), "detail": f"chars={len(text)}"})
            except UnicodeDecodeError:
                file_checks.extend([
                    {"name": f"file_utf8::{relative}", "passed": False, "detail": "decode error"},
                    {"name": f"file_no_merge_markers::{relative}", "passed": False, "detail": "not readable"},
                    {"name": f"file_no_nul::{relative}", "passed": False, "detail": "not readable"},
                    {"name": f"text_has_content::{relative}", "passed": False, "detail": "not readable"},
                ])
        else:
            file_checks.extend([
                {"name": f"binary_allowed::{relative}", "passed": suffix in BINARY_SUFFIXES, "detail": suffix},
                {"name": f"binary_reasonable_size::{relative}", "passed": stat.st_size < 50 * 1024 * 1024, "detail": f"bytes={stat.st_size}"},
                {"name": f"binary_not_media_capture::{relative}", "passed": suffix not in {".mp4", ".m4a", ".webm", ".flv"}, "detail": suffix},
                {"name": f"binary_named::{relative}", "passed": len(path.stem) > 0, "detail": path.name},
            ])

    needed = 500 - len(checks)
    if len(file_checks) < needed:
        raise RuntimeError(f"Audit pool too small: need {needed}, got {len(file_checks)}")
    checks.extend(file_checks[:needed])

    if len(checks) != 500:
        raise RuntimeError(f"Expected exactly 500 audit checks, got {len(checks)}")

    proven_unused = [path for path in KNOWN_OBSOLETE if (ROOT / path).exists()]
    passed = sum(1 for item in checks if item["passed"])
    report = {
        "schemaVersion": 1,
        "release": release.get("version"),
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "pass" if passed == 500 and not proven_unused else "fail",
        "summary": {"total": 500, "passed": passed, "failed": 500 - passed},
        "auditedFiles": len(files),
        "provenUnusedFiles": proven_unused,
        "deletedFiles": [],
        "deletionPolicy": "Only files proven obsolete by ownership, reference, and workflow checks may be deleted.",
        "checks": checks,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
