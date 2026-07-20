#!/usr/bin/env python3
"""Run a risk-budgeted queue-schema hydration matrix."""
from __future__ import annotations

import copy
import json
import os
import pathlib

import run_scan_with_auto_recovery_v2 as wrapper

ROOT = pathlib.Path(__file__).resolve().parents[1]
catalog = json.loads((ROOT / "data/eleven-game-world-ac-shadows-catalog.json").read_text(encoding="utf-8"))
source_items = [item for item in catalog.get("items", []) if 25 <= int(item.get("page", 0)) <= 35]
source_by_id = {item["id"]: item for item in source_items}
results: list[dict[str, object]] = []
REQUESTED_CHECKS = max(5, int(os.environ.get("ATLAS_CHECKS", "500")))
VALIDATION_TIER = os.environ.get("ATLAS_VALIDATION_TIER", "full" if REQUESTED_CHECKS >= 500 else "targeted")


def group_sizes(total: int, groups: int) -> list[int]:
    base, remainder = divmod(total, groups)
    return [base + (1 if index < remainder else 0) for index in range(groups)]


def queue_item(page: int) -> dict:
    source = source_by_id[f"bili-eleven-acshadows-BV1FdQ9YdEcN-p{page:03d}"]
    return {
        "externalSourceId": source["id"],
        "sequence": source["sequence"],
        "page": source["page"],
        "title": source["title"],
        "url": source["url"],
        "bvid": source["bvid"],
        "cid": source["cid"],
        "durationSeconds": source["durationSeconds"],
        "scanClass": source["scanClass"],
        "mapUtility": source["mapUtility"],
        "priority": source["priority"],
        "partTitle": source["partTitle"],
        "state": "pending",
    }


def record(name: str, passed: bool, detail: str) -> None:
    results.append({"name": name, "passed": bool(passed), "detail": detail})
    if not passed:
        raise AssertionError(f"{name}: {detail}")


title_count, identity_count, analysis_count, idempotent_count, unknown_count = group_sizes(REQUESTED_CHECKS, 5)

for index in range(title_count):
    page = 25 + index % 11
    item = queue_item(page)
    item.pop("title")
    queue = {"items": [item]}
    changed = wrapper.hydrate_queue_from_catalog(queue, catalog)
    record(f"title-{index:03d}", changed and queue["items"][0]["title"] == source_by_id[item["externalSourceId"]]["title"], f"page={page}")

for index in range(identity_count):
    page = 25 + index % 11
    item = queue_item(page)
    for field in ("url", "bvid", "cid"):
        item.pop(field)
    queue = {"items": [item]}
    changed = wrapper.hydrate_queue_from_catalog(queue, catalog)
    record(f"identity-{index:03d}", changed and all(queue["items"][0].get(field) not in (None, "") for field in ("url", "bvid", "cid")), f"page={page}")

for index in range(analysis_count):
    page = 25 + index % 11
    item = queue_item(page)
    for field in ("durationSeconds", "scanClass", "mapUtility", "priority", "partTitle"):
        item.pop(field)
    queue = {"items": [item]}
    changed = wrapper.hydrate_queue_from_catalog(queue, catalog)
    record(f"analysis-{index:03d}", changed and all(queue["items"][0].get(field) not in (None, "") for field in ("durationSeconds", "scanClass", "mapUtility", "priority", "partTitle")), f"page={page}")

for index in range(idempotent_count):
    page = 25 + index % 11
    original = queue_item(page)
    queue = {"items": [copy.deepcopy(original)]}
    changed = wrapper.hydrate_queue_from_catalog(queue, catalog)
    record(f"idempotent-{index:03d}", not changed and queue["items"][0] == original, f"page={page}")

for index in range(unknown_count):
    queue = {"items": [{"externalSourceId": f"unknown-{index}", "state": "pending"}]}
    failed = False
    try:
        wrapper.hydrate_queue_from_catalog(queue, catalog)
    except KeyError:
        failed = True
    record(f"unknown-{index:03d}", failed and queue["items"][0]["externalSourceId"] == f"unknown-{index}", "unknown IDs must stop before transfer")

if len(results) != REQUESTED_CHECKS:
    raise SystemExit(f"expected exactly {REQUESTED_CHECKS} queue-schema checks, got {len(results)}")
report = {
    "schemaVersion": 2,
    "validationTier": VALIDATION_TIER,
    "requestedChecks": REQUESTED_CHECKS,
    "queueItems": 11,
    "maximumConcurrentItems": 1,
    "coverageFamilies": ["title", "identity", "analysis", "idempotent", "unknown-id-stop"],
    "totalChecks": len(results),
    "passed": all(item["passed"] for item in results),
    "checks": results,
}
out = ROOT / "data/conflict-reports/queue-schema-matrix.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Queue schema hydration matrix: {len(results)}/{REQUESTED_CHECKS} checks passed ({VALIDATION_TIER})")
