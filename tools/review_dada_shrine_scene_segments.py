#!/usr/bin/env python3
"""Review scene-aware shrine segments with resumable two-model consensus.

Only representative contact sheets are sent to GitHub Models. Successful model packets are
persisted as text and reused when another model is rate-limited, provided the transient
frame hashes and detected segment fingerprint are unchanged. No slot is confirmed until
both configured models independently select the same registered candidate from directly
readable text at the configured minimum confidence.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
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
DEFAULT_MANIFEST = ROOT / "data/geospatial/dada-shrines-27-scene-evidence-manifest.json"
DEFAULT_OUTPUT = ROOT / "data/geospatial/dada-shrines-27-anchors-batch01.json"
FENCED_JSON = re.compile(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", re.I)
ALLOWED_TYPES = {"direct_popup_text", "direct_map_label", "unique_highlight_with_readable_text"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def data_url(path: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def parse_content(content: str) -> dict[str, Any]:
    match = FENCED_JSON.search(content)
    return json.loads(match.group(1) if match else content)


def clean_review(raw: dict[str, Any], slot: int, model: str, candidate_ids: set[str]) -> dict[str, Any]:
    selected = raw.get("selectedLocationId")
    if selected in (None, "", "null", "None"):
        selected = None
    elif str(selected) not in candidate_ids:
        selected = None
    else:
        selected = str(selected)
    visible = str(raw.get("visibleLabel") or "").strip()
    region = str(raw.get("regionClue") or "").strip()
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
        "regionClue": region,
        "evidenceType": evidence_type,
        "confidence": round(confidence, 4),
        "reasonZhCN": str(raw.get("reasonZhCN") or "").strip()[:600],
    }


def call_model(
    endpoint: str,
    token: str,
    model: str,
    prompt: dict[str, Any],
    sheets: list[Path],
    timeout: int,
    maximum_output_tokens: int,
) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "text", "text": json.dumps(prompt, ensure_ascii=False)}]
    for sheet in sheets:
        content.append({"type": "image_url", "image_url": {"url": data_url(sheet), "detail": "high"}})
    payload = json.dumps({
        "model": model,
        "temperature": 0.0,
        "max_tokens": max(5000, int(maximum_output_tokens)),
        "messages": [
            {
                "role": "system",
                "content": "你是严格的地图证据审核员。只认画面中直接可读的地点文字；宁可无法确认，也不能按视频顺序、建筑外观或候选数量猜测。输出严格JSON。",
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
            with urllib.request.urlopen(request, timeout=min(timeout, 90)) as response:
                body = json.loads(response.read().decode("utf-8"))
            parsed = parse_content(body["choices"][0]["message"]["content"])
            parsed["model"] = model
            return parsed
        except urllib.error.HTTPError as exc:
            last_error = exc
            retry_after = 0
            try:
                retry_after = int(exc.headers.get("Retry-After") or 0)
            except (TypeError, ValueError):
                retry_after = 0
            if attempt < 2:
                time.sleep(min(30, max(retry_after, 12 * attempt)))
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(8 * attempt)
    raise RuntimeError(f"scene model review failed with {model}: {last_error}")


def complete_cached_packet(packet: dict[str, Any], slots: list[int]) -> bool:
    reviews = packet.get("reviews") or []
    found = {
        int(row.get("slot")) for row in reviews
        if isinstance(row, dict) and str(row.get("slot", "")).isdigit()
    }
    return found == set(slots)


def reconstruct_packet_from_legacy(existing: dict[str, Any], model: str, slots: list[int]) -> dict[str, Any] | None:
    reviews: list[dict[str, Any]] = []
    for row in existing.get("reviews", []):
        for model_review in row.get("modelReviews", []):
            if model_review.get("model") == model:
                reviews.append(model_review)
    packet = {"model": model, "reviews": reviews, "source": "reconstructed-from-persisted-review"}
    return packet if complete_cached_packet(packet, slots) else None


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
    output_path = Path(args.output).resolve()
    manifest = load(manifest_path)
    evidence_dir = Path(args.evidence_dir).resolve()
    candidates = stage["candidateShrines"]
    candidate_by_id = {str(row["locationId"]): row for row in candidates}
    candidate_ids = set(candidate_by_id)
    models = list(policy["models"])
    minimum = float(policy["confirmation"]["minimumConfidencePerModel"])
    start = int(manifest["batch"]["startSlot"])
    end = int(manifest["batch"]["endSlot"])
    slots = list(range(start, end + 1))
    fingerprint = str(manifest["evidenceFingerprint"])

    sheets = [evidence_dir / row["filename"] for row in manifest["extraction"]["contactSheets"]]
    if not sheets or not all(path.is_file() for path in sheets):
        raise RuntimeError("scene representative sheets are missing")
    compact_candidates = [{
        "locationId": row["locationId"],
        "title": row["title"],
        "regionTitle": row["regionTitle"],
    } for row in candidates]
    segment_context = [{
        "slot": row["slot"],
        "startSeconds": row["startSeconds"],
        "endSeconds": row["endSeconds"],
        "representativeTimeSeconds": row["representativeTimeSeconds"],
    } for row in manifest["segments"]]
    prompt = {
        "task": "review_scene_aware_shrine_events",
        "sourceTitle": stage["source"]["title"],
        "eventRange": [start, end],
        "sheetLabelFormat": "E01 representative 12.345s",
        "eventSegments": segment_context,
        "rules": [
            "必须逐个返回全部事件E01到E14，不能省略。",
            "每个E编号是通过画面切换峰值检测得到的独立视频场景，不再是平均时长切片。",
            "只允许依据代表画面中直接可读的地点弹窗、地图地点标签或带可读文字的唯一高亮位置。",
            "禁止按视频顺序、建筑外观、区域常识、相邻事件或候选数量推断。",
            "若地点文字不清楚，selectedLocationId必须为null，evidenceType必须为insufficient，confidence不得高于0.60。",
            "selectedLocationId必须严格来自候选列表。",
            "不得把同一个候选复制给多个事件；无法区分时全部返回null。",
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
                "reasonZhCN": "简短说明直接证据",
            }]
        },
    }

    existing = load(output_path, {})
    reuse_allowed = (
        existing.get("evidenceFingerprint") == fingerprint
        and existing.get("source", {}).get("bvid") == stage["source"]["bvid"]
    )
    cached_packets: dict[str, dict[str, Any]] = {}
    if reuse_allowed:
        for packet in existing.get("modelPackets", []):
            model = str(packet.get("model") or "")
            if model in models and complete_cached_packet(packet, slots):
                cached_packets[model] = packet
        for model in models:
            if model not in cached_packets:
                reconstructed = reconstruct_packet_from_legacy(existing, model, slots)
                if reconstructed:
                    cached_packets[model] = reconstructed

    model_packets: list[dict[str, Any]] = []
    model_errors: list[dict[str, str]] = []
    requested_models: list[str] = []
    reused_models: list[str] = []
    for model in models:
        if model in cached_packets:
            packet = cached_packets[model]
            packet["source"] = "reused-persisted-text-review"
            model_packets.append(packet)
            reused_models.append(model)
            continue
        requested_models.append(model)
        try:
            raw_packet = call_model(
                policy["endpoint"], token, model, prompt, sheets,
                int(policy["request"]["timeoutSeconds"]),
                int(policy["request"]["maximumOutputTokens"]),
            )
            by_slot = {
                int(row.get("slot")): clean_review(row, int(row.get("slot")), model, candidate_ids)
                for row in raw_packet.get("reviews", [])
                if isinstance(row, dict)
                and str(row.get("slot", "")).isdigit()
                and start <= int(row.get("slot")) <= end
            }
            packet = {
                "model": model,
                "source": "fresh-model-review",
                "reviewedAt": now(),
                "reviews": [by_slot[slot] for slot in slots if slot in by_slot],
            }
            if not complete_cached_packet(packet, slots):
                raise RuntimeError(f"model returned incomplete event set: {sorted(by_slot)}")
            model_packets.append(packet)
        except Exception as exc:
            model_errors.append({"model": model, "error": str(exc)[:1600]})

    packet_by_model = {packet["model"]: packet for packet in model_packets}
    reviews_by_model = {
        model: {int(row["slot"]): row for row in packet["reviews"]}
        for model, packet in packet_by_model.items()
    }
    frames_by_slot: dict[int, list[dict[str, Any]]] = {}
    for row in manifest["extraction"]["frames"]:
        frames_by_slot.setdefault(int(row["slot"]), []).append(row)

    anchors: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    all_models_present = set(packet_by_model) == set(models)
    for slot in slots:
        present = [reviews_by_model[model][slot] for model in models if model in reviews_by_model and slot in reviews_by_model[model]]
        selections = [row["selectedLocationId"] for row in present if row["selectedLocationId"]]
        consensus_id = (
            selections[0]
            if all_models_present
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
        } for row in sorted(frames_by_slot.get(slot, []), key=lambda item: item["role"])]
        reviews.append({
            "slot": slot,
            "modelReviews": present,
            "consensusLocationId": consensus_id,
            "consensusPassedBeforeUniquenessGate": passed,
            "frames": frame_evidence,
        })
        if passed:
            candidate = candidate_by_id[consensus_id]
            anchors.append({
                "videoPosition": slot,
                "observedLabelZh": consensus_rows[0]["visibleLabel"],
                "confidence": round(min(row["confidence"] for row in consensus_rows), 4),
                "resolutionMethod": "two-model-scene-aware-direct-visual-consensus",
                "basis": "两个独立模型在场景切换检测得到的代表画面中读取到直接地点文字，并选择同一神社候选。",
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
                "reason": "two_model_scene_consensus_or_direct_evidence_not_met",
                "modelReviews": present,
                "modelErrors": model_errors,
                "evidence": frame_evidence,
            })

    assignments: dict[str, list[dict[str, Any]]] = {}
    for anchor in anchors:
        assignments.setdefault(anchor["locationId"], []).append(anchor)
    duplicate_ids = {location_id for location_id, rows in assignments.items() if len(rows) > 1}
    if duplicate_ids:
        kept: list[dict[str, Any]] = []
        for anchor in anchors:
            if anchor["locationId"] in duplicate_ids:
                unresolved.append({
                    "videoPosition": anchor["videoPosition"],
                    "status": "unresolved",
                    "reason": "duplicate_candidate_assignment_rejected",
                    "rejectedLocationId": anchor["locationId"],
                    "modelReviews": anchor["modelReviews"],
                    "evidence": anchor["evidence"],
                })
                for review in reviews:
                    if review["slot"] == anchor["videoPosition"]:
                        review["consensusPassedAfterUniquenessGate"] = False
                        review["uniquenessGateReason"] = "duplicate_candidate_assignment_rejected"
            else:
                kept.append(anchor)
        anchors = kept
    for review in reviews:
        review.setdefault("consensusPassedAfterUniquenessGate", bool(
            review["consensusPassedBeforeUniquenessGate"]
            and review["consensusLocationId"] not in duplicate_ids
        ))

    output = {
        "schemaVersion": 2,
        "generatedAt": now(),
        "stage": "shrine-anchor-batch01-scene-aware-two-model-review",
        "status": "complete" if all_models_present else "partial-model-review",
        "evidenceFingerprint": fingerprint,
        "source": {
            "bvid": stage["source"]["bvid"],
            "title": stage["source"]["title"],
            "authorizationId": stage["source"]["authorizationId"],
            "stage1Path": "data/geospatial/dada-shrines-27-stage1.json",
            "segmentationPath": manifest["segmentationPath"],
            "evidenceManifestPath": manifest_path.relative_to(ROOT).as_posix(),
        },
        "counts": {
            "reviewedSlots": len(slots),
            "confirmed": len(anchors),
            "unresolved": len({int(row["videoPosition"]) for row in unresolved}),
            "candidateShrines": len(candidates),
            "successfulModels": len(model_packets),
            "failedModels": len(model_errors),
            "requestedModelsThisRun": len(requested_models),
            "reusedModelsThisRun": len(reused_models),
            "duplicateCandidateIdsRejected": len(duplicate_ids),
        },
        "policy": {
            "models": models,
            "minimumConfidencePerModel": minimum,
            "requireTwoModelConsensus": True,
            "allowedEvidenceTypes": sorted(ALLOWED_TYPES),
            "uniqueLocationAssignment": True,
            "sceneAwareSegmentationRequired": True,
            "repositoryContainsEvidencePixels": False,
        },
        "modelPackets": model_packets,
        "modelErrors": model_errors,
        "requestedModelsThisRun": requested_models,
        "reusedModelsThisRun": reused_models,
        "duplicateCandidateIdsRejected": sorted(duplicate_ids),
        "anchors": sorted(anchors, key=lambda row: row["videoPosition"]),
        "unresolved": sorted(unresolved, key=lambda row: row["videoPosition"]),
        "reviews": reviews,
        "privacy": {
            "repositoryContainsPixels": False,
            "persistedEvidence": "scene boundaries, timestamps, SHA-256 hashes, visible text, model decisions and existing Atlas coordinates only",
        },
    }
    write(output_path, output)
    print(json.dumps({
        "status": output["status"],
        "counts": output["counts"],
        "requestedModels": requested_models,
        "reusedModels": reused_models,
        "modelErrors": model_errors,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
