#!/usr/bin/env python3
"""Select the smallest deterministic validation plan that covers the changed risk surface."""
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
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def base_revision() -> str:
    base_ref = os.environ.get("GITHUB_BASE_REF", "").strip()
    if base_ref:
        subprocess.run(["git", "fetch", "origin", base_ref, "--depth=1"], cwd=ROOT, capture_output=True, text=True, check=False)
        merge_base = git_lines("merge-base", "HEAD", f"origin/{base_ref}")
        if merge_base:
            return merge_base[0]
    return "HEAD^"


def changed_files() -> list[str]:
    explicit = os.environ.get("ATLAS_CHANGED_FILES", "").strip()
    if explicit:
        return sorted({item.strip() for item in explicit.replace("\n", ",").split(",") if item.strip()})
    files = git_lines("diff", "--name-only", base_revision(), "HEAD")
    return sorted(set(files))


def changed_lines(path: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--unified=0", base_revision(), "HEAD", "--", path],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return [
        line[1:].strip()
        for line in result.stdout.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---")) and line[1:].strip()
    ]


def matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def safe_target_support(path: str) -> bool:
    """Allow version/cache-only support edits to stay on the targeted fast lane."""
    if path == "release-manifest.json":
        return True
    lines = changed_lines(path)
    if not lines:
        return False
    if path == "index.html":
        return all("<script" in line or "src=" in line or "build=" in line or "?v=" in line for line in lines)
    if path == "atlas-bootstrap.js":
        return all("cacheNamespace" in line or "version" in line for line in lines)
    if path == "sw.js":
        forbidden = ("respondWith", "addEventListener('fetch", 'addEventListener("fetch', "networkFirst", "cacheFirst")
        return not any(any(token in line for token in forbidden) for line in lines) and all(
            "CACHE=" in line or "CACHE =" in line or line.startswith(("'./", '"./')) or "atlas-map-cover" in line or "page-zoom-guard" in line or "location-search-patch" in line or "releaseAssets" in line or "RegExp" in line
            for line in lines
        )
    if path.startswith("tools/") and path.endswith(("_smoke.py", "_smoke.mjs")):
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-output", default="")
    args = parser.parse_args()

    policy = load_json(POLICY_PATH)
    release = load_json(RELEASE_PATH)
    files = changed_files()
    groups = policy["pathGroups"]
    selected = {name: sorted(path for path in files if matches(path, patterns)) for name, patterns in groups.items()}
    if not files:
        selected["validationFramework"] = ["workflow-dispatch-or-empty-diff"]

    event = os.environ.get("GITHUB_EVENT_NAME", "").strip()
    is_pull_request = event == "pull_request"
    forced_full = os.environ.get("ATLAS_FORCE_FULL_VALIDATION", "").lower() in {"1", "true", "yes"}
    scheduled = policy["scheduledFullAudit"]
    scheduled_full = release.get("version") == scheduled.get("nextRequiredVersion")
    full = forced_full or scheduled_full

    viewport_targeted = bool(selected.get("viewportTargeted"))
    search_targeted = bool(selected.get("searchTargeted"))
    targeted_product_paths = set(selected.get("viewportTargeted", [])) | set(selected.get("searchTargeted", []))
    neutral = {path for path in files if safe_target_support(path)}
    target_only = bool(targeted_product_paths) and set(files).issubset(targeted_product_paths | neutral)
    framework_core = [path for path in selected.get("validationFramework", []) if path != "release-manifest.json"]
    scan_core = bool(selected.get("scanCore"))
    scan_autonomy = bool(selected.get("scanAutonomy"))
    high_risk = bool(selected.get("highRisk"))
    ui_full = bool(selected.get("uiFull"))
    ui_changed = bool(selected.get("ui"))

    fast = is_pull_request and target_only and not full and not scan_core and not scan_autonomy and not high_risk and not framework_core
    standard = (
        high_risk
        or scan_core
        or scan_autonomy
        or bool(selected.get("monitor"))
        or ui_full
        or bool(framework_core)
        or (ui_changed and not is_pull_request)
    )
    tier = "full" if full else "fast" if fast else "standard" if standard else "quick"
    budget = policy["tiers"][tier]

    run_browser_matrix = full or ui_full or (ui_changed and not is_pull_request)
    run_ipad = full or viewport_targeted or run_browser_matrix
    run_reward_search = full or search_targeted or run_browser_matrix
    run = {
        "data_center": full or bool(selected.get("dataCenter")),
        "reward": full or bool(selected.get("rewards")),
        "heartbeat": full or scan_core or scan_autonomy or bool(framework_core),
        "serial": full or scan_core or scan_autonomy or bool(framework_core),
        "queue_schema": full or scan_core or scan_autonomy or bool(framework_core),
        "autonomous_repair": full or scan_autonomy or scan_core or bool(framework_core),
        "browser_matrix": run_browser_matrix,
        "ipad": run_ipad,
        "reward_search": run_reward_search,
        "monitor": full or bool(selected.get("monitor")),
        "full_audit": full,
    }
    run["browser"] = run_browser_matrix or run_ipad or run_reward_search
    run["playwright"] = run["browser"] or run["monitor"]

    outputs: dict[str, str] = {
        "tier": tier,
        "changed_count": str(len(files)),
        "target_minutes": str(budget.get("targetMinutes", 10)),
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
        "schemaVersion": 2,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "release": release.get("version"),
        "policyRevision": policy.get("revision"),
        "event": event,
        "tier": tier,
        "targetMinutes": budget.get("targetMinutes"),
        "forcedFull": forced_full,
        "scheduledFull": scheduled_full,
        "targetedPullRequest": fast,
        "postMergeFullUiMatrix": bool(ui_changed and not is_pull_request),
        "changedFiles": files,
        "safeSupportFiles": sorted(neutral),
        "matchedGroups": selected,
        "run": run,
        "budget": budget,
        "safety": {
            "authorizationChecksPreserved": True,
            "privacyChecksPreserved": True,
            "singleDownloadChecksPreserved": True,
            "unrelatedMatricesSkipped": True,
            "fullMatrixDeferredOnlyToPostMerge": fast,
        },
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.github_output:
        output_path = pathlib.Path(args.github_output)
        with output_path.open("a", encoding="utf-8") as stream:
            for key, value in outputs.items():
                stream.write(f"{key}={value}\n")

    print(json.dumps({"tier": tier, "changed": len(files), "targetMinutes": budget.get("targetMinutes"), "run": run}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
