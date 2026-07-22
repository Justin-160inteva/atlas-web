#!/usr/bin/env python3
"""Follow quest detail links and inspect page sections for explicit rewards.

This diagnostic consumes the first-level quest source report, follows only links whose
labels match the exact quest title, renders public pages through Jina Reader when useful,
and captures bounded sections. It never mutates reward records or evidence status.
"""
from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / 'data/rewards/reward-quest-source-diagnostic.json'
OUTPUT_PATH = ROOT / 'data/rewards/reward-quest-detail-diagnostic.json'

REWARD_TERM = re.compile(
    r'(?i)\b(reward|rewards|xp|experience|skill point|knowledge point|mastery point|gear|weapon|armor|armour|trinket|amulet|outfit|engraving|ryo|mon|material|rewarded)\b'
)
REWARD_HEADING = re.compile(r'(?im)^#{1,6}\s+.*(?:reward|rewards|奖励).*$')
MARKDOWN_HEADING = re.compile(r'(?m)^(#{1,6})\s+(.+?)\s*$')
SPACE = re.compile(r'\s+')


def load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def normalize_text(value: str) -> str:
    return html.unescape(value).replace('\r\n', '\n').replace('\r', '\n').replace('’', "'").replace('‘', "'")


def normalize_title(value: str) -> str:
    value = normalize_text(value).casefold()
    value = re.sub(r'[^a-z0-9]+', ' ', value)
    return SPACE.sub(' ', value).strip()


def equivalent_label(label: str, title: str) -> bool:
    left = normalize_title(label)
    right = normalize_title(title)
    return bool(left and right and (left == right or left.endswith(right) or right.endswith(left)))


def render_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.hostname == 'r.jina.ai':
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ''))
    scheme = 'http'
    path = parsed.path or '/'
    query = f'?{parsed.query}' if parsed.query else ''
    return f'https://r.jina.ai/{scheme}://{parsed.netloc}{path}{query}'


def fetch_text(url: str) -> tuple[str, str | None]:
    request = urllib.request.Request(url, headers={
        'User-Agent': 'AtlasRewardResearch/0.9.4.8 (+public evidence audit)',
        'Accept': 'text/plain,text/markdown,text/html;q=0.9,*/*;q=0.1',
    })
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
        return normalize_text(raw.decode('utf-8', errors='replace')), None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        return '', f'{type(exc).__name__}: {exc}'


def title_pattern(title: str) -> re.Pattern[str]:
    words = normalize_title(title).split()
    if not words:
        return re.compile(r'(?!x)x')
    return re.compile(r'(?i)' + r'[^A-Za-z0-9]{0,8}'.join(re.escape(word) for word in words))


def section_for_match(text: str, start: int, title: str) -> str:
    headings = list(MARKDOWN_HEADING.finditer(text))
    containing = None
    for heading in headings:
        if heading.start() <= start:
            containing = heading
        else:
            break
    if containing and equivalent_label(containing.group(2), title):
        level = len(containing.group(1))
        end = min(len(text), containing.start() + 8000)
        for heading in headings:
            if heading.start() <= containing.start():
                continue
            if len(heading.group(1)) <= level:
                end = heading.start()
                break
        return text[containing.start():end].strip()[:8000]
    left = max(0, start - 600)
    return text[left:min(len(text), start + 4200)].strip()


def reward_lines(section: str) -> list[str]:
    lines: list[str] = []
    raw_lines = section.splitlines()
    for index, raw in enumerate(raw_lines):
        line = SPACE.sub(' ', raw).strip()
        if not line:
            continue
        if REWARD_TERM.search(line):
            context = '\n'.join(raw_lines[max(0, index - 1):min(len(raw_lines), index + 4)]).strip()
            if context and context not in lines:
                lines.append(context[:1000])
    return lines[:12]


def main() -> int:
    first = load(INPUT_PATH, {})
    if first.get('targetCount') != 73:
        raise ValueError('Expected the 73-quest first-level diagnostic')

    quest_links: dict[str, list[dict[str, str]]] = {}
    for row in first.get('results', []):
        title = str(row.get('title') or '')
        links: list[dict[str, str]] = []
        for source in row.get('sourceMatches', []):
            for context in source.get('contexts', []):
                for link in context.get('nearbyLinks', []):
                    label = str(link.get('label') or '')
                    url = str(link.get('url') or '')
                    if not url or not equivalent_label(label, title):
                        continue
                    candidate = {
                        'label': label,
                        'url': url,
                        'sourceId': str(source.get('sourceId') or ''),
                    }
                    if candidate not in links:
                        links.append(candidate)
        quest_links[str(row.get('locationId'))] = links

    page_cache: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    for row in first.get('results', []):
        title = str(row.get('title') or '')
        details: list[dict[str, Any]] = []
        for link in quest_links.get(str(row.get('locationId')), []):
            original_url = link['url']
            rendered = render_url(original_url)
            cache_key = rendered
            if cache_key not in page_cache:
                text, error = fetch_text(rendered)
                page_cache[cache_key] = {
                    'renderedUrl': rendered,
                    'text': text,
                    'error': error,
                    'characterCount': len(text),
                }
            packet = page_cache[cache_key]
            pattern = title_pattern(title)
            matches = list(pattern.finditer(packet['text'])) if packet['text'] else []
            sections: list[dict[str, Any]] = []
            for match in matches[:3]:
                section = section_for_match(packet['text'], match.start(), title)
                terms = sorted({hit.group(0).lower() for hit in REWARD_TERM.finditer(section)})
                sections.append({
                    'matchStart': match.start(),
                    'rewardTerms': terms,
                    'hasRewardTerminology': bool(terms),
                    'rewardLikeContexts': reward_lines(section),
                    'section': section,
                })
            details.append({
                **link,
                'renderedUrl': packet['renderedUrl'],
                'fetched': not bool(packet['error']),
                'characterCount': packet['characterCount'],
                'error': packet['error'],
                'matchCount': len(matches),
                'sections': sections,
                'hasExplicitRewardContext': any(section['rewardLikeContexts'] for section in sections),
            })
        results.append({
            'locationId': row.get('locationId'),
            'sourceLocationId': row.get('sourceLocationId'),
            'title': title,
            'detailLinkCount': len(details),
            'details': details,
            'fetchedDetailCount': sum(detail['fetched'] for detail in details),
            'rewardContextDetailCount': sum(detail['hasExplicitRewardContext'] for detail in details),
        })

    payload = {
        'schemaVersion': 1,
        'release': '0.9.4.8',
        'generatedAt': now_iso(),
        'targetCount': len(results),
        'questWithDetailLinkCount': sum(row['detailLinkCount'] > 0 for row in results),
        'uniqueRenderedPageCount': len(page_cache),
        'successfullyFetchedPageCount': sum(not packet['error'] for packet in page_cache.values()),
        'questWithRewardContextCount': sum(row['rewardContextDetailCount'] > 0 for row in results),
        'results': results,
        'invariants': {
            'all73QuestTargetsInspected': len(results) == 73,
            'onlyExactTitleLinksFollowed': True,
            'noRewardRecordsModified': True,
            'noEvidenceStatusesModified': True,
            'boundedSections': all(len(section['section']) <= 8000 for row in results for detail in row['details'] for section in detail['sections']),
        },
    }
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({
        'targets': payload['targetCount'],
        'withLinks': payload['questWithDetailLinkCount'],
        'pages': payload['uniqueRenderedPageCount'],
        'fetched': payload['successfullyFetchedPageCount'],
        'withRewardContext': payload['questWithRewardContextCount'],
    }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
