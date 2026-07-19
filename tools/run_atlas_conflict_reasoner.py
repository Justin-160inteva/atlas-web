#!/usr/bin/env python3
"""Canonical runner for Atlas Conflict Reasoner.

Applies DOM-scoped navigation checks and distinguishes harmless component
version metadata from code that actually owns the public release label.
"""
from __future__ import annotations

import re
import sys

import atlas_conflict_reasoner as core


def scoped_release_ownership(self: core.Reasoner) -> None:
    owner = self.manifest['releaseOwner']
    owner_text = self.files.get(owner, '')
    if self.version not in owner_text:
        self.add('critical', 'RELEASE_OWNER_VERSION_MISSING', f'{owner} does not contain manifest version {self.version}', [owner, 'release-manifest.json'])
    if self.manifest['versionText'] not in owner_text:
        self.add('critical', 'RELEASE_OWNER_TEXT_MISSING', f'{owner} does not contain canonical version text', [owner, 'release-manifest.json'])

    index = self.files.get('index.html', '')
    query_versions = re.findall(r'[?&]v=(0\.\d+\.\d+\.\d+)', index)
    wrong = sorted({version for version in query_versions if version != self.version})
    if wrong:
        self.add('critical', 'INDEX_VERSION_DRIFT', f'index.html contains non-release cache versions: {wrong}', ['index.html'], versions=wrong)
    if self.manifest['versionText'] not in index:
        self.add('high', 'INDEX_VERSION_TEXT_DRIFT', 'index.html static version text differs from the release manifest', ['index.html', 'release-manifest.json'])

    cache = self.manifest['cacheNamespace']
    sw = self.files.get('sw.js', '')
    if cache not in sw:
        self.add('critical', 'SW_CACHE_NAMESPACE_DRIFT', f'sw.js does not use {cache}', ['sw.js', 'release-manifest.json'])

    # Component-local VERSION constants are allowed. Only assignments that write
    # an ALPHA release string into the brand label are release owners.
    writer_patterns = [
        re.compile(r'(?:brand|label|e)\.textContent\s*=\s*[`"\']([^`"\']*ALPHA\s+(0\.\d+\.\d+\.\d+))', re.I),
        re.compile(r'querySelector\([`"\']\.brand-copy\s+small[`"\']\)[\s\S]{0,180}?textContent\s*=\s*[`"\']([^`"\']*ALPHA\s+(0\.\d+\.\d+\.\d+))', re.I),
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


def scoped_navigation_check(self: core.Reasoner) -> None:
    index = self.files.get('index.html', '')
    controls = self.files.get('atlas-controls-0938.js', '')
    ipad = self.files.get('atlas-ipad-nav-0940.js', '')

    nav_match = re.search(r'<nav\b[^>]*class=["\'][^"\']*\bbottom-nav\b[^"\']*["\'][^>]*>(.*?)</nav>', index, flags=re.I | re.S)
    if not nav_match:
        self.add('critical', 'BOTTOM_NAV_MISSING', 'Bottom navigation element is missing', ['index.html'])
    else:
        nav_html = nav_match.group(1)
        button_blocks = re.findall(r'<button\b[^>]*class=["\'][^"\']*\bnav-item\b[^"\']*["\'][^>]*>(.*?)</button>', nav_html, flags=re.I | re.S)
        if len(button_blocks) != 5:
            self.add('critical', 'BOTTOM_NAV_BUTTON_COUNT', f'Expected 5 bottom navigation buttons, found {len(button_blocks)}', ['index.html'], count=len(button_blocks))
        for index_number, button_html in enumerate(button_blocks, start=1):
            span_match = re.search(r'<span\b[^>]*>(.*?)</span>', button_html, flags=re.I | re.S)
            if not span_match:
                self.add('critical', 'BOTTOM_NAV_ICON_HOST_MISSING', f'Button {index_number} has no icon host', ['index.html'], button=index_number)
                continue
            text_only = re.sub(r'<[^>]+>', '', span_match.group(1)).strip()
            if text_only:
                self.add('critical', 'LEGACY_NAV_TEXT_ICON', f'Bottom navigation button {index_number} contains legacy text icon {text_only!r}', ['index.html'], button=index_number, text=text_only)

    if 'innerHTML=icons[' not in controls:
        self.add('high', 'CONTROL_ICON_REPLACER_MISSING', 'Controls layer does not install canonical SVG icons', ['atlas-controls-0938.js'])
    required_ipad_tokens = ['Node.TEXT_NODE', ':scope > svg.atlas-control-icon', 'indicator.animate']
    missing = [token for token in required_ipad_tokens if token not in ipad]
    if missing:
        self.add('critical', 'IPAD_NAV_INVARIANT_MISSING', f'iPad navigation cleanup/compositor tokens missing: {missing}', ['atlas-ipad-nav-0940.js'], missing=missing)


core.Reasoner.check_release_ownership = scoped_release_ownership
core.Reasoner.check_navigation_invariants = scoped_navigation_check

if __name__ == '__main__':
    sys.exit(core.main())
