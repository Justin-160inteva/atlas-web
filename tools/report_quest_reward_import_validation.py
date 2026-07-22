#!/usr/bin/env python3
"""Validate strict quest Reward-field imports and persist a compact diagnostic report."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OVERRIDES = ROOT / "data/rewards/reward-point-evidence-overrides.json"
CATALOG = ROOT / "data/rewards/reward-summary-catalog.json"
AUDIT = ROOT / "data/rewards/reward-source-audit.json"
OUTPUT = ROOT / "data/rewards/reward-quest-evidence-validation-report.json"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    baseline = load_json(Path(args.baseline), {})
    overrides = load_json(OVERRIDES, {})
    catalog = load_json(CATALOG, {})
    audit = load_json(AUDIT, {})
    records = catalog.get("records", {})
    override_records = overrides.get("records", {})
    count = int(overrides.get("overrideCount", 0))
    errors: list[str] = []
    details: list[dict[str, Any]] = []

    if catalog.get("recordCount") != 3430 or catalog.get("coverage", {}).get("total") != 3430:
        errors.append("catalog_count_failed")
    if audit.get("pointOverrideLocations") != count:
        errors.append("point_override_count_mismatch")
    expected_unresolved = int(baseline.get("unresolved", 0)) - count
    actual_unresolved = int(audit.get("statusCounts", {}).get("unresolved", 0))
    if actual_unresolved != expected_unresolved:
        errors.append("unresolved_delta_mismatch")
    for key in (
        "exactly3430Records",
        "oneRecordPerLocation",
        "coverageConserved",
        "batchLimitRespected",
        "allPointOverridesApplied",
        "singleSourcePointOverridesStayInference",
    ):
        if not audit.get("invariants", {}).get(key):
            errors.append(f"audit_invariant_failed:{key}")

    for location_id, override in override_records.items():
        record = records.get(location_id, {})
        row_errors: list[str] = []
        if record.get("status") != "high_confidence_inference":
            row_errors.append("status_not_high_confidence_inference")
        if float(record.get("confidence", -1)) != 0.88:
            row_errors.append("confidence_not_0_88")
        if len(record.get("sources", [])) != 1:
            row_errors.append("source_count_not_one")
        if record.get("review", {}).get("method") != "atlas_reward_builder_v2_point_override":
            row_errors.append("review_method_mismatch")
        if not record.get("rewards"):
            row_errors.append("missing_parsed_rewards")
        if "高置信推断" not in str(record.get("summaryZhCN") or ""):
            row_errors.append("summary_missing_inference_label")
        if row_errors:
            errors.append(f"override_record_failed:{location_id}")
        details.append({
            "locationId": location_id,
            "title": override.get("title"),
            "rewardFieldOriginal": override.get("rewardFieldOriginal"),
            "rewardLines": override.get("rewardLines"),
            "recordStatus": record.get("status"),
            "confidence": record.get("confidence"),
            "summaryZhCN": record.get("summaryZhCN"),
            "rewards": record.get("rewards"),
            "sourceCount": len(record.get("sources", [])),
            "reviewMethod": record.get("review", {}).get("method"),
            "errors": row_errors,
        })

    broken = records.get("location-mapgenie-437614", {})
    broken_reward_types = {(reward.get("type"), reward.get("quantity")) for reward in broken.get("rewards", [])}
    broken_errors: list[str] = []
    if ("experience", 2000) not in broken_reward_types:
        broken_errors.append("missing_2000_experience")
    if ("skill_point", 3) not in broken_reward_types:
        broken_errors.append("missing_3_skill_points")
    if any(str(source.get("sourceId") or "").startswith("mapgenie-") for source in broken.get("sources", [])):
        broken_errors.append("mapgenie_incorrectly_counted_as_reward_source")
    if broken_errors:
        errors.append("broken_horn_exact_values_failed")

    report = {
        "schemaVersion": 1,
        "release": "0.9.4.8",
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "valid": not errors,
        "validationErrors": errors,
        "baseline": baseline,
        "overrideCount": count,
        "expectedUnresolved": expected_unresolved,
        "actualUnresolved": actual_unresolved,
        "catalogCoverage": catalog.get("coverage"),
        "auditPointOverrideLocations": audit.get("pointOverrideLocations"),
        "brokenHorn": {
            "summaryZhCN": broken.get("summaryZhCN"),
            "rewards": broken.get("rewards"),
            "sources": broken.get("sources"),
            "errors": broken_errors,
        },
        "overrides": details,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "valid": report["valid"],
        "errors": errors,
        "overrides": count,
        "unresolved": f"{baseline.get('unresolved')}->{actual_unresolved}",
        "brokenHorn": broken.get("summaryZhCN"),
    }, ensure_ascii=False))
    return 1 if args.validate and errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
