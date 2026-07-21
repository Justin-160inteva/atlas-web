#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
policy = json.loads((ROOT / 'data/scan-autonomy-policy.json').read_text(encoding='utf-8'))
source = (ROOT / 'tools/scan_autonomous_repair.py').read_text(encoding='utf-8')
workflow_path = ROOT / '.github/workflows/atlas-autonomous-scan-repair.yml'
workflow = workflow_path.read_text(encoding='utf-8') if workflow_path.exists() else ''
ast.parse(source)
checks = {
    'enabled': policy.get('enabled') is True,
    'confirmation_bypassed': policy.get('authorization', {}).get('confirmationRequired') is False,
    'owner_grant': policy.get('authorization', {}).get('grantedByProjectOwner') is True,
    'target_five_minutes': policy.get('timeBudget', {}).get('targetMinutes') == 5,
    'hard_ten_minutes': policy.get('timeBudget', {}).get('hardMaximumMinutes') == 10,
    'ai_patch_enabled': policy.get('execution', {}).get('allowAiSourcePatch') is True,
    'auto_commit': policy.get('execution', {}).get('commitPassingRepairAutomatically') is True,
    'bounded_files': int(policy.get('execution', {}).get('maximumChangedFiles', 99)) <= 3,
    'bounded_lines': int(policy.get('execution', {}).get('maximumChangedLines', 9999)) <= 240,
    'auth_blocked': 'data/authorizations.json' in policy.get('blockedPathPatterns', []),
    'ui_blocked': '*.js' in policy.get('blockedPathPatterns', []) and '*.css' in policy.get('blockedPathPatterns', []),
    'single_download': policy.get('mandatorySafety', {}).get('maximumConcurrentDownloads') == 1,
    'rollback': policy.get('mandatorySafety', {}).get('rollbackOnValidationFailure') is True,
    'no_retention': policy.get('mandatorySafety', {}).get('neverRetainOriginalMedia') is True and policy.get('mandatorySafety', {}).get('neverRetainFramePixels') is True,
    'model_endpoint': 'models.github.ai/inference/chat/completions' in source,
    'untrusted_logs': 'untrusted data' in source,
    'path_allowlist': 'allowedPathPatterns' in source and 'blockedPathPatterns' in source,
    'snapshot_guard': 'protected_snapshot' in source and 'verify_snapshot' in source,
    'git_apply_check': 'git", "apply", "--check' in source,
    'quick_tests': 'heartbeat_system_smoke.py' in source and 'serial_queue_order_smoke.py' in source and 'queue_schema_smoke.py' in source,
    'queue_reset_only_after_pass': 'autonomous_repair_ready' in source and source.index('tests = validate') < source.index('autonomous_repair_ready'),
    'workflow_exists': bool(workflow),
    'workflow_models_permission': 'models: read' in workflow,
    'workflow_not_pr_triggered': 'pull_request:' not in workflow,
    'workflow_commits': 'git push origin HEAD:main' in workflow,
}
failed = [name for name, passed in checks.items() if not passed]
report = {
    'schemaVersion': 1,
    'passed': not failed,
    'totalChecks': len(checks),
    'failedChecks': failed,
    'checks': checks,
}
out = ROOT / 'data/conflict-reports/autonomous-scan-repair-smoke.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f"Autonomous scan repair contract: {len(checks)-len(failed)}/{len(checks)}; failed={','.join(failed) or 'none'}")
raise SystemExit(2 if failed else 0)
