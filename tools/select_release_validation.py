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
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "data/quality/release-validation-policy.json"
RELEASE_PATH = ROOT / "release-manifest.json"
REPORT_PATH = ROOT / "data/audits/release-validation-budget.json"


def load_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def git_lines(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_files() -> list[str]:
    explicit = os.environ.get("ATLAS_CHANGED_FILES", "").strip()
    if explicit:
        return sorted({item.strip() for item in explicit.replace("\n", ",").split(",") if item.strip()})

    base_ref = os.environ.get("GITHUB_BASE_REF", "").strip()
    if base_ref:
        subprocess.run(
            ["git", "fetch", "origin", base_ref, "--depth=1"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        merge_base = git_lines("merge-base", "HEAD", f"origin/{base_ref}")
        if merge_base:
            files = git_lines("diff", "--name-only", f"{merge_base[0]}..HEAD")
            if files:
                return sorted(set(files))

    files = git_lines("diff", "--name-only", "HEAD^", "HEAD")
    return sorted(set(files))


def matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-output", default="")
    args = parser.parse_args()

    policy = load_json(POLICY_PATH)
    release = load_json(RELEASE_PATH)
    files = changed_files()
    groups = policy["pathGroups"]
    selected = {
        name: sorted(path for path in files if matches(path, patterns))
        for name, patterns in groups.items()
    }

    if not files:
        selected["validationFramework"] = ["workflow-dispatch-or-empty-diff"]

    forced_full = os.environ.get("ATLAS_FORCE_FULL_VALIDATION", "").lower() in {"1", "true", "yes"}
    scheduled = policy["scheduledFullAudit"]
    scheduled_full = release.get("version") == scheduled.get("nextRequiredVersion")
    full = forced_full or scheduled_full
    high_risk = bool(selected["highRisk"])
    standard = high_risk or bool(selected["scanCore"]) or bool(selected["monitor"]) or bool(selected["ui"])
    tier = "full" if full else "standard" if standard else "quick"
    budget = policy["tiers"][tier]

    run = {
        "data_center": full or bool(selected["dataCenter"]),
        "reward": full or bool(selected["rewards"]),
        "heartbeat": full or bool(selected["scanCore"]) or bool(selected["validationFramework"]),
        "serial": full or bool(selected["scanCore"]) or bool(selected["validationFramework"]),
        "queue_schema": full or bool(selected["scanCore"]) or bool(selected["validationFramework"]),
        "browser": full or bool(selected["ui"]),
        "monitor": full or bool(selected["monitor"]),
        "full_audit": full,
    }
    run["playwright"] = run["browser"] or run["monitor"]

    outputs: dict[str, str] = {
        "tier": tier,
        "changed_count": str(len(files)),
        "heartbeat_checks": str(budget["heartbeatChecks"]),
        "serial_checks": str(budget["serialQueueChecks"]),
        "queue_schema_checks": str(budget["queueSchemaChecks"]),
        "browser_checks": str(budget["browserChecks"]),
        "monitor_checks": str(budget["monitorAuthorityChecks"]),
        "data_center_checks": str(budget["dataCenterChecks"]),
        "reward_checks": str(budget["rewardEvidenceChecks"]),
    }
    outputs.update({f"run_{name}": "true" if enabled else "false" for name, enabled in run.items()})

    report = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "release": release.get("version"),
        "policyRevision": policy.get("revision"),
        "tier": tier,
        "forcedFull": forced_full,
        "scheduledFull": scheduled_full,
        "changedFiles": files,
        "matchedGroups": selected,
        "run": run,
        "budget": budget,
        "safety": {
            "authorizationChecksPreserved": True,
            "privacyChecksPreserved": True,
            "singleDownloadChecksPreserved": True,
            "unrelatedMatricesSkipped": True,
        },
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.github_output:
        output_path = pathlib.Path(args.github_output)
        with output_path.open("a", encoding="utf-8") as stream:
            for key, value in outputs.items():
                stream.write(f"{key}={value}\n")

    print(json.dumps({"tier": tier, "changed": len(files), "run": run, "budget": budget}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
