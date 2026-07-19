#!/usr/bin/env python3
"""Canonical runner for Atlas Conflict Reasoner.

Keeps the core reasoning engine reusable while applying DOM-scoped checks that
must not use cross-element regular expressions.
"""
from __future__ import annotations

import re
import sys

import atlas_conflict_reasoner as core


def scoped_navigation_check(self: core.Reasoner) -> None:
    index = self.files.get('index.html', '')
    controls = self.files.get('atlas-controls-0938.js', '')
    ipad = self.files.get('atlas-ipad-nav-0940.js', '')

    nav_match = re.search(
        r'<nav\b[^>]*class=["\'][^"\']*\bbottom-nav\b[^"\']*["\'][^>]*>(.*?)</nav>',
        index,
        flags=re.I | re.S,
    )
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


core.Reasoner.check_navigation_invariants = scoped_navigation_check

if __name__ == '__main__':
    sys.exit(core.main())
