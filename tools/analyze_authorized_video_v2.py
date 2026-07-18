#!/usr/bin/env python3
"""Resilient authorized-video runner.

Downloads an authorized public source into a temporary directory, delegates numeric
frame analysis to analyze_authorized_video.py, and always writes a machine-readable
result. Original media and frame pixels are never committed.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any

from curl_cffi import requests

import analyze_authorized_video as base


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def clean_error(value: str, limit: int = 5000) -> str:
    text = "\n".join(line for line in value.splitlines() if "cookie" not in line.lower())
    return text[-limit:]


def run_download(command: list[str]) -> tuple[pathlib.Path | None, str]:
    result = subprocess.run(command, capture_output=True, text=True)
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    if result.returncode != 0:
        return None, clean_error(output)
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    for line in reversed(lines):
        candidate = pathlib.Path(line)
        if candidate.exists():
            return candidate, clean_error(output)
    return None, clean_error(output or "yt-dlp completed without returning a media path")


def api_get_json(url: str) -> dict[str, Any]:
    response = requests.get(url, headers=HEADERS, impersonate="chrome", timeout=30)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"Bilibili API code={payload.get('code')} message={payload.get('message')}")
    return payload["data"]


def stream_to_file(url: str, destination: pathlib.Path) -> None:
    with requests.get(url, headers=HEADERS, impersonate="chrome", stream=True, timeout=60) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    if destination.stat().st_size < 1024:
        raise RuntimeError("Downloaded Bilibili media segment is unexpectedly small")


def direct_bilibili_download(url: str, workdir: pathlib.Path) -> pathlib.Path:
    match = re.search(r"(BV[0-9A-Za-z]+)", url)
    if not match:
        raise ValueError("No BV identifier found in Bilibili URL")
    bvid = match.group(1)
    view = api_get_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}")
    pages = view.get("pages") or []
    if not pages:
        raise RuntimeError("Bilibili view API returned no pages")
    cid = pages[0]["cid"]
    play = api_get_json(
        f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn=64&fnver=0&fnval=0&fourk=0"
    )
    segments = play.get("durl") or []
    if not segments:
        raise RuntimeError("Bilibili playurl API returned no progressive media URLs")
    downloaded: list[pathlib.Path] = []
    for index, segment in enumerate(segments):
        candidates = [segment.get("url"), *(segment.get("backup_url") or [])]
        last_error = "no media URL"
        for candidate in filter(None, candidates):
            target = workdir / f"segment-{index:03d}.flv"
            try:
                stream_to_file(str(candidate), target)
                downloaded.append(target)
                break
            except Exception as exc:
                last_error = repr(exc)
                target.unlink(missing_ok=True)
        else:
            raise RuntimeError(f"Unable to download segment {index}: {last_error}")
    output = workdir / "source.mp4"
    if len(downloaded) == 1:
        command = ["ffmpeg", "-y", "-i", str(downloaded[0]), "-c", "copy", str(output)]
    else:
        concat_file = workdir / "segments.txt"
        concat_file.write_text("".join(f"file '{path.as_posix()}'\n" for path in downloaded), encoding="utf-8")
        command = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(output)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not output.exists():
        raise RuntimeError(clean_error(result.stderr or "ffmpeg remux failed"))
    return output


def download_with_fallbacks(url: str, workdir: pathlib.Path) -> tuple[pathlib.Path, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    try:
        path = direct_bilibili_download(url, workdir)
        attempts.append({"strategy": "bilibili-public-api", "success": True, "diagnostic": "view + playurl progressive stream"})
        return path, attempts
    except Exception as exc:
        attempts.append({"strategy": "bilibili-public-api", "success": False, "diagnostic": clean_error(repr(exc))})

    template = str(workdir / "source.%(ext)s")
    common = [
        "yt-dlp", "--no-playlist", "--no-progress", "--merge-output-format", "mp4",
        "--referer", "https://www.bilibili.com/", "--user-agent", HEADERS["User-Agent"],
        "--retries", "5", "--fragment-retries", "5", "--retry-sleep", "2",
        "-o", template, "--print", "after_move:filepath",
    ]
    strategies = [
        ("dash-720", ["-f", "bv*[height<=720]+ba/b[height<=720]/b"]),
        ("impersonated-480", ["--impersonate", "chrome", "-f", "b[height<=480]/bv*[height<=480]+ba/b"]),
        ("multi-flv", ["--extractor-args", "bilibili:prefer_multi_flv=true", "-f", "b[height<=480]/b"]),
        ("best-public", ["-f", "b"]),
    ]
    for name, options in strategies:
        for old in workdir.glob("source.*"):
            old.unlink(missing_ok=True)
        path, diagnostic = run_download(common + options + [url])
        attempts.append({"strategy": name, "success": bool(path), "diagnostic": diagnostic})
        if path:
            return path, attempts
    raise RuntimeError(json.dumps(attempts, ensure_ascii=False))


def failure_report(job: dict[str, Any], stage: str, error: str, attempts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schemaVersion": 2,
        "jobId": job.get("id"),
        "status": "failed",
        "generatedAt": utc_now(),
        "stage": stage,
        "error": clean_error(error),
        "attempts": attempts or [],
        "source": {
            "author": job.get("author"), "title": job.get("title"), "url": job.get("url"),
            "platform": job.get("platform", "哔哩哔哩"), "authorizationId": job.get("authorizationId"),
            "externalSourceId": job.get("externalSourceId"),
        },
        "media": {"videoRetained": False, "framePixelsRetained": False},
        "privacy": "Only diagnostics are committed. No original media or frame pixels are retained.",
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: analyze_authorized_video_v2.py JOB_JSON", file=sys.stderr)
        return 2
    job_path = pathlib.Path(sys.argv[1])
    job = json.loads(job_path.read_text(encoding="utf-8"))
    output = pathlib.Path(job["output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any]
    try:
        with tempfile.TemporaryDirectory(prefix="atlas-authorized-") as directory:
            attempts: list[dict[str, Any]] = []
            try:
                video_path, attempts = download_with_fallbacks(job["url"], pathlib.Path(directory))
            except Exception as exc:
                try:
                    parsed = json.loads(str(exc))
                    attempts = parsed if isinstance(parsed, list) else attempts
                except Exception:
                    pass
                report = failure_report(job, "download", str(exc), attempts)
            else:
                try:
                    report = base.analyze(job, video_path)
                    report["schemaVersion"] = 2
                    report["downloadAttempts"] = attempts
                except Exception as exc:
                    report = failure_report(job, "analysis", repr(exc), attempts)
    except Exception as exc:
        report = failure_report(job, "runner", repr(exc))
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"analysis result written: {output} status={report.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
