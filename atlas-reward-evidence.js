(() => {
  'use strict';

  const VERSION=window.AtlasRelease?.version||'0.9.4.8';
  const INDEX_PATH='data/reward-evidence-index.json';
  const ALLOWED_STATUS=new Set(['official_confirmed','multi_source_confirmed','high_confidence_inference','unresolved']);
  const records=new Map();
  let indexData=null;
  let loadPromise=null;
  let applying=false;

  const statusLabel=status=>({
    official_confirmed:'官方确认',
    multi_source_confirmed:'多来源确认',
    high_confidence_inference:'高置信推断',
    unresolved:'待核实'
  })[status]||'待核实';

  const sourceLabel=source=>{
    if(source==='mapgenie_location_snapshot')return 'MapGenie 地点快照';
    return indexData?.sources?.[source]?.publisher||source||'未知来源';
  };

  function validate(payload){
    if(!payload||payload.schemaVersion!==1||payload.locale!=='zh-Hans')throw new Error('reward evidence schema mismatch');
    if(payload.targetLocationCount!==3430)throw new Error('reward evidence target mismatch');
    if(!Array.isArray(payload.records))throw new Error('reward evidence records missing');
    const ids=new Set();
    for(const record of payload.records){
      if(!record?.locationId||ids.has(record.locationId))throw new Error('duplicate reward evidence location');
      if(!ALLOWED_STATUS.has(record.evidenceStatus))throw new Error('invalid reward evidence status');
      if(!Number.isFinite(record.confidence)||record.confidence<0||record.confidence>1)throw new Error('invalid reward evidence confidence');
      if(!Array.isArray(record.rewards)||!Array.isArray(record.evidence))throw new Error('incomplete reward evidence record');
      ids.add(record.locationId);
    }
    if(payload.coverage?.records!==payload.records.length)throw new Error('reward evidence coverage mismatch');
    return payload;
  }

  async function load(){
    if(loadPromise)return loadPromise;
    loadPromise=fetch(`${INDEX_PATH}?v=${encodeURIComponent(VERSION)}`,{cache:'no-store'})
      .then(response=>{if(!response.ok)throw new Error(`reward evidence HTTP ${response.status}`);return response.json();})
      .then(validate)
      .then(payload=>{
        indexData=payload;
        records.clear();
        payload.records.forEach(record=>records.set(record.locationId,record));
        document.documentElement.dataset.atlasRewardEvidence=VERSION;
        applyToCurrent();
        return payload;
      })
      .catch(error=>{
        console.warn('[Atlas reward evidence unavailable]',error);
        document.documentElement.dataset.atlasRewardEvidence='unavailable';
        return null;
      });
    return loadPromise;
  }

  function createStatusBadge(status){
    const badge=document.createElement('span');
    badge.className='atlas-reward-status';
    badge.dataset.status=status;
    badge.textContent=statusLabel(status);
    return badge;
  }

  function createRewardRow(reward){
    const row=document.createElement('li');
    row.className='atlas-reward-row';
    const copy=document.createElement('span');
    const name=document.createElement('b');
    if(reward.kind==='xp')name.textContent=`${Number(reward.amount||0).toLocaleString('zh-CN')} ${reward.nameZhHans||'经验值'}`;
    else if(reward.kind==='mastery_points')name.textContent=`${Number(reward.amount||0)} 点${reward.nameZhHans||'精通点数'}`;
    else name.textContent=reward.nameZhHans||reward.originalName||'未命名奖励';
    copy.appendChild(name);
    if(reward.originalName&&reward.originalName!==reward.nameZhHans){
      const original=document.createElement('small');
      original.textContent=reward.originalName;
      copy.appendChild(original);
    }
    row.append(copy,createStatusBadge(reward.evidenceStatus));
    return row;
  }

  function createEvidenceDetails(record){
    const details=document.createElement('details');
    details.className='atlas-reward-sources';
    const summary=document.createElement('summary');
    summary.textContent=`查看 ${record.evidence.length} 项证据`;
    details.appendChild(summary);
    const list=document.createElement('div');
    for(const evidence of record.evidence){
      const item=document.createElement(evidence.url?'a':'span');
      item.className='atlas-reward-source';
      item.textContent=`${sourceLabel(evidence.source)}${evidence.locator?` · ${evidence.locator}`:''}`;
      if(evidence.url){
        item.href=evidence.url;
        item.target='_blank';
        item.rel='noopener noreferrer';
      }
      list.appendChild(item);
    }
    details.appendChild(list);
    return details;
  }

  function createEvidenceCard(record){
    const card=document.createElement('section');
    card.className='atlas-reward-evidence';
    card.dataset.locationId=record.locationId;
    card.dataset.status=record.evidenceStatus;

    const header=document.createElement('header');
    const title=document.createElement('div');
    const eyebrow=document.createElement('small');
    eyebrow.textContent='ATLAS REWARD EVIDENCE';
    const heading=document.createElement('b');
    heading.textContent='奖励证据';
    title.append(eyebrow,heading);
    const confidence=document.createElement('span');
    confidence.className='atlas-reward-confidence';
    confidence.textContent=`${Math.round(record.confidence*100)}%`;
    header.append(title,createStatusBadge(record.evidenceStatus),confidence);

    const list=document.createElement('ul');
    record.rewards.forEach(reward=>list.appendChild(createRewardRow(reward)));

    const note=document.createElement('p');
    note.textContent=record.translation?.official?'育碧官方简体中文名称。':'Atlas 项目标准简体中文译名；不代表育碧官方译名。';

    card.append(header,list,note,createEvidenceDetails(record));
    return card;
  }

  function createUnresolvedCard(){
    const card=document.createElement('section');
    card.className='atlas-reward-evidence atlas-reward-unresolved';
    card.dataset.status='unresolved';
    const heading=document.createElement('b');
    heading.textContent='该点位尚未进入奖励证据批次';
    const copy=document.createElement('p');
    copy.textContent='当前奖励文本来自旧资料快照，仅供线索参考；Atlas 不会把它显示为官方事实。';
    card.append(heading,copy);
    return card;
  }

  function currentLocation(){
    try{return typeof state!=='undefined'?state.selected:null;}catch(_){return null;}
  }

  function applyToCurrent(){
    if(applying)return;
    const detail=document.getElementById('detailContent');
    const location=currentLocation();
    const highlight=detail?.querySelector('.sheet-highlight');
    if(!detail||!location||!highlight)return;
    const record=records.get(location.id)||null;
    const existing=detail.querySelector('.atlas-reward-evidence');
    if(existing?.dataset.locationId===(record?.locationId||'')&&existing?.dataset.status===(record?.evidenceStatus||'unresolved'))return;
    applying=true;
    try{
      existing?.remove();
      const label=highlight.querySelector('small');
      const value=highlight.querySelector('b');
      if(record){
        if(label)label.textContent=`奖励摘要 · ${statusLabel(record.evidenceStatus)}`;
        if(value)value.textContent=record.summaryZhHans;
        highlight.insertAdjacentElement('afterend',createEvidenceCard(record));
      }else{
        if(label)label.textContent='奖励摘要 · 待核实';
        highlight.insertAdjacentElement('afterend',createUnresolvedCard());
      }
    }finally{applying=false;}
  }

  function init(){
    const detail=document.getElementById('detailContent');
    if(detail)new MutationObserver(()=>queueMicrotask(applyToCurrent)).observe(detail,{childList:true,subtree:true});
    load();
  }

  window.AtlasRewardEvidence={
    version:VERSION,
    load,
    recordFor:id=>records.get(id)||null,
    coverage:()=>indexData?.coverage||null,
    statusLabel,
    applyToCurrent
  };

  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',init,{once:true}):init();
})();
