#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'data/rewards/reward-evidence-phase2-plan.json'
OUTPUT = ROOT / 'data/rewards/reward-evidence-phase2-summary.json'


def main() -> int:
    plan = json.loads(PLAN.read_text(encoding='utf-8'))
    summary = {
        'schemaVersion': 1,
        'release': plan.get('release'),
        'generatedAt': plan.get('generatedAt'),
        'targetLocationCount': plan.get('targetLocationCount'),
        'unresolvedCount': plan.get('unresolvedCount'),
        'resolvedOrInferredCount': plan.get('resolvedOrInferredCount'),
        'unresolvedWithDescription': plan.get('unresolvedWithDescription'),
        'unresolvedWithSourceLocationId': plan.get('unresolvedWithSourceLocationId'),
        'categoryCount': plan.get('categoryCount'),
        'regionCount': plan.get('regionCount'),
        'strategyCounts': plan.get('strategyCounts'),
        'topCategories': (plan.get('topCategories') or [])[:20],
        'topRegions': (plan.get('topRegions') or [])[:15],
        'registeredSources': plan.get('registeredSources'),
        'nextBatchSize': plan.get('nextBatchSize'),
        'nextTargets': (plan.get('nextBatch') or [])[:20],
        'researchPolicyZhCN': plan.get('researchPolicyZhCN'),
        'invariants': plan.get('invariants'),
    }
    OUTPUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'unresolved': summary['unresolvedCount'], 'nextTargets': len(summary['nextTargets'])}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
