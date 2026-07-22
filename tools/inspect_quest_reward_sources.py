#!/usr/bin/env python3
"""Inspect public quest guides for point-specific reward evidence.

This diagnostic never changes reward records. It fetches registered public sources,
locates every unresolved quest title, captures a bounded nearby excerpt, extracts nearby
links, and marks whether reward terminology appears in the same context.
"""
from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / 'data/rewards/reward-evidence-phase2-plan.json'
SOURCES_PATH = ROOT / 'data/rewards/reward-quest-research-sources.json'
OUTPUT_PATH = ROOT / 'data/rewards/reward-quest-source-diagnostic.json'

LINK = re.compile(r'\[([^\]]+)\]\((https?://[^)]+)\)')
REWARD_TERM = re.compile(
    r'(?i)\b(reward|rewards|xp|experience|skill point|knowledge point|mastery point|gear|weapon|armor|armour|trinket|amulet|outfit|engraving|ryo|mon|material)\b'
)
SPACE = re.compile(r'[ \t]+')


def load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def fetch_text(url: str) -> tuple[str, str | None]:
    request = urllib.request.Request(url, headers={
        'User-Agent': 'AtlasRewardResearch/0.9.4.8 (+public evidence audit)',
        'Accept': 'text/plain,text/markdown,text/html;q=0.9,*/*;q=0.1',
    })
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read()
        return raw.decode('utf-8', errors='replace'), None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        return '', f'{type(exc).__name__}: {exc}'


def normalize(value: str) -> str:
    value = html.unescape(value).replace('\r\n', '\n').replace('\r', '\n')
    value = value.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    return value


def normalized_title(value: str) -> str:
    value = normalize(value).casefold()
    value = re.sub(r'[^a-z0-9]+', ' ', value)
    return SPACE.sub(' ', value).strip()


def title_pattern(title: str) -> re.Pattern[str]:
    words = normalized_title(title).split()
    if not words:
        return re.compile(r'(?!x)x')
    return re.compile(r'(?i)' + r'[^A-Za-z0-9]{0,8}'.join(re.escape(word) for word in words))


def bounded_excerpt(text: str, start: int, end: int, radius: int = 900) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    excerpt = text[left:right].strip()
    return excerpt[:2400]


def inspect_source(text: str, quest_title: str) -> dict[str, Any]:
    pattern = title_pattern(quest_title)
    matches = list(pattern.finditer(text))
    contexts: list[dict[str, Any]] = []
    for match in matches[:3]:
        excerpt = bounded_excerpt(text, match.start(), match.end())
        reward_terms = sorted({term.group(0).lower() for term in REWARD_TERM.finditer(excerpt)})
        links = []
        for label, url in LINK.findall(excerpt):
            row = {'label': SPACE.sub(' ', label).strip()[:160], 'url': url}
            if row not in links:
                links.append(row)
        contexts.append({
            'matchStart': match.start(),
            'rewardTerms': reward_terms,
            'hasRewardTerminology': bool(reward_terms),
            'nearbyLinks': links[:12],
            'excerpt': excerpt,
        })
    return {
        'matchCount': len(matches),
        'contexts': contexts,
        'hasAnyRewardContext': any(row['hasRewardTerminology'] for row in contexts),
    }


def main() -> int:
    plan = load(PLAN_PATH, {})
    registry = load(SOURCES_PATH, {'sources': []})
    quest_targets = [
        item for item in plan.get('allCandidates', [])
        if item.get('categoryId') == 'category-12341-quest'
    ]
    if len(quest_targets) != 73:
        raise ValueError(f'Expected 73 unresolved quest targets, found {len(quest_targets)}')

    fetched: dict[str, dict[str, Any]] = {}
    for source in registry.get('sources', []):
        text, error = fetch_text(str(source.get('locator') or ''))
        text = normalize(text)
        fetched[source['sourceId']] = {
            'source': source,
            'text': text,
            'error': error,
            'characterCount': len(text),
        }

    results: list[dict[str, Any]] = []
    for target in quest_targets:
        source_matches: list[dict[str, Any]] = []
        for source_id, packet in fetched.items():
            inspection = inspect_source(packet['text'], str(target.get('title') or '')) if packet['text'] else {
                'matchCount': 0,
                'contexts': [],
                'hasAnyRewardContext': False,
            }
            source_matches.append({
                'sourceId': source_id,
                'canonicalLocator': packet['source'].get('canonicalLocator') or packet['source'].get('locator'),
                **inspection,
            })
        results.append({
            'locationId': target.get('locationId'),
            'sourceLocationId': target.get('sourceLocationId'),
            'title': target.get('title'),
            'regionId': target.get('regionId'),
            'sourceMatches': source_matches,
            'matchedSourceCount': sum(row['matchCount'] > 0 for row in source_matches),
            'rewardContextSourceCount': sum(row['hasAnyRewardContext'] for row in source_matches),
        })

    payload = {
        'schemaVersion': 1,
        'release': '0.9.4.8',
        'generatedAt': now_iso(),
        'targetCount': len(results),
        'sources': [{
            'sourceId': source_id,
            'title': packet['source'].get('title'),
            'locator': packet['source'].get('locator'),
            'canonicalLocator': packet['source'].get('canonicalLocator'),
            'fetched': not bool(packet['error']),
            'characterCount': packet['characterCount'],
            'error': packet['error'],
        } for source_id, packet in fetched.items()],
        'matchedQuestCount': sum(row['matchedSourceCount'] > 0 for row in results),
        'rewardContextQuestCount': sum(row['rewardContextSourceCount'] > 0 for row in results),
        'unmatchedQuestCount': sum(row['matchedSourceCount'] == 0 for row in results),
        'results': results,
        'invariants': {
            'all73QuestTargetsInspected': len(results) == 73,
            'noRewardRecordsModified': True,
            'noEvidenceStatusesModified': True,
            'boundedContexts': all(len(context['excerpt']) <= 2400 for row in results for source in row['sourceMatches'] for context in source['contexts']),
        },
    }
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({
        'targets': payload['targetCount'],
        'matched': payload['matchedQuestCount'],
        'rewardContext': payload['rewardContextQuestCount'],
        'unmatched': payload['unmatchedQuestCount'],
    }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
