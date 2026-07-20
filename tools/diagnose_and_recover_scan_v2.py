#!/usr/bin/env python3
"""Dictionary-driven Atlas scan diagnosis and bounded recovery.

The engine reconciles failed analyzer results with queue state, matches a curated bug
signature, applies only pre-approved runtime changes, and writes an auditable report.
It never changes authorization, queue scope, executable source, or media retention.
"""
from __future__ import annotations
import json, pathlib, re, sys
from datetime import datetime, timezone
from typing import Any
ROOT=pathlib.Path(__file__).resolve().parents[1]
DICTIONARY=ROOT/'data/scan-bug-dictionary.json'
REPORT=ROOT/'data/batch-analysis/eleven-pilot-recovery-report.json'
def now()->str:return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def load(path:pathlib.Path,default:Any=None)->Any:
    if not path.exists():return default
    return json.loads(path.read_text(encoding='utf-8'))
def write(path:pathlib.Path,value:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)
def safe_error(value:Any)->str:
    text=str(value or '').replace('\x00','');text=re.sub(r'https?://\S+','[url-redacted]',text,flags=re.I);text=re.sub(r'(?i)(authorization|cookie|token)\s*[:=]\s*\S+',r'\1=[redacted]',text);text=re.sub(r'/tmp/\S+','[temporary-path-redacted]',text);return text[-12000:]
def match_entry(error:str,dictionary:dict[str,Any])->tuple[dict[str,Any]|None,str]:
    low=error.lower();matches=[]
    for entry in dictionary.get('entries',[]):
        for pattern in entry.get('patterns',[]):
            needle=str(pattern).lower()
            if needle and needle in low:matches.append((len(needle),entry,pattern))
    if not matches:return None,'no known signature'
    _,entry,pattern=max(matches,key=lambda item:item[0]);return entry,str(pattern)
def latest_failed_result(queue):
    candidates=[]
    for item in queue.get('items',[]):
        page=int(item.get('page') or item.get('sequence') or 0);path=ROOT/f'data/analysis-results/eleven-p{page:03d}.json';result=load(path,{})
        if result.get('status')!='failed':continue
        candidates.append((path.stat().st_mtime if path.exists() else 0,item,result))
    if not candidates:return None,None
    _,item,result=max(candidates,key=lambda v:v[0]);return item,result
def reconcile_failure(queue,status):
    failed=[item for item in queue.get('items',[]) if item.get('state')=='failed']
    if failed:return failed[0],safe_error(failed[0].get('error'))
    item,result=latest_failed_result(queue)
    if item and result:
        error=safe_error(result.get('error') or f"analysis stage {result.get('stage')} failed")
        if item.get('state')=='running':item['state']='failed';item['error']=error;item['lastFinishedAt']=result.get('generatedAt') or now();queue.pop('activeExternalSourceId',None)
        return item,error
    events=status.get('events') or [];return None,safe_error(events[-1].get('error')) if events else ''
def _enable_adaptive_transfer(manifest,*,parallel=True):
    manifest['analyzer']='tools/analyze_authorized_video_v13.py';opt=manifest.setdefault('downloadOptimization',{})
    opt.update({'noArtificialRateLimit':True,'adaptiveParallelRanges':bool(parallel),'maxRangeWorkers':max(2,min(6,int(opt.get('maxRangeWorkers',6)))),'parallelRangeThresholdBytes':int(opt.get('parallelRangeThresholdBytes',16777216)),'chunkSizeBytes':int(opt.get('chunkSizeBytes',2097152)),'rangeRetries':max(3,int(opt.get('rangeRetries',3))),'rangeRetriesPerCdn':max(1,min(3,int(opt.get('rangeRetriesPerCdn',2)))),'heartbeatSeconds':min(20,int(opt.get('heartbeatSeconds',20))),'speedWindowSeconds':min(30,int(opt.get('speedWindowSeconds',30))),'fallbackToResumableSingleStream':True,'preferBackupUrlOnRepeated412':True,'metadataRefreshPasses':max(2,int(opt.get('metadataRefreshPasses',2))),'analysisVideoMaxHeight':int(opt.get('analysisVideoMaxHeight',480)),'allowLegacyProgressiveFallback':True,'bypassPublicVideoWebpage':True,'preservePartialAcrossCdnCandidates':True})
    return {'analyzer':manifest['analyzer'],'adaptiveParallelRanges':opt['adaptiveParallelRanges'],'maxRangeWorkers':opt['maxRangeWorkers'],'fallbackToResumableSingleStream':True,'wbiSignedPlayerMetadata':True,'apiProvidedCdnRotation':True}
