#!/usr/bin/env python3
"""Process one bounded authorized-video queue item with durable machine-readable state.

The scanner persists a running/failure/imported state locally before and after analysis.
Original video media and frame pixels remain transient and are never committed.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def load(path: pathlib.Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def run(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def build_job(item: dict[str, Any], catalog: dict[str, Any], manifest: dict[str, Any]) -> tuple[pathlib.Path, pathlib.Path]:
    page = int(item.get("page") or item.get("sequence") or 1)
    prefix = str(manifest.get("outputPrefix") or "eleven")
    job_path = ROOT / f"data/analysis-jobs/{prefix}-p{page:03d}.json"
    result_path = ROOT / f"data/analysis-results/{prefix}-p{page:03d}.json"
    duration = int(item.get("durationSeconds") or 0)
    maximum = int(
        manifest.get("maxSamplesA", 540)
        if item.get("scanClass") == "A"
        else manifest.get("maxSamplesDefault", 360)
    )
    interval = max(float(manifest.get("minimumIntervalSeconds", 3.0)), duration / max(1, maximum))
    job = {
        "id": f"{prefix}-p{page:03d}-v2",
        "externalSourceId": item["externalSourceId"],
        "authorizationId": catalog["authorizationId"],
        "author": catalog["author"],
        "platform": catalog.get("platform", "哔哩哔哩"),
        "title": item["title"],
        "url": item["url"],
        "intervalSeconds": round(interval, 3),
        "maxSamples": maximum,
        "minimumSharpness": 18,
        "duplicateHashDistance": 0.11,
        "duplicateColorDistance": 0.055,
        "output": result_path.relative_to(ROOT).as_posix(),
        "retention": {
            "originalVideo": False,
            "framePixels": False,
            "numericDescriptorsOnly": True,
        },
        "batch": {
            "catalog": manifest["catalog"],
            "queue": manifest["queue"],
            "page": item.get("page"),
            "cid": item.get("cid"),
            "regionGuess": item.get("regionGuess"),
            "sourceKey": f"{item.get('bvid')}:p{item.get('page')}",
        },
    }
    write(job_path, job)
    return job_path, result_path


def summarize(queue: dict[str, Any], max_attempts: int) -> dict[str, int]:
    items = queue.get("items", [])
    imported = sum(item.get("state") == "imported" for item in items)
    running = sum(item.get("state") == "running" for item in items)
    failed = sum(item.get("state") == "failed" for item in items)
    blocked = sum(
        item.get("state") == "failed" and int(item.get("attemptCount", 0)) >= max_attempts
        for item in items
    )
    retryable = sum(
        item.get("state") == "failed" and int(item.get("attemptCount", 0)) < max_attempts
        for item in items
    )
    return {
        "total": len(items),
        "imported": imported,
        "running": running,
        "failed": failed,
        "blocked": blocked,
        "retryableFailed": retryable,
        "remaining": len(items) - imported,
    }


def status_payload(
    manifest: dict[str, Any],
    catalog: dict[str, Any],
    queue: dict[str, Any],
    max_attempts: int,
    *,
    phase: str,
    active: dict[str, Any] | None = None,
    events: list[dict[str, Any]] | None = None,
    attempted: int = 0,
    imported_this_run: int = 0,
) -> dict[str, Any]:
    summary = summarize(queue, max_attempts)
    summary["attemptedThisRun"] = attempted
    summary["newlyImportedThisRun"] = imported_this_run
    return {
        "schemaVersion": 2,
        "batchId": manifest.get("id", "eleven-pilot-scan-v2"),
        "author": catalog["author"],
        "authorizationId": catalog["authorizationId"],
        "pilotRegion": queue.get("pilotRegion"),
        "updatedAt": now(),
        "phase": phase,
        "activeItem": active,
        "complete": summary["remaining"] == 0,
        "summary": summary,
        "items": [
            {
                "externalSourceId": item.get("externalSourceId"),
                "sequence": item.get("sequence"),
                "page": item.get("page"),
                "state": item.get("state", "pending"),
                "attemptCount": int(item.get("attemptCount", 0)),
                "lastStartedAt": item.get("lastStartedAt"),
                "lastFinishedAt": item.get("lastFinishedAt"),
                "resultPath": item.get("resultPath"),
                "error": item.get("error"),
            }
            for item in queue.get("items", [])
        ],
        "events": events or [],
        "privacy": "Original videos and frame pixels are transient and are not retained in the public repository.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    args = parser.parse_args()

    manifest_path = (ROOT / args.manifest).resolve()
    manifest = load(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")

    catalog_path = ROOT / manifest["catalog"]
    queue_path = ROOT / manifest["queue"]
    status_path = ROOT / manifest["statusOutput"]
    index_path = ROOT / "data/analysis-index.json"
    catalog = load(catalog_path)
    queue = load(queue_path)
    index = load(index_path, {"version": "0.9.1.4", "items": []})
    if not isinstance(catalog, dict) or not isinstance(queue, dict):
        raise ValueError("catalog and queue must be JSON objects")

    indexed = {
        item.get("externalSourceId"): item
        for item in index.get("items", [])
        if item.get("externalSourceId")
    }
    catalog_items = {item["id"]: item for item in catalog.get("items", [])}
    max_attempts = max(1, int(manifest.get("maxAttemptsPerItem", 3)))
    stale_seconds = max(900, int(manifest.get("staleRunningAfterSeconds", 7200)))
    current_time = datetime.now(timezone.utc)

    for item in queue.get("items", []):
        external_id = item.get("externalSourceId")
        if indexed.get(external_id, {}).get("status") == "imported":
            item["state"] = "imported"
            item.pop("error", None)
            continue
        if item.get("state") == "running":
            started = parse_time(item.get("lastStartedAt"))
            if started is None or (current_time - started).total_seconds() >= stale_seconds:
                item["state"] = "failed"
                item["error"] = "stale running lease recovered by scanner v2"

    selected: list[dict[str, Any]] = []
    for item in queue.get("items", []):
        state = item.get("state", "pending")
        attempts = int(item.get("attemptCount", 0))
        if state == "imported" or state == "running":
            continue
        if state == "failed" and attempts >= max_attempts:
            continue
        if state not in {"pending", "failed"}:
            continue
        selected.append(item)
        if len(selected) >= max(1, int(manifest.get("maxItemsPerRun", 1))):
            break

    if not selected:
        queue["status"] = "complete" if summarize(queue, max_attempts)["remaining"] == 0 else "blocked"
        queue["updatedAt"] = now()
        write(queue_path, queue)
        write(
            status_path,
            status_payload(manifest, catalog, queue, max_attempts, phase=queue["status"]),
        )
        print(json.dumps(summarize(queue, max_attempts), ensure_ascii=False))
        return 0

    events: list[dict[str, Any]] = []
    newly_imported = 0
    for item in selected:
        external_id = str(item["externalSourceId"])
        source = catalog_items[external_id]
        started_at = now()
        item["attemptCount"] = int(item.get("attemptCount", 0)) + 1
        item["state"] = "running"
        item["lastStartedAt"] = started_at
        item.pop("error", None)
        queue["status"] = "in_progress"
        queue["activeExternalSourceId"] = external_id
        queue["updatedAt"] = started_at
        active = {
            "externalSourceId": external_id,
            "sequence": item.get("sequence"),
            "page": item.get("page"),
            "title": item.get("title"),
            "startedAt": started_at,
            "attemptCount": item["attemptCount"],
        }
        write(queue_path, queue)
        write(
            status_path,
            status_payload(
                manifest,
                catalog,
                queue,
                max_attempts,
                phase="running",
                active=active,
                attempted=1,
            ),
        )

        event: dict[str, Any] = dict(active)
        try:
            job_path, result_path = build_job(item, catalog, manifest)
            process = run(
                [
                    sys.executable,
                    manifest.get("analyzer", "tools/analyze_authorized_video_v5.py"),
                    job_path.relative_to(ROOT).as_posix(),
                ],
                int(manifest.get("perItemTimeoutSeconds", 5400)),
            )
            event["analyzerReturnCode"] = process.returncode
            event["analyzerOutput"] = (process.stdout + "\n" + process.stderr)[-6000:]
            if not result_path.exists():
                raise RuntimeError("analyzer did not write result")
            result = load(result_path)
            event["analysisStatus"] = result.get("status")
            update = run(
                [sys.executable, "tools/update_analysis_index.py", result_path.relative_to(ROOT).as_posix()],
                180,
            )
            event["indexReturnCode"] = update.returncode
            if update.returncode != 0:
                raise RuntimeError((update.stdout + "\n" + update.stderr)[-3000:])
            if result.get("status") == "analyzed":
                item["state"] = "imported"
                item["resultPath"] = result_path.relative_to(ROOT).as_posix()
                item.pop("error", None)
                source["analysisStatus"] = "imported"
                source["analysisResultPath"] = item["resultPath"]
                source["analysisUpdatedAt"] = now()
                newly_imported += 1
                event["completed"] = True
            else:
                item["state"] = "failed"
                item["error"] = result.get("error") or f"analysis status {result.get('status')}"
                source["analysisStatus"] = "failed"
                event["completed"] = False
                event["error"] = item["error"]
        except subprocess.TimeoutExpired as exc:
            item["state"] = "failed"
            item["error"] = f"timeout after {exc.timeout} seconds"
            source["analysisStatus"] = "failed"
            event["completed"] = False
            event["error"] = item["error"]
        except Exception as exc:
            item["state"] = "failed"
            item["error"] = repr(exc)[-4000:]
            source["analysisStatus"] = "failed"
            event["completed"] = False
            event["error"] = item["error"]

        finished_at = now()
        item["lastFinishedAt"] = finished_at
        event["finishedAt"] = finished_at
        events.append(event)
        queue.pop("activeExternalSourceId", None)
        write(queue_path, queue)
        write(catalog_path, catalog)

    index = load(index_path, index)
    indexed = {
        item.get("externalSourceId"): item
        for item in index.get("items", [])
        if item.get("externalSourceId")
    }
    for item in queue.get("items", []):
        if indexed.get(item.get("externalSourceId"), {}).get("status") == "imported":
            item["state"] = "imported"
            item.pop("error", None)

    summary = summarize(queue, max_attempts)
    if summary["remaining"] == 0:
        phase = "complete"
    elif newly_imported:
        phase = "progress"
    elif summary["retryableFailed"]:
        phase = "retryable_failure"
    elif summary["blocked"]:
        phase = "blocked"
    else:
        phase = "idle"
    queue["status"] = phase
    queue["updatedAt"] = now()
    write(queue_path, queue)

    catalog_status = catalog.setdefault("catalogStatus", {})
    catalog_status["analysisImported"] = sum(
        item.get("analysisStatus") == "imported" for item in catalog.get("items", [])
    )
    catalog_status["analysisRemaining"] = len(catalog.get("items", [])) - catalog_status["analysisImported"]
    catalog_status["pilotImported"] = summary["imported"]
    catalog_status["pilotRemaining"] = summary["remaining"]
    catalog_status["pilotBlocked"] = summary["blocked"]
    catalog["updatedAt"] = now()
    write(catalog_path, catalog)
    write(
        status_path,
        status_payload(
            manifest,
            catalog,
            queue,
            max_attempts,
            phase=phase,
            events=events,
            attempted=len(selected),
            imported_this_run=newly_imported,
        ),
    )
    print(json.dumps(summarize(queue, max_attempts), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
