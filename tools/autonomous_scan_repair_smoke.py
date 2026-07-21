#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
policy = json.loads((ROOT / 'data/scan-autonomy-policy.json').read_text(encoding='utf-8'))
validation = json.loads((ROOT / 'data/quality/release-validation-policy.json').read_text(encoding='utf-8'))
release = json.loads((ROOT / 'release-manifest.json').read_text(encoding='utf-8'))
source = (ROOT / 'tools/scan_autonomous_repair.py').read_text(encoding='utf-8')
orchestrator = (ROOT / 'tools/run_scan_with_auto_recovery.py').read_text(encoding='utf-8')
selector = (ROOT / 'tools/select_release_validation.py').read_text(encoding='utf-8')
workflow = (ROOT / '.github/workflows/atlas-autonomous-scan-repair.yml').read_text(encoding='utf-8')
scan_workflow = (ROOT / '.github/workflows/scan-eleven-pilot-v2.yml').read_text(encoding='utf-8')
ci_workflow = (ROOT / '.github/workflows/atlas-conflict-reasoner.yml').read_text(encoding='utf-8')
ast.parse(source)
ast.parse(orchestrator)
ast.parse(selector)
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
    'orchestrator_invokes_ai': 'invoke_autonomous_repair' in orchestrator and 'autonomous_repair_retrying' in orchestrator,
    'workflow_models_permission': 'models: read' in workflow,
    'workflow_not_pr_triggered': 'pull_request:' not in workflow,
    'workflow_commits': 'git push origin HEAD:main' in workflow,
    'scan_workflow_models_permission': 'models: read' in scan_workflow,
    'scan_workflow_token': 'ATLAS_AI_REPAIR_TOKEN' in scan_workflow,
    'scan_workflow_persists_patch': "data/scan-autonomy-policy.json" in scan_workflow and "tools'" in scan_workflow,
    'release_owner': release.get('runtimeOwners', {}).get('scanAutonomousRepair') == 'tools/scan_autonomous_repair.py',
    'release_confirmation_invariant': release.get('invariants', {}).get('scanAutonomousRepairConfirmationRequired') is False,
    'release_time_budget': release.get('invariants', {}).get('scanAutonomousRepairTargetMinutes') == 5 and release.get('invariants', {}).get('scanAutonomousRepairMaximumMinutes') == 10,
    'fast_tier_exists': validation.get('tiers', {}).get('fast', {}).get('targetMinutes') == 5,
    'targeted_pr_lane': validation.get('principles', {}).get('targetedPullRequestFastLane') is True,
    'post_merge_full_matrix': validation.get('principles', {}).get('fullUiMatrixAfterMerge') is True,
    'selector_targeted_outputs': all(token in selector for token in ('run_browser_matrix', 'run_ipad', 'run_reward_search', 'targetedPullRequest')),
    'playwright_cache': 'actions/cache@v4' in ci_workflow and 'ms-playwright' in ci_workflow,
    'full_matrix_separated': "run_browser_matrix == 'true'" in ci_workflow and "run_ipad == 'true'" in ci_workflow,
}
failed = [name for name, passed in checks.items() if not passed]
report = {
    'schemaVersion': 2,
    'passed': not failed,
    'totalChecks': len(checks),
    'failedChecks': failed,
    'checks': checks,
}
out = ROOT / 'data/conflict-reports/autonomous-scan-repair-smoke.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f"Autonomous repair and fast-lane contract: {len(checks)-len(failed)}/{len(checks)}; failed={','.join(failed) or 'none'}")
raise SystemExit(2 if failed else 0)
