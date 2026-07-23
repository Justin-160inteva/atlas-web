#!/usr/bin/env python3
"""Review transient shrine frames with two-model consensus.

Only direct readable map/popup evidence can become a confirmed anchor. The script
persists text, hashes, timestamps, candidate IDs and coordinates; image bytes are never
written into repository outputs.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STAGE_PATH = ROOT / "data/geospatial/dada-shrines-27-stage1.json"
POLICY_PATH = ROOT / "data/geospatial/geospatial-vision-policy.json"
DEFAULT_MANIFEST = ROOT / "data/geospatial/dada-shrines-27-batch01-evidence-manifest.json"
DEFAULT_OUTPUT = ROOT / "data/geospatial/dada-shrines-27-anchors-batch01.json"
FENCED_JSON = re.compile(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", re.I)
ALLOWED_TYPES = {"direct_popup_text", "direct_map_label", "unique_highlight_with_readable_text"}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_content(content: str) -> dict[str, Any]:
    match = FENCED_JSON.search(content)
    return json.loads(match.group(1) if match else content)


def image_data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def call_model(
    endpoint: str,
    token: str,
    model: str,
    candidates: list[dict[str, Any]],
    slot: int,
    frame_paths: list[Path],
    frame_rows: list[dict[str, Any]],
    timeout: int,
    max_tokens: int,
) -> dict[str, Any]:
    compact_candidates = [{
        "locationId": row["locationId"],
        "title": row["title"],
        "regionTitle": row["regionTitle"],
    } for row in candidates]
    instructions = {
        "task": "identify_assassins_creed_shadows_shrine_map_location",
        "slot": slot,
        "rules": [
            "只根据三张画面中可直接读取的地点弹窗、地图标签或带文字的唯一高亮位置判断。",
            "禁止仅凭建筑外观、路线顺序、颜色、模糊轮廓或常识猜测。",
            "selectedLocationId必须来自候选列表；无法读取明确证据时必须为null。",
            "confidence是0到1的小数。没有清晰文字时不得高于0.60。",
            "evidenceType只能是direct_popup_text、direct_map_label、unique_highlight_with_readable_text或insufficient。",
            "visibleLabel保留画面中实际看到的中文、日文或英文地点文字；没有则为空字符串。",
        ],
        "frameTimes": [{"role": row["role"], "timeSeconds": row["timeSeconds"]} for row in frame_rows],
        "candidateShrines": compact_candidates,
        "requiredOutput": {
            "slot": slot,
            "selectedLocationId": "候选ID或null",
            "visibleLabel": "画面中直接读取的地点文字",
            "regionClue": "画面中直接读取的区域文字或空字符串",
            "evidenceType": "四种允许值之一",
            "confidence": 0.0,
            "reasonZhCN": "简短说明哪张画面提供了什么直接证据",
        },
    }
    content: list[dict[str, Any]] = [{"type": "text", "text": json.dumps(instructions, ensure_ascii=False)}]
    for path in frame_paths:
        content.append({"type": "image_url", "image_url": {"url": image_data_url(path), "detail": "high"}})
    payload = json.dumps({
        "model": model,
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "system",
                "content": "你是地图证据审核员。宁可返回无法确认，也不得猜测地点。输出严格JSON。",
            },
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_object"},
    }, ensure_ascii=False).encode("utf-8")

    last_error: Exception | None = None
    for attempt in range(1, 4):
        request = urllib.request.Request(endpoint, data=payload, method="POST", headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            parsed = parse_content(body["choices"][0]["message"]["content"])
            parsed["model"] = model
            return parsed
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(attempt * 5)
    raise RuntimeError(f"model review failed for slot {slot} with {model}: {last_error}")


def validate_model_row(row: dict[str, Any], slot: int, candidate_ids: set[str]) -> dict[str, Any]:
    selected = row.get("selectedLocationId")
    if selected in ("", "null", "None"):
        selected = None
    if selected is not None:
        selected = str(selected)
        if selected not in candidate_ids:
            selected = None
    evidence_type = str(row.get("evidenceType") or "insufficient")
    if evidence_type not in ALLOWED_TYPES:
        evidence_type = "insufficient"
    visible = str(row.get("visibleLabel") or "").strip()
    try:
        confidence = max(0.0, min(1.0, float(row.get("confidence") or 0)))
    except (TypeError, ValueError):
        confidence = 0.0
    if not visible or evidence_type == "insufficient":
        selected = None
        confidence = min(confidence, 0.60)
    return {
        "slot": slot,
        "model": row.get("model"),
        "selectedLocationId": selected,
        "visibleLabel": visible,
        "regionClue": str(row.get("regionClue") or "").strip(),
        "evidenceType": evidence_type,
        "confidence": round(confidence, 4),
        "reasonZhCN": str(row.get("reasonZhCN") or "").strip()[:500],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    token = os.environ.get("ATLAS_GEOSPATIAL_VISION_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GitHub Models token is unavailable")
    stage = load(STAGE_PATH)
    policy = load(POLICY_PATH)
    manifest = load(Path(args.manifest))
    evidence_dir = Path(args.evidence_dir).resolve()
    output_path = Path(args.output)
    candidates = stage["candidateShrines"]
    candidate_by_id = {str(row["locationId"]): row for row in candidates}
    candidate_ids = set(candidate_by_id)
    models = list(policy["models"])
    minimum = float(policy["confirmation"]["minimumConfidencePerModel"])
    timeout = int(policy["request"]["timeoutSeconds"])
    max_tokens = int(policy["request"]["maximumOutputTokens"])
    delay = float(policy["request"]["delayBetweenRequestsSeconds"])

    frames_by_slot: dict[int, list[dict[str, Any]]] = {}
    for row in manifest["extraction"]["frames"]:
        frames_by_slot.setdefault(int(row["slot"]), []).append(row)
    slots = list(range(int(manifest["batch"]["startSlot"]), int(manifest["batch"]["endSlot"]) + 1))

    reviews: list[dict[str, Any]] = []
    anchors: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for slot in slots:
        frame_rows = sorted(frames_by_slot.get(slot, []), key=lambda row: ("early", "middle", "late").index(row["role"]))
        if len(frame_rows) != 3:
            raise RuntimeError(f"slot {slot} does not have exactly three evidence frames")
        paths = [evidence_dir / row["filename"] for row in frame_rows]
        if not all(path.is_file() for path in paths):
            raise RuntimeError(f"slot {slot} is missing transient frame files")

        model_rows: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for model in models:
            try:
                raw = call_model(policy["endpoint"], token, model, candidates, slot, paths, frame_rows, timeout, max_tokens)
                model_rows.append(validate_model_row(raw, slot, candidate_ids))
            except Exception as exc:  # keep the batch auditable instead of guessing
                errors.append({"model": model, "error": str(exc)[:1000]})
            time.sleep(delay)

        selections = [row["selectedLocationId"] for row in model_rows if row["selectedLocationId"]]
        consensus_id = selections[0] if len(model_rows) == len(models) and len(set(selections)) == 1 and len(selections) == len(models) else None
        consensus_rows = [row for row in model_rows if row["selectedLocationId"] == consensus_id] if consensus_id else []
        direct = bool(consensus_rows) and all(row["evidenceType"] in ALLOWED_TYPES for row in consensus_rows)
        confident = bool(consensus_rows) and all(row["confidence"] >= minimum for row in consensus_rows)
        visible = bool(consensus_rows) and all(row["visibleLabel"] for row in consensus_rows)

        review = {
            "slot": slot,
            "frames": [{
                "role": row["role"],
                "timeSeconds": row["timeSeconds"],
                "sha256": row["sha256"],
            } for row in frame_rows],
            "modelReviews": model_rows,
            "modelErrors": errors,
            "consensusLocationId": consensus_id,
            "consensusPassed": bool(consensus_id and direct and confident and visible),
        }
        reviews.append(review)
        if review["consensusPassed"]:
            candidate = candidate_by_id[consensus_id]
            anchor = {
                "videoPosition": slot,
                "observedLabelZh": consensus_rows[0]["visibleLabel"],
                "confidence": round(min(row["confidence"] for row in consensus_rows), 4),
                "resolutionMethod": "two-model-direct-visual-consensus",
                "basis": "两个独立模型均从同一组三张临时画面中读取到直接地点文字，并选择相同的神社候选。",
                "evidence": review["frames"],
                "modelReviews": model_rows,
                "status": "confirmed",
                "locationId": consensus_id,
                "title": candidate["title"],
                "regionId": candidate["regionId"],
                "regionTitle": candidate["regionTitle"],
                "atlas": candidate["atlas"],
                "sourceLocationId": candidate["sourceLocationId"],
            }
            anchors.append(anchor)
        else:
            unresolved.append({
                "videoPosition": slot,
                "status": "unresolved",
                "reason": "two_model_consensus_or_direct_evidence_not_met",
                "modelReviews": model_rows,
                "modelErrors": errors,
                "evidence": review["frames"],
            })

    # Enforce unique candidate ownership. Any duplicate assignments are all reverted.
    counts: dict[str, int] = {}
    for anchor in anchors:
        counts[anchor["locationId"]] = counts.get(anchor["locationId"], 0) + 1
    duplicates = {location_id for location_id, count in counts.items() if count > 1}
    if duplicates:
        kept: list[dict[str, Any]] = []
        for anchor in anchors:
            if anchor["locationId"] in duplicates:
                unresolved.append({
                    "videoPosition": anchor["videoPosition"],
                    "status": "unresolved",
                    "reason": "duplicate_candidate_assignment",
                    "rejectedLocationId": anchor["locationId"],
                    "evidence": anchor["evidence"],
                    "modelReviews": anchor["modelReviews"],
                })
            else:
                kept.append(anchor)
        anchors = kept

    output = {
        "schemaVersion": 1,
        "generatedAt": now(),
        "stage": "shrine-anchor-batch01-two-model-review",
        "status": "complete",
        "source": {
            "bvid": stage["source"]["bvid"],
            "title": stage["source"]["title"],
            "authorizationId": stage["source"]["authorizationId"],
            "stage1Path": "data/geospatial/dada-shrines-27-stage1.json",
            "evidenceManifestPath": Path(args.manifest).relative_to(ROOT).as_posix(),
        },
        "counts": {
            "reviewedSlots": len(slots),
            "confirmed": len(anchors),
            "unresolved": len(unresolved),
            "candidateShrines": len(candidates),
        },
        "policy": {
            "models": models,
            "minimumConfidencePerModel": minimum,
            "requireTwoModelConsensus": True,
            "allowedEvidenceTypes": sorted(ALLOWED_TYPES),
            "uniqueLocationAssignment": True,
            "repositoryContainsEvidencePixels": False,
        },
        "anchors": sorted(anchors, key=lambda row: row["videoPosition"]),
        "unresolved": sorted(unresolved, key=lambda row: row["videoPosition"]),
        "reviews": reviews,
        "privacy": {
            "repositoryContainsPixels": False,
            "persistedEvidence": "timestamps, SHA-256 hashes, visible text, model decisions and existing Atlas coordinates only",
        },
    }
    write(output_path, output)
    print(json.dumps(output["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
