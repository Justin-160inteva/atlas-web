#!/usr/bin/env python3
"""Canonical entrypoint for Atlas Conflict Reasoner v2."""
from __future__ import annotations

import re
import sys

import atlas_conflict_reasoner_v2 as core


def scoped_release(self: core.Reasoner) -> None:
    owner = self.manifest['releaseOwner']
    owner_text = self.files.get(owner, '')
    index = self.files.get('index.html', '')
    sw = self.files.get(self.manifest.get('serviceWorker', 'sw.js'), '')

    if self.version not in owner_text or self.manifest['versionText'] not in owner_text:
        self.add('critical', 'RELEASE_OWNER_DRIFT', f'{owner} is not synchronized with release-manifest.json', [owner, 'release-manifest.json'])
    if self.manifest['versionText'] not in index:
        self.add('critical', 'INDEX_VERSION_TEXT_DRIFT', 'index.html does not contain the canonical version text', ['index.html', 'release-manifest.json'])
    wrong_queries = sorted({version for version in re.findall(r'[?&]v=(0\.\d+\.\d+\.\d+)', index) if version != self.version})
    if wrong_queries:
        self.add('critical', 'INDEX_VERSION_DRIFT', f'index.html contains cache versions {wrong_queries}', ['index.html'], versions=wrong_queries)
    if self.manifest['cacheNamespace'] not in sw:
        self.add('critical', 'SW_CACHE_NAMESPACE_DRIFT', 'Service-worker cache namespace differs from the manifest', ['sw.js', 'release-manifest.json'])

    # Component metadata such as "资料库 0.9.1.3" is allowed. A conflict exists
    # only when a module assigns an ALPHA release label to the public brand node.
    writer_patterns = [
        re.compile(r'(?:brand|label|e)\.textContent\s*=\s*[`"\']([^`"\']*ALPHA\s+(0\.\d+\.\d+\.\d+))', re.I),
        re.compile(r'querySelector\([`"\']\.brand-copy\s+small[`"\']\)[\s\S]{0,200}?textContent\s*=\s*[`"\']([^`"\']*ALPHA\s+(0\.\d+\.\d+\.\d+))', re.I),
    ]
    for name, text in self.files.items():
        if not name.endswith(('.js', '.html')):
            continue
        for pattern in writer_patterns:
            for match in pattern.finditer(text):
                version = match.group(2)
                if name not in {owner, 'index.html'}:
                    self.add('critical', 'VERSION_OWNER_CONFLICT', f'{name} writes release label {version}; only {owner} may own it', [name, owner], version=version)
                elif version != self.version:
                    self.add('critical', 'VERSION_LITERAL_DRIFT', f'{name} writes {version}, expected {self.version}', [name, 'release-manifest.json'])


core.Reasoner.check_release = scoped_release

if __name__ == '__main__':
    sys.exit(core.main())
