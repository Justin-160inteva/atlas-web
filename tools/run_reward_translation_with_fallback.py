#!/usr/bin/env python3
"""Run reward-name translation with bounded GitHub Models fallbacks.

The underlying translator and its validation rules remain unchanged. This runner only
changes the model ID and request batch size after a complete provider failure, restores
the checked-in policy before exiting, and writes a compact diagnostic if every model
fails.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / 'data/rewards/reward-translation-research-policy.json'
TRANSLATOR = ROOT / 'tools/research_reward_translation_batch.py'
FAILURE_PATH = ROOT / 'data/rewards/reward-translation-model-failure.json'

MODEL_ATTEMPTS = [
    {'id': 'openai/gpt-4.1', 'namesPerRequest': 20, 'delayBeforeSeconds': 0},
    {'id': 'openai/gpt-4.1-mini', 'namesPerRequest': 10, 'delayBeforeSeconds': 30},
    {'id': 'openai/gpt-4o-mini', 'namesPerRequest': 8, 'delayBeforeSeconds': 45},
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main() -> int:
    original_text = POLICY_PATH.read_text(encoding='utf-8')
    original = json.loads(original_text)
    attempts: list[dict[str, Any]] = []
    success = False

    if not (os.environ.get('ATLAS_REWARD_TRANSLATION_TOKEN') or os.environ.get('GITHUB_TOKEN')):
        raise RuntimeError('GitHub Models token is unavailable')

    try:
        for index, candidate in enumerate(MODEL_ATTEMPTS, start=1):
            delay = int(candidate['delayBeforeSeconds'])
            if delay:
                print(f"Waiting {delay}s before model fallback {candidate['id']}.", flush=True)
                time.sleep(delay)

            policy = json.loads(original_text)
            policy.setdefault('model', {})['id'] = candidate['id']
            policy.setdefault('batch', {})['namesPerModelRequest'] = candidate['namesPerRequest']
            POLICY_PATH.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

            started = now_iso()
            print(
                f"Translation model attempt {index}/{len(MODEL_ATTEMPTS)}: "
                f"{candidate['id']} with {candidate['namesPerRequest']} names/request",
                flush=True,
            )
            result = subprocess.run(
                [sys.executable, str(TRANSLATOR)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                env=os.environ.copy(),
                check=False,
            )
            if result.stdout:
                print(result.stdout, end='', flush=True)
            if result.stderr:
                print(result.stderr, end='', file=sys.stderr, flush=True)

            attempts.append({
                'model': candidate['id'],
                'namesPerRequest': candidate['namesPerRequest'],
                'startedAt': started,
                'finishedAt': now_iso(),
                'returnCode': result.returncode,
                'stderrTail': (result.stderr or '')[-1200:],
            })
            if result.returncode == 0:
                success = True
                if FAILURE_PATH.exists():
                    FAILURE_PATH.unlink()
                print(f"Reward translation succeeded with {candidate['id']}.", flush=True)
                return 0

        write_json(FAILURE_PATH, {
            'schemaVersion': 1,
            'release': '0.9.4.8',
            'generatedAt': now_iso(),
            'status': 'all_models_failed',
            'attempts': attempts,
            'safety': {
                'rewardQuantitiesChanged': False,
                'rewardTypesChanged': False,
                'locationAssociationsChanged': False,
                'evidenceStatusesChanged': False,
            },
        })
        print('All bounded GitHub Models translation attempts failed.', file=sys.stderr)
        return 1
    finally:
        POLICY_PATH.write_text(original_text, encoding='utf-8')
        if success and FAILURE_PATH.exists():
            FAILURE_PATH.unlink()


if __name__ == '__main__':
    raise SystemExit(main())
