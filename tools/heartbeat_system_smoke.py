#!/usr/bin/env python3
"""Run exactly 500 distinct heartbeat supervision scenarios for an eleven-item serial queue."""
from __future__ import annotations

import json
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


for i in range(100):
    age = i % 90
    report, queue, projection = supervisor.evaluate(config, manifest, base_queue(), {"updatedAt": stamp(1)}, runtime("p025", state="running", stage="analysis", age=age, sequence=i + 1), dictionary, {}, NOW)
    record(f"fresh-{i:03d}", report["decision"] == "healthy" and not report["resumeWorkflow"] and projection is None and not report["queueChanged"] and valid_serial(queue), f"age={age}")

for i in range(100):
    age = 91 + (i % 89)
    report, queue, projection = supervisor.evaluate(config, manifest, base_queue(), {"updatedAt": stamp(1)}, runtime("p025", state="running", stage="analysis", age=age, sequence=i + 101), dictionary, {}, NOW)
    record(f"soft-{i:03d}", report["decision"] == "soft_stale" and report["repair"] == "observe_and_recheck" and not report["resumeWorkflow"] and projection is None and not report["queueChanged"] and valid_serial(queue), f"age={age}")

for i in range(100):
    age = 180 + i
    report, queue, projection = supervisor.evaluate(config, manifest, base_queue(), {"updatedAt": stamp(1)}, runtime("p025", state="running", stage="persisting", age=age, sequence=i + 201), dictionary, {}, NOW)
    record(f"hard-{i:03d}", report["decision"] == "hard_stale" and report["resumeWorkflow"] and report["queueChanged"] and queue["items"][0]["state"] == "failed" and projection is not None and projection["state"] == "queued" and valid_serial(queue), f"age={age}")

for i in range(100):
    age = i
    report, queue, projection = supervisor.evaluate(config, manifest, base_queue(first_state="imported"), {"updatedAt": stamp(1)}, runtime("p025", state="running", stage="persisting", age=age, sequence=i + 301), dictionary, {}, NOW)
    record(f"terminal-{i:03d}", report["decision"] == "stale_terminal_heartbeat" and report["resumeWorkflow"] and not report["queueChanged"] and projection is not None and projection["externalSourceId"] == "p026" and projection["state"] == "queued" and valid_serial(queue), f"age={age}")

for i in range(100):
    previous = {"resumeTargetExternalSourceId": "p026", "lastResumeRequestedAt": stamp(i)}
    report, queue, projection = supervisor.evaluate(config, manifest, base_queue(first_state="imported"), {"updatedAt": stamp(1)}, runtime("p026", state="queued", stage="queued", age=400 + i, sequence=i + 401), dictionary, previous, NOW)
    record(f"dedup-{i:03d}", report["decision"] == "pending_queued" and not report["resumeWorkflow"] and report["resumeSuppressedByCooldown"] and report["resumeTargetExternalSourceId"] == "p026" and projection is None and not report["queueChanged"] and valid_serial(queue), f"elapsed={i}")

if len(results) != 500:
    raise SystemExit(f"expected exactly 500 heartbeat checks, got {len(results)}")
output = {
    "schemaVersion": 3,
    "generatedAt": NOW.isoformat().replace("+00:00", "Z"),
    "queueItems": 11,
    "maximumConcurrentItems": 1,
    "totalChecks": len(results),
    "passed": all(item["passed"] for item in results),
    "checks": results,
}
out = ROOT / "data/conflict-reports/heartbeat-matrix.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Heartbeat eleven-item serial supervision matrix: 500/500 checks passed")
