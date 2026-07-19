#!/usr/bin/env python3
"""Synchronize release-manifest.json into runtime entry files."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / 'release-manifest.json'


def apply_manifest(content: str, path: str, manifest: dict) -> str:
    version = manifest['version']
    version_text = manifest['versionText']
    cache = manifest['cacheNamespace']
    if path == 'index.html':
        content = re.sub(r'([?&]v=)0\.\d+\.\d+\.\d+', rf'\g<1>{version}', content)
        content = re.sub(r"ASSASSIN'S CREED SHADOWS · ALPHA 0\.\d+\.\d+\.\d+", version_text, content)
    elif path == 'atlas-bootstrap.js':
        content = re.sub(r"version:\s*'0\.\d+\.\d+\.\d+'", f"version: '{version}'", content, count=1)
        content = re.sub(r"versionText:\s*\"ASSASSIN'S CREED SHADOWS · ALPHA 0\.\d+\.\d+\.\d+\"", f'versionText: "{version_text}"', content, count=1)
        content = re.sub(r"cacheNamespace:\s*'atlas-alpha-[^']+'", f"cacheNamespace: '{cache}'", content, count=1)
    elif path == 'sw.js':
        content = re.sub(r"const CACHE='atlas-alpha-[^']+'", f"const CACHE='{cache}'", content, count=1)
    return content


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    drift: list[str] = []
    for name in ['index.html', 'atlas-bootstrap.js', 'sw.js']:
        path = ROOT / name
        current = path.read_text(encoding='utf-8')
        expected = apply_manifest(current, name, manifest)
        if current != expected:
            drift.append(name)
            if args.write:
                path.write_text(expected, encoding='utf-8')
    if drift and not args.write:
        print('Release manifest drift:', ', '.join(drift))
        return 2
    print('Release manifest synchronized' if args.write else 'Release manifest is synchronized')
    return 0


if __name__ == '__main__':
    sys.exit(main())
