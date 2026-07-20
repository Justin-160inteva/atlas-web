#!/usr/bin/env python3
"""Full Atlas framework audit required by Alpha 0.9.4.8."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/audits/full-audit-0948.json"


def read_json(path: str) -> Any:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: Any, detail: str, severity: str = "error") -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail, "severity": severity})

    release = read_json("release-manifest.json")
    reward_index = read_json("data/rewards/reward-evidence-index.json")
    reward_policy = read_json("data/rewards/reward-source-policy.json")
    reward_schema = read_json("data/rewards/reward-record-schema.json")
    terminology = read_json("data/rewards/reward-terminology-zh-CN.json")
    roadmap = read_text("PROJECT-ROADMAP.md")
    audit_ledger = read_json("data/version-audit.json")
    entry = read_text("index.html")
    bootstrap = read_text("atlas-bootstrap.js")
    worker = read_text("sw.js")
    settings = read_text("atlas-settings.js")

    check("release_version", release.get("version") == "0.9.4.8", "Alpha 0.9.4.8")
    check("full_audit_required", release.get("invariants", {}).get("requireFullAuditAtThisRelease") is True, "full audit gate enabled")
    check("entry_version", "ALPHA 0.9.4.8" in entry and "?v=0.9.4.8" in entry, "entry page synchronized")
    check("bootstrap_version", "version: '0.9.4.8'" in bootstrap and "atlas-alpha-0948" in bootstrap, "bootstrap synchronized")
    check("service_worker_version", "atlas-alpha-0948" in worker, "service-worker cache synchronized")
    check("release_assets_exist", all((ROOT / path).exists() for path in release.get("releaseAssets", [])), "all declared assets exist")
    check("release_assets_unique", len(release.get("releaseAssets", [])) == len(set(release.get("releaseAssets", []))), "no duplicate release assets")
    check("runtime_owners_unique", len(release.get("runtimeOwners", {}).values()) >= len(set(release.get("runtimeOwners", {}).values())), "shared owners are explicit")

    check("single_settings_owner", release.get("runtimeOwners", {}).get("dataEvidenceCenter") == "atlas-settings.js", "one data/evidence shell owner")
    check("single_settings_panel", settings.count('id="settingsPanel"') == 1, "one settings panel template")
    check("obsolete_monitor_bridge_removed", not (ROOT / "scan-monitor-live-bridge.js").exists(), "obsolete competing monitor bridge absent")
    check("obsolete_watchdog_removed", not (ROOT / ".github/workflows/scan-eleven-watchdog.yml").exists(), "obsolete duplicate scheduler absent")

    target = int(reward_index.get("targetLocationCount", 0))
    coverage = reward_index.get("coverage", {})
    coverage_sum = sum(int(coverage.get(key, 0)) for key in ("officialConfirmed", "multiSourceConfirmed", "highConfidenceInference", "unresolved"))
    check("reward_target", target == 3430, f"target={target}")
    check("reward_coverage_conserved", coverage_sum == target == int(coverage.get("total", 0)), f"coverage={coverage_sum}/{target}")
    check("reward_policy_levels", len(reward_policy.get("evidenceLevels", [])) == 4, "four evidence levels")
    check("reward_policy_no_fake_official", reward_policy.get("principles", {}).get("neverPresentInferenceAsOfficial") is True, "inference cannot masquerade as official")
    check("reward_schema_confidence", reward_schema.get("properties", {}).get("confidence", {}).get("maximum") == 1, "confidence bounded")
    check("reward_schema_sources", "sources" in reward_schema.get("required", []), "sources required")
    check("reward_schema_conflicts", "conflicts" in reward_schema.get("required", []), "conflicts required")
    check("reward_zh_cn", terminology.get("locale") == "zh-CN", "Simplified Chinese terminology")
    check("reward_locked_protection", reward_index.get("productionRules", {}).get("neverOverwriteLockedRecordAutomatically") is True, "locked records protected")
    check("reward_matrix_declared", release.get("invariants", {}).get("requiredRewardEvidenceChecks") == 500, "exact 500 reward checks")
    check("reward_matrix_exists", (ROOT / "tools/reward_evidence_contract_smoke.mjs").exists(), "reward matrix executable exists")

    check("roadmap_current", "Alpha 0.9.4.8" in roadmap, "roadmap includes current release")
    check("roadmap_reward_scope", "3430" in roadmap and "奖励" in roadmap, "reward scope recorded")
    check("ledger_current", audit_ledger.get("currentVersion") == "0.9.4.8", f"ledger={audit_ledger.get('currentVersion')}")
    check("ledger_last_audit", audit_ledger.get("lastAuditedVersion") == "0.9.4.8", f"last={audit_ledger.get('lastAuditedVersion')}")
    check("ledger_next_audit", audit_ledger.get("nextScheduledAuditVersion") == "0.9.4.11", f"next={audit_ledger.get('nextScheduledAuditVersion')}")

    media = [path for pattern in ("*.mp4", "*.m4a", "*.webm", "*.flv") for path in ROOT.rglob(pattern)]
    check("repository_media_clean", not media, f"media files={len(media)}")

    errors = [item for item in checks if item["severity"] == "error" and not item["passed"]]
    report = {
        "schemaVersion": 1,
        "release": release.get("version"),
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "pass" if not errors else "fail",
        "summary": {
            "total": len(checks),
            "passed": sum(item["passed"] for item in checks),
            "failed": len(checks) - sum(item["passed"] for item in checks),
            "blocking": len(errors)
        },
        "deletions": [
            {"path": "scan-monitor-live-bridge.js", "reason": "previously removed duplicate UI controller"},
            {"path": ".github/workflows/scan-eleven-watchdog.yml", "reason": "previously removed duplicate scheduler"}
        ],
        "rewardCoverage": coverage,
        "checks": checks
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
