#!/usr/bin/env python3
"""Run exactly 500 strict serial queue-order scenarios."""
from __future__ import annotations

import copy
import json
import pathlib

import run_scan_with_auto_recovery_v2 as ordered

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS: list[dict[str, object]] = []


def make_queue(states: list[str]) -> dict:
    return {
        "status": "queued",
        "activeExternalSourceId": "stale-active",
        "items": [
            {
                "externalSourceId": f"p{index + 12:03d}",
                "sequence": index + 12,
                "page": index + 12,
                "state": state,
                "attemptCount": 0,
            }
            for index, state in enumerate(states)
        ],
    }


def record(name: str, passed: bool, detail: str) -> None:
    RESULTS.append({"name": name, "passed": bool(passed), "detail": detail})
    if not passed:
        raise AssertionError(f"{name}: {detail}")


# 100 cases: after N durable imports, the earliest queued item becomes claimable.
for i in range(100):
    imported = i % 10
    states = ["imported"] * imported + ["queued"] + ["pending"] * (9 - imported)
    queue = make_queue(states)
    changed = ordered.normalize_queue(queue)
    first_open = queue["items"][imported]
    record(
        f"claim-earliest-queued-{i:03d}",
        changed
        and first_open["state"] == "pending"
        and all(item["state"] == "imported" for item in queue["items"][:imported])
        and "activeExternalSourceId" not in queue,
        json.dumps(queue, ensure_ascii=False),
    )

# 100 cases: an active running/recovery item prevents any queued transition.
for i in range(100):
    active_index = i % 10
    active_state = "running" if i % 2 == 0 else "recovery"
    states = ["queued"] * 10
    states[active_index] = active_state
    queue = make_queue(states)
    before = copy.deepcopy(queue)
    changed = ordered.normalize_queue(queue)
    record(
        f"active-guard-{i:03d}",
        not changed and queue == before,
        f"active={active_index}:{active_state}",
    )

# 100 cases: an earlier pending item remains authoritative; later queued items are untouched.
for i in range(100):
    imported = i % 9
    states = ["imported"] * imported + ["pending", "queued"] + ["pending"] * (8 - imported)
    queue = make_queue(states)
    before = copy.deepcopy(queue)
    changed = ordered.normalize_queue(queue)
    record(
        f"pending-before-queued-{i:03d}",
        not changed and queue == before,
        json.dumps(states, ensure_ascii=False),
    )

# 100 cases: only the earliest queued item changes even when several queued items exist.
for i in range(100):
    imported = i % 10
    states = ["imported"] * imported + ["queued"] * (10 - imported)
    queue = make_queue(states)
    changed = ordered.normalize_queue(queue)
    open_states = [item["state"] for item in queue["items"][imported:]]
    record(
        f"single-transition-{i:03d}",
        changed and open_states[0] == "pending" and all(state == "queued" for state in open_states[1:]),
        json.dumps(open_states, ensure_ascii=False),
    )

# 100 cases: normalization is idempotent and cannot create two claimable transitions.
for i in range(100):
    imported = i % 10
    states = ["imported"] * imported + ["queued"] + ["pending"] * (9 - imported)
    queue = make_queue(states)
    first = ordered.normalize_queue(queue)
    snapshot = copy.deepcopy(queue)
    second = ordered.normalize_queue(queue)
    record(
        f"idempotent-{i:03d}",
        first and not second and queue == snapshot and sum(item["state"] == "pending" for item in queue["items"]) == 10 - imported,
        json.dumps(queue, ensure_ascii=False),
    )

if len(RESULTS) != 500:
    raise SystemExit(f"expected exactly 500 queue-order checks, got {len(RESULTS)}")

output = {
    "schemaVersion": 1,
    "totalChecks": len(RESULTS),
    "passed": all(item["passed"] for item in RESULTS),
    "checks": RESULTS,
}
out = ROOT / "data/conflict-reports/queue-order-matrix.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Strict serial queue-order matrix: 500/500 checks passed")
