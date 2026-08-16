#!/usr/bin/env python3
"""Download one explicitly authorized Bilibili page to a temporary directory."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from curl_cffi import requests

ROOT = Path(__file__).resolve().parents[1]
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


def download(url: str, destination: Path) -> None:
    destination.unlink(missing_ok=True)
    result = subprocess.run([
        "curl", "--location", "--fail", "--silent", "--show-error", "--http1.1",
        "--retry", "12", "--retry-all-errors", "--retry-delay", "2", "--continue-at", "-",
        "--user-agent", HEADERS["User-Agent"], "--referer", HEADERS["Referer"],
        "--header", f"Origin: {HEADERS['Origin']}", "--output", str(destination), url,
    ], capture_output=True, text=True, timeout=1800, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or f"curl exited {result.returncode}")[-2000:])
    if not destination.is_file() or destination.stat().st_size < 1024 * 1024:
        raise RuntimeError("downloaded segment is missing or unexpectedly small")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--authorization-registry", default="data/authorizations.json")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", type=int, default=32)
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    if output_dir == ROOT or ROOT in output_dir.parents:
        raise RuntimeError("transient media output must remain outside the repository")
    job = json.loads(Path(args.job).read_text(encoding="utf-8"))
    authorizations = json.loads(Path(args.authorization_registry).read_text(encoding="utf-8"))
    auth = next(row for row in authorizations["records"] if row["id"] == job["authorizationId"])
    required_scope = ("localDownloadAndAnalysis", "downloadFromPublicVideoPage", "computerVisionAnalysis", "privateLowResolutionKeyframes")
    if auth["status"] != "active" or auth["author"] != job["author"] or auth["platform"] != job["platform"]:
        raise RuntimeError("job does not match an active author/platform authorization")
    if any(auth["scope"].get(key) is not True for key in required_scope):
        raise RuntimeError("authorization scope does not allow this transient download")
    if not any(token in job["title"] for token in auth["matchingRule"]["titleMustContainAny"]):
        raise RuntimeError("job title does not match the authorized game scope")

    batch = job.get("batch") or {}
    page, cid = int(batch.get("page") or 0), int(batch.get("cid") or 0)
    match = re.search(r"(BV[0-9A-Za-z]+)", str(job.get("url") or ""))
    if page <= 0 or cid <= 0 or not match:
        raise RuntimeError("job must contain explicit BVID, page and CID")
    bvid = match.group(1)
    view = api_get(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}")
    matches = [row for row in view.get("pages") or [] if int(row.get("page") or 0) == page and int(row.get("cid") or 0) == cid]
    if len(matches) != 1:
        raise RuntimeError(f"page/CID verification failed for {bvid}: page={page} cid={cid}")
    play = api_get(f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn={args.quality}&fnver=0&fnval=0&fourk=0")
    segments = play.get("durl") or []
    if not segments:
        raise RuntimeError("Bilibili play metadata returned no progressive segments")

    output_dir.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    for index, segment in enumerate(segments):
        last_error = "no media URL"
        for candidate in filter(None, [segment.get("url"), *(segment.get("backup_url") or [])]):
            target = output_dir / f"segment-{index:03d}.flv"
            try:
                download(str(candidate), target)
                parts.append(target)
                break
            except Exception as exc:
                last_error = type(exc).__name__
                target.unlink(missing_ok=True)
        else:
            raise RuntimeError(f"failed to download segment {index}: {last_error}")

    output = output_dir / f"{job['id']}.mp4"
    if len(parts) == 1:
        command = ["ffmpeg", "-y", "-i", str(parts[0]), "-c", "copy", str(output)]
    else:
        listing = output_dir / "segments.txt"
        listing.write_text("".join(f"file '{part.as_posix()}'\n" for part in parts), encoding="utf-8")
        command = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(output)]
    remux = subprocess.run(command, capture_output=True, text=True, timeout=1800, check=False)
    if remux.returncode != 0 or not output.is_file():
        raise RuntimeError((remux.stderr or "ffmpeg remux failed")[-3000:])
    print(json.dumps({"status": "downloaded-transiently", "jobId": job["id"], "authorizationId": job["authorizationId"], "bvid": bvid, "page": page, "cid": cid, "segments": len(parts), "bytes": output.stat().st_size, "retention": "temporary-directory-only"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
