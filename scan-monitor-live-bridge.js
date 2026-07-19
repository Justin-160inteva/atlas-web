(() => {
  'use strict';
  const VERSION='0.2.1';
  const REPO='Justin-160inteva/atlas-web';
  const PATH='data/runtime-progress/eleven-pilot-progress.json';
  const RAW=`https://raw.githubusercontent.com/${REPO}/main/${PATH}`;
  const API=`https://api.github.com/repos/${REPO}/contents/${PATH}?ref=main`;
  const RAW_POLL=5000,API_POLL=65000,APPLY_TICK=1000,MAX_PROJECT=35;
  let accepted=null,lastDownload=null,rawTimer=0,apiTimer=0,applyTimer=0;
  const $=id=>document.getElementById(id);
  const valid=v=>v&&Number(v.schemaVersion)>=2&&typeof v.state==='string'&&Number.isFinite(Date.parse(v.updatedAt||''));
  const measured=v=>valid(v)&&Number(v.totalBytes||0)>0;
  const newer=(a,b)=>{if(!valid(a))return b;if(!valid(b))return a;const at=Date.parse(a.updatedAt),bt=Date.parse(b.updatedAt);if(a.externalSourceId!==b.externalSourceId)return at>=bt?a:b;const ah=Number(a.heartbeatSequence||0),bh=Number(b.heartbeatSequence||0);return ah!==bh?(ah>bh?a:b):(at>=bt?a:b);};
  const decode=s=>new TextDecoder().decode(Uint8Array.from(atob(String(s||'').replace(/\s+/g,'')),c=>c.charCodeAt(0)));
  const fetchJson=async url=>{const r=await fetch(`${url}${url.includes('?')?'&':'?'}live=${Date.now()}`,{cache:'no-store',headers:{Accept:'application/json'}});if(!r.ok)throw new Error(String(r.status));return r.json();};
  const mib=n=>Number(n||0)/1048576;
  const mb=n=>`${mib(n).toFixed(1)} MB`;
  const speed=n=>`${mib(n).toFixed(2)} MB/s`;
  const seconds=v=>Math.max(0,(Date.now()-Date.parse(v||0))/1000);
  const age=v=>{const s=Math.round(seconds(v));return s<60?`${s}秒前`:`${Math.floor(s/60)}分钟前`;};
  const eta=n=>{const s=Math.max(0,Number(n)||0);if(!s)return '—';return s<60?`${Math.ceil(s)}秒`:`${Math.ceil(s/60)}分钟`;};
  function accept(candidate,origin){const chosen=newer(candidate,accepted);if(chosen===candidate&&valid(candidate)){accepted={...candidate,__origin:origin};if(measured(candidate))lastDownload={...candidate,__origin:origin};}apply();}
  async function pollRaw(){try{accept(await fetchJson(RAW),'GitHub Raw');}catch(_){}}
  async function pollApi(){try{const p=await fetchJson(API);accept(JSON.parse(decode(p.content)),'GitHub Contents API');}catch(_){}}
  function apply(){
    const current=accepted;if(!valid(current))return;
    const telemetry=measured(current)?current:(lastDownload?.externalSourceId===current.externalSourceId?lastDownload:null);
    if(telemetry){
      const total=Number(telemetry.totalBytes||0),actual=Number(telemetry.downloadedBytes||0);
      const measuredAt=telemetry.telemetryMeasuredAt||telemetry.updatedAt;
      const rate=Math.max(0,Number(telemetry.speedBytesPerSecond||telemetry.averageSpeedBytesPerSecond||0));
      const elapsed=Math.min(MAX_PROJECT,seconds(measuredAt));
      const estimated=current.stage==='download'&&elapsed>1&&elapsed<MAX_PROJECT&&rate>0;
      const shown=Math.min(total,actual+(estimated?rate*elapsed:0));
      const ratio=total?shown/total*100:0;
      const st=Number(telemetry.segmentTotalBytes||0),sd=Number(telemetry.segmentDownloadedBytes||0);
      const shownSegment=Math.min(st,sd+Math.max(0,shown-actual));
      const segmentRatio=st?shownSegment/st*100:0;
      $('downloadedAmount').textContent=`${estimated?'≈ ':''}${mb(shown)} / ${mb(total)}`;
      $('downloadSpeed').textContent=`${speed(telemetry.speedBytesPerSecond)} · 平均 ${speed(telemetry.averageSpeedBytesPerSecond)}`;
      $('downloadSegment').textContent=telemetry.segmentCount?`${telemetry.segmentIndex||0} / ${telemetry.segmentCount}`:'—';
      $('downloadEta').textContent=current.stage==='download'?eta((total-shown)/Math.max(1,rate)):'—';
      $('downloadBar').style.width=`${Math.min(100,ratio)}%`;
      $('segmentBar').style.width=`${Math.min(100,segmentRatio)}%`;
      $('downloadHeartbeatMeta').textContent=`实测心跳 #${telemetry.heartbeatSequence||'—'} · ${age(measuredAt)} · ${telemetry.__origin}`;
      $('downloadDetail').textContent=current.stage==='download'?`${estimated?'实时估算':'实时实测'} · 最近实测 ${mb(actual)} · 总进度 ${ratio.toFixed(1)}%`:`保留最后下载实测 ${mb(actual)}；当前阶段：${current.stage}`;
    }
    const heartbeatAge=seconds(current.updatedAt),notice=$('freshnessNotice');
    if(notice){
      if(heartbeatAge<=75){notice.dataset.level='live';notice.textContent=`30秒心跳链路正常；当前任务状态更新于${age(current.updatedAt)}。`;}
      else if(heartbeatAge>150){notice.dataset.level='danger';notice.textContent=`任务已超过150秒没有新心跳，自动调查与恢复链应当接管。`;}
      else{notice.dataset.level='warn';notice.textContent=`心跳延迟：最后更新于${age(current.updatedAt)}，正在继续核对权威状态。`;}
    }
    $('activeDetail').textContent=`本期 ${Number(current.progressPercent||0).toFixed(1)}% · ${current.message||current.stage}`;
    $('heartbeatAge').textContent=age(current.updatedAt);
    $('dataOrigin').textContent=`数据源：${current.__origin} · 心跳 #${current.heartbeatSequence||'—'}`;
  }
  function start(){pollRaw();pollApi();rawTimer=setInterval(pollRaw,RAW_POLL);apiTimer=setInterval(pollApi,API_POLL);applyTimer=setInterval(apply,APPLY_TICK);}
  addEventListener('pagehide',()=>{clearInterval(rawTimer);clearInterval(apiTimer);clearInterval(applyTimer);},{once:true});
  window.AtlasLiveTelemetryBridge={version:VERSION,refresh:()=>{pollRaw();pollApi();}};
  start();
})();
