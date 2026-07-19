(() => {
  'use strict';
  const VERSION='0.1.0';
  const REPO='Justin-160inteva/atlas-web';
  const PATH='data/runtime-progress/eleven-pilot-progress.json';
  const RAW=`https://raw.githubusercontent.com/${REPO}/main/${PATH}`;
  const API=`https://api.github.com/repos/${REPO}/contents/${PATH}?ref=main`;
  const RAW_POLL=10000;
  const API_POLL=55000;
  const APPLY_TICK=3000;
  let accepted=null, rawTimer=0, apiTimer=0, applyTimer=0;
  const $=id=>document.getElementById(id);
  const valid=v=>v&&Number(v.schemaVersion)>=2&&typeof v.state==='string'&&Number.isFinite(Date.parse(v.updatedAt||''));
  const newer=(a,b)=>{
    if(!valid(a))return b;if(!valid(b))return a;
    if(a.externalSourceId!==b.externalSourceId)return Date.parse(a.updatedAt)>=Date.parse(b.updatedAt)?a:b;
    const ah=Number(a.heartbeatSequence||0),bh=Number(b.heartbeatSequence||0);
    return ah!==bh?(ah>bh?a:b):(Date.parse(a.updatedAt)>=Date.parse(b.updatedAt)?a:b);
  };
  const decode=s=>new TextDecoder().decode(Uint8Array.from(atob(String(s||'').replace(/\s+/g,'')),c=>c.charCodeAt(0)));
  const json=async url=>{const r=await fetch(`${url}${url.includes('?')?'&':'?'}live=${Date.now()}`,{cache:'no-store',headers:{Accept:'application/json'}});if(!r.ok)throw new Error(String(r.status));return r.json();};
  const mb=n=>`${(Number(n||0)/1048576).toFixed(1)} MB`;
  const speed=n=>`${(Number(n||0)/1048576).toFixed(2)} MB/s`;
  const eta=n=>{const s=Math.max(0,Number(n)||0);if(!s)return '—';return s<60?`${Math.ceil(s)}秒`:`${Math.ceil(s/60)}分钟`;};
  const age=v=>{const s=Math.max(0,Math.round((Date.now()-Date.parse(v))/1000));return s<60?`${s}秒前`:`${Math.floor(s/60)}分钟前`;};
  function accept(candidate,origin){const chosen=newer(candidate,accepted);if(chosen===candidate&&valid(candidate)){accepted=candidate;accepted.__origin=origin;}apply();}
  async function pollRaw(){try{accept(await json(RAW),'GitHub Raw');}catch(_){}}
  async function pollApi(){try{const p=await json(API);accept(JSON.parse(decode(p.content)),'GitHub Contents API');}catch(_){}}
  function apply(){
    const d=accepted;if(!valid(d))return;
    const downloaded=Number(d.downloadedBytes||0),total=Number(d.totalBytes||0),ratio=total?Math.min(100,downloaded/total*100):0;
    const sd=Number(d.segmentDownloadedBytes||0),st=Number(d.segmentTotalBytes||0),sr=st?Math.min(100,sd/st*100):0;
    if($('downloadedAmount'))$('downloadedAmount').textContent=total?`${mb(downloaded)} / ${mb(total)}`:mb(downloaded);
    if($('downloadSpeed'))$('downloadSpeed').textContent=`${speed(d.speedBytesPerSecond)} · 平均 ${speed(d.averageSpeedBytesPerSecond)}`;
    if($('downloadSegment'))$('downloadSegment').textContent=d.segmentCount?`${d.segmentIndex||0} / ${d.segmentCount}`:'—';
    if($('downloadEta'))$('downloadEta').textContent=eta(d.etaSeconds);
    if($('downloadBar'))$('downloadBar').style.width=`${ratio}%`;
    if($('segmentBar'))$('segmentBar').style.width=`${sr}%`;
    if($('downloadHeartbeatMeta'))$('downloadHeartbeatMeta').textContent=`实时心跳 #${d.heartbeatSequence||'—'} · ${age(d.updatedAt)} · ${d.__origin}`;
    if($('downloadDetail'))$('downloadDetail').textContent=d.stage==='download'?`${downloaded?'下载正常':'等待首字节'} · 总进度 ${ratio.toFixed(1)}% · 当前分片 ${sr.toFixed(1)}%`:`当前阶段：${d.stage}`;
    if($('activeDetail'))$('activeDetail').textContent=`本期 ${(d.stage==='download'&&total?ratio:Number(d.progressPercent||0)).toFixed(1)}% · ${d.message||d.stage}`;
    if($('heartbeatAge'))$('heartbeatAge').textContent=age(d.updatedAt);
    if($('dataOrigin'))$('dataOrigin').textContent=`数据源：${d.__origin} · 心跳 #${d.heartbeatSequence||'—'}`;
    const row=[...document.querySelectorAll('.queue-item')].find(x=>x.querySelector('.queue-page')?.textContent.trim()===`P${d.page}`);
    if(row){const s=row.querySelector('.queue-state');if(s){s.className=`queue-state ${d.state}`;s.textContent=d.state==='running'?'运行中':d.state==='recovery'?'自动恢复':d.state;}}
  }
  function start(){pollRaw();pollApi();rawTimer=setInterval(pollRaw,RAW_POLL);apiTimer=setInterval(pollApi,API_POLL);applyTimer=setInterval(apply,APPLY_TICK);}
  addEventListener('pagehide',()=>{clearInterval(rawTimer);clearInterval(apiTimer);clearInterval(applyTimer);},{once:true});
  window.AtlasLiveTelemetryBridge={version:VERSION,refresh:()=>{pollRaw();pollApi();}};
  start();
})();