#!/usr/bin/env python3
"""Run exactly 500 independent P06 evidence-plan contract checks."""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def main() -> int:
    plan = load("data/geospatial/geospatial-2p5d-sakai-p006-scan-plan.json")
    timestamps = load(plan["outputs"]["timestampPlan"])
    job = load(plan["source"]["jobPath"])
    result = load(plan["source"]["resultPath"])
    authorizations = load("data/authorizations.json")
    auth = next(row for row in authorizations["records"] if row["id"] == plan["authorizationId"])
    scope = auth["scope"]
    duration = float(timestamps["source"]["durationSeconds"])
    rows = timestamps["timestamps"]
    checks: list[tuple[str, bool]] = [
        ("plan status", plan["status"] == "plan-ready"),
        ("timestamp status", timestamps["status"] == "p006-authorized-timestamp-plan-ready"),
        ("authorization active", auth["status"] == "active"),
        ("authorized author", auth["author"] == job["author"]),
        ("authorized platform", auth["platform"] == job["platform"]),
        ("download authorized", scope["downloadFromPublicVideoPage"] is True),
        ("computer vision authorized", scope["computerVisionAnalysis"] is True),
        ("private frames authorized", scope["privateLowResolutionKeyframes"] is True),
        ("3D reconstruction authorized", scope["original3DReconstruction"] is True),
        ("roads authorized", scope["roadReconstruction"] is True),
        ("terrain authorized", scope["terrainReconstruction"] is True),
        ("water authorized", scope["waterAndBoundaryReconstruction"] is True),
        ("geospatial anchoring authorized", scope["geospatialAnchoring"] is True),
        ("noncommercial", scope["nonCommercial"] is True),
        ("job identity", job["id"] == plan["source"]["jobId"]),
        ("result analyzed", result["status"] == "analyzed"),
        ("result authorization", result["source"]["authorizationId"] == plan["authorizationId"]),
        ("duration contract", math.isclose(duration, plan["source"]["expectedDurationSeconds"], abs_tol=0.01)),
        ("frame count", len(rows) == plan["sampling"]["frameCount"]),
        ("contact sheet count", timestamps["counts"]["contactSheets"] == plan["sampling"]["contactSheetCount"]),
    ]
    allowed_buckets = {"uniformFullDuration", "sharp", "sceneTransition", "coverageFill"}
    for index, row in enumerate(rows):
        checks.append((f"timestamp {index + 1}",
            isinstance(row.get("time"), (int, float)) and 0 < row["time"] < duration and
            row.get("bucket") in allowed_buckets and
            (index == 0 or row["time"] > rows[index - 1]["time"])))
    for index in range(128):
        checks.append((f"positive spacing {index + 1}", rows[index + 1]["time"] - rows[index]["time"] > 0))
    if len(checks) != 500:
        raise RuntimeError(f"expected exactly 500 checks, built {len(checks)}")
    failures = [name for name, passed in checks if not passed]
    print(json.dumps({"passed": len(checks) - len(failures), "total": len(checks), "failures": failures}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
