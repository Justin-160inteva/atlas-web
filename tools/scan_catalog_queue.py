#!/usr/bin/env python3
"""Process a bounded authorized catalog queue with transient media retention."""
from __future__ import annotations
import argparse, json, pathlib, subprocess, sys
from datetime import datetime, timezone

ROOT=pathlib.Path(__file__).resolve().parents[1]

def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def load(path,default=None): return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8'); tmp.replace(path)
def run(command,timeout): return subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=timeout)

def build_job(item,catalog,manifest):
    page=int(item.get('page') or item.get('sequence') or 1)
    prefix=manifest.get('outputPrefix','eleven')
    job_path=ROOT/f"data/analysis-jobs/{prefix}-p{page:03d}.json"
    result_path=ROOT/f"data/analysis-results/{prefix}-p{page:03d}.json"
    duration=int(item.get('durationSeconds') or 0)
    max_samples=int(manifest.get('maxSamplesA',720) if item.get('scanClass')=='A' else manifest.get('maxSamplesDefault',480))
    interval=max(float(manifest.get('minimumIntervalSeconds',2.0)),duration/max(1,max_samples))
    job={
        'id':f"{prefix}-p{page:03d}-v1",'externalSourceId':item['externalSourceId'],'authorizationId':catalog['authorizationId'],
        'author':catalog['author'],'platform':catalog.get('platform','哔哩哔哩'),'title':item['title'],'url':item['url'],
        'intervalSeconds':round(interval,3),'maxSamples':max_samples,'minimumSharpness':18,
        'duplicateHashDistance':0.11,'duplicateColorDistance':0.055,'output':result_path.relative_to(ROOT).as_posix(),
        'retention':{'originalVideo':False,'framePixels':False,'numericDescriptorsOnly':True},
        'batch':{'catalog':manifest['catalog'],'queue':manifest['queue'],'page':item.get('page'),'cid':item.get('cid'),'regionGuess':item.get('regionGuess'),'sourceKey':f"{item.get('bvid')}:p{item.get('page')}"}
    }
    write(job_path,job); return job_path,result_path

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('manifest'); args=parser.parse_args(); manifest=load((ROOT/args.manifest).resolve())
    catalog_path=ROOT/manifest['catalog']; queue_path=ROOT/manifest['queue']; status_path=ROOT/manifest['statusOutput']; index_path=ROOT/'data/analysis-index.json'
    catalog=load(catalog_path); queue=load(queue_path); index=load(index_path,{'version':'0.9.1.4','items':[]}); indexed={x.get('externalSourceId'):x for x in index.get('items',[])}
    catalog_items={x['id']:x for x in catalog['items']}; selected=[]
    for queued in queue.get('items',[]):
        if indexed.get(queued['externalSourceId'],{}).get('status')=='imported': queued['state']='imported'; continue
        if queued.get('state') not in ('pending','failed'): continue
        selected.append(queued)
        if len(selected)>=max(1,int(manifest.get('maxItemsPerRun',1))): break
    events=[]; newly_imported=0
    for queued in selected:
        source=catalog_items[queued['externalSourceId']]; event={'externalSourceId':queued['externalSourceId'],'page':queued.get('page'),'startedAt':now()}; queued['attemptCount']=int(queued.get('attemptCount',0))+1; queued['state']='running'; write(queue_path,queue)
        try:
            job_path,result_path=build_job(queued,catalog,manifest)
            process=run([sys.executable,manifest.get('analyzer','tools/analyze_authorized_video_v5.py'),job_path.relative_to(ROOT).as_posix()],int(manifest.get('perItemTimeoutSeconds',5400)))
            event['analyzerReturnCode']=process.returncode; event['analyzerOutput']=(process.stdout+'\n'+process.stderr)[-4000:]
            if not result_path.exists(): raise RuntimeError('analyzer did not write result')
            result=load(result_path); event['analysisStatus']=result.get('status')
            update=run([sys.executable,'tools/update_analysis_index.py',result_path.relative_to(ROOT).as_posix()],180)
            if update.returncode!=0: raise RuntimeError((update.stdout+'\n'+update.stderr)[-3000:])
            if result.get('status')=='analyzed':
                queued['state']='imported'; queued['resultPath']=result_path.relative_to(ROOT).as_posix(); source['analysisStatus']='imported'; source['analysisResultPath']=queued['resultPath']; source['analysisUpdatedAt']=now(); newly_imported+=1; event['completed']=True
            else:
                queued['state']='failed'; queued['error']=result.get('error'); source['analysisStatus']='failed'; event['completed']=False
        except subprocess.TimeoutExpired as exc:
            queued['state']='failed'; queued['error']=f'timeout after {exc.timeout} seconds'; source['analysisStatus']='failed'; event['completed']=False; event['error']=queued['error']
        except Exception as exc:
            queued['state']='failed'; queued['error']=repr(exc)[-3000:]; source['analysisStatus']='failed'; event['completed']=False; event['error']=queued['error']
        event['finishedAt']=now(); events.append(event); write(queue_path,queue); write(catalog_path,catalog)
    index=load(index_path,index); indexed={x.get('externalSourceId'):x for x in index.get('items',[])}
    for queued in queue.get('items',[]):
        if indexed.get(queued['externalSourceId'],{}).get('status')=='imported': queued['state']='imported'
    imported=sum(x.get('state')=='imported' for x in queue.get('items',[])); failed=sum(x.get('state')=='failed' for x in queue.get('items',[])); remaining=len(queue.get('items',[]))-imported
    queue['status']='complete' if remaining==0 else 'in_progress'; queue['updatedAt']=now(); write(queue_path,queue)
    catalog['catalogStatus']['analysisImported']=sum(x.get('analysisStatus')=='imported' for x in catalog['items']); catalog['catalogStatus']['analysisRemaining']=len(catalog['items'])-catalog['catalogStatus']['analysisImported']; catalog['catalogStatus']['pilotImported']=imported; catalog['catalogStatus']['pilotRemaining']=remaining; catalog['updatedAt']=now(); write(catalog_path,catalog)
    status={'schemaVersion':1,'batchId':manifest.get('id','eleven-pilot-scan-v1'),'author':catalog['author'],'authorizationId':catalog['authorizationId'],'updatedAt':now(),'complete':remaining==0,'summary':{'total':len(queue.get('items',[])),'imported':imported,'failed':failed,'remaining':remaining,'attemptedThisRun':len(selected),'newlyImportedThisRun':newly_imported},'events':events,'privacy':'Original video media and frame pixels are transient and deleted after analysis.'}
    write(status_path,status); print(json.dumps(status['summary'],ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
