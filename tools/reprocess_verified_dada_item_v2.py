#!/usr/bin/env python3
"""Hardened wrapper for one verified Dada reprocessing request.

It adds sequence-neutral preflight checks, preserves the identity of the stale
result being replaced, and can verify the post-audit queue transition. The
legacy analyzer remains the single implementation for media processing.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEGACY_TOOL = ROOT / "tools/reprocess_verified_dada_item.py"
CATALOG_PATH = ROOT / "data/dada-ac-shadows-catalog.json"
QUEUE_PATH = ROOT / "data/analysis-jobs/dada-quality-reprocess.json"
BVID_RE = re.compile(r"BV[0-9A-Za-z]+")


def load(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: pathlib.Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def bvid_from(value: Any) -> str | None:
    match = BVID_RE.search(str(value or ""))
    return match.group(0) if match else None


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def resolve_manifest(value: str) -> pathlib.Path:
    path = (ROOT / value).resolve()
    allowed = (ROOT / "data/reprocess").resolve()
    require(path.is_relative_to(allowed), "manifest must stay inside data/reprocess")
    require(path.is_file(), f"manifest does not exist: {path.relative_to(ROOT)}")
    return path


def validate_manifest(
    path: pathlib.Path,
    *,
    require_stale_identity: bool = True,
) -> tuple[dict[str, Any], int, pathlib.Path]:
    manifest = load(path)
    sequence = int(manifest.get("sequence") or 0)
    padded = f"{sequence:02d}"
    verified_bvid = str(manifest.get("verifiedBvid") or "")
    verified_url = str(manifest.get("verifiedUrl") or "")
    expected_result = f"data/analysis-results/dada-{padded}.json"
    result_path = ROOT / expected_result
    expected_scope = f"sequence-{padded}-only"

    checks = {
        "schemaVersion": manifest.get("schemaVersion") == 1,
        "sequencePositive": sequence > 0,
        "filenameMatchesSequence": path.name == f"dada-seq{padded}.json",
        "scopeMatchesSequence": manifest.get("scope") == expected_scope,
        "verifiedBvid": bool(BVID_RE.fullmatch(verified_bvid)),
        "verifiedUrl": verified_url == f"https://www.bilibili.com/video/{verified_bvid}/",
        "resultPath": manifest.get("replaceResultPath") == expected_result,
        "replaceWrongBvid": bool(BVID_RE.fullmatch(str(manifest.get("replaceWrongBvid") or ""))),
        "replaceJobId": bool(str(manifest.get("replaceJobId") or "")),
        "expectedDuration": int(manifest.get("expectedDurationSeconds") or 0) > 0,
        "resultExists": result_path.is_file(),
    }
    require(all(checks.values()), "manifest preflight failed: " + json.dumps(checks, ensure_ascii=False))

    # Before analysis, the existing result must be the exact stale result named
    # by the manifest. After analysis, that file has intentionally been replaced
    # by the verified result, so transition verification must not re-apply the
    # stale identity assertions.
    if require_stale_identity:
        stale_result = load(result_path)
        stale_checks = {
            "jobIdMatches": stale_result.get("jobId") == manifest.get("replaceJobId"),
            "wrongBvidMatches": bvid_from((stale_result.get("source") or {}).get("url")) == manifest.get("replaceWrongBvid"),
            "staleResultNotRetained": (stale_result.get("media") or {}).get("videoRetained") is False,
            "staleFramesNotRetained": (stale_result.get("media") or {}).get("framePixelsRetained") is False,
        }
        require(all(stale_checks.values()), "stale-result identity failed: " + json.dumps(stale_checks, ensure_ascii=False))
    return manifest, sequence, result_path


def run_legacy(path: pathlib.Path, validate_only: bool) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(LEGACY_TOOL), path.relative_to(ROOT).as_posix()]
    if validate_only:
        command.append("--validate-only")
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True)


def patch_sequence_metadata(manifest: dict[str, Any], sequence: int) -> None:
    catalog = load(CATALOG_PATH)
    item = next(entry for entry in catalog["items"] if int(entry.get("sequence") or 0) == sequence)
    verification = item.setdefault("analysisVerification", {})
    verification["replacesJobId"] = manifest["replaceJobId"]
    verification["replacesWrongBvid"] = manifest["replaceWrongBvid"]
    write(CATALOG_PATH, catalog)

    report_path = ROOT / f"data/batch-analysis/dada-seq{sequence:02d}-reprocess-status.json"
    report = load(report_path)
    report["replacesJobId"] = manifest["replaceJobId"]
    report["selfCheckRounds"] = int(manifest.get("selfCheckRounds") or 400)
    write(report_path, report)


def verify_transition(manifest: dict[str, Any], sequence: int, result_path: pathlib.Path) -> dict[str, bool]:
    result = load(result_path)
    report = load(ROOT / f"data/batch-analysis/dada-seq{sequence:02d}-reprocess-status.json")
    queue = load(QUEUE_PATH)
    catalog = load(CATALOG_PATH)
    item = next(entry for entry in catalog["items"] if int(entry.get("sequence") or 0) == sequence)
    expected_remaining = manifest.get("expectedRemainingSequences")

    checks = {
        "statusAnalyzed": result.get("status") == "analyzed",
        "bvidExact": bvid_from((result.get("source") or {}).get("url")) == manifest["verifiedBvid"],
        "durationWithinTolerance": abs(float((result.get("media") or {}).get("durationSeconds") or 0) - int(manifest["expectedDurationSeconds"])) <= 3,
        "videoDeleted": (result.get("media") or {}).get("videoRetained") is False,
        "framesDeleted": (result.get("media") or {}).get("framePixelsRetained") is False,
        "reportComplete": report.get("status") == "complete",
        "qualityVerified": item.get("analysisQualityStatus") == "verified-correct-source",
        "replacesJobId": (item.get("analysisVerification") or {}).get("replacesJobId") == manifest["replaceJobId"],
        "sequenceRemovedFromQueue": sequence not in set(queue.get("sequences") or []),
    }
    if expected_remaining is not None:
        checks["remainingQueueExact"] = set(queue.get("sequences") or []) == set(expected_remaining)
    require(all(checks.values()), "post-audit transition failed: " + json.dumps(checks, ensure_ascii=False))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--verify-transition", action="store_true")
    parser.add_argument("--self-check-rounds", type=int, default=400)
    args = parser.parse_args()
    require(not (args.validate_only and args.verify_transition), "choose only one validation mode")
    require(1 <= args.self_check_rounds <= 2000, "self-check rounds must be between 1 and 2000")

    manifest_path = resolve_manifest(args.manifest)
    manifest: dict[str, Any] | None = None
    sequence = 0
    result_path = ROOT
    for _ in range(args.self_check_rounds):
        manifest, sequence, result_path = validate_manifest(
            manifest_path,
            require_stale_identity=not args.verify_transition,
        )
    assert manifest is not None

    if args.verify_transition:
        checks: dict[str, bool] = {}
        for _ in range(args.self_check_rounds):
            checks = verify_transition(manifest, sequence, result_path)
        print(json.dumps({"sequence": sequence, "status": "verified", "rounds": args.self_check_rounds, "checks": checks}, ensure_ascii=False))
        return 0

    legacy = run_legacy(manifest_path, validate_only=args.validate_only)
    if legacy.returncode != 0:
        raise RuntimeError((legacy.stdout + "\n" + legacy.stderr)[-6000:])
    if args.validate_only:
        print(json.dumps({"sequence": sequence, "status": "ready", "rounds": args.self_check_rounds}, ensure_ascii=False))
        return 0

    patch_sequence_metadata(manifest, sequence)
    print(legacy.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
