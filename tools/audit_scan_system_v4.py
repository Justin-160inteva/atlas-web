#!/usr/bin/env python3
"""Audit Alpha 0.9.4.8 scan, monitor, data-center, and reward contracts."""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Any

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'data/batch-analysis/scan-system-health.json'
EXPECTED_BATCH='eleven-production-p025-p035-v1'
EXPECTED_PAGES=list(range(25,36))


def text(path:str)->str:return (ROOT/path).read_text(encoding='utf-8')
def data(path:str)->Any:return json.loads(text(path))


def main()->int:
    checks=[]
    def check(name:str,passed:Any,detail:str)->None:checks.append({'name':name,'passed':bool(passed),'detail':detail})

    release=data('release-manifest.json'); inv=release.get('invariants',{}); owners=release.get('runtimeOwners',{})
    reward=data('data/reward-evidence-index.json'); records=reward.get('records',[])
    queue=data('data/batch-analysis/eleven-pilot-scan-queue.json'); status=data('data/batch-analysis/eleven-pilot-scan-status.json')
    scan=data('data/batch-analysis/eleven-pilot-scan-manifest.json'); supervisor=data('data/batch-analysis/eleven-heartbeat-supervisor.json')
    bugs=data('data/scan-bug-dictionary.json'); catalog=data('data/eleven-game-world-ac-shadows-catalog.json')
    workflow=text('.github/workflows/scan-eleven-pilot-v2.yml'); gate=text('.github/workflows/atlas-conflict-reasoner.yml')
    monitor=text('scan-monitor.js'); worker=text('sw.js'); settings=text('atlas-settings.js')
    reward_runtime=text('atlas-reward-evidence.js'); reward_css=text('atlas-reward-evidence.css')
    marker=text('atlas-ui-fix-0931.js'); controls=text('atlas-controls-0938.js')
    supervisor_source=text('tools/supervise_runtime_heartbeat.py'); publisher=text('tools/publish_runtime_progress.py')
    publisher_v2=text('tools/publish_runtime_progress_v2.py'); orchestrator=text('tools/run_scan_with_auto_recovery.py')

    matrix_keys=('requiredBrowserMatrixChecks','requiredDataCenterMatrixChecks','requiredRewardEvidenceMatrixChecks','requiredFullProjectAuditChecks','requiredHeartbeatMatrixChecks','requiredSerialQueueOrderChecks','requiredMonitorBatchAuthorityChecks','requiredQueueSchemaChecks')
    check('release_version',release.get('version')=='0.9.4.8','Alpha 0.9.4.8')
    check('audit_cycle',inv.get('requireFullAuditAtThisRelease') is True and inv.get('nextFullAuditRelease')=='0.9.4.11','audit now; next 0.9.4.11')
    check('eight_500_gates',all(inv.get(key)==500 for key in matrix_keys),'all matrices exact')
    check('release_assets',all((ROOT/path).is_file() for path in release.get('releaseAssets',[])),'all assets exist')
    check('single_owners',owners.get('dataEvidenceCenter')=='atlas-settings.js' and owners.get('rewardEvidence')=='atlas-reward-evidence.js' and owners.get('scanMonitor')=='scan-monitor.js','single runtime owners')
    check('marker_contract',inv.get('markerSelectionUsesScaleOnly') is True and inv.get('markerSelectionDecorationLayers')==0 and 'selectionUsesScaleOnly:true' in marker and 'ctx.ellipse(' not in marker,'scale-only selection')
    check('settings_icon',inv.get('settingsIconDesign')=='radial-eight' and "dataset.iconDesign='radial-eight'" in controls,'radial settings icon')
    check('data_center',inv.get('singleDataEvidenceCenter') is True and inv.get('dataEvidenceCenterViews')==2 and all(token in settings for token in ('data-center-tab="database"','data-center-tab="evidence"','id="settingsEvidenceHost"')),'one two-view center')

    allowed={'official_confirmed','multi_source_confirmed','high_confidence_inference','unresolved'}
    check('reward_target',reward.get('targetLocationCount')==inv.get('rewardEvidenceTargetLocationCount')==3430,'3430 points')
    check('reward_seed',len(records)==reward.get('coverage',{}).get('records')==inv.get('rewardEvidenceSeedRecords')==8,'eight records')
    check('reward_unique',len({item.get('locationId') for item in records})==8,'unique points')
    check('reward_status',all(item.get('evidenceStatus') in allowed for item in records),'bounded statuses')
    check('reward_no_false_official',reward.get('coverage',{}).get('officialConfirmed')==0 and all(item.get('translation',{}).get('official') is False for item in records),'no false official label')
    check('reward_provenance',all(item.get('rewards') and len(item.get('evidence',[]))>=2 for item in records),'claims cite sources')
    check('reward_runtime',all(token in reward_runtime for token in ('payload.targetLocationCount!==3430','document.createElement','该点位尚未进入奖励证据批次','noopener noreferrer')) and 'innerHTML=' not in reward_runtime,'safe evidence runtime')
    check('reward_styles',all(f'[data-status="{state}"]' in reward_css for state in allowed) and '.atlas-quality-performance .atlas-reward-evidence' in reward_css,'four states and fallback')

    items=queue.get('items',[]); sequences=[item.get('sequence') for item in items]
    active=sum(item.get('state') in {'running','recovery'} for item in items)
    check('queue_batch',queue.get('queueId')==status.get('batchId')==scan.get('id')==EXPECTED_BATCH,'same batch identity')
    check('queue_pages',sequences==EXPECTED_PAGES,f'{sequences}')
    check('queue_capacity',len(items)==queue.get('maximumQueueItems')==scan.get('maximumQueueItems')==11,'eleven items')
    check('queue_serial',queue.get('maximumConcurrentItems')==scan.get('maximumConcurrentDownloads')==1 and active<=1,'one active')
    check('queue_continue',queue.get('autoContinueAfterDurableSuccess') is True and scan.get('autoContinueAfterDurableSuccess') is True,'auto continue')
    check('status_coherent',status.get('summary',{}).get('total')==11 and len(status.get('items',[]))==11,'status has eleven items')
    check('catalog_identity',all(item.get('externalSourceId') in {entry.get('id') for entry in catalog.get('items',[])} for item in items),'queue sources in catalog')

    check('workflow_serial','Scan exactly one item' in workflow and '400/400 eleven-item serial integrity and privacy checks passed' in workflow,'serial privacy gate')
    check('workflow_continue','Continue with exactly one next item after durable success' in workflow,'bounded continuation')
    check('gate_reward',all(token in gate for token in ('node tools/reward_evidence_smoke.mjs','python tools/full_project_audit_0948.py','node --check atlas-reward-evidence.js')),'reward gates wired')
    check('monitor_poll',all(token in monitor for token in ('RAW_POLL_MS','API_POLL_MS','APPLY_TICK_MS','5000','180000','1000')),'monitor cadence')
    check('monitor_authority',all(token in monitor for token in ('chooseDurableBatch','completedStatus','batchKey','批次冲突已自动隔离')),'legacy batch isolation')
    check('monitor_single','scan-monitor-live-bridge' not in worker and not (ROOT/'scan-monitor-live-bridge.js').exists(),'single monitor')
    policy=supervisor.get('policy',{})
    check('supervisor_capacity',supervisor.get('maximumQueueItems')==11 and policy.get('maximumConcurrentDownloads')==1,'eleven and one')
    check('supervisor_thresholds',supervisor.get('staleAfterSeconds')==90 and supervisor.get('hardStaleAfterSeconds')==180,'90/180 seconds')
    check('supervisor_safety',all(token in supervisor_source for token in ('sourceCodeModified','authorizationBroadened','queueScopeExpanded','mediaRetentionChanged')),'bounded repair')
    check('publisher_conflict','ATLAS_PROGRESS_CONFLICT_RETRIES' in publisher and 'error.code not in {409, 422}' in publisher,'fresh SHA retries')
    check('telemetry_preserved','PRESERVE_STAGES' in publisher_v2 and 'telemetryMeasuredAt' in publisher_v2,'same-item telemetry')
    check('success_projection','publish_durable_projection(queue)' in orchestrator and 'clear_stale_recovery(queue)' in orchestrator,'next-item projection')

    bug_ids={entry.get('id') for entry in bugs.get('entries',[])}
    check('bug_dictionary',len(bug_ids)>=25 and {'bilibili-http-412','bilibili-http-429','opencv-open-failure'}<=bug_ids,'known failure signatures')
    check('retention',scan.get('retention',{}).get('originalVideo') is False and scan.get('retention',{}).get('framePixels') is False,'no retained media')
    media=[path for pattern in ('*.mp4','*.m4a','*.webm','*.flv') for path in ROOT.rglob(pattern)]
    check('repository_media_clean',not media,f'media files={len(media)}')

    passed=sum(item['passed'] for item in checks)
    report={'schemaVersion':11,'generatedAt':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'status':'pass' if passed==len(checks) else 'fail','summary':{'total':len(checks),'passed':passed,'failed':len(checks)-passed},'dictionaryVersion':bugs.get('version'),'release':release.get('version'),'queueItems':len(items),'maximumConcurrentItems':queue.get('maximumConcurrentItems'),'batchId':queue.get('queueId'),'rewardEvidenceRecords':len(records),'rewardEvidenceTarget':reward.get('targetLocationCount'),'checks':checks}
    OUTPUT.parent.mkdir(parents=True,exist_ok=True);OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report['summary'],ensure_ascii=False));return 0 if report['status']=='pass' else 1


if __name__=='__main__':raise SystemExit(main())
