#!/usr/bin/env python3
"""Enforce Atlas project-wide release, quality and evidence contracts.

This gate is intentionally small and deterministic. It does not replace browser
or device testing; it prevents known sources of release drift and quality debt
from being accepted as a completed release.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^0\.\d+\.\d+\.\d+$")
QUERY_VERSION_RE = re.compile(r"[?&]v=(0\.\d+\.\d+\.\d+)")


def load_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("static", "browser"), default="static")
    args = parser.parse_args()

    manifest = load_json("release-manifest.json")
    audit = load_json("data/version-audit.json")
    roadmap = read("PROJECT-ROADMAP.md")
    index = read("index.html")
    bootstrap = read("atlas-bootstrap.js")
    service_worker = read("sw.js")
    report = load_json("data/conflict-reports/latest.json")
    budget = manifest.get("qualityBudget", {})
    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    version = manifest.get("version", "")
    require(bool(VERSION_RE.fullmatch(version)), f"Invalid release version: {version!r}")
    require(audit.get("currentVersion") == version, "version-audit currentVersion differs from release manifest")
    require(f"Updated baseline: Alpha {version}" in roadmap, "roadmap baseline differs from release manifest")
    require(manifest.get("versionText") in index, "index release label differs from release manifest")
    require(manifest.get("versionText") in bootstrap, "bootstrap release label differs from release manifest")
    require(version in bootstrap, "bootstrap release version differs from release manifest")
    require(manifest.get("cacheNamespace") in bootstrap, "bootstrap cache namespace differs from release manifest")
    require(manifest.get("cacheNamespace") in service_worker, "service-worker cache namespace differs from release manifest")

    query_versions = set(QUERY_VERSION_RE.findall(index))
    require(not query_versions or query_versions == {version}, f"index contains mixed release query versions: {sorted(query_versions)}")

    require("const CACHE_PREFIX='atlas-alpha-'" in service_worker, "service worker lacks Atlas-scoped cache deletion prefix")
    require("key.startsWith(CACHE_PREFIX)&&key!==CACHE" in service_worker.replace(" ", ""), "service worker may delete caches outside Atlas")

    require(report.get("release") == version, "conflict report was generated for a different release")
    summary = report.get("summary", {})
    critical = int(summary.get("critical", 0))
    high = int(summary.get("high", 0))
    warnings = int(summary.get("warning", 0))
    risk = int(report.get("riskScore", 100))
    require(critical <= int(budget.get("maxCritical", 0)), f"critical findings exceed budget: {critical}")
    require(high <= int(budget.get("maxHigh", 0)), f"high findings exceed budget: {high}")
    require(warnings <= int(budget.get("maxWarnings", 0)), f"warning debt increased: {warnings}")
    require(risk <= int(budget.get("maxRiskScore", 0)), f"risk score increased: {risk}")
    require(report.get("status") != "blocked", "conflict reasoner blocked the release")

    # Legacy release scripts may remain as history, but an active workflow may not
    # invoke a script that pads its count with repeated integrity slices.
    workflows = list((ROOT / ".github" / "workflows").glob("*.yml"))
    active_text = "\n".join(path.read_text(encoding="utf-8") for path in workflows)
    for script in (ROOT / "tools").glob("validate_release_*.py"):
        text = script.read_text(encoding="utf-8")
        padded = "while len(results)<" in text and "integrity" in text
        require(not (padded and script.name in active_text), f"active workflow invokes padded verification script {script.name}")

    if args.phase == "browser":
        matrix = load_json("data/conflict-reports/browser-matrix.json")
        verification = manifest.get("verification", {})
        total = int(matrix.get("totalChecks", 0))
        require(matrix.get("release") == version, "browser matrix was generated for a different release")
        require(matrix.get("passed") is True, "browser matrix did not pass")
        require(total >= int(verification.get("browserChecksMin", 200)), f"browser matrix has too few checks: {total}")
        require(total <= int(verification.get("browserChecksMax", 500)), f"browser matrix has too many checks: {total}")

    if errors:
        for error in errors:
            print(f"CONTRACT ERROR: {error}", file=sys.stderr)
        return 2

    print(f"Atlas project contract passed: release={version} phase={args.phase} warnings={warnings} risk={risk}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
