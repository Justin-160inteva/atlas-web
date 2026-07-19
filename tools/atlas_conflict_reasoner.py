#!/usr/bin/env python3
"""Atlas Conflict Reasoner v1.

Builds a resource graph and detects release, ownership, fetch, DOM icon,
CSS cascade and service-worker conflicts. Uses only the Python standard library.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {'.html', '.js', '.css', '.json', '.webmanifest'}
SKIP_DIRS = {'.git', 'node_modules', '.venv', '__pycache__'}
VERSION_RE = re.compile(r'\b0\.\d+\.\d+\.\d+\b')
ALPHA_WRITE_RE = re.compile(r'(?:textContent|innerHTML)\s*=\s*[`\"\'][^`\"\']*ALPHA\s+(0\.\d+\.\d+\.\d+)', re.I)
HTML_ASSET_RE = re.compile(r'<(?:script|link)\b[^>]*(?:src|href)=[\"\']([^\"\']+)', re.I)
JS_ASSET_RE = re.compile(r'\.(?:src|href)\s*=\s*[`\"\']([^`\"\']+)', re.I)
CSS_IMPORT_RE = re.compile(r'@import\s+(?:url\()?\s*[\"\']([^\"\']+)', re.I)
FETCH_OVERRIDE_RE = re.compile(r'window\.fetch\s*=')
SW_REGISTER_RE = re.compile(r'(?:navigator\.)?serviceWorker\.register\s*\(')
CSS_BLOCK_RE = re.compile(r'([^{}]+)\{([^{}]*)\}', re.S)
CSS_DECL_RE = re.compile(r'([\w-]+)\s*:\s*([^;]+)')
CRITICAL_CSS_PROPS = {'content', 'background-image', 'mask-image', '-webkit-mask-image', 'backdrop-filter', '-webkit-backdrop-filter', 'transform', 'transition'}


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    files: list[str]
    evidence: dict


class Reasoner:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.manifest = json.loads((root / 'release-manifest.json').read_text(encoding='utf-8'))
        self.version = self.manifest['version']
        self.findings: list[Finding] = []
        self.files = self._load_files()
        self.graph: dict[str, list[str]] = defaultdict(list)

    def _load_files(self) -> dict[str, str]:
        files: dict[str, str] = {}
        for path in self.root.rglob('*'):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            rel = path.relative_to(self.root).as_posix()
            try:
                files[rel] = path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                continue
        return files

    def add(self, severity: str, code: str, message: str, files: Iterable[str] = (), **evidence) -> None:
        self.findings.append(Finding(severity, code, message, list(files), evidence))

    @staticmethod
    def normalize_asset(asset: str) -> str | None:
        value = asset.strip().replace('\\', '/')
        if not value or value.startswith(('http:', 'https:', 'data:', '#')):
            return None
        if '${' in value or value.startswith('javascript:'):
            return None
        value = value.split('#', 1)[0].split('?', 1)[0]
        while value.startswith('./'):
            value = value[2:]
        return value or 'index.html'

    def build_resource_graph(self) -> None:
        for name, text in self.files.items():
            matches: list[str] = []
            if name.endswith('.html'):
                matches += HTML_ASSET_RE.findall(text)
            if name.endswith('.js'):
                matches += JS_ASSET_RE.findall(text)
            if name.endswith('.css'):
                matches += CSS_IMPORT_RE.findall(text)
            for raw in matches:
                asset = self.normalize_asset(raw)
                if asset:
                    self.graph[name].append(asset)
                    if asset not in self.files and not (self.root / asset).exists():
                        self.add('critical', 'RESOURCE_MISSING', f'{name} references missing resource {asset}', [name, asset], raw=raw)

        index_assets = self.graph.get('index.html', [])
        duplicates = sorted({asset for asset in index_assets if index_assets.count(asset) > 1})
        for asset in duplicates:
            self.add('high', 'RESOURCE_DUPLICATE_LOAD', f'index.html loads {asset} more than once', ['index.html', asset])

        # Service-worker asset list must contain release-critical files.
        sw = self.files.get(self.manifest.get('serviceWorker', 'sw.js'), '')
        for asset in self.manifest.get('releaseAssets', []):
            if asset not in sw:
                self.add('critical', 'SW_RELEASE_ASSET_MISSING', f'Service worker does not include release asset {asset}', ['sw.js', asset])

    def check_release_ownership(self) -> None:
        owner = self.manifest['releaseOwner']
        owner_text = self.files.get(owner, '')
        if self.version not in owner_text:
            self.add('critical', 'RELEASE_OWNER_VERSION_MISSING', f'{owner} does not contain manifest version {self.version}', [owner, 'release-manifest.json'])
        if self.manifest['versionText'] not in owner_text:
            self.add('critical', 'RELEASE_OWNER_TEXT_MISSING', f'{owner} does not contain canonical version text', [owner, 'release-manifest.json'])

        index = self.files.get('index.html', '')
        query_versions = re.findall(r'[?&]v=(0\.\d+\.\d+\.\d+)', index)
        wrong = sorted({v for v in query_versions if v != self.version})
        if wrong:
            self.add('critical', 'INDEX_VERSION_DRIFT', f'index.html contains non-release cache versions: {wrong}', ['index.html'], versions=wrong)
        if self.manifest['versionText'] not in index:
            self.add('high', 'INDEX_VERSION_TEXT_DRIFT', 'index.html static version text differs from the release manifest', ['index.html', 'release-manifest.json'])

        cache = self.manifest['cacheNamespace']
        sw = self.files.get('sw.js', '')
        if cache not in sw:
            self.add('critical', 'SW_CACHE_NAMESPACE_DRIFT', f'sw.js does not use {cache}', ['sw.js', 'release-manifest.json'])

        version_writers: list[tuple[str, str]] = []
        for name, text in self.files.items():
            if not name.endswith(('.js', '.html')):
                continue
            for match in ALPHA_WRITE_RE.finditer(text):
                version_writers.append((name, match.group(1)))
        for name, version in version_writers:
            if name not in {owner, 'index.html'}:
                self.add('critical', 'VERSION_OWNER_CONFLICT', f'{name} writes release label {version}; only {owner} may own it', [name, owner], version=version)
            elif version != self.version:
                self.add('critical', 'VERSION_LITERAL_DRIFT', f'{name} writes {version}, expected {self.version}', [name, 'release-manifest.json'])

    def check_global_ownership(self) -> None:
        fetch_writers = [name for name, text in self.files.items() if name.endswith('.js') and FETCH_OVERRIDE_RE.search(text)]
        allowed_fetch_owner = self.manifest['runtimeOwners']['locationDataRecovery']
        unexpected = [name for name in fetch_writers if name != allowed_fetch_owner]
        if unexpected:
            self.add('critical', 'FETCH_OWNER_CONFLICT', f'Multiple or unexpected window.fetch owners: {fetch_writers}', fetch_writers, allowed=allowed_fetch_owner)
        if allowed_fetch_owner not in fetch_writers:
            self.add('high', 'FETCH_OWNER_MISSING', f'Expected fetch owner {allowed_fetch_owner} was not detected', [allowed_fetch_owner])

        register_writers = [name for name, text in self.files.items() if name.endswith('.js') and SW_REGISTER_RE.search(text)]
        sw_owner = self.manifest['runtimeOwners']['serviceWorkerRegistration']
        delegated = 'installRegistrationDelegate' in self.files.get(sw_owner, '')
        for name in register_writers:
            if name == sw_owner:
                continue
            severity = 'warning' if delegated and name == 'app.js' else 'high'
            self.add(severity, 'SW_REGISTRATION_DELEGATED' if severity == 'warning' else 'SW_OWNER_CONFLICT',
                     f'{name} calls serviceWorker.register; canonical owner is {sw_owner}', [name, sw_owner], delegated=delegated)

    def check_navigation_invariants(self) -> None:
        index = self.files.get('index.html', '')
        controls = self.files.get('atlas-controls-0938.js', '')
        ipad = self.files.get('atlas-ipad-nav-0940.js', '')
        if re.search(r'<nav class="bottom-nav[\s\S]*?<span>[^<]+</span>', index):
            self.add('critical', 'LEGACY_NAV_TEXT_ICON', 'Bottom navigation still contains legacy text icons', ['index.html'])
        if 'innerHTML=icons[' not in controls:
            self.add('high', 'CONTROL_ICON_REPLACER_MISSING', 'Controls layer does not install canonical SVG icons', ['atlas-controls-0938.js'])
        required_ipad_tokens = ['Node.TEXT_NODE', ':scope > svg.atlas-control-icon', 'indicator.animate']
        missing = [token for token in required_ipad_tokens if token not in ipad]
        if missing:
            self.add('critical', 'IPAD_NAV_INVARIANT_MISSING', f'iPad navigation cleanup/compositor tokens missing: {missing}', ['atlas-ipad-nav-0940.js'], missing=missing)

    def check_css_conflicts(self) -> None:
        declarations: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
        for name, text in self.files.items():
            if not name.endswith('.css'):
                continue
            stripped = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
            for selector_text, body in CSS_BLOCK_RE.findall(stripped):
                selectors = [s.strip() for s in selector_text.split(',') if s.strip() and not s.strip().startswith('@')]
                for prop, value in CSS_DECL_RE.findall(body):
                    prop = prop.strip().lower()
                    if prop not in CRITICAL_CSS_PROPS:
                        continue
                    for selector in selectors:
                        declarations[(selector, prop)].append((name, value.strip()))
        for (selector, prop), entries in declarations.items():
            values = {value for _, value in entries}
            files = sorted({name for name, _ in entries})
            if len(values) > 1 and len(files) > 1:
                severity = 'high' if '::before' in selector or '::after' in selector or prop in {'content', 'mask-image', '-webkit-mask-image'} else 'warning'
                self.add(severity, 'CSS_CASCADE_CONFLICT', f'{selector} has conflicting {prop} values across {files}', files, selector=selector, property=prop, values=sorted(values))

    def check_data_pipeline(self) -> None:
        guard = self.files.get('atlas-data-guard-0939.js', '')
        names = self.files.get('location-names.js', '')
        polish = self.files.get('location-title-polish.js', '')
        minimum = str(self.manifest['invariants']['minimumLocationCount'])
        if minimum not in guard:
            self.add('critical', 'LOCATION_THRESHOLD_MISSING', f'Data guard does not enforce minimum location count {minimum}', ['atlas-data-guard-0939.js'])
        if 'AtlasDataTransforms' not in guard or 'AtlasDataTransforms' not in names or 'AtlasDataTransforms' not in polish:
            self.add('critical', 'DATA_TRANSFORM_PIPELINE_MISSING', 'Location transforms are not registered through the single data pipeline', ['atlas-data-guard-0939.js', 'location-names.js', 'location-title-polish.js'])

    def run(self) -> dict:
        self.build_resource_graph()
        self.check_release_ownership()
        self.check_global_ownership()
        self.check_navigation_invariants()
        self.check_css_conflicts()
        self.check_data_pipeline()
        weights = {'critical': 25, 'high': 12, 'warning': 4, 'info': 1}
        score = min(100, sum(weights.get(item.severity, 1) for item in self.findings))
        blockers = [item for item in self.findings if item.severity == 'critical']
        status = 'blocked' if blockers else ('review' if score >= 20 else 'pass')
        return {
            'schemaVersion': 1,
            'generatedAt': datetime.now(timezone.utc).isoformat(),
            'release': self.version,
            'status': status,
            'riskScore': score,
            'summary': {
                'critical': sum(f.severity == 'critical' for f in self.findings),
                'high': sum(f.severity == 'high' for f in self.findings),
                'warning': sum(f.severity == 'warning' for f in self.findings),
                'total': len(self.findings)
            },
            'resourceGraph': dict(sorted(self.graph.items())),
            'findings': [asdict(item) for item in self.findings]
        }


def markdown(report: dict) -> str:
    lines = [
        '# Atlas Conflict Report', '',
        f"- Release: **{report['release']}**",
        f"- Status: **{report['status']}**",
        f"- Risk score: **{report['riskScore']}/100**",
        f"- Findings: {report['summary']['total']} ({report['summary']['critical']} critical, {report['summary']['high']} high, {report['summary']['warning']} warning)", ''
    ]
    if not report['findings']:
        lines.append('No conflicts detected.')
    for item in report['findings']:
        lines += [f"## {item['severity'].upper()} · {item['code']}", '', item['message'], '']
        if item['files']:
            lines.append('Files: ' + ', '.join(f'`{name}`' for name in item['files']))
            lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', default='data/conflict-reports/latest.json')
    parser.add_argument('--markdown', default='CONFLICT-REPORT.md')
    parser.add_argument('--report-only', action='store_true')
    args = parser.parse_args()
    report = Reasoner(ROOT).run()
    json_path = ROOT / args.json
    md_path = ROOT / args.markdown
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    md_path.write_text(markdown(report), encoding='utf-8')
    print(json.dumps(report['summary'], ensure_ascii=False), f"status={report['status']} score={report['riskScore']}")
    if report['status'] == 'blocked' and not args.report_only:
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
