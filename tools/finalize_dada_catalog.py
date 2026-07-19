#!/usr/bin/env python3
"""Finalize and verify the authorized Dada catalog after all source repairs.

This tool never downloads media. It validates catalog/result identity, media
retention, SHA-256 evidence, duplicate BVID separation, queue completion, and
then optionally rebuilds stale catalog/status summary metadata.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data/dada-ac-shadows-catalog.json"
STATUS_PATH = ROOT / "data/batch-analysis/dada-author-catalog-status.json"
QUEUE_PATH = ROOT / "data/analysis-jobs/dada-quality-reprocess.json"
AUDIT_PATH = ROOT / "data/batch-analysis/dada-catalog-quality-audit.json"
REPORT_PATH = ROOT / "data/batch-analysis/dada-final-integrity.json"
BVID_RE = re.compile(r"BV[0-9A-Za-z]+")
SEQ_RE = re.compile(r"(?:攻略[】〗\s]*)?0?(\d{1,2})(?:\s|[^0-9])")
EXPECTED_AUTHOR = "不再犹豫的达达猪"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def normalized(value: Any) -> str:
    text = str(value or "").lower().replace("【", "〖").replace("】", "〗")
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", text)


def bvid(value: Any) -> str | None:
    match = BVID_RE.search(str(value or ""))
    return match.group(0) if match else None


def sequence_from_title(value: Any) -> int | None:
    match = SEQ_RE.search(str(value or ""))
    return int(match.group(1)) if match else None


def duration_seconds(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        return int(round(float(value)))
    text = str(value or "").strip()
    if not text:
        return None
    parts = text.split(":")
    if not all(part.isdigit() for part in parts):
        return None
    total = 0
    for part in parts:
        total = total * 60 + int(part)
    return total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--fail-on-error", action="store_true")
    args = parser.parse_args()

    catalog = load(CATALOG_PATH)
    status = load(STATUS_PATH)
    queue = load(QUEUE_PATH)
    audit = load(AUDIT_PATH)
    catalog_items = sorted(catalog.get("items", []), key=lambda item: int(item.get("sequence") or 0))
    status_by_sequence = {int(item.get("sequence") or 0): item for item in status.get("items", [])}

    checks: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    bvid_groups: dict[str, list[int]] = defaultdict(list)
    exact_sequences: list[int] = []
    named_sequences: list[int] = []
    imported_sequences: list[int] = []

    def record(sequence: int | None, code: str, passed: bool, **evidence: Any) -> None:
        row = {"sequence": sequence, "code": code, "passed": bool(passed), "evidence": evidence}
        checks.append(row)
        if not passed:
            errors.append(row)

    expected_sequences = list(range(1, 24))
    actual_sequences = [int(item.get("sequence") or 0) for item in catalog_items]
    record(None, "SEQUENCE_SET_EXACT", actual_sequences == expected_sequences, actual=actual_sequences)
    record(None, "QUEUE_EMPTY", queue.get("sequences") == [] and queue.get("items") == [], queue=queue.get("sequences"))
    record(None, "QUALITY_AUDIT_COMPLETE", audit.get("qualityComplete") is True, summary=audit.get("summary"))
    record(None, "QUALITY_AUDIT_NO_CRITICAL", int((audit.get("summary") or {}).get("critical") or 0) == 0, summary=audit.get("summary"))

    for item in catalog_items:
        sequence = int(item.get("sequence") or 0)
        expected_title = str(item.get("title") or "")
        title_sequence = sequence_from_title(expected_title)
        if title_sequence == sequence:
            named_sequences.append(sequence)
        record(sequence, "CATALOG_TITLE_SEQUENCE", title_sequence == sequence, title=expected_title, parsedSequence=title_sequence)
        record(sequence, "CATALOG_AUTHOR", item.get("author") == EXPECTED_AUTHOR, author=item.get("author"))

        catalog_bvid = str(item.get("resolvedBvid") or bvid(item.get("url")) or "")
        record(sequence, "CATALOG_BVID", bool(BVID_RE.fullmatch(catalog_bvid)), bvid=catalog_bvid)
        if catalog_bvid:
            bvid_groups[catalog_bvid].append(sequence)
        if item.get("exactUrlVerified") is True:
            exact_sequences.append(sequence)

        result_relative = str(item.get("analysisResultPath") or f"data/analysis-results/dada-{sequence:02d}.json")
        result_path = ROOT / result_relative
        record(sequence, "RESULT_EXISTS", result_path.is_file(), resultPath=result_relative)
        if not result_path.is_file():
            continue
        result = load(result_path)
        source = result.get("source") or {}
        media = result.get("media") or {}
        result_bvid = str(bvid(source.get("url")) or "")
        catalog_duration = duration_seconds(item.get("duration"))
        result_duration = float(media.get("durationSeconds") or 0)

        record(sequence, "RESULT_ANALYZED", result.get("status") == "analyzed", status=result.get("status"))
        record(sequence, "RESULT_AUTHOR", source.get("author") == EXPECTED_AUTHOR, author=source.get("author"))
        record(sequence, "RESULT_TITLE", normalized(source.get("title")) == normalized(expected_title), expected=expected_title, actual=source.get("title"))
        record(sequence, "RESULT_BVID", result_bvid == catalog_bvid, expected=catalog_bvid, actual=result_bvid)
        record(sequence, "RESULT_DURATION", catalog_duration is not None and abs(result_duration - catalog_duration) <= 3, expected=catalog_duration, actual=result_duration)
        record(sequence, "RESULT_SHA256", bool(re.fullmatch(r"[0-9a-f]{64}", str(media.get("fileSha256") or ""))), sha256=media.get("fileSha256"))
        record(sequence, "VIDEO_NOT_RETAINED", media.get("videoRetained") is False, value=media.get("videoRetained"))
        record(sequence, "FRAMES_NOT_RETAINED", media.get("framePixelsRetained") is False, value=media.get("framePixelsRetained"))

        status_item = status_by_sequence.get(sequence) or {}
        record(sequence, "STATUS_IMPORTED", status_item.get("state") == "imported", state=status_item.get("state"))
        record(sequence, "STATUS_NOT_STALE", status_item.get("resultStale") is not True, resultStale=status_item.get("resultStale"))
        imported_sequences.append(sequence)

    duplicate_groups = [
        {"bvid": value, "sequences": sequences}
        for value, sequences in sorted(bvid_groups.items())
        if len(set(sequences)) > 1
    ]
    record(None, "NO_DUPLICATE_BVIDS", not duplicate_groups, duplicateGroups=duplicate_groups)

    timestamp = now()
    if args.apply:
        catalog_status = catalog.setdefault("catalogStatus", {})
        catalog_status.update({
            "confirmedNumberedEntries": len(catalog_items),
            "namedEntries": len(named_sequences),
            "pendingTitleVerification": sorted(set(expected_sequences) - set(named_sequences)),
            "exactVideoUrlsVerified": sorted(exact_sequences),
            "analysisImported": len(imported_sequences),
            "analysisRemaining": len(catalog_items) - len(imported_sequences),
            "analysisComplete": len(imported_sequences) == len(catalog_items),
            "analysisUpdatedAt": timestamp,
            "integrityVerifiedAt": timestamp if not errors else None,
        })
        status["updatedAt"] = timestamp
        status["complete"] = len(imported_sequences) == len(catalog_items)
        status.setdefault("summary", {}).update({
            "total": len(catalog_items),
            "imported": len(imported_sequences),
            "failed": 0 if not errors else len({row["sequence"] for row in errors if row["sequence"] is not None}),
            "unresolved": 0 if not errors else len({row["sequence"] for row in errors if row["sequence"] is not None}),
            "remaining": len(catalog_items) - len(imported_sequences),
        })
        write(CATALOG_PATH, catalog)
        write(STATUS_PATH, status)

    report = {
        "schemaVersion": 1,
        "generatedAt": timestamp,
        "applied": args.apply,
        "status": "pass" if not errors else "fail",
        "summary": {
            "catalogItems": len(catalog_items),
            "checks": len(checks),
            "passed": len(checks) - len(errors),
            "failed": len(errors),
            "namedSequences": named_sequences,
            "exactUrlSequences": exact_sequences,
            "importedSequences": imported_sequences,
            "duplicateBvidGroups": duplicate_groups,
        },
        "errors": errors,
        "checks": checks,
    }
    write(REPORT_PATH, report)
    print(json.dumps(report["summary"], ensure_ascii=False))
    if args.fail_on_error and errors:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
