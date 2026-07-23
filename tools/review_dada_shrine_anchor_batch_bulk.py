#!/usr/bin/env python3
"""Bulk-review a shrine anchor batch with two multimodal model calls.

Five labeled contact sheets are sent once to each model. Each model returns decisions
for all requested slots. A slot is confirmed only when both models independently select
the same registered candidate from direct readable evidence at confidence >= policy
minimum. Repository outputs never contain image bytes.
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


def data_url(path: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def parse_content(content: str) -> dict[str, Any]:
    match = FENCED_JSON.search(content)
    return json.loads(match.group(1) if match else content)


def call_model(endpoint: str, token: str, model: str, prompt: dict[str, Any], sheets: list[Path], timeout: int, max_tokens: int) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "text", "text": json.dumps(prompt, ensure_ascii=False)}]
    for sheet in sheets:
        content.append({"type": "image_url", "image_url": {"url": data_url(sheet), "detail": "high"}})
    payload = json.dumps({
        "model": model,
        "temperature": 0.0,
        "max_tokens": max(max_tokens, 5000),
        "messages": [
            {
                "role": "system",
                "content": "你是严格的地图证据审核员。宁可返回无法确认，也不得根据建筑外观或顺序猜测地点。输出严格JSON。",
            },
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_object"},
    }, ensure_ascii=False).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(1, 3):
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
            if attempt < 2:
                time.sleep(6)
    raise RuntimeError(f"bulk model review failed with {model}: {last_error}")


def clean_review(raw: dict[str, Any], slot: int, model: str, candidate_ids: set[str]) -> dict[str, Any]:
    selected = raw.get("selectedLocationId")
    if selected in (None, "", "null", "None"):
        selected = None
    elif str(selected) not in candidate_ids:
        selected = None
    else:
        selected = str(selected)
    visible = str(raw.get("visibleLabel") or "").strip()
    evidence_type = str(raw.get("evidenceType") or "insufficient")
    if evidence_type not in ALLOWED_TYPES:
        evidence_type = "insufficient"
    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence") or 0)))
    except (TypeError, ValueError):
        confidence = 0.0
    if not visible or evidence_type == "insufficient":
        selected = None
        confidence = min(confidence, 0.60)
    return {
        "slot": slot,
        "model": model,
        "selectedLocationId": selected,
        "visibleLabel": visible,
        "regionClue": str(raw.get("regionClue") or "").strip(),
        "evidenceType": evidence_type,
        "confidence": round(confidence, 4),
        "reasonZhCN": str(raw.get("reasonZhCN") or "").strip()[:500],
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
    manifest_path = Path(args.manifest).resolve()
    manifest = load(manifest_path)
    evidence_dir = Path(args.evidence_dir).resolve()
    output_path = Path(args.output).resolve()
    candidates = stage["candidateShrines"]
    candidate_by_id = {str(row["locationId"]): row for row in candidates}
    candidate_ids = set(candidate_by_id)
    models = list(policy["models"])
    minimum = float(policy["confirmation"]["minimumConfidencePerModel"])
    start = int(manifest["batch"]["startSlot"])
    end = int(manifest["batch"]["endSlot"])
    slots = list(range(start, end + 1))

    sheets = [evidence_dir / row["filename"] for row in manifest["extraction"]["contactSheets"]]
    if not sheets or not all(path.is_file() for path in sheets):
        raise RuntimeError("labeled contact sheets are missing")
    compact_candidates = [{
        "locationId": row["locationId"],
        "title": row["title"],
        "regionTitle": row["regionTitle"],
    } for row in candidates]
    prompt = {
        "task": "review_shrine_slots_from_labeled_contact_sheets",
        "sourceTitle": stage["source"]["title"],
        "slotRange": [start, end],
        "contactSheetLabelFormat": "S01 early/middle/late timeSeconds",
        "rules": [
            "逐个返回所有槽位，不能省略。",
            "只允许依据画面中可直接读取的地点弹窗、地图地点标签或带可读文字的唯一高亮位置。",
            "禁止凭建筑外观、颜色、视频顺序、区域常识或候选数量猜测。",
            "无法读取明确地点文字时selectedLocationId必须为null、evidenceType为insufficient。",
            "selectedLocationId必须来自候选列表。",
            "confidence为0到1；没有清晰文字时不得高于0.60。",
        ],
        "candidateShrines": compact_candidates,
        "requiredOutput": {
            "reviews": [{
                "slot": 1,
                "selectedLocationId": "候选ID或null",
                "visibleLabel": "画面直接读取文字或空字符串",
                "regionClue": "直接读取的区域文字或空字符串",
                "evidenceType": "direct_popup_text|direct_map_label|unique_highlight_with_readable_text|insufficient",
                "confidence": 0.0,
                "reasonZhCN": "简短说明证据所在槽位画面",
            }]
        },
    }

    model_packets: list[dict[str, Any]] = []
    model_errors: list[dict[str, str]] = []
    for model in models:
        try:
            packet = call_model(
                policy["endpoint"], token, model, prompt, sheets,
                int(policy["request"]["timeoutSeconds"]),
                int(policy["request"]["maximumOutputTokens"]),
            )
            by_slot = {
                int(row.get("slot")): clean_review(row, int(row.get("slot")), model, candidate_ids)
                for row in packet.get("reviews", [])
                if isinstance(row, dict) and str(row.get("slot", "")).isdigit() and start <= int(row.get("slot")) <= end
            }
            model_packets.append({"model": model, "reviews": by_slot})
        except Exception as exc:
            model_errors.append({"model": model, "error": str(exc)[:1200]})

    frames_by_slot: dict[int, list[dict[str, Any]]] = {}
    for row in manifest["extraction"]["frames"]:
        frames_by_slot.setdefault(int(row["slot"]), []).append(row)

    anchors: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    for slot in slots:
        slot_rows = [packet["reviews"].get(slot) for packet in model_packets]
        present = [row for row in slot_rows if row]
        selections = [row["selectedLocationId"] for row in present if row["selectedLocationId"]]
        consensus_id = (
            selections[0]
            if len(model_packets) == len(models)
            and len(present) == len(models)
            and len(selections) == len(models)
            and len(set(selections)) == 1
            else None
        )
        consensus_rows = [row for row in present if row["selectedLocationId"] == consensus_id] if consensus_id else []
        passed = bool(
            consensus_id
            and len(consensus_rows) == len(models)
            and all(row["confidence"] >= minimum for row in consensus_rows)
            and all(row["visibleLabel"] for row in consensus_rows)
            and all(row["evidenceType"] in ALLOWED_TYPES for row in consensus_rows)
        )
        frame_evidence = [{
            "role": row["role"],
            "timeSeconds": row["timeSeconds"],
            "sha256": row["sha256"],
        } for row in sorted(frames_by_slot.get(slot, []), key=lambda row: row["role"])]
        reviews.append({
            "slot": slot,
            "modelReviews": present,
            "modelErrors": model_errors,
            "consensusLocationId": consensus_id,
            "consensusPassed": passed,
            "frames": frame_evidence,
        })
        if passed:
            candidate = candidate_by_id[consensus_id]
            anchors.append({
                "videoPosition": slot,
                "observedLabelZh": consensus_rows[0]["visibleLabel"],
                "confidence": round(min(row["confidence"] for row in consensus_rows), 4),
                "resolutionMethod": "two-model-bulk-direct-visual-consensus",
                "basis": "两个独立模型从带槽位标签的临时联系表中读取到直接地点文字，并选择同一神社候选。",
                "evidence": frame_evidence,
                "modelReviews": consensus_rows,
                "status": "confirmed",
                "locationId": consensus_id,
                "title": candidate["title"],
                "regionId": candidate["regionId"],
                "regionTitle": candidate["regionTitle"],
                "atlas": candidate["atlas"],
                "sourceLocationId": candidate["sourceLocationId"],
            })
        else:
            unresolved.append({
                "videoPosition": slot,
                "status": "unresolved",
                "reason": "bulk_two_model_consensus_or_direct_evidence_not_met",
                "modelReviews": present,
                "modelErrors": model_errors,
                "evidence": frame_evidence,
            })

    duplicate_ids = {row["locationId"] for row in anchors if sum(1 for other in anchors if other["locationId"] == row["locationId"]) > 1}
    if duplicate_ids:
        kept = []
        for anchor in anchors:
            if anchor["locationId"] in duplicate_ids:
                unresolved.append({
                    "videoPosition": anchor["videoPosition"],
                    "status": "unresolved",
                    "reason": "duplicate_candidate_assignment",
                    "rejectedLocationId": anchor["locationId"],
                    "modelReviews": anchor["modelReviews"],
                    "evidence": anchor["evidence"],
                })
            else:
                kept.append(anchor)
        anchors = kept

    output = {
        "schemaVersion": 1,
        "generatedAt": now(),
        "stage": "shrine-anchor-batch01-two-model-bulk-review",
        "status": "complete",
        "source": {
            "bvid": stage["source"]["bvid"],
            "title": stage["source"]["title"],
            "authorizationId": stage["source"]["authorizationId"],
            "stage1Path": "data/geospatial/dada-shrines-27-stage1.json",
            "evidenceManifestPath": manifest_path.relative_to(ROOT).as_posix(),
        },
        "counts": {
            "reviewedSlots": len(slots),
            "confirmed": len(anchors),
            "unresolved": len(unresolved),
            "candidateShrines": len(candidates),
            "successfulModels": len(model_packets),
            "failedModels": len(model_errors),
        },
        "policy": {
            "models": models,
            "minimumConfidencePerModel": minimum,
            "requireTwoModelConsensus": True,
            "allowedEvidenceTypes": sorted(ALLOWED_TYPES),
            "uniqueLocationAssignment": True,
            "repositoryContainsEvidencePixels": False,
            "modelRequestCount": len(models),
        },
        "anchors": sorted(anchors, key=lambda row: row["videoPosition"]),
        "unresolved": sorted(unresolved, key=lambda row: row["videoPosition"]),
        "reviews": reviews,
        "modelErrors": model_errors,
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
