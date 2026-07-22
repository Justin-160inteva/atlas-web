#!/usr/bin/env python3
"""Run a risk-budgeted heartbeat supervision matrix for an eleven-item serial queue."""
from __future__ import annotations

import json
import os
import pathlib
from datetime import datetime, timedelta, timezone

import supervise_runtime_heartbeat as supervisor

ROOT = pathlib.Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 20, 13, 35, tzinfo=timezone.utc)
config = json.loads((ROOT / "data/batch-analysis/eleven-heartbeat-supervisor.json").read_text(encoding="utf-8"))
manifest = json.loads((ROOT / "data/batch-analysis/eleven-pilot-scan-manifest.json").read_text(encoding="utf-8"))
dictionary = json.loads((ROOT / "data/scan-bug-dictionary.json").read_text(encoding="utf-8"))
results: list[dict[str, object]] = []
PAGES = list(range(25, 36))
REQUESTED_CHECKS = max(5, int(os.environ.get("ATLAS_CHECKS", "500")))
VALIDATION_TIER = os.environ.get("ATLAS_VALIDATION_TIER", "full" if REQUESTED_CHECKS >= 500 else "targeted")


def group_sizes(total: int, groups: int) -> list[int]:
    base, remainder = divmod(total, groups)
    return [base + (1 if index < remainder else 0) for index in range(groups)]


def stamp(seconds_ago: int) -> str:
    return (NOW - timedelta(seconds=seconds_ago)).isoformat().replace("+00:00", "Z")


def base_queue(*, first_state: str = "pending", second_state: str = "pending") -> dict:
    items = []
    for index, page in enumerate(PAGES):
        state = first_state if index == 0 else second_state if index == 1 else "pending"
        items.append({
            "externalSourceId": f"p{page:03d}",
            "page": page,
            "sequence": page,
            "regionGuess": "P25-P35",
            "durationSeconds": 1200 + index,
            "state": state,
            "attemptCount": 1 if index == 0 else 0,
        })
    return {
        "updatedAt": stamp(1),
        "maximumQueueItems": 11,
        "maximumConcurrentItems": 1,
        "items": items,
    }


def runtime(source: str, *, state: str, stage: str, age: int, sequence: int) -> dict:
    page = int(source.removeprefix("p"))
    return {
        "schemaVersion": 5,
        "author": "11的游戏世界",
        "authorizationId": "auth",
        "pilotRegion": "P25-P35",
        "externalSourceId": source,
        "page": page,
        "state": state,
        "stage": stage,
        "progressPercent": 50,
        "updatedAt": stamp(age),
        "heartbeatSequence": sequence,
    }


def valid_serial(queue: dict) -> bool:
    items = queue["items"]
    return (
        len(items) == 11
        and queue["maximumConcurrentItems"] == 1
        and [item["sequence"] for item in items] == PAGES
        and sum(item.get("state") in {"running", "recovery"} for item in items) <= 1
    )


def record(name: str, passed: bool, detail: str) -> None:
    results.append({"name": name, "passed": bool(passed), "detail": detail})
    if not passed:
        raise AssertionError(f"{name}: {detail}")


fresh_count, soft_count, hard_count, terminal_count, dedup_count = group_sizes(REQUESTED_CHECKS, 5)
sequence = 1

for index in range(fresh_count):
    age = index % 90
    report, queue, projection = supervisor.evaluate(config, manifest, base_queue(), {"updatedAt": stamp(1)}, runtime("p025", state="running", stage="analysis", age=age, sequence=sequence), dictionary, {}, NOW)
    sequence += 1
    record(f"fresh-{index:03d}", report["decision"] == "healthy" and not report["resumeWorkflow"] and projection is None and not report["queueChanged"] and valid_serial(queue), f"age={age}")

for index in range(soft_count):
    age = 91 + (index % 89)
    report, queue, projection = supervisor.evaluate(config, manifest, base_queue(), {"updatedAt": stamp(1)}, runtime("p025", state="running", stage="analysis", age=age, sequence=sequence), dictionary, {}, NOW)
    sequence += 1
    record(f"soft-{index:03d}", report["decision"] == "soft_stale" and report["repair"] == "observe_and_recheck" and not report["resumeWorkflow"] and projection is None and not report["queueChanged"] and valid_serial(queue), f"age={age}")

for index in range(hard_count):
    age = 180 + index
    report, queue, projection = supervisor.evaluate(config, manifest, base_queue(), {"updatedAt": stamp(1)}, runtime("p025", state="running", stage="persisting", age=age, sequence=sequence), dictionary, {}, NOW)
    sequence += 1
    record(f"hard-{index:03d}", report["decision"] == "hard_stale" and report["resumeWorkflow"] and report["queueChanged"] and queue["items"][0]["state"] == "failed" and projection is not None and projection["state"] == "queued" and valid_serial(queue), f"age={age}")

for index in range(terminal_count):
    age = index
    report, queue, projection = supervisor.evaluate(config, manifest, base_queue(first_state="imported"), {"updatedAt": stamp(1)}, runtime("p025", state="running", stage="persisting", age=age, sequence=sequence), dictionary, {}, NOW)
    sequence += 1
    record(f"terminal-{index:03d}", report["decision"] == "stale_terminal_heartbeat" and report["resumeWorkflow"] and not report["queueChanged"] and projection is not None and projection["externalSourceId"] == "p026" and projection["state"] == "queued" and valid_serial(queue), f"age={age}")

for index in range(dedup_count):
    previous = {"resumeTargetExternalSourceId": "p026", "lastResumeRequestedAt": stamp(index)}
    report, queue, projection = supervisor.evaluate(config, manifest, base_queue(first_state="imported"), {"updatedAt": stamp(1)}, runtime("p026", state="queued", stage="queued", age=400 + index, sequence=sequence), dictionary, previous, NOW)
    sequence += 1
    record(f"dedup-{index:03d}", report["decision"] == "pending_queued" and not report["resumeWorkflow"] and report["resumeSuppressedByCooldown"] and report["resumeTargetExternalSourceId"] == "p026" and projection is None and not report["queueChanged"] and valid_serial(queue), f"elapsed={index}")

if len(results) != REQUESTED_CHECKS:
    raise SystemExit(f"expected exactly {REQUESTED_CHECKS} heartbeat checks, got {len(results)}")
output = {
    "schemaVersion": 4,
    "generatedAt": NOW.isoformat().replace("+00:00", "Z"),
    "validationTier": VALIDATION_TIER,
    "requestedChecks": REQUESTED_CHECKS,
    "queueItems": 11,
    "maximumConcurrentItems": 1,
    "coverageFamilies": ["fresh", "soft-stale", "hard-stale", "terminal-projection", "resume-deduplication"],
    "totalChecks": len(results),
    "passed": all(item["passed"] for item in results),
    "checks": results,
}
out = ROOT / "data/conflict-reports/heartbeat-matrix.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Heartbeat eleven-item serial supervision matrix: {len(results)}/{REQUESTED_CHECKS} checks passed ({VALIDATION_TIER})")
