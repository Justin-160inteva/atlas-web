#!/usr/bin/env python3
"""Run one authorized analyzer and publish a sanitized live progress snapshot.

The publisher updates one public GitHub issue without committing heartbeat files every
few seconds. Publishing failures never fail the underlying analysis task.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: pathlib.Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def bounded_number(value: Any, minimum: float, maximum: float, default: float = 0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def public_snapshot(progress: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    source = progress.get("source") if isinstance(progress.get("source"), dict) else {}
    counts = progress.get("counts") if isinstance(progress.get("counts"), dict) else {}
    media = progress.get("media") if isinstance(progress.get("media"), dict) else {}
    recovery = progress.get("recovery") if isinstance(progress.get("recovery"), dict) else {}
    batch = job.get("batch") if isinstance(job.get("batch"), dict) else {}
    snapshot = {
        "schemaVersion": 1,
        "state": str(progress.get("state") or "running"),
        "stage": str(progress.get("stage") or "starting"),
        "progressPercent": round(bounded_number(progress.get("progressPercent"), 0, 100), 1),
        "message": str(progress.get("message") or "扫描任务运行中")[:240],
        "updatedAt": str(progress.get("updatedAt") or now()),
        "author": str(source.get("author") or job.get("author") or ""),
        "title": str(source.get("title") or job.get("title") or "")[:300],
        "externalSourceId": str(source.get("externalSourceId") or job.get("externalSourceId") or ""),
        "page": batch.get("page"),
        "region": batch.get("regionGuess"),
        "attempt": progress.get("attempt"),
        "elapsedSeconds": round(bounded_number(progress.get("elapsedSeconds"), 0, 86400 * 7), 1),
        "processedSeconds": round(bounded_number(media.get("processedSeconds"), 0, 86400 * 7), 1),
        "durationSeconds": round(bounded_number(media.get("durationSeconds"), 0, 86400 * 7), 1),
        "sampledFrames": int(bounded_number(counts.get("sampled"), 0, 10_000_000)),
        "targetFrames": int(bounded_number(counts.get("target"), 0, 10_000_000)),
        "keptFrames": int(bounded_number(counts.get("kept"), 0, 10_000_000)),
        "blurredFrames": int(bounded_number(counts.get("blurred"), 0, 10_000_000)),
        "duplicateFrames": int(bounded_number(counts.get("duplicates"), 0, 10_000_000)),
        "recoveryCategory": str(recovery.get("category") or ""),
        "recoveryAction": str(recovery.get("action") or "")[:200],
        "requiresHumanReview": bool(recovery.get("requiresHumanReview", False)),
        "runId": os.environ.get("GITHUB_RUN_ID", ""),
        "runAttempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
    }
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = snapshot["runId"]
    snapshot["runUrl"] = f"https://github.com/{repository}/actions/runs/{run_id}" if repository and run_id else ""
    return snapshot


def render_issue(snapshot: dict[str, Any]) -> str:
    state_labels = {
        "running": "运行中",
        "queued": "排队中",
        "retrying": "自动恢复中",
        "complete": "已完成",
        "failed": "失败",
        "blocked": "需要人工检查",
        "idle": "空闲",
    }
    state = state_labels.get(str(snapshot.get("state")), str(snapshot.get("state") or "未知"))
    percent = snapshot.get("progressPercent", 0)
    sampled = snapshot.get("sampledFrames", 0)
    target = snapshot.get("targetFrames", 0)
    updated = snapshot.get("updatedAt", "")
    run_url = snapshot.get("runUrl", "")
    run_line = f"\n- GitHub Actions：{run_url}" if run_url else ""
    return (
        "此 Issue 由 Atlas GitHub Actions 自动更新，用于公开展示授权视频扫描的安全进度摘要。\n\n"
        f"- 状态：**{state}**\n"
        f"- 阶段：`{snapshot.get('stage', 'unknown')}`\n"
        f"- 进度：**{percent}%**\n"
        f"- 当前内容：{snapshot.get('title') or '—'}\n"
        f"- 区域 / 分P：{snapshot.get('region') or '—'} / P{snapshot.get('page') or '—'}\n"
        f"- 采样：{sampled} / {target}\n"
        f"- 最后心跳：{updated}"
        f"{run_line}\n\n"
        "```json\n"
        f"{json.dumps(snapshot, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        "不会展示 Cookie、临时下载地址、原始视频、关键帧或未清理的错误日志。"
    )


def publish(issue_number: int, snapshot: dict[str, Any]) -> None:
    repository = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not repository or not token or issue_number <= 0:
        return
    payload = json.dumps({"body": render_issue(snapshot)}, ensure_ascii=False)
    command = [
        "gh",
        "api",
        f"repos/{repository}/issues/{issue_number}",
        "--method",
        "PATCH",
        "--input",
        "-",
    ]
    result = subprocess.run(
        command,
        input=payload,
        text=True,
        capture_output=True,
        env={**os.environ, "GH_TOKEN": token},
        timeout=30,
    )
    if result.returncode != 0:
        print(f"live progress publish warning: {result.stderr[-500:]}", file=sys.stderr, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("job_json")
    parser.add_argument("--analyzer", required=True)
    parser.add_argument("--issue", type=int, default=0)
    parser.add_argument("--refresh-seconds", type=int, default=30)
    args = parser.parse_args()

    job_path = (ROOT / args.job_json).resolve()
    job = read_json(job_path)
    if not isinstance(job, dict):
        raise ValueError("job JSON must be an object")
    progress_path = ROOT / str(job.get("progressOutput") or "data/runtime-progress/eleven-pilot-progress.json")
    started = time.monotonic()
    initial = {
        "schemaVersion": 1,
        "state": "running",
        "stage": "starting",
        "progressPercent": 1,
        "message": "正在启动授权视频扫描",
        "updatedAt": now(),
        "source": {
            "author": job.get("author"),
            "title": job.get("title"),
            "externalSourceId": job.get("externalSourceId"),
        },
        "counts": {"sampled": 0, "target": int(job.get("maxSamples", 0)), "kept": 0, "blurred": 0, "duplicates": 0},
        "media": {"processedSeconds": 0, "durationSeconds": 0},
    }
    write_json(progress_path, initial)
    publish(args.issue, public_snapshot(initial, job))

    refresh = max(15, min(120, args.refresh_seconds))
    with tempfile.NamedTemporaryFile(prefix="atlas-live-analyzer-", suffix=".log", delete=False) as log_handle:
        log_path = pathlib.Path(log_handle.name)
    try:
        with log_path.open("w", encoding="utf-8") as output:
            process = subprocess.Popen(
                [sys.executable, args.analyzer, job_path.relative_to(ROOT).as_posix()],
                cwd=ROOT,
                stdout=output,
                stderr=subprocess.STDOUT,
                text=True,
                env=os.environ.copy(),
            )
        last_publish = 0.0
        while process.poll() is None:
            current = read_json(progress_path, initial)
            if not isinstance(current, dict):
                current = dict(initial)
            current["elapsedSeconds"] = round(time.monotonic() - started, 1)
            current["updatedAt"] = current.get("updatedAt") or now()
            if time.monotonic() - last_publish >= refresh:
                snapshot = public_snapshot(current, job)
                publish(args.issue, snapshot)
                print(
                    f"live heartbeat stage={snapshot['stage']} progress={snapshot['progressPercent']}% "
                    f"samples={snapshot['sampledFrames']}/{snapshot['targetFrames']}",
                    flush=True,
                )
                last_publish = time.monotonic()
            time.sleep(5)
        return_code = int(process.returncode or 0)
        current = read_json(progress_path, initial)
        if not isinstance(current, dict):
            current = dict(initial)
        current["elapsedSeconds"] = round(time.monotonic() - started, 1)
        current["updatedAt"] = now()
        if return_code == 0 and current.get("state") not in {"complete", "failed", "blocked"}:
            current.update({"state": "complete", "stage": "complete", "progressPercent": 100, "message": "扫描和结果写入已完成"})
        elif return_code != 0 and current.get("state") not in {"failed", "blocked"}:
            current.update({"state": "failed", "stage": "analyzer", "message": "扫描器返回失败，正在进入自动诊断"})
        write_json(progress_path, current)
        publish(args.issue, public_snapshot(current, job))
        tail = log_path.read_text(encoding="utf-8", errors="replace")[-12000:]
        if tail:
            print(tail, flush=True)
        return return_code
    finally:
        log_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
