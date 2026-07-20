#!/usr/bin/env python3
"""Run exactly 500 queue-schema hydration checks."""
from __future__ import annotations

import copy
import json
import pathlib

import run_scan_with_auto_recovery_v2 as wrapper

ROOT = pathlib.Path(__file__).resolve().parents[1]
catalog = json.loads((ROOT / "data/eleven-game-world-ac-shadows-catalog.json").read_text(encoding="utf-8"))
source_items = [item for item in catalog.get("items", []) if 25 <= int(item.get("page", 0)) <= 35]
source_by_id = {item["id"]: item for item in source_items}
results: list[dict[str, object]] = []


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


for index in range(100):
    page = 25 + index % 11
    item = queue_item(page)
    item.pop("title")
    queue = {"items": [item]}
    changed = wrapper.hydrate_queue_from_catalog(queue, catalog)
    record(f"title-{index:03d}", changed and queue["items"][0]["title"] == source_by_id[item["externalSourceId"]]["title"], f"page={page}")

for index in range(100):
    page = 25 + index % 11
    item = queue_item(page)
    for field in ("url", "bvid", "cid"):
        item.pop(field)
    queue = {"items": [item]}
    changed = wrapper.hydrate_queue_from_catalog(queue, catalog)
    record(f"identity-{index:03d}", changed and all(queue["items"][0].get(field) not in (None, "") for field in ("url", "bvid", "cid")), f"page={page}")

for index in range(100):
    page = 25 + index % 11
    item = queue_item(page)
    for field in ("durationSeconds", "scanClass", "mapUtility", "priority", "partTitle"):
        item.pop(field)
    queue = {"items": [item]}
    changed = wrapper.hydrate_queue_from_catalog(queue, catalog)
    record(f"analysis-{index:03d}", changed and all(queue["items"][0].get(field) not in (None, "") for field in ("durationSeconds", "scanClass", "mapUtility", "priority", "partTitle")), f"page={page}")

for index in range(100):
    page = 25 + index % 11
    original = queue_item(page)
    queue = {"items": [copy.deepcopy(original)]}
    changed = wrapper.hydrate_queue_from_catalog(queue, catalog)
    record(f"idempotent-{index:03d}", not changed and queue["items"][0] == original, f"page={page}")

for index in range(100):
    queue = {"items": [{"externalSourceId": f"unknown-{index}", "state": "pending"}]}
    failed = False
    try:
        wrapper.hydrate_queue_from_catalog(queue, catalog)
    except KeyError:
        failed = True
    record(f"unknown-{index:03d}", failed and queue["items"][0]["externalSourceId"] == f"unknown-{index}", "unknown IDs must stop before transfer")

if len(results) != 500:
    raise SystemExit(f"expected exactly 500 queue-schema checks, got {len(results)}")
report = {
    "schemaVersion": 1,
    "queueItems": 11,
    "maximumConcurrentItems": 1,
    "totalChecks": len(results),
    "passed": all(item["passed"] for item in results),
    "checks": results,
}
out = ROOT / "data/conflict-reports/queue-schema-matrix.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Queue schema hydration matrix: 500/500 checks passed")
