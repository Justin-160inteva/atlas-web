#!/usr/bin/env python3
"""Page-aware resilient Bilibili analyzer for multipart authorized videos."""
from __future__ import annotations

import pathlib
import re
import subprocess
from urllib.parse import parse_qs, urlparse

import analyze_authorized_video_v4 as v4

runner = v4.runner


def direct_bilibili_download(url: str, workdir: pathlib.Path) -> pathlib.Path:
    match = re.search(r"(BV[0-9A-Za-z]+)", url)
    if not match:
        raise ValueError("No BV identifier found in Bilibili URL")
    bvid = match.group(1)
    query = parse_qs(urlparse(url).query)
    try:
        page_number = max(1, int((query.get("p") or ["1"])[0]))
    except (TypeError, ValueError):
        page_number = 1

    view = runner.api_get_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}")
    pages = view.get("pages") or []
    if not pages:
        raise RuntimeError("Bilibili view API returned no pages")
    if page_number > len(pages):
        raise RuntimeError(f"Requested page {page_number} exceeds multipart page count {len(pages)}")
    page = pages[page_number - 1]
    cid = page["cid"]
    play = runner.api_get_json(
        f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn=32&fnver=0&fnval=0&fourk=0"
    )
    segments = play.get("durl") or []
    if not segments:
        raise RuntimeError("Bilibili playurl API returned no progressive media URLs")

    downloaded: list[pathlib.Path] = []
    for index, segment in enumerate(segments):
        candidates = [segment.get("url"), *(segment.get("backup_url") or [])]
        last_error = "no media URL"
        for candidate in filter(None, candidates):
            target = workdir / f"p{page_number:03d}-segment-{index:03d}.flv"
            try:
                runner.stream_to_file(str(candidate), target)
                downloaded.append(target)
                break
            except Exception as exc:
                last_error = repr(exc)
                target.unlink(missing_ok=True)
        else:
            raise RuntimeError(f"Unable to download page {page_number} segment {index}: {last_error}")

    output = workdir / f"source-p{page_number:03d}.mp4"
    if len(downloaded) == 1:
        command = ["ffmpeg", "-y", "-i", str(downloaded[0]), "-c", "copy", str(output)]
    else:
        concat_file = workdir / "segments.txt"
        concat_file.write_text("".join(f"file '{path.as_posix()}'\n" for path in downloaded), encoding="utf-8")
        command = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(output)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not output.exists():
        raise RuntimeError(runner.clean_error(result.stderr or "ffmpeg remux failed"))
    return output


runner.direct_bilibili_download = direct_bilibili_download

if __name__ == "__main__":
    raise SystemExit(runner.main())
