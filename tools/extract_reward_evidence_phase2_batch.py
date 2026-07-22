#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'data/rewards/reward-evidence-phase2-plan.json'
LOCATIONS = ROOT / 'data/locations.json'
CATALOG = ROOT / 'data/rewards/reward-summary-catalog.json'
OUTPUT = ROOT / 'data/rewards/reward-evidence-phase2-batch-001-input.json'

REWARD_LINE = re.compile(r'(?im)^.{0,80}(?:reward|rewards|奖励).{0,260}$')
HTML_TAG = re.compile(r'<[^>]+>')


def load(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def clean_text(value: Any) -> str:
    text = str(value or '').replace('\r\n', '\n').replace('\r', '\n')
    text = HTML_TAG.sub(' ', text)
    return re.sub(r'[ \t]+', ' ', text).strip()


def main() -> int:
    plan = load(PLAN, {})
    locations = load(LOCATIONS, [])
    catalog = load(CATALOG, {})
    by_id = {str(item.get('id')): item for item in locations if isinstance(item, dict) and item.get('id')}
    records = catalog.get('records', {})
    items = []
    for target in plan.get('nextBatch', []):
        location_id = str(target.get('locationId'))
        location = by_id.get(location_id, {})
        record = records.get(location_id, {})
        description = clean_text(location.get('description'))
        reward_lines = [line.strip() for line in REWARD_LINE.findall(description)]
        items.append({
            **target,
            'description': description,
            'rewardLikeLines': reward_lines,
            'locationSource': location.get('source'),
            'currentRecord': {
                'status': record.get('status'),
                'summaryZhCN': record.get('summaryZhCN'),
                'rewards': record.get('rewards', []),
                'evidence': record.get('evidence', []),
                'confidence': record.get('confidence'),
            },
        })
    payload = {
        'schemaVersion': 1,
        'release': '0.9.4.8',
        'generatedAt': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'batchId': 'reward-evidence-phase2-batch-001',
        'targetCount': len(items),
        'itemsWithDescription': sum(bool(item['description']) for item in items),
        'itemsWithRewardLikeLines': sum(bool(item['rewardLikeLines']) for item in items),
        'items': items,
        'invariants': {
            'maximumBatchSizeRespected': len(items) <= 100,
            'noCatalogMutation': True,
            'sourceLocationIdsPreserved': all(item.get('sourceLocationId') is not None for item in items),
        },
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({
        'targets': len(items),
        'descriptions': payload['itemsWithDescription'],
        'rewardLikeLines': payload['itemsWithRewardLikeLines'],
    }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
