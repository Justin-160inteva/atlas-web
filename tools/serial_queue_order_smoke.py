#!/usr/bin/env python3
"""Run exactly 500 strict-order checks for supervisor-projected queued items."""
from __future__ import annotations

import copy
import json
import pathlib

import run_scan_with_auto_recovery_v2 as serial

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGES = [12, 13, 14, 15, 16, 17, 18, 19, 23, 24]
results: list[dict[str, object]] = []


def make_queue(states: list[str]) -> dict:
    return {
        "status": "queued",
        "maximumQueueItems": 10,
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


# 100 imported-prefix scenarios: the earliest remaining queued item must become pending.
for index in range(100):
    prefix = index % 10
    states = ["imported"] * prefix + ["queued"] + ["pending"] * (9 - prefix)
    queue = make_queue(states)
    before_ids = [item["externalSourceId"] for item in queue["items"]]
    changed = serial.normalize_queue(queue)
    target = queue["items"][prefix]
    record(
        f"queued-prefix-{index:03d}",
        changed
        and target["state"] == "pending"
        and [item["externalSourceId"] for item in queue["items"]] == before_ids
        and active_count(queue) == 0,
        f"prefix={prefix}, target={target['externalSourceId']}",
    )

# 100 active-lease scenarios: no queued item may be changed while work is running/recovering.
for index in range(100):
    active_index = 1 + (index % 9)
    active_state = "running" if index % 2 == 0 else "recovery"
    states = ["queued"] + ["pending"] * 9
    states[active_index] = active_state
    queue = make_queue(states)
    before = copy.deepcopy(queue)
    changed = serial.normalize_queue(queue)
    record(
        f"active-block-{index:03d}",
        not changed and queue == before and active_count(queue) == 1,
        f"active={active_index}:{active_state}",
    )

# 100 pending-first scenarios: a later queued projection must not leapfrog earlier pending work.
for index in range(100):
    queued_index = 1 + (index % 9)
    states = ["pending"] * 10
    states[queued_index] = "queued"
    queue = make_queue(states)
    before = copy.deepcopy(queue)
    changed = serial.normalize_queue(queue)
    record(
        f"pending-first-{index:03d}",
        not changed and queue == before and queue["items"][0]["state"] == "pending",
        f"laterQueued={queued_index}",
    )

# 100 idempotency scenarios: normalization applies once and never changes another item on repeat.
for index in range(100):
    prefix = index % 10
    states = ["imported"] * prefix + ["queued"] + ["pending"] * (9 - prefix)
    queue = make_queue(states)
    first = serial.normalize_queue(queue)
    after_first = copy.deepcopy(queue)
    second = serial.normalize_queue(queue)
    record(
        f"idempotent-{index:03d}",
        first and not second and queue == after_first and queue["items"][prefix]["state"] == "pending",
        f"prefix={prefix}",
    )

# 100 no-queued scenarios: complete, failed, and ordinary pending queues remain untouched.
for index in range(100):
    mode = index % 4
    if mode == 0:
        states = ["imported"] * 10
    elif mode == 1:
        states = ["failed"] + ["pending"] * 9
    elif mode == 2:
        states = ["imported"] * (index % 10) + ["pending"] * (10 - (index % 10))
    else:
        states = ["pending"] * 10
    queue = make_queue(states)
    before = copy.deepcopy(queue)
    changed = serial.normalize_queue(queue)
    record(
        f"no-queued-{index:03d}",
        not changed and queue == before and active_count(queue) == 0,
        f"mode={mode}",
    )

if len(results) != 500:
    raise SystemExit(f"expected exactly 500 serial-order checks, got {len(results)}")

output = {
    "schemaVersion": 1,
    "queueItems": 10,
    "maximumConcurrentItems": 1,
    "totalChecks": len(results),
    "passed": all(item["passed"] for item in results),
    "checks": results,
}
out = ROOT / "data/conflict-reports/serial-queue-order-matrix.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Serial queue order matrix: 500/500 checks passed")