def apply_action(action,active,manifest):
    changed={};attempts=max(1,int(active.get('attemptCount',1)));policy=manifest.get('recoveryPolicy',{});cap=max(5,min(60,int(policy.get('fastCooldownCapSeconds',60))));floor=max(0,min(cap,int(policy.get('minimumSafeCooldownSeconds',5))))
    if action in {'increase_backoff_and_retry_public_api','fast_backoff_public_api_and_adaptive_range','refresh_wbi_metadata_rotate_cdn'}:
        backoff=min(cap,max(floor,20*(2**max(0,attempts-1))));manifest['downloadBackoffSeconds']=backoff;manifest['preferPublicApi']=True;manifest['refreshSourceMetadata']=True;changed={'downloadBackoffSeconds':backoff,'preferPublicApi':True,'refreshSourceMetadata':True}
        if action in {'fast_backoff_public_api_and_adaptive_range','refresh_wbi_metadata_rotate_cdn'}:changed.update(_enable_adaptive_transfer(manifest,parallel=True))
    elif action in {'switch_to_public_api','refresh_source_metadata_and_retry'}:manifest['preferPublicApi']=True;manifest['refreshSourceMetadata']=True;changed={'preferPublicApi':True,'refreshSourceMetadata':True}
    elif action in {'use_v10_response_compatibility_adapter','use_v11_transfer_adapter','enable_adaptive_range_and_retry'}:manifest['refreshSourceMetadata']=True;changed={'refreshSourceMetadata':True};changed.update(_enable_adaptive_transfer(manifest,parallel=True))
    elif action=='fallback_resumable_single_stream':changed=_enable_adaptive_transfer(manifest,parallel=False)
    elif action=='enable_transcode_fallback_and_retry':manifest['forceTranscodeFallback']=True;changed={'forceTranscodeFallback':True}
    elif action=='extend_timeout_reduce_samples_and_retry':manifest['perItemTimeoutSeconds']=min(10800,int(manifest.get('perItemTimeoutSeconds',5400))+900);manifest['maxSamplesA']=max(300,int(manifest.get('maxSamplesA',480))-60);manifest['maxSamplesDefault']=max(240,int(manifest.get('maxSamplesDefault',360))-60);changed={k:manifest[k] for k in ('perItemTimeoutSeconds','maxSamplesA','maxSamplesDefault')}
    elif action=='reduce_memory_pressure_and_retry':manifest['maxSamplesA']=max(240,int(manifest.get('maxSamplesA',480))//2);manifest['maxSamplesDefault']=max(180,int(manifest.get('maxSamplesDefault',360))//2);manifest['minimumIntervalSeconds']=min(8.0,float(manifest.get('minimumIntervalSeconds',3.0))*1.35);changed={k:manifest[k] for k in ('maxSamplesA','maxSamplesDefault','minimumIntervalSeconds')}
    elif action=='retry_progress_publish_with_fresh_sha':manifest['progressPublishConflictRetries']=5;changed={'progressPublishConflictRetries':5}
    elif action=='cleanup_then_retry':manifest['cleanupTransientMediaBeforeRetry']=True;changed={'cleanupTransientMediaBeforeRetry':True}
    elif action=='reset_stale_lease_and_retry':active.pop('lastStartedAt',None);changed={'staleLeaseReset':True}
    elif action=='wait_then_retry':manifest['downloadBackoffSeconds']=min(cap,max(floor,int(manifest.get('downloadBackoffSeconds',20))));changed={'rateLimitCooldown':manifest['downloadBackoffSeconds']}
    return changed
def main()->int:
    if len(sys.argv)!=2:print('usage: diagnose_and_recover_scan_v2.py MANIFEST_JSON',file=sys.stderr);return 2
    manifest_path=(ROOT/sys.argv[1]).resolve();manifest=load(manifest_path);queue_path=ROOT/manifest['queue'];status_path=ROOT/manifest['statusOutput'];queue=load(queue_path);status=load(status_path,{});dictionary=load(DICTIONARY,{'entries':[],'defaultPolicy':{}})
    active,error=reconcile_failure(queue,status);entry,signature=match_entry(error,dictionary);base_maximum=int(manifest.get('recoveryPolicy',{}).get('maxAttemptsPerItem',manifest.get('maxAttemptsPerItem',3)));override=int((entry or {}).get('maximumAttemptsOverride') or base_maximum);maximum=max(base_maximum,min(5,override));attempts=int((active or {}).get('attemptCount',0));action='none';retry=False;requires_human=False;cooldown=0;changed={}
    if active:
        if attempts>=maximum:action='block_after_attempt_limit';requires_human=True
        elif entry is None:action='human_review_required';requires_human=True
        else:
            action=str(entry.get('autoAction') or 'human_review_required');configured=max(0,int(entry.get('cooldownSeconds') or 0));cap=max(0,min(60,int(manifest.get('recoveryPolicy',{}).get('fastCooldownCapSeconds',60))));cooldown=min(configured,cap) if cap else configured;retry=bool(entry.get('retryable')) and action!='human_review_required';requires_human=not retry
            if retry:changed=apply_action(action,active,manifest);active['state']='pending';active.pop('error',None);active['lastRecoveryAt']=now();active['lastRecoveryAction']=action;active['effectiveAttemptLimit']=maximum;queue['status']='recovery_scheduled';queue.pop('activeExternalSourceId',None)
            else:queue['status']='blocked'
    report={'schemaVersion':5,'generatedAt':now(),'dictionaryVersion':dictionary.get('version'),'dictionaryEntryId':(entry or {}).get('id'),'manifest':manifest_path.relative_to(ROOT).as_posix(),'activeExternalSourceId':(active or {}).get('externalSourceId'),'category':(entry or {}).get('layer','unknown'),'matchedSignature':signature,'diagnosis':(entry or {}).get('diagnosis','No safe deterministic match was found.'),'action':action,'retryScheduled':retry,'retryDelaySeconds':cooldown,'requiresHumanReview':requires_human,'attemptCount':attempts,'baseMaxAttempts':base_maximum,'maxAttempts':maximum,'attemptOverrideApplied':maximum>base_maximum,'changedRuntimeSettings':changed,'errorExcerpt':error[-3000:],'safety':{'sourceCodeModified':False,'authorizationBroadened':False,'mediaRetentionChanged':False,'queueScopeExpanded':False}}
    write(manifest_path,manifest);write(queue_path,queue);write(REPORT,report);print(json.dumps(report,ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
