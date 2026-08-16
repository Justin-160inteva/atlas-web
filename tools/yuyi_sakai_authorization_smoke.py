#!/usr/bin/env python3
"""Validate the Yuyi authorization, corrected source identities, and scan boundary."""
from __future__ import annotations

import json
from pathlib import Path

from extract_authorized_review_frames import build_timestamps

ROOT = Path(__file__).resolve().parents[1]


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def main() -> int:
    registry = load("data/authorizations.json")
    auth = next(row for row in registry["records"] if row["id"] == "auth-yuyi-20260816")
    candidates = load("data/geospatial/geospatial-2p5d-sakai-video-authorization-candidates.json")
    candidate = next(row for row in candidates["candidates"] if row["author"] == "侑依")
    review = load("data/geospatial/geospatial-2p5d-sakai-yuyi-visual-review.json")
    expected = {
        "yuyi-sakai-005": ("BV1ECZNYwEyH", 29083961886, 2536, 240),
        "yuyi-sakai-006": ("BV1nFZjYcEFs", 29102571716, 4537, 320),
    }
    checks = {
        "authorization active": auth["status"] == "active",
        "exact grant recorded": auth["grantText"] == "我同意Atlas项目按上述范围使用我目前已公开的全部《刺客信条：影》视频。",
        "existing videos included": auth["matchingRule"]["appliesToExisting"] is True,
        "future videos excluded": auth["matchingRule"]["appliesToFuture"] is False,
        "future inheritance excluded": auth["scope"]["futureVideosAutomaticallyIncluded"] is False,
        "author MID pinned": auth["matchingRule"]["authorMidMustEqual"] == 4442785,
        "proof remains private": auth["proof"]["storage"] == "private-user-held" and auth["proof"]["publicScreenshot"] is False,
        "proof digest": auth["proof"]["fileSha256"] == "08b8f49dd8ef52c24ae961e91a19275fc9408240a29f77c04e9e298e61f08551",
        "proof dimensions": (auth["proof"]["imageWidth"], auth["proof"]["imageHeight"]) == (1344, 2912),
        "low detail 3D only": auth["scope"]["original3DReconstructionLimitedToLowDetail"] is True,
        "source frames not public": auth["scope"]["publicExtractedFrames"] is False,
        "commercial use excluded": auth["scope"]["nonCommercial"] is True and auth["scope"]["noAdvertising"] is True,
        "season entry corrected": candidate["seasonDiscoveryBvid"] == "BV1pQdvYnEkq" and "episode 29" in candidate["identityCorrection"],
        "candidate authorized": candidate["authorizationId"] == auth["id"] and candidate["futureVideosIncluded"] is False,
        "candidate has two independent BVIDs": {row["bvid"] for row in candidate["relevantParts"]} == {row[1][0] for row in expected.items()},
        "contact queue corrected": "侑依" not in candidates["recommendedContactOrder"],
        "Atlas registration required": candidates["minimumAuthorizationSetToResumePilot"]["evidenceGate"] == "targeted-dense-review-passed-atlas-registration-blocked" and candidates["minimumAuthorizationSetToResumePilot"]["geometryStillBlockedUntilAtlasRegistration"] is True,
    }
    for job_id, (bvid, cid, duration, samples) in expected.items():
        job = load(f"data/analysis-jobs/{job_id}.json")
        part = next(row for row in candidate["relevantParts"] if row["bvid"] == bvid)
        checks[f"{job_id} authorization"] = job["authorizationId"] == auth["id"]
        checks[f"{job_id} independent BVID"] = bvid in job["url"] and job["batch"]["sourceKey"] == f"{bvid}:p1"
        checks[f"{job_id} CID"] = job["batch"]["cid"] == cid == part["cid"]
        checks[f"{job_id} duration"] = job["batch"]["durationSeconds"] == duration == part["durationSeconds"]
        checks[f"{job_id} low resolution"] = job["reviewSampling"]["frameWidth"] <= 640 and job["reviewSampling"]["frameHeight"] <= 360
        checks[f"{job_id} review samples"] = job["reviewSampling"]["samples"] == samples <= 400
        checks[f"{job_id} one-day artifact"] = job["reviewSampling"]["artifactRetentionDays"] == 1
        dense = job["targetedDenseSampling"]
        expected_windows = [
            row for row in review["targetedDenseScan"]["windows"] if row["jobId"] == job_id
        ]
        configured_windows = [
            {key: value for key, value in row.items() if key != "id"} for row in dense["windows"]
        ]
        checks[f"{job_id} dense windows match review"] = configured_windows == [
            {key: value for key, value in row.items() if key != "jobId"} for row in expected_windows
        ]
        checks[f"{job_id} dense sample count"] = len(build_timestamps(dense, duration)) == dense["samples"]
        checks[f"{job_id} dense low resolution"] = (dense["frameWidth"], dense["frameHeight"]) == (640, 360)
        checks[f"{job_id} dense one-day artifact"] = dense["artifactRetentionDays"] == 1
        checks[f"{job_id} no retained source pixels"] = job["retention"] == {"originalVideo": False, "framePixels": False, "numericDescriptorsOnly": True}

    checks["exact dense frame total"] = sum(
        load(f"data/analysis-jobs/{job_id}.json")["targetedDenseSampling"]["samples"] for job_id in expected
    ) == review["targetedDenseScan"]["estimatedFrames"] == 375
    checks["geometry remains blocked"] = review["targetedDenseScan"]["geometryGenerated"] is False
    checks["dense review completed"] = review["targetedDenseScan"]["completed"] is True and review["targetedDenseScan"]["actualFrames"] == 375
    checks["unvalidated transform rejected"] = review["atlasRegistrationAssessment"]["transformComputed"] is False and review["hardGates"]["geometryEligible"] is False

    workflow = (ROOT / ".github/workflows/geospatial-2p5d-sakai-yuyi-evidence.yml").read_text(encoding="utf-8")
    checks["workflow read-only"] = "permissions:\n  contents: read" in workflow
    checks["artifact one-day"] = "retention-days: 1" in workflow
    checks["cleanup always"] = "if: always()" in workflow
    checks["single concurrent download"] = "max-parallel: 1" in workflow
    checks["both jobs scanned"] = all(f"job_file: data/analysis-jobs/{job_id}.json" in workflow for job_id in expected)
    p006_workflow = (ROOT / ".github/workflows/geospatial-2p5d-sakai-p006-evidence.yml").read_text(encoding="utf-8")
    shared_group = "group: geospatial-sakai-transient-${{ github.event.pull_request.number || github.ref }}"
    checks["cross-workflow downloads serialized"] = shared_group in workflow and shared_group in p006_workflow
    checks["running scan not cancelled"] = "cancel-in-progress: false" in workflow and "cancel-in-progress: false" in p006_workflow
    generic_workflow = (ROOT / ".github/workflows/analyze-authorized-video.yml").read_text(encoding="utf-8")
    checks["no duplicate generic scan"] = generic_workflow.count("!data/analysis-jobs/yuyi-sakai-*.json") == 2

    failures = [name for name, passed in checks.items() if not passed]
    print(json.dumps({"passed": len(checks) - len(failures), "total": len(checks), "failures": failures}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
