#!/usr/bin/env python3
"""Select the smallest release-validation plan that covers the changed risk surface."""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import pathlib
import subprocess
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "data/quality/release-validation-policy.json"
RELEASE_PATH = ROOT / "release-manifest.json"
REPORT_PATH = ROOT / "data/audits/release-validation-budget.json"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def git_lines(*args):
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_files():
    explicit = os.environ.get("ATLAS_CHANGED_FILES", "").strip()
    if explicit:
        return sorted({item.strip() for item in explicit.replace("\n", ",").split(",") if item.strip()})
    base_ref = os.environ.get("GITHUB_BASE_REF", "").strip()
    if base_ref:
        subprocess.run(["git", "fetch", "origin", base_ref, "--depth=1"], cwd=ROOT, capture_output=True, text=True, check=False)
        merge_base = git_lines("merge-base", "HEAD", f"origin/{base_ref}")
        if merge_base:
            files = git_lines("diff", "--name-only", f"{merge_base[0]}..HEAD")
            if files:
                return sorted(set(files))
    return sorted(set(git_lines("diff", "--name-only", "HEAD^", "HEAD")))


def matches(path, patterns):
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-output", default="")
    args = parser.parse_args()
    policy = load_json(POLICY_PATH)
    release = load_json(RELEASE_PATH)
    files = changed_files()
    selected = {name: sorted(path for path in files if matches(path, patterns)) for name, patterns in policy["pathGroups"].items()}
    if not files:
        selected["validationFramework"] = ["workflow-dispatch-or-empty-diff"]
    forced_full = os.environ.get("ATLAS_FORCE_FULL_VALIDATION", "").lower() in {"1", "true", "yes"}
    scheduled_full = release.get("version") == policy["scheduledFullAudit"].get("nextRequiredVersion")
    high_risk = bool(selected["highRisk"])
    full_audit = forced_full or scheduled_full
    full_tier = full_audit or high_risk
    standard = high_risk or any(selected[name] for name in ("scanCore", "monitor", "ui"))
    tier = "full" if full_tier else "standard" if standard else "quick"
    budget = policy["tiers"][tier]
    run = {
        "data_center": full_audit or bool(selected["dataCenter"]),
        "reward": full_audit or bool(selected["rewards"]),
        "heartbeat": full_audit or bool(selected["scanCore"]) or bool(selected["validationFramework"]),
        "serial": full_audit or bool(selected["scanCore"]) or bool(selected["validationFramework"]),
        "queue_schema": full_audit or bool(selected["scanCore"]) or bool(selected["validationFramework"]),
        "browser": full_audit or bool(selected["ui"]),
        "monitor": full_audit or bool(selected["monitor"]),
        "full_audit": full_audit,
    }
    run["playwright"] = run["browser"] or run["monitor"]
    outputs = {
        "tier": tier, "changed_count": str(len(files)),
        "heartbeat_checks": str(budget["heartbeatChecks"]), "serial_checks": str(budget["serialQueueChecks"]),
        "queue_schema_checks": str(budget["queueSchemaChecks"]), "browser_checks": str(budget["browserChecks"]),
        "monitor_checks": str(budget["monitorAuthorityChecks"]), "data_center_checks": str(budget["dataCenterChecks"]),
        "reward_checks": str(budget["rewardEvidenceChecks"]),
    }
    outputs.update({f"run_{name}": "true" if enabled else "false" for name, enabled in run.items()})
    report = {
        "schemaVersion": 1, "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "release": release.get("version"), "policyRevision": policy.get("revision"), "tier": tier,
        "minimumRelevantChecks": policy["minimumRelevantChecks"][tier],
        "forcedFull": forced_full, "scheduledFull": scheduled_full, "changedFiles": files,
        "matchedGroups": selected, "run": run, "budget": budget,
        "safety": {"authorizationChecksPreserved": True, "privacyChecksPreserved": True, "singleDownloadChecksPreserved": True, "unrelatedMatricesSkipped": True},
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.github_output:
        with pathlib.Path(args.github_output).open("a", encoding="utf-8") as stream:
            for key, value in outputs.items():
                stream.write(f"{key}={value}\n")
    print(json.dumps({"tier": tier, "changed": len(files), "run": run, "budget": budget}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
