#!/usr/bin/env python3
"""Write a compact validation report for parsed Legendary Chest rewards."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'data/rewards/reward-summary-catalog.json'
AUDIT = ROOT / 'data/rewards/reward-source-audit.json'
STATE = ROOT / 'data/rewards/reward-translation-research-state.json'
EVIDENCE = ROOT / 'data/rewards/reward-translation-evidence.json'
OUTPUT = ROOT / 'data/rewards/reward-legendary-chest-validation-report.json'
CJK = re.compile(r'[\u3400-\u9fff]')

EXPECTED = {
    'location-mapgenie-438759': 'Scale of the Koi',
    'location-mapgenie-437354': 'Armor of the Legendary Samurai',
    'location-mapgenie-434597': 'Tools Master Mask',
    'location-mapgenie-438443': 'Lengthened Horizon',
    'location-mapgenie-438314': "Yukimitsu's Revenge",
    'location-mapgenie-438765': 'Armor Eater',
    'location-mapgenie-435068': 'Demon Tooth',
}


def load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def reward_errors(reward: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    original = str(reward.get('nameOriginal') or '')
    chinese = str(reward.get('nameZhCN') or '')
    if not original:
        errors.append('missing_original')
    if original.startswith('??'):
        errors.append('placeholder_original')
    if not CJK.search(chinese):
        errors.append('missing_chinese')
    if '具体名称待核对' in chinese:
        errors.append('untranslated_placeholder')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--validate', action='store_true')
    args = parser.parse_args()

    catalog = load(CATALOG, {})
    audit = load(AUDIT, {})
    state = load(STATE, {})
    translation_evidence = load(EVIDENCE, {})
    records = catalog.get('records', {})

    sample_results: list[dict[str, Any]] = []
    for location_id, expected_original in EXPECTED.items():
        record = records.get(location_id, {})
        matching = next(
            (reward for reward in record.get('rewards', []) if reward.get('nameOriginal') == expected_original),
            None,
        )
        errors: list[str] = []
        if record.get('status') not in {'high_confidence_inference', 'multi_source_confirmed'}:
            errors.append('record_not_resolved')
        if not matching:
            errors.append('expected_reward_missing')
        else:
            errors.extend(reward_errors(matching))
            if matching.get('rarity') != 'legendary':
                errors.append('rarity_not_legendary')
        if not record.get('evidence'):
            errors.append('missing_evidence')
        sample_results.append({
            'locationId': location_id,
            'expectedOriginal': expected_original,
            'recordStatus': record.get('status'),
            'summaryZhCN': record.get('summaryZhCN'),
            'evidenceCount': len(record.get('evidence', [])),
            'matchingReward': matching,
            'errors': errors,
        })

    parsed_chests: list[dict[str, Any]] = []
    invalid_rewards: list[dict[str, Any]] = []
    for record in records.values() if isinstance(records, dict) else []:
        if record.get('categoryId') != 'category-12342-legendary-chest' or not record.get('rewards'):
            continue
        parsed_chests.append(record)
        for reward in record['rewards']:
            errors = reward_errors(reward)
            if errors:
                invalid_rewards.append({
                    'locationId': record.get('locationId'),
                    'summaryZhCN': record.get('summaryZhCN'),
                    'reward': reward,
                    'errors': errors,
                })

    invariants = audit.get('invariants', {})
    validation_errors: list[str] = []
    if not parsed_chests:
        validation_errors.append('no_parsed_legendary_chests')
    if any(row['errors'] for row in sample_results):
        validation_errors.append('sample_validation_failed')
    if invalid_rewards:
        validation_errors.append('parsed_chest_translation_failed')
    if catalog.get('recordCount') != 3430 or catalog.get('coverage', {}).get('total') != 3430:
        validation_errors.append('catalog_count_failed')
    for key in ('exactly3430Records', 'oneRecordPerLocation', 'coverageConserved', 'batchLimitRespected'):
        if not invariants.get(key):
            validation_errors.append(f'audit_invariant_failed:{key}')
    if int(audit.get('statusCounts', {}).get('unresolved', 3430)) >= 2533:
        validation_errors.append('unresolved_count_did_not_decrease')
    if any(bool(value) for value in state.get('safety', {}).values()):
        validation_errors.append('translation_safety_failed')
    if any(str(original).startswith('??') for original in translation_evidence.get('translations', {})):
        validation_errors.append('placeholder_translation_present')

    report = {
        'schemaVersion': 1,
        'release': '0.9.4.8',
        'generatedAt': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'valid': not validation_errors,
        'validationErrors': validation_errors,
        'parsedLegendaryChestCount': len(parsed_chests),
        'invalidParsedRewardCount': len(invalid_rewards),
        'unresolvedCount': audit.get('statusCounts', {}).get('unresolved'),
        'multiSourceConfirmedCount': audit.get('statusCounts', {}).get('multi_source_confirmed'),
        'highConfidenceInferenceCount': audit.get('statusCounts', {}).get('high_confidence_inference'),
        'translationState': {
            'acceptedThisRun': state.get('acceptedThisRun'),
            'rejectedThisRun': state.get('rejectedThisRun'),
            'remainingCandidateNames': state.get('remainingCandidateNames'),
            'totalRegisteredStandardTranslations': state.get('totalRegisteredStandardTranslations'),
        },
        'samples': sample_results,
        'invalidParsedRewards': invalid_rewards,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({
        'valid': report['valid'],
        'errors': report['validationErrors'],
        'parsed': report['parsedLegendaryChestCount'],
        'invalid': report['invalidParsedRewardCount'],
        'unresolved': report['unresolvedCount'],
    }, ensure_ascii=False))
    return 1 if args.validate and validation_errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
