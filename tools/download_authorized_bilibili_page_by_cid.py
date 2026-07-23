#!/usr/bin/env python3
"""Download one authorized Bilibili multipart page transiently using its explicit CID.

The job JSON must contain batch.page and batch.cid. The script never guesses the first
page of a multipart source. Media is written only to the caller-provided temporary
output directory.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from curl_cffi import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
}


def api_get(url: str) -> dict[str, Any]:
    response = requests.get(url, headers=HEADERS, impersonate="chrome", timeout=45)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"Bilibili API code={payload.get('code')} message={payload.get('message')}")
    return payload["data"]


def curl_download(url: str, destination: Path) -> None:
    destination.unlink(missing_ok=True)
    command = [
        "curl", "--location", "--fail", "--silent", "--show-error", "--http1.1",
        "--retry", "12", "--retry-all-errors", "--retry-delay", "2", "--continue-at", "-",
        "--user-agent", HEADERS["User-Agent"], "--referer", HEADERS["Referer"],
        "--header", f"Origin: {HEADERS['Origin']}", "--output", str(destination), url,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=1200)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-4000:] or f"curl exited {result.returncode}")
    if not destination.is_file() or destination.stat().st_size < 1024 * 1024:
        raise RuntimeError("downloaded segment is missing or unexpectedly small")


def remux(parts: list[Path], output: Path) -> None:
    if len(parts) == 1:
        command = ["ffmpeg", "-y", "-i", str(parts[0]), "-c", "copy", str(output)]
    else:
        listing = output.parent / "segments.txt"
        listing.write_text("".join(f"file '{part.as_posix()}'\n" for part in parts), encoding="utf-8")
        command = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(output)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=1200)
    if result.returncode != 0 or not output.is_file():
        raise RuntimeError((result.stderr or "ffmpeg remux failed")[-5000:])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", type=int, default=32, help="Bilibili progressive quality code; 32 is 480p")
    args = parser.parse_args()

    job_path = Path(args.job)
    job = json.loads(job_path.read_text(encoding="utf-8"))
    batch = job.get("batch") or {}
    page = int(batch.get("page") or 0)
    cid = int(batch.get("cid") or 0)
    if page <= 0 or cid <= 0:
        raise RuntimeError("authorized job must contain explicit positive batch.page and batch.cid")
    match = re.search(r"(BV[0-9A-Za-z]+)", str(job.get("url") or ""))
    if not match:
        raise RuntimeError("job URL does not contain a BVID")
    bvid = match.group(1)

    view = api_get(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}")
    pages = view.get("pages") or []
    matching = [row for row in pages if int(row.get("page") or 0) == page and int(row.get("cid") or 0) == cid]
    if len(matching) != 1:
        raise RuntimeError(f"page/CID verification failed for {bvid}: page={page} cid={cid}")
    page_info = matching[0]

    play = api_get(
        f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn={args.quality}&fnver=0&fnval=0&fourk=0"
    )
    segments = play.get("durl") or []
    if not segments:
        raise RuntimeError("Bilibili playurl returned no progressive segments")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    attempts: list[dict[str, Any]] = []
    for index, segment in enumerate(segments):
        candidates = [segment.get("url"), *(segment.get("backup_url") or [])]
        last_error = "no URL"
        for candidate_index, candidate in enumerate(filter(None, candidates)):
            target = output_dir / f"segment-{index:03d}.flv"
            try:
                curl_download(str(candidate), target)
                downloaded.append(target)
                attempts.append({"segment": index, "candidate": candidate_index, "success": True})
                break
            except Exception as exc:
                last_error = repr(exc)
                attempts.append({"segment": index, "candidate": candidate_index, "success": False, "error": last_error[-1000:]})
                target.unlink(missing_ok=True)
        else:
            raise RuntimeError(f"failed to download segment {index}: {last_error}")

    output = output_dir / f"{job['id']}.mp4"
    remux(downloaded, output)
    manifest = {
        "schemaVersion": 1,
        "status": "downloaded-transiently",
        "jobId": job["id"],
        "authorizationId": job.get("authorizationId"),
        "bvid": bvid,
        "page": page,
        "cid": cid,
        "pageTitle": page_info.get("part"),
        "durationHintSeconds": page_info.get("duration"),
        "requestedQuality": args.quality,
        "actualQuality": play.get("quality"),
        "segmentCount": len(downloaded),
        "bytes": output.stat().st_size,
        "attempts": attempts,
        "mediaPath": str(output.resolve()),
        "retention": "temporary-directory-only",
    }
    manifest_path = output_dir / "download-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
