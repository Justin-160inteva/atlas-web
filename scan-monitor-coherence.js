(() => {
  'use strict';
  const VERSION='0.4.0';
  const REPO='Justin-160inteva/atlas-web';
  const BRANCH='main';
  const PATH='data/runtime-progress/eleven-pilot-progress.json';
  const RAW=`https://raw.githubusercontent.com/${REPO}/${BRANCH}/${PATH}`;
  const API=`https://api.github.com/repos/${REPO}/contents/${PATH}?ref=${BRANCH}`;
  const POLL_MS=10000;
  const API_MIN_MS=60000;
  let timer=0;
  let apiCheckedAt=0;
  let accepted=null;
  let acceptedOrigin='GitHub main';
  let observer=null;

  const $=id=>document.getElementById(id);
  const valid=value=>value&&Number(value.schemaVersion)>=2&&typeof value.state==='string'&&typeof value.stage==='string'&&Number.isFinite(Date.parse(value.updatedAt||''));
  const rank=value=>[Number(value?.heartbeatSequence||0),Date.parse(value?.updatedAt||'')||0];
  const newer=(a,b)=>{
    if(!valid(a))return b;
    if(!valid(b))return a;
    if(a.externalSourceId&&b.externalSourceId&&a.externalSourceId!==b.externalSourceId)return rank(a)[1]>=rank(b)[1]?a:b;
    const ar=rank(a),br=rank(b);
    return ar[0]!==br[0]?(ar[0]>br[0]?a:b):(ar[1]>=br[1]?a:b);
  };
  const decode=value=>{
    const binary=atob(String(value||'').replace(/\s+/g,''));
    return new TextDecoder().decode(Uint8Array.from(binary,char=>char.charCodeAt(0)));
  };
  const taskPercent=data=>{
    const downloaded=Number(data?.downloadedBytes||0),total=Number(data?.totalBytes||0);
    if(data?.stage==='download'&&total>0)return Math.min(100,downloaded/total*100);
    return Math.min(100,Math.max(0,Number(data?.progressPercent||0)));
  };
  const stateLabel=state=>({running:'运行中',queued:'排队',recovery:'恢复中',blocked:'已阻塞',failed:'失败'})[state]||state;

  async function json(url){
    const response=await fetch(`${url}${url.includes('?')?'&':'?'}coherence=${Date.now()}`,{cache:'no-store',headers:{Accept:'application/json'}});
    if(!response.ok)throw new Error(String(response.status));
    return response.json();
  }

  async function apiRuntime(){
    const payload=await json(API);
    if(!payload?.content)throw new Error('runtime content unavailable');
    return JSON.parse(decode(payload.content));
  }

  function apply(data,previous=null){
    if(!valid(data))return;
    const percent=taskPercent(data);
    const sequence=Number(data.heartbeatSequence||0);
    const page=Number(data.page||0);
    const age=Math.max(0,Math.round((Date.now()-Date.parse(data.updatedAt))/1000));
    const detail=$('activeDetail');
    if(detail&&['running','recovery'].includes(data.state))detail.textContent=`本期 ${percent.toFixed(1)}% · ${data.message||data.stage}`;
    const ageNode=$('heartbeatAge');
    if(ageNode)ageNode.textContent=age<60?`${age}秒前`:`${Math.floor(age/60)}分钟前`;
    const origin=$('dataOrigin');
    if(origin)origin.textContent=`数据源：${acceptedOrigin}${sequence?` · 心跳 #${sequence}`:''}`;
    const badge=$('statusBadge');
    if(badge&&['running','queued','recovery','blocked'].includes(data.state)){
      badge.dataset.state=data.state;
      const text=badge.querySelector('b');
      if(text)text.textContent=stateLabel(data.state);
    }
    const queueItems=[...document.querySelectorAll('.queue-item')];
    const row=queueItems.find(item=>item.querySelector('.queue-page')?.textContent.trim()===`P${page}`);
    if(row){
      const state=row.querySelector('.queue-state');
      if(state){state.className=`queue-state ${data.state}`;state.textContent=stateLabel(data.state);}
      const small=row.querySelector('.queue-copy small');
      if(small){
        const base=small.textContent.replace(/ · 本期 [^·]+/g,'').replace(/ · 心跳 #[0-9]+/g,'');
        small.textContent=`${base} · 本期 ${percent.toFixed(1)}%${sequence?` · 心跳 #${sequence}`:''}`;
      }
    }
    const pilot=$('pilotProgress')?.textContent.match(/(\d+)\s*\/\s*(\d+)/);
    if(pilot){
      const imported=Number(pilot[1]),total=Number(pilot[2]);
      if(total>0){
        const batch=Math.min(100,(imported+(['running','recovery'].includes(data.state)?percent/100:0))/total*100);
        if($('heroPercent'))$('heroPercent').textContent=`${Math.round(batch)}%`;
        if($('heroBar'))$('heroBar').style.width=`${batch}%`;
      }
    }
    window.dispatchEvent(new CustomEvent('atlas-runtime-update',{detail:{runtime:data,previous,origin:acceptedOrigin}}));
  }

  async function refresh(force=false){
    let candidate=null;
    let origin='GitHub main';
    try{candidate=await json(RAW);}catch(_){/* API fallback below */}
    const rawAge=valid(candidate)?Date.now()-Date.parse(candidate.updatedAt):Infinity;
    const regressed=valid(accepted)&&newer(accepted,candidate)===accepted;
    if((force||rawAge>75000||regressed||!valid(candidate))&&Date.now()-apiCheckedAt>=API_MIN_MS){
      apiCheckedAt=Date.now();
      try{
        const api=await apiRuntime();
        if(valid(api)&&newer(api,candidate)===api){candidate=api;origin='GitHub Contents API';}
      }catch(_){/* keep raw or accepted */}
    }
    const chosen=newer(candidate,accepted);
    if(valid(chosen)){
      const previous=accepted;
      accepted=chosen;
      if(chosen===candidate)acceptedOrigin=origin;
      apply(chosen,previous);
    }
  }

  observer=new MutationObserver(()=>{if(accepted)apply(accepted,accepted);});
  const queue=$('queueList');
  if(queue)observer.observe(queue,{childList:true,subtree:true});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh(true);});
  addEventListener('online',()=>refresh(true));
  addEventListener('message',event=>{if(event.data?.type==='atlas-monitor-refresh')refresh(true);});
  addEventListener('pagehide',()=>{clearInterval(timer);observer?.disconnect();},{once:true});
  refresh(true);
  timer=setInterval(()=>refresh(false),POLL_MS);
  window.AtlasRuntimeCoherence={refresh:()=>refresh(true),getRuntime:()=>accepted,version:VERSION};
})();