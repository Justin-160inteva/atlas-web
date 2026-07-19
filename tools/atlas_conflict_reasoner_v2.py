#!/usr/bin/env python3
"""Atlas Conflict Reasoner v2.

Builds a release/resource/ownership graph and blocks only contradictions that can
change runtime behaviour. Expected responsive CSS overrides are reported but do
not become false release blockers.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {'.html', '.js', '.css', '.json', '.webmanifest'}
SKIP_DIRS = {'.git', 'node_modules', '.venv', '__pycache__'}
HTML_ASSET_RE = re.compile(r'<(?:script|link)\b[^>]*(?:src|href)=["\']([^"\']+)', re.I)
JS_ASSET_RE = re.compile(r'\.(?:src|href)\s*=\s*[`"\']([^`"\']+)', re.I)
CSS_IMPORT_RE = re.compile(r'@import\s+(?:url\()?\s*["\']([^"\']+)', re.I)
FETCH_OVERRIDE_RE = re.compile(r'window\.fetch\s*=')
SW_REGISTER_RE = re.compile(r'(?:navigator\.)?serviceWorker\.register\s*\(')
ALPHA_LITERAL_RE = re.compile(r'ALPHA\s+(0\.\d+\.\d+\.\d+)', re.I)
CSS_BLOCK_RE = re.compile(r'([^{}]+)\{([^{}]*)\}', re.S)
CSS_DECL_RE = re.compile(r'([\w-]+)\s*:\s*([^;]+)')


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
        self.files = self._load_files()
        self.findings: list[Finding] = []
        self.graph: dict[str, list[str]] = defaultdict(list)

    def _load_files(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for path in self.root.rglob('*'):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            try:
                result[path.relative_to(self.root).as_posix()] = path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                continue
        return result

    def add(self, severity: str, code: str, message: str, files: Iterable[str] = (), **evidence) -> None:
        self.findings.append(Finding(severity, code, message, list(files), evidence))

    @staticmethod
    def normalize_asset(raw: str) -> str | None:
        value = raw.strip().replace('\\', '/')
        if not value or value.startswith(('http:', 'https:', 'data:', '#', 'javascript:')) or '${' in value:
            return None
        value = value.split('#', 1)[0].split('?', 1)[0]
        while value.startswith('./'):
            value = value[2:]
        return value or 'index.html'

    def build_resource_graph(self) -> None:
        for name, text in self.files.items():
            candidates: list[str] = []
            if name.endswith('.html'):
                candidates.extend(HTML_ASSET_RE.findall(text))
            if name.endswith('.js'):
                candidates.extend(JS_ASSET_RE.findall(text))
            if name.endswith('.css'):
                candidates.extend(CSS_IMPORT_RE.findall(text))
            for raw in candidates:
                asset = self.normalize_asset(raw)
                if not asset:
                    continue
                self.graph[name].append(asset)
                if asset not in self.files and not (self.root / asset).exists():
                    self.add('critical', 'RESOURCE_MISSING', f'{name} references missing resource {asset}', [name, asset], raw=raw)

        index_assets = self.graph.get('index.html', [])
        for asset in sorted({asset for asset in index_assets if index_assets.count(asset) > 1}):
            self.add('high', 'RESOURCE_DUPLICATE_LOAD', f'index.html loads {asset} multiple times', ['index.html', asset])

        sw = self.files.get(self.manifest.get('serviceWorker', 'sw.js'), '')
        for asset in self.manifest.get('releaseAssets', []):
            if asset not in sw:
                self.add('critical', 'SW_RELEASE_ASSET_MISSING', f'Service worker omits release asset {asset}', ['sw.js', asset])

    def check_release(self) -> None:
        owner = self.manifest['releaseOwner']
        owner_text = self.files.get(owner, '')
        index = self.files.get('index.html', '')
        sw = self.files.get(self.manifest.get('serviceWorker', 'sw.js'), '')

        if self.version not in owner_text or self.manifest['versionText'] not in owner_text:
            self.add('critical', 'RELEASE_OWNER_DRIFT', f'{owner} is not synchronized with release-manifest.json', [owner, 'release-manifest.json'])
        if self.manifest['versionText'] not in index:
            self.add('critical', 'INDEX_VERSION_TEXT_DRIFT', 'index.html does not contain the canonical version text', ['index.html', 'release-manifest.json'])
        wrong_queries = sorted({v for v in re.findall(r'[?&]v=(0\.\d+\.\d+\.\d+)', index) if v != self.version})
        if wrong_queries:
            self.add('critical', 'INDEX_VERSION_DRIFT', f'index.html contains cache versions {wrong_queries}', ['index.html'], versions=wrong_queries)
        if self.manifest['cacheNamespace'] not in sw:
            self.add('critical', 'SW_CACHE_NAMESPACE_DRIFT', 'Service-worker cache namespace differs from the manifest', ['sw.js', 'release-manifest.json'])

        for name, text in self.files.items():
            if name in {owner, 'index.html', 'release-manifest.json'} or not name.endswith(('.js', '.html')):
                continue
            versions = sorted(set(ALPHA_LITERAL_RE.findall(text)))
            if versions:
                self.add('critical', 'VERSION_OWNER_CONFLICT', f'{name} contains release-label literals {versions}; only {owner} may own the label', [name, owner], versions=versions)

    def check_ownership(self) -> None:
        fetch_writers = sorted(name for name, text in self.files.items() if name.endswith('.js') and FETCH_OVERRIDE_RE.search(text))
        allowed_fetch = self.manifest['runtimeOwners']['locationDataRecovery']
        if fetch_writers != [allowed_fetch]:
            self.add('critical', 'FETCH_OWNER_CONFLICT', f'Expected only {allowed_fetch} to override window.fetch, found {fetch_writers}', fetch_writers or [allowed_fetch])

        sw_writers = sorted(name for name, text in self.files.items() if name.endswith('.js') and SW_REGISTER_RE.search(text))
        sw_owner = self.manifest['runtimeOwners']['serviceWorkerRegistration']
        delegate = 'installRegistrationDelegate' in self.files.get(sw_owner, '')
        unexpected = [name for name in sw_writers if name != sw_owner]
        for name in unexpected:
            if delegate and name == 'app.js':
                self.add('warning', 'SW_REGISTRATION_DELEGATED', 'Legacy app registration is intercepted by the canonical bootstrap owner', [name, sw_owner])
            else:
                self.add('critical', 'SW_OWNER_CONFLICT', f'{name} registers a service worker outside the canonical owner', [name, sw_owner])

    def check_data_pipeline(self) -> None:
        index = self.files.get('index.html', '')
        ordered = ['atlas-i18n.js', 'location-names.js', 'location-title-polish.js', 'atlas-data-guard-0939.js', 'app.js']
        positions = [index.find(name) for name in ordered]
        if any(position < 0 for position in positions) or positions != sorted(positions):
            self.add('critical', 'DATA_PIPELINE_ORDER', f'Data pipeline must load in order: {ordered}', ['index.html'], positions=positions)

        guard = self.files.get('atlas-data-guard-0939.js', '')
        for transform_file in ['atlas-i18n.js', 'location-names.js', 'location-title-polish.js']:
            text = self.files.get(transform_file, '')
            if 'AtlasDataTransforms' not in text or 'atlasPaths' not in text:
                self.add('critical', 'DATA_TRANSFORM_REGISTRATION', f'{transform_file} is not path-scoped in the shared transform pipeline', [transform_file, 'atlas-data-guard-0939.js'])
        if 'AtlasDataTransforms' not in guard or str(self.manifest['invariants']['minimumLocationCount']) not in guard:
            self.add('critical', 'DATA_GUARD_INCOMPLETE', 'Shared data guard lacks transform or minimum-count enforcement', ['atlas-data-guard-0939.js'])

    def check_navigation(self) -> None:
        index = self.files.get('index.html', '')
        match = re.search(r'<nav\b[^>]*class=["\'][^"\']*\bbottom-nav\b[^"\']*["\'][^>]*>(.*?)</nav>', index, re.I | re.S)
        if not match:
            self.add('critical', 'BOTTOM_NAV_MISSING', 'Bottom navigation block is missing', ['index.html'])
        else:
            nav = match.group(1)
            legacy = re.findall(r'<button\b[^>]*>\s*<span>\s*([^<\s][^<]*)</span>', nav, re.I | re.S)
            if legacy:
                self.add('critical', 'LEGACY_NAV_TEXT_ICON', f'Bottom navigation contains legacy text icons: {legacy}', ['index.html'])

        controls = self.files.get('atlas-controls-0938.js', '')
        ipad = self.files.get('atlas-ipad-nav-0940.js', '')
        for token in ['bottom-nav .nav-item', 'quick-rail .rail-button', 'viewBox="0 0 24 24"']:
            if token not in controls:
                self.add('critical', 'CONTROL_ICON_RUNTIME_MISSING', f'Controls runtime lacks {token}', ['atlas-controls-0938.js'])
        for token in ['Node.TEXT_NODE', ':scope > svg.atlas-control-icon', 'indicator.animate']:
            if token not in ipad:
                self.add('critical', 'IPAD_NAV_INVARIANT_MISSING', f'iPad navigation runtime lacks {token}', ['atlas-ipad-nav-0940.js'])

    def check_css(self) -> None:
        declarations: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
        watched = {'content', 'background-image', 'mask-image', '-webkit-mask-image', 'backdrop-filter', '-webkit-backdrop-filter', 'transform', 'transition'}
        for name, text in self.files.items():
            if not name.endswith('.css'):
                continue
            stripped = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
            for selector_text, body in CSS_BLOCK_RE.findall(stripped):
                selectors = [part.strip() for part in selector_text.split(',') if part.strip() and not part.strip().startswith('@')]
                for prop, value in CSS_DECL_RE.findall(body):
                    prop = prop.strip().lower()
                    if prop not in watched:
                        continue
                    for selector in selectors:
                        declarations[(selector, prop)].append((name, value.strip()))
        for (selector, prop), entries in declarations.items():
            values = sorted({value for _, value in entries})
            files = sorted({name for name, _ in entries})
            if len(values) <= 1 or len(files) <= 1:
                continue
            pseudo_icon = ('::before' in selector or '::after' in selector) and prop in {'content', 'background-image', 'mask-image', '-webkit-mask-image'}
            severity = 'high' if pseudo_icon else 'warning'
            self.add(severity, 'CSS_CASCADE_CONFLICT', f'{selector} has multiple {prop} definitions', files, selector=selector, property=prop, values=values)

    def run(self) -> dict:
        self.build_resource_graph()
        self.check_release()
        self.check_ownership()
        self.check_data_pipeline()
        self.check_navigation()
        self.check_css()
        weights = {'critical': 25, 'high': 8, 'warning': 2, 'info': 1}
        score = min(100, sum(weights.get(finding.severity, 1) for finding in self.findings))
        critical = sum(finding.severity == 'critical' for finding in self.findings)
        status = 'blocked' if critical else ('review' if any(f.severity == 'high' for f in self.findings) else 'pass')
        return {
            'schemaVersion': 2,
            'generatedAt': datetime.now(timezone.utc).isoformat(),
            'release': self.version,
            'status': status,
            'riskScore': score,
            'summary': {
                'critical': critical,
                'high': sum(f.severity == 'high' for f in self.findings),
                'warning': sum(f.severity == 'warning' for f in self.findings),
                'total': len(self.findings)
            },
            'resourceGraph': dict(sorted(self.graph.items())),
            'findings': [asdict(finding) for finding in self.findings]
        }


def render_markdown(report: dict) -> str:
    lines = [
        '# Atlas Conflict Report', '',
        f"- Release: **{report['release']}**",
        f"- Status: **{report['status']}**",
        f"- Risk score: **{report['riskScore']}/100**",
        f"- Findings: {report['summary']['total']} ({report['summary']['critical']} critical, {report['summary']['high']} high, {report['summary']['warning']} warning)", ''
    ]
    if not report['findings']:
        lines.append('No conflicts detected.')
    for finding in report['findings']:
        lines.extend([f"## {finding['severity'].upper()} · {finding['code']}", '', finding['message'], ''])
        if finding['files']:
            lines.extend(['Files: ' + ', '.join(f"`{name}`" for name in finding['files']), ''])
    return '\n'.join(lines).rstrip() + '\n'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', default='data/conflict-reports/latest.json')
    parser.add_argument('--markdown', default='CONFLICT-REPORT.md')
    parser.add_argument('--report-only', action='store_true')
    args = parser.parse_args()
    report = Reasoner(ROOT).run()
    json_path = ROOT / args.json
    markdown_path = ROOT / args.markdown
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    markdown_path.write_text(render_markdown(report), encoding='utf-8')
    print(json.dumps(report['summary'], ensure_ascii=False), f"status={report['status']} score={report['riskScore']}")
    if report['status'] == 'blocked' and not args.report_only:
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
