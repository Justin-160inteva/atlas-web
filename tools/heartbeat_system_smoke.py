#!/usr/bin/env python3
"""Run exactly 500 distinct heartbeat supervision scenarios."""
from __future__ import annotations

import copy
import json
import pathlib
from datetime import datetime, timedelta, timezone

import supervise_runtime_heartbeat as supervisor

ROOT = pathlib.Path(__file__).resolve().parents[1]
NOW = datetime(2026, 7, 20, 0, 0, tzinfo=timezone.utc)
config = json.loads((ROOT / "data/batch-analysis/eleven-heartbeat-supervisor.json").read_text(encoding="utf-8"))
manifest = json.loads((ROOT / "data/batch-analysis/eleven-pilot-scan-manifest.json").read_text(encoding="utf-8"))
dictionary = json.loads((ROOT / "data/scan-bug-dictionary.json").read_text(encoding="utf-8"))
results: list[dict[str, object]] = []


def stamp(seconds_ago: int) -> str:
    return (NOW - timedelta(seconds=seconds_ago)).isoformat().replace("+00:00", "Z")


def base_queue(*, first_state: str = "pending", second_state: str = "pending") -> dict:
    return {
        "updatedAt": stamp(1),
        "items": [
            {"externalSourceId": "p010", "page": 10, "sequence": 10, "regionGuess": "P07-P11", "durationSeconds": 1713, "state": first_state, "attemptCount": 1},
            {"externalSourceId": "p011", "page": 11, "sequence": 11, "regionGuess": "P07-P11", "durationSeconds": 2498, "state": second_state, "attemptCount": 0},
        ],
    }


def runtime(source: str, *, state: str, stage: str, age: int, sequence: int) -> dict:
    return {
        "schemaVersion": 4,
        "author": "11的游戏世界",
        "authorizationId": "auth",
        "pilotRegion": "P07-P11",
        "externalSourceId": source,
        "page": 10 if source == "p010" else 11,
        "state": state,
        "stage": stage,
        "progressPercent": 50,
        "updatedAt": stamp(age),
        "heartbeatSequence": sequence,
    }


def record(name: str, passed: bool, detail: str) -> None:
    results.append({"name": name, "passed": bool(passed), "detail": detail})
    if not passed:
        raise AssertionError(f"{name}: {detail}")


# 100 fresh running heartbeats with distinct age/sequence pairs.
for i in range(100):
    age = i % 90
    report, queue, projection = supervisor.evaluate(config, manifest, base_queue(), {"updatedAt": stamp(1)}, runtime("p010", state="running", stage="analysis", age=age, sequence=i + 1), dictionary, {}, NOW)
    record(f"fresh-{i:03d}", report["decision"] == "healthy" and not report["resumeWorkflow"] and projection is None and not report["queueChanged"] and queue["items"][0]["state"] == "pending", f"age={age}")

# 100 soft-stale heartbeats, below the hard threshold.
for i in range(100):
    age = 91 + (i % 89)
    report, queue, projection = supervisor.evaluate(config, manifest, base_queue(), {"updatedAt": stamp(1)}, runtime("p010", state="running", stage="analysis", age=age, sequence=i + 101), dictionary, {}, NOW)
    record(f"soft-{i:03d}", report["decision"] == "soft_stale" and report["repair"] == "observe_and_recheck" and not report["resumeWorkflow"] and projection is None and not report["queueChanged"], f"age={age}")

# 100 hard-stale leases must be released once and queued for a bounded retry.
for i in range(100):
    age = 180 + i
    report, queue, projection = supervisor.evaluate(config, manifest, base_queue(), {"updatedAt": stamp(1)}, runtime("p010", state="running", stage="persisting", age=age, sequence=i + 201), dictionary, {}, NOW)
    record(f"hard-{i:03d}", report["decision"] == "hard_stale" and report["resumeWorkflow"] and report["queueChanged"] and queue["items"][0]["state"] == "failed" and projection is not None and projection["state"] == "queued", f"age={age}")

# 100 durable-terminal cases must ignore stale running data and project the next item.
for i in range(100):
    age = i
    report, queue, projection = supervisor.evaluate(config, manifest, base_queue(first_state="imported"), {"updatedAt": stamp(1)}, runtime("p010", state="running", stage="persisting", age=age, sequence=i + 301), dictionary, {}, NOW)
    record(f"terminal-{i:03d}", report["decision"] == "stale_terminal_heartbeat" and report["resumeWorkflow"] and not report["queueChanged"] and projection is not None and projection["externalSourceId"] == "p011" and projection["state"] == "queued", f"age={age}")

# 100 duplicate resume requests inside cooldown must be suppressed.
for i in range(100):
    previous = {"resumeTargetExternalSourceId": "p011", "lastResumeRequestedAt": stamp(i)}
    report, queue, projection = supervisor.evaluate(config, manifest, base_queue(first_state="imported"), {"updatedAt": stamp(1)}, runtime("p011", state="queued", stage="queued", age=400 + i, sequence=i + 401), dictionary, previous, NOW)
    record(f"dedup-{i:03d}", report["decision"] == "pending_queued" and not report["resumeWorkflow"] and report["resumeSuppressedByCooldown"] and report["resumeTargetExternalSourceId"] == "p011" and projection is None and not report["queueChanged"], f"elapsed={i}")

if len(results) != 500:
    raise SystemExit(f"expected exactly 500 heartbeat checks, got {len(results)}")
output = {
    "schemaVersion": 1,
    "generatedAt": NOW.isoformat().replace("+00:00", "Z"),
    "totalChecks": len(results),
    "passed": all(item["passed"] for item in results),
    "checks": results,
}
out = ROOT / "data/conflict-reports/heartbeat-matrix.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Heartbeat supervision matrix: 500/500 checks passed")
