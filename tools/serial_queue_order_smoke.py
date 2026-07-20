#!/usr/bin/env python3
"""Run a risk-budgeted strict-order matrix for supervisor-projected queued items."""
from __future__ import annotations

import copy
import json
import os
import pathlib

import run_scan_with_auto_recovery_v2 as serial

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGES = list(range(25, 36))
results: list[dict[str, object]] = []
REQUESTED_CHECKS = max(5, int(os.environ.get("ATLAS_CHECKS", "500")))
VALIDATION_TIER = os.environ.get("ATLAS_VALIDATION_TIER", "full" if REQUESTED_CHECKS >= 500 else "targeted")


def group_sizes(total: int, groups: int) -> list[int]:
    base, remainder = divmod(total, groups)
    return [base + (1 if index < remainder else 0) for index in range(groups)]


def make_queue(states: list[str]) -> dict:
    return {
        "status": "queued",
        "maximumQueueItems": 11,
        "maximumConcurrentItems": 1,
        "items": [
            {
                "externalSourceId": f"p{page:03d}",
                "sequence": page,
                "page": page,
                "state": state,
                "attemptCount": 0,
            }
            for page, state in zip(PAGES, states, strict=True)
        ],
    }


def active_count(queue: dict) -> int:
    return sum(item.get("state") in {"running", "recovery"} for item in queue["items"])


def record(name: str, passed: bool, detail: str) -> None:
    results.append({"name": name, "passed": bool(passed), "detail": detail})
    if not passed:
        raise AssertionError(f"{name}: {detail}")


queued_count, active_count_checks, pending_first_count, idempotent_count, no_queued_count = group_sizes(REQUESTED_CHECKS, 5)

for index in range(queued_count):
    prefix = index % 11
    states = ["imported"] * prefix + ["queued"] + ["pending"] * (10 - prefix)
    queue = make_queue(states)
    before_ids = [item["externalSourceId"] for item in queue["items"]]
    changed = serial.normalize_queue(queue)
    target = queue["items"][prefix]
    record(f"queued-prefix-{index:03d}", changed and target["state"] == "pending" and [item["externalSourceId"] for item in queue["items"]] == before_ids and active_count(queue) == 0, f"prefix={prefix}, target={target['externalSourceId']}")

for index in range(active_count_checks):
    active_index = 1 + (index % 10)
    active_state = "running" if index % 2 == 0 else "recovery"
    states = ["queued"] + ["pending"] * 10
    states[active_index] = active_state
    queue = make_queue(states)
    before = copy.deepcopy(queue)
    changed = serial.normalize_queue(queue)
    record(f"active-block-{index:03d}", not changed and queue == before and active_count(queue) == 1, f"active={active_index}:{active_state}")

for index in range(pending_first_count):
    queued_index = 1 + (index % 10)
    states = ["pending"] * 11
    states[queued_index] = "queued"
    queue = make_queue(states)
    before = copy.deepcopy(queue)
    changed = serial.normalize_queue(queue)
    record(f"pending-first-{index:03d}", not changed and queue == before and queue["items"][0]["state"] == "pending", f"laterQueued={queued_index}")

for index in range(idempotent_count):
    prefix = index % 11
    states = ["imported"] * prefix + ["queued"] + ["pending"] * (10 - prefix)
    queue = make_queue(states)
    first = serial.normalize_queue(queue)
    after_first = copy.deepcopy(queue)
    second = serial.normalize_queue(queue)
    record(f"idempotent-{index:03d}", first and not second and queue == after_first and queue["items"][prefix]["state"] == "pending", f"prefix={prefix}")

for index in range(no_queued_count):
    mode = index % 4
    if mode == 0:
        states = ["imported"] * 11
    elif mode == 1:
        states = ["failed"] + ["pending"] * 10
    elif mode == 2:
        prefix = index % 11
        states = ["imported"] * prefix + ["pending"] * (11 - prefix)
    else:
        states = ["pending"] * 11
    queue = make_queue(states)
    before = copy.deepcopy(queue)
    changed = serial.normalize_queue(queue)
    record(f"no-queued-{index:03d}", not changed and queue == before and active_count(queue) == 0, f"mode={mode}")

if len(results) != REQUESTED_CHECKS:
    raise SystemExit(f"expected exactly {REQUESTED_CHECKS} serial-order checks, got {len(results)}")

output = {
    "schemaVersion": 3,
    "validationTier": VALIDATION_TIER,
    "requestedChecks": REQUESTED_CHECKS,
    "queueItems": 11,
    "maximumConcurrentItems": 1,
    "coverageFamilies": ["queued-prefix", "active-block", "pending-first", "idempotent", "no-queued"],
    "totalChecks": len(results),
    "passed": all(item["passed"] for item in results),
    "checks": results,
}
out = ROOT / "data/conflict-reports/serial-queue-order-matrix.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Serial queue order matrix: {len(results)}/{REQUESTED_CHECKS} checks passed ({VALIDATION_TIER})")
