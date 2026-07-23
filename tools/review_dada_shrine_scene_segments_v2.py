#!/usr/bin/env python3
"""High-resolution, event-batched review for scene-aware shrine segments.

Each request contains at most four events. Every event is introduced by an explicit text
label and followed by its own before/representative/after frames, preventing contact-sheet
cross-event leakage. Two independent reviewer pools are required. The reasoning pool may
fall back from GPT-4.1 to GPT-4.1-mini when rate-limited; the vision pool remains GPT-4o-mini.
Successful batch packets are persisted as text and reused only when the evidence fingerprint
and strategy version match. No image bytes are written to the repository.
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
DEFAULT_MANIFEST = ROOT / "data/geospatial/dada-shrines-27-scene-evidence-manifest.json"
DEFAULT_OUTPUT = ROOT / "data/geospatial/dada-shrines-27-anchors-batch01.json"
STRATEGY_VERSION = 2
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
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def data_url(path: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def parse_content(content: str) -> dict[str, Any]:
    match = FENCED_JSON.search(content)
    return json.loads(match.group(1) if match else content)


def clean_review(raw: dict[str, Any], slot: int, model: str, pool_id: str, candidate_ids: set[str]) -> dict[str, Any]:
    selected = raw.get("selectedLocationId")
    if selected in (None, "", "null", "None"):
        selected = None
    elif str(selected) in candidate_ids:
        selected = str(selected)
    else:
        selected = None
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
        "reviewerPool": pool_id,
        "model": model,
        "selectedLocationId": selected,
        "visibleLabel": visible,
        "regionClue": region,
        "evidenceType": evidence_type,
        "confidence": round(confidence, 4),
        "reasonZhCN": str(raw.get("reasonZhCN") or "").strip()[:700],
    }


def reject_duplicate_selections(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    assignments: dict[str, list[dict[str, Any]]] = {}
    for row in reviews:
        if row.get("selectedLocationId"):
            assignments.setdefault(str(row["selectedLocationId"]), []).append(row)
    duplicates = {location_id for location_id, rows in assignments.items() if len(rows) > 1}
    cleaned: list[dict[str, Any]] = []
    for row in reviews:
        value = dict(row)
        if value.get("selectedLocationId") in duplicates:
            rejected = value["selectedLocationId"]
            value["selectedLocationId"] = None
            value["evidenceType"] = "insufficient"
            value["confidence"] = min(float(value.get("confidence") or 0), 0.60)
            value["reasonZhCN"] = (
                f"同一候选{rejected}被该模型分配给多个事件，按唯一性规则全部拒绝。 "
                + str(value.get("reasonZhCN") or "")
            )[:700]
            value["duplicateSelectionRejected"] = rejected
        cleaned.append(value)
    return cleaned


def call_model_batch(
    endpoint: str,
    token: str,
    model: str,
    pool_id: str,
    batch_slots: list[int],
    frames_by_slot: dict[int, list[dict[str, Any]]],
    evidence_dir: Path,
    prompt: dict[str, Any],
    timeout: int,
    attempts: int,
    retry_cap: int,
    maximum_output_tokens: int,
) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "text", "text": json.dumps(prompt, ensure_ascii=False)}]
    for slot in batch_slots:
        content.append({
            "type": "text",
            "text": f"EVENT E{slot:02d}: The next three images belong only to this event, in before / representative / after order.",
        })
        ordered = sorted(
            frames_by_slot[slot],
            key=lambda row: {"before": 0, "representative": 1, "after": 2}.get(str(row["role"]), 9),
        )
        if len(ordered) != 3:
            raise RuntimeError(f"event {slot} does not have exactly three context frames")
        for row in ordered:
            path = evidence_dir / row["filename"]
            if not path.is_file():
                raise RuntimeError(f"missing transient event frame: {path}")
            content.append({"type": "image_url", "image_url": {"url": data_url(path), "detail": "high"}})

    payload = json.dumps({
        "model": model,
        "temperature": 0.0,
        "max_tokens": max(2600, int(maximum_output_tokens)),
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是严格的游戏地图证据审核员。每个EVENT后面的三张图只属于该EVENT。"
                    "只认图中直接可读的地点文字，禁止把前一事件文字复制到后一事件，禁止按顺序和外观猜测。输出严格JSON。"
                ),
            },
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_object"},
    }, ensure_ascii=False).encode("utf-8")

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
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
            parsed["reviewerPool"] = pool_id
            return parsed
        except urllib.error.HTTPError as exc:
            last_error = exc
            retry_after = 0
            try:
                retry_after = int(exc.headers.get("Retry-After") or 0)
            except (TypeError, ValueError):
                retry_after = 0
            if attempt < attempts:
                time.sleep(min(retry_cap, max(retry_after, 8 * attempt)))
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(min(retry_cap, 8 * attempt))
    raise RuntimeError(f"event-batch review failed: pool={pool_id} model={model} slots={batch_slots}: {last_error}")


def batch_ranges(slots: list[int], size: int) -> list[list[int]]:
    return [slots[index:index + size] for index in range(0, len(slots), size)]


def packet_key(pool_id: str, model: str, slots: list[int]) -> tuple[str, str, int, int]:
    return pool_id, model, min(slots), max(slots)


def complete_batch_packet(packet: dict[str, Any], slots: list[int]) -> bool:
    reviews = packet.get("reviews") or []
    found = {
        int(row.get("slot")) for row in reviews
        if isinstance(row, dict) and str(row.get("slot", "")).isdigit()
    }
    return found == set(slots)


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
    pools = list(policy.get("reviewerPools") or [])
    if len(pools) != 2:
        raise RuntimeError(f"expected two independent reviewer pools, found {len(pools)}")
    pool_ids = [str(pool["id"]) for pool in pools]
    if len(set(pool_ids)) != 2:
        raise RuntimeError("reviewer pool IDs are not unique")
    pool_model_sets = [set(map(str, pool["models"])) for pool in pools]
    if pool_model_sets[0] & pool_model_sets[1]:
        raise RuntimeError("reviewer pools must not share a model")

    minimum = float(policy["confirmation"]["minimumConfidencePerModel"])
    request_config = policy["request"]
    event_batch_size = int(request_config.get("eventsPerRequest") or 4)
    timeout = min(90, int(request_config.get("timeoutSeconds") or 90))
    attempts = min(2, int(request_config.get("maximumAttempts") or 2))
    retry_cap = min(30, int(request_config.get("maximumRetryAfterSeconds") or 30))
    delay = max(0, int(request_config.get("delayBetweenRequestsSeconds") or 0))
    max_tokens = int(request_config.get("maximumOutputTokens") or 1600)

    start = int(manifest["batch"]["startSlot"])
    end = int(manifest["batch"]["endSlot"])
    slots = list(range(start, end + 1))
    batches = batch_ranges(slots, event_batch_size)
    fingerprint = str(manifest["evidenceFingerprint"])
    frames_by_slot: dict[int, list[dict[str, Any]]] = {}
    for row in manifest["extraction"]["frames"]:
        frames_by_slot.setdefault(int(row["slot"]), []).append(row)
    if sorted(frames_by_slot) != slots:
        raise RuntimeError(f"manifest frame slots do not match review range: {sorted(frames_by_slot)}")

    compact_candidates = [{
        "locationId": row["locationId"],
        "title": row["title"],
        "regionTitle": row["regionTitle"],
    } for row in candidates]
    segments_by_slot = {int(row["slot"]): row for row in manifest["segments"]}

    existing = load(output_path, {})
    cache_allowed = (
        int(existing.get("reviewStrategyVersion") or 0) == STRATEGY_VERSION
        and existing.get("evidenceFingerprint") == fingerprint
        and existing.get("source", {}).get("bvid") == stage["source"]["bvid"]
    )
    cached_packets: dict[tuple[str, str, int, int], dict[str, Any]] = {}
    if cache_allowed:
        for packet in existing.get("batchPackets", []):
            batch_slots = [int(value) for value in packet.get("slots", [])]
            if not batch_slots:
                continue
            key = packet_key(str(packet.get("reviewerPool") or ""), str(packet.get("model") or ""), batch_slots)
            if complete_batch_packet(packet, batch_slots):
                cached_packets[key] = packet

    all_batch_packets: dict[tuple[str, str, int, int], dict[str, Any]] = dict(cached_packets)
    requested_calls: list[dict[str, Any]] = []
    reused_calls: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    selected_pool_packets: list[dict[str, Any]] = []

    for pool in pools:
        pool_id = str(pool["id"])
        selected: dict[str, Any] | None = None
        for model in map(str, pool["models"]):
            packet_rows: list[dict[str, Any]] = []
            model_failed = False
            for batch_slots in batches:
                key = packet_key(pool_id, model, batch_slots)
                cached = all_batch_packets.get(key)
                if cached and complete_batch_packet(cached, batch_slots):
                    packet_rows.extend(cached["reviews"])
                    reused_calls.append({"reviewerPool": pool_id, "model": model, "slots": batch_slots})
                    continue
                prompt = {
                    "task": "review_individually_labeled_shrine_events",
                    "reviewerPool": pool_id,
                    "sourceTitle": stage["source"]["title"],
                    "requiredEvents": [f"E{slot:02d}" for slot in batch_slots],
                    "eventSegments": [{
                        "event": f"E{slot:02d}",
                        "startSeconds": segments_by_slot[slot]["startSeconds"],
                        "endSeconds": segments_by_slot[slot]["endSeconds"],
                        "representativeTimeSeconds": segments_by_slot[slot]["representativeTimeSeconds"],
                    } for slot in batch_slots],
                    "rules": [
                        "只返回本请求列出的EVENT，每个EVENT恰好一条结果。",
                        "EVENT文字后紧跟的三张图只属于该EVENT，顺序为before、representative、after。",
                        "只允许读取图中直接显示的地点名称或地图弹窗；禁止从候选列表反推文字。",
                        "禁止把一个EVENT中读取的地点复制到其他EVENT。",
                        "无法清楚读取时selectedLocationId必须为null、evidenceType为insufficient、confidence不得高于0.60。",
                        "不得将同一个候选分配给本批次中的多个EVENT。",
                    ],
                    "candidateShrines": compact_candidates,
                    "requiredOutput": {
                        "reviews": [{
                            "slot": batch_slots[0],
                            "selectedLocationId": "候选ID或null",
                            "visibleLabel": "直接读取文字或空字符串",
                            "regionClue": "直接读取区域文字或空字符串",
                            "evidenceType": "direct_popup_text|direct_map_label|unique_highlight_with_readable_text|insufficient",
                            "confidence": 0.0,
                            "reasonZhCN": "说明具体从哪一张图读到文字",
                        }]
                    },
                }
                requested_calls.append({"reviewerPool": pool_id, "model": model, "slots": batch_slots})
                try:
                    raw = call_model_batch(
                        policy["endpoint"], token, model, pool_id, batch_slots,
                        frames_by_slot, evidence_dir, prompt, timeout, attempts,
                        retry_cap, max_tokens,
                    )
                    by_slot = {
                        int(row.get("slot")): clean_review(row, int(row.get("slot")), model, pool_id, candidate_ids)
                        for row in raw.get("reviews", [])
                        if isinstance(row, dict)
                        and str(row.get("slot", "")).isdigit()
                        and int(row.get("slot")) in batch_slots
                    }
                    reviews = [by_slot[slot] for slot in batch_slots if slot in by_slot]
                    reviews = reject_duplicate_selections(reviews)
                    packet = {
                        "reviewerPool": pool_id,
                        "model": model,
                        "slots": batch_slots,
                        "reviewedAt": now(),
                        "source": "fresh-high-resolution-event-batch",
                        "reviews": reviews,
                    }
                    if not complete_batch_packet(packet, batch_slots):
                        raise RuntimeError(f"model returned incomplete batch: got {sorted(by_slot)}, expected {batch_slots}")
                    all_batch_packets[key] = packet
                    packet_rows.extend(reviews)
                    if delay:
                        time.sleep(delay)
                except Exception as exc:
                    errors.append({
                        "reviewerPool": pool_id,
                        "model": model,
                        "slots": batch_slots,
                        "error": str(exc)[:1800],
                    })
                    model_failed = True
                    break
            if not model_failed and {int(row["slot"]) for row in packet_rows} == set(slots):
                packet_rows = reject_duplicate_selections(sorted(packet_rows, key=lambda row: int(row["slot"])))
                selected = {
                    "reviewerPool": pool_id,
                    "model": model,
                    "reviews": packet_rows,
                    "selectedAt": now(),
                }
                break
        if selected:
            selected_pool_packets.append(selected)

    pool_by_id = {packet["reviewerPool"]: packet for packet in selected_pool_packets}
    reviews_by_pool = {
        pool_id: {int(row["slot"]): row for row in packet["reviews"]}
        for pool_id, packet in pool_by_id.items()
    }
    all_pools_present = set(pool_by_id) == set(pool_ids)

    frame_evidence_by_slot = {
        slot: [{
            "role": row["role"],
            "timeSeconds": row["timeSeconds"],
            "sha256": row["sha256"],
        } for row in sorted(frames_by_slot[slot], key=lambda item: item["role"])]
        for slot in slots
    }
    anchors: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    for slot in slots:
        present = [reviews_by_pool[pool_id][slot] for pool_id in pool_ids if pool_id in reviews_by_pool]
        selections = [row["selectedLocationId"] for row in present if row.get("selectedLocationId")]
        consensus_id = (
            selections[0]
            if all_pools_present
            and len(present) == 2
            and len(selections) == 2
            and len(set(selections)) == 1
            else None
        )
        consensus_rows = [row for row in present if row.get("selectedLocationId") == consensus_id] if consensus_id else []
        passed = bool(
            consensus_id
            and len(consensus_rows) == 2
            and all(float(row["confidence"]) >= minimum for row in consensus_rows)
            and all(row["visibleLabel"] for row in consensus_rows)
            and all(row["evidenceType"] in ALLOWED_TYPES for row in consensus_rows)
        )
        reviews.append({
            "slot": slot,
            "reviewerPoolReviews": present,
            "consensusLocationId": consensus_id,
            "consensusPassedBeforeGlobalUniquenessGate": passed,
            "frames": frame_evidence_by_slot[slot],
        })
        if passed:
            candidate = candidate_by_id[consensus_id]
            anchors.append({
                "videoPosition": slot,
                "observedLabelZh": consensus_rows[0]["visibleLabel"],
                "confidence": round(min(float(row["confidence"]) for row in consensus_rows), 4),
                "resolutionMethod": "two-pool-high-resolution-scene-event-consensus",
                "basis": "两个独立审核池分别查看该事件的before、representative、after高分辨率画面，读取到直接地点文字并选择同一神社候选。",
                "evidence": frame_evidence_by_slot[slot],
                "reviewerPoolReviews": consensus_rows,
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
                "reason": "two_pool_high_resolution_consensus_or_direct_evidence_not_met",
                "reviewerPoolReviews": present,
                "errors": errors,
                "evidence": frame_evidence_by_slot[slot],
            })

    global_assignments: dict[str, list[dict[str, Any]]] = {}
    for anchor in anchors:
        global_assignments.setdefault(anchor["locationId"], []).append(anchor)
    duplicate_ids = {location_id for location_id, rows in global_assignments.items() if len(rows) > 1}
    if duplicate_ids:
        kept: list[dict[str, Any]] = []
        for anchor in anchors:
            if anchor["locationId"] in duplicate_ids:
                unresolved.append({
                    "videoPosition": anchor["videoPosition"],
                    "status": "unresolved",
                    "reason": "global_duplicate_candidate_assignment_rejected",
                    "rejectedLocationId": anchor["locationId"],
                    "reviewerPoolReviews": anchor["reviewerPoolReviews"],
                    "evidence": anchor["evidence"],
                })
            else:
                kept.append(anchor)
        anchors = kept

    output = {
        "schemaVersion": 3,
        "reviewStrategyVersion": STRATEGY_VERSION,
        "generatedAt": now(),
        "stage": "shrine-anchor-batch01-high-resolution-event-batches",
        "status": "complete" if all_pools_present else "partial-reviewer-pools",
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
            "successfulReviewerPools": len(selected_pool_packets),
            "failedReviewerPools": 2 - len(selected_pool_packets),
            "requestedBatchCallsThisRun": len(requested_calls),
            "reusedBatchCallsThisRun": len(reused_calls),
            "persistedBatchPackets": len(all_batch_packets),
            "duplicateCandidateIdsRejected": len(duplicate_ids),
        },
        "policy": {
            "reviewerPools": pools,
            "eventsPerRequest": event_batch_size,
            "framesPerEvent": 3,
            "minimumConfidencePerReviewerPool": minimum,
            "requireTwoIndependentReviewerPools": True,
            "requireDirectReadableText": True,
            "rejectPerModelDuplicateAssignments": True,
            "rejectGlobalDuplicateAssignments": True,
            "repositoryContainsEvidencePixels": False,
        },
        "selectedReviewerPools": selected_pool_packets,
        "batchPackets": sorted(
            all_batch_packets.values(),
            key=lambda packet: (str(packet["reviewerPool"]), str(packet["model"]), min(packet["slots"])),
        ),
        "requestedBatchCallsThisRun": requested_calls,
        "reusedBatchCallsThisRun": reused_calls,
        "errors": errors,
        "duplicateCandidateIdsRejected": sorted(duplicate_ids),
        "anchors": sorted(anchors, key=lambda row: row["videoPosition"]),
        "unresolved": sorted(unresolved, key=lambda row: row["videoPosition"]),
        "reviews": reviews,
        "privacy": {
            "repositoryContainsPixels": False,
            "persistedEvidence": "scene boundaries, frame timestamps and SHA-256 hashes, visible labels, reviewer decisions and existing Atlas coordinates only",
        },
    }
    write(output_path, output)
    print(json.dumps({
        "status": output["status"],
        "counts": output["counts"],
        "selectedReviewerModels": {
            packet["reviewerPool"]: packet["model"] for packet in selected_pool_packets
        },
        "errors": errors,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
