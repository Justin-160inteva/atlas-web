#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
policy = json.loads((ROOT / 'data/scan-autonomy-policy.json').read_text(encoding='utf-8'))
manifest = json.loads((ROOT / 'data/batch-analysis/eleven-pilot-scan-manifest.json').read_text(encoding='utf-8'))
controller = (ROOT / 'tools/scan_autonomous_repair.py').read_text(encoding='utf-8')
orchestrator = (ROOT / 'tools/run_scan_with_auto_recovery.py').read_text(encoding='utf-8')
diagnoser = (ROOT / 'tools/diagnose_and_recover_scan_v2.py').read_text(encoding='utf-8')
workflow = (ROOT / '.github/workflows/scan-eleven-pilot-v2.yml').read_text(encoding='utf-8')

for source in (controller, orchestrator, diagnoser):
    ast.parse(source)

checks = {
    'enabled': policy.get('enabled') is True,
    'confirmation_not_required': policy.get('authorization', {}).get('confirmationRequired') is False,
    'owner_grant_recorded': policy.get('authorization', {}).get('grantedByProjectOwner') is True,
    'deterministic_first': policy.get('execution', {}).get('deterministicRecoveryFirst') is True,
    'ai_patch_enabled': policy.get('execution', {}).get('allowAiSourcePatch') is True,
    'retry_same_item': policy.get('execution', {}).get('retrySameQueueItemAfterRepair') is True,
    'automatic_commit': policy.get('execution', {}).get('commitPassingRepairAutomatically') is True,
    'bounded_files': int(policy.get('execution', {}).get('maximumChangedFiles', 99)) <= 3,
    'bounded_lines': int(policy.get('execution', {}).get('maximumChangedLines', 9999)) <= 240,
    'authorization_blocked': 'data/authorizations.json' in policy.get('blockedPathPatterns', []),
    'public_ui_blocked': all(pattern in policy.get('blockedPathPatterns', []) for pattern in ('*.html', '*.js', '*.css', 'sw.js')),
    'single_download': policy.get('mandatorySafety', {}).get('maximumConcurrentDownloads') == 1,
    'serial_order': policy.get('mandatorySafety', {}).get('strictSerialOrder') is True,
    'no_original_media': policy.get('mandatorySafety', {}).get('neverRetainOriginalMedia') is True,
    'no_frame_pixels': policy.get('mandatorySafety', {}).get('neverRetainFramePixels') is True,
    'rollback_required': policy.get('mandatorySafety', {}).get('rollbackOnValidationFailure') is True,
    'untrusted_logs': 'untrusted data' in controller,
    'allowlist_validation': 'allowedPathPatterns' in controller and 'blockedPathPatterns' in controller,
    'protected_snapshot': 'protected_snapshot' in controller and 'verify_snapshot' in controller,
    'git_apply_check': 'git", "apply", "--check' in controller,
    'rollback_implemented': 'rollback(changed)' in controller,
    'fast_validation': all(name in controller for name in ('heartbeat_system_smoke.py', 'serial_queue_order_smoke.py', 'queue_schema_smoke.py')),
    'orchestrator_invokes_ai': 'invoke_autonomous_repair' in orchestrator,
    'orchestrator_no_confirmation': '"confirmationRequired": False' in orchestrator,
    'workflow_models_permission': 'models: read' in workflow,
    'workflow_ai_token': 'ATLAS_AI_REPAIR_TOKEN' in workflow,
    'workflow_persists_repair': 'tools/*.py' in workflow and 'data/scan-autonomy-policy.json' in workflow,
    'manifest_single_download': manifest.get('maximumConcurrentDownloads') == manifest.get('maxItemsPerRun') == 1,
    'manifest_no_retention': manifest.get('retention', {}).get('originalVideo') is False and manifest.get('retention', {}).get('framePixels') is False,
    'manifest_source_repair_allowed': manifest.get('recoveryPolicy', {}).get('neverModifySourceCodeAutomatically') is False,
}
failed = [name for name, passed in checks.items() if not passed]
report = {'schemaVersion': 1, 'passed': not failed, 'totalChecks': len(checks), 'failedChecks': failed, 'checks': checks}
out = ROOT / 'data/conflict-reports/autonomous-scan-repair-smoke.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f"Autonomous scan repair contract: {len(checks)-len(failed)}/{len(checks)}; failed={','.join(failed) or 'none'}")
raise SystemExit(2 if failed else 0)
