(() => {
  'use strict';
  const VERSION='0.5.0';
  const REPO='Justin-160inteva/atlas-web';
  const BRANCH='main';
  const RAW=`https://raw.githubusercontent.com/${REPO}/${BRANCH}/`;
  const API=`https://api.github.com/repos/${REPO}/contents/`;
  const POLL_MS=10000;
  const TIMEOUT_MS=7000;
  const HEARTBEAT_EXPECTED=60;
  const HEARTBEAT_WARN=150;
  const HEARTBEAT_FAIL=180;
  const paths={
    status:'data/batch-analysis/eleven-pilot-scan-status.json',
    queue:'data/batch-analysis/eleven-pilot-scan-queue.json',
    catalog:'data/eleven-game-world-ac-shadows-catalog.json',
    runtime:'data/runtime-progress/eleven-pilot-progress.json',
    recovery:'data/batch-analysis/eleven-pilot-recovery-report.json',
    watchdog:'data/batch-analysis/eleven-pilot-watchdog-state.json'
  };
  const state={data:{},origin:{},lastSync:0,nextPoll:0,refreshing:false,timer:0,clock:0};
  const $=id=>document.getElementById(id);
  const esc=value=>String(value??'').replace(/[&<>\'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const validRuntime=v=>v&&Number(v.schemaVersion)>=2&&typeof v.state==='string'&&typeof v.stage==='string'&&Number.isFinite(Date.parse(v.updatedAt||''));
  const ageSeconds=value=>{const t=Date.parse(value||'');return Number.isFinite(t)?Math.max(0,Math.round((Date.now()-t)/1000)):null;};
  const ageLabel=value=>{const s=ageSeconds(value);if(s===null)return '—';if(s<5)return '刚刚';if(s<60)return `${s}秒前`;if(s<3600)return `${Math.floor(s/60)}分钟前`;return `${Math.floor(s/3600)}小时前`;};
  const mb=value=>Number.isFinite(Number(value))?`${(Number(value)/1048576).toFixed(1)} MB`:'—';
  const speed=value=>Number.isFinite(Number(value))?`${(Number(value)/1048576).toFixed(2)} MB/s`:'—';
  const eta=value=>{const s=Math.max(0,Number(value)||0);if(!s)return '—';if(s<60)return `${Math.ceil(s)}秒`;if(s<3600)return `${Math.ceil(s/60)}分钟`;return `${Math.floor(s/3600)}小时 ${Math.ceil((s%3600)/60)}分钟`;};
  const stateLabel=value=>({running:'运行中',queued:'排队中',recovery:'自动恢复',blocked:'需要人工检查',failed:'失败',complete:'批次完成',idle:'等待任务'})[value]||'等待任务';
  const queueLabel=value=>({pending:'等待',queued:'排队',running:'运行中',recovery:'自动恢复',failed:'失败',imported:'已导入'})[value]||value||'等待';

  function withTimeout(promise,ms=TIMEOUT_MS){
    return Promise.race([promise,new Promise((_,reject)=>setTimeout(()=>reject(new Error('timeout')),ms))]);
  }
  async function fetchJson(url){
    const response=await withTimeout(fetch(`${url}${url.includes('?')?'&':'?'}t=${Date.now()}`,{cache:'no-store',headers:{Accept:'application/json'}}));
    if(!response.ok)throw new Error(String(response.status));
    return response.json();
  }
  function decodeBase64(content){
    const binary=atob(String(content||'').replace(/\s+/g,''));
    return new TextDecoder().decode(Uint8Array.from(binary,c=>c.charCodeAt(0)));
  }
  async function read(path,apiFallback=false){
    const attempts=[['GitHub main',`${RAW}${path}`],['站点回退',path]];
    for(const [origin,url] of attempts){
      try{return{data:await fetchJson(url),origin};}catch(_){/* continue */}
    }
    if(apiFallback){
      try{
        const payload=await fetchJson(`${API}${path}?ref=${BRANCH}`);
        return{data:JSON.parse(decodeBase64(payload.content)),origin:'GitHub Contents API'};
      }catch(_){/* unavailable */}
    }
    return{data:null,origin:'不可用'};
  }
  function runtimeNewer(a,b){
    if(!validRuntime(a))return b;
    if(!validRuntime(b))return a;
    const at=Date.parse(a.updatedAt),bt=Date.parse(b.updatedAt);
    if(a.externalSourceId!==b.externalSourceId)return at>=bt?a:b;
    const ah=Number(a.heartbeatSequence||0),bh=Number(b.heartbeatSequence||0);
    return ah!==bh?(ah>bh?a:b):(at>=bt?a:b);
  }
  function itemsWithRuntime(queue,status,runtime){
    const items=(queue?.items||status?.items||[]).map(item=>({...item}));
    if(validRuntime(runtime)){
      const item=items.find(entry=>entry.externalSourceId===runtime.externalSourceId);
      if(item&&item.state!=='imported'){
        item.state=runtime.state==='recovery'?'recovery':runtime.state;
        item.livePercent=taskPercent(runtime);
        item.heartbeatSequence=runtime.heartbeatSequence;
      }
    }
    return items;
  }
  function taskPercent(runtime){
    const total=Number(runtime?.totalBytes||0),downloaded=Number(runtime?.downloadedBytes||0);
    if(runtime?.stage==='download'&&total>0)return Math.min(100,downloaded/total*100);
    return Math.min(100,Math.max(0,Number(runtime?.progressPercent||0)));
  }
  function currentItem(items,runtime){
    if(validRuntime(runtime))return items.find(i=>i.externalSourceId===runtime.externalSourceId)||null;
    return items.find(i=>i.state==='running'||i.state==='recovery')||items.find(i=>i.state==='pending')||null;
  }
  function deriveState(status,items,runtime,recovery){
    if(status?.complete||items.length&&items.every(i=>i.state==='imported'))return 'complete';
    if(recovery?.requiresHumanReview||items.some(i=>i.state==='blocked'))return 'blocked';
    if(runtime?.state==='recovery'||runtime?.state==='failed'||recovery?.retryScheduled)return 'recovery';
    if(runtime?.state==='running'||items.some(i=>i.state==='running'))return 'running';
    if(runtime?.state==='queued'||items.some(i=>i.state==='queued'||i.state==='pending'))return 'queued';
    return 'idle';
  }
  function renderQueue(items,region){
    $('queueSummary').textContent=`${items.length} 个任务`;
    $('queueList').innerHTML=items.length?items.map(item=>{
      const title=item.partTitle||item.title||`第${item.sequence||item.page||'—'}期`;
      const detail=[item.regionGuess||region,item.durationSeconds?`${Math.round(item.durationSeconds/60)}分钟`:null,item.attemptCount?`尝试 ${item.attemptCount}`:null,item.livePercent!=null?`本期 ${item.livePercent.toFixed(1)}%`:null,item.heartbeatSequence?`心跳 #${item.heartbeatSequence}`:null,item.lastFinishedAt?`完成于 ${ageLabel(item.lastFinishedAt)}`:null].filter(Boolean).join(' · ');
      return `<article class="queue-item"><span class="queue-page">P${esc(item.page||item.sequence||'—')}</span><span class="queue-copy"><b>${esc(title)}</b><small>${esc(detail)}</small></span><span class="queue-state ${esc(item.state)}">${esc(queueLabel(item.state))}</span></article>`;
    }).join(''):'<div class="empty">队列为空。</div>';
  }
  function renderStages(mode,runtime){
    const order=['queued','download','remux','analysis','index','cleanup','persist'];
    const labels={queued:'任务排队',download:'临时下载',remux:'媒体转封装',analysis:'抽帧与数值分析',index:'写入分析索引',cleanup:'删除临时媒体',persist:'持久化状态'};
    const alias={queued:'queued',download:'download',downloading:'download',remuxing:'remux',transcoding:'remux',analysis:'analysis','frame-analysis':'analysis',analyzing:'analysis',indexing:'index',cleanup:'cleanup',persisting:'persist',complete:'persist',recovery:'download'};
    const active=mode==='complete'?'persist':alias[String(runtime?.stage||mode)]||'queued';
    const activeIndex=order.indexOf(active);
    $('stageList').innerHTML=order.map((key,index)=>`<div class="stage ${mode==='complete'||index<activeIndex?'done':index===activeIndex?'active':''}"><i></i><span>${labels[key]}</span></div>`).join('');
  }
  function renderTelemetry(runtime,previous){
    const active=validRuntime(runtime)&&runtime.stage==='download';
    $('downloadTelemetry').dataset.active=active?'true':'false';
    if(!validRuntime(runtime)){
      $('downloadHeartbeatMeta').textContent='等待任务心跳';
      $('downloadDetail').textContent='当前没有可用下载遥测';
      return;
    }
    const downloaded=Number(runtime.downloadedBytes||0),total=Number(runtime.totalBytes||0);
    const segmentDownloaded=Number(runtime.segmentDownloadedBytes||0),segmentTotal=Number(runtime.segmentTotalBytes||0);
    const ratio=total>0?Math.min(100,downloaded/total*100):0;
    const segmentRatio=segmentTotal>0?Math.min(100,segmentDownloaded/segmentTotal*100):0;
    const delta=previous?.externalSourceId===runtime.externalSourceId?Math.max(0,downloaded-Number(previous.downloadedBytes||0)):0;
    $('downloadedAmount').textContent=total?`${mb(downloaded)} / ${mb(total)}`:mb(downloaded);
    $('downloadSpeed').textContent=`${speed(runtime.speedBytesPerSecond)} · 平均 ${speed(runtime.averageSpeedBytesPerSecond)}`;
    $('downloadSegment').textContent=runtime.segmentCount?`${runtime.segmentIndex||0} / ${runtime.segmentCount}`:'—';
    $('downloadEta').textContent=eta(runtime.etaSeconds);
    $('downloadBar').style.width=`${ratio}%`;
    $('segmentBar').style.width=`${segmentRatio}%`;
    $('downloadHeartbeatMeta').textContent=`心跳 #${runtime.heartbeatSequence||'—'} · ${ageLabel(runtime.updatedAt)}`;
    $('downloadDetail').textContent=active?`${downloaded===0?'等待首字节':`下载正常${delta?` · 本次新增 ${mb(delta)}`:''}`} · 总进度 ${ratio.toFixed(1)}% · 当前分片 ${segmentRatio.toFixed(1)}%`:`下载阶段已结束，当前阶段：${runtime.stage}`;
  }
  function renderRecovery(recovery,current){
    const relevant=recovery&&(!current||!recovery.activeExternalSourceId||recovery.activeExternalSourceId===current.externalSourceId)?recovery:null;
    if(!relevant){$('recoveryCategory').textContent='未触发';$('recoveryPanel').innerHTML='<div class="empty">当前没有恢复事件。</div>';return;}
    $('recoveryCategory').textContent=relevant.dictionaryEntryId||relevant.category||'unknown';
    $('recoveryPanel').innerHTML=`<div class="event"><b>${esc(relevant.action||'none')}</b><small>${relevant.retryScheduled?'已安排安全重试':'未安排重试'} · ${relevant.requiresHumanReview?'需要人工检查':'无需人工介入'}</small><small>${esc(relevant.diagnosis||'')}</small></div>`;
  }
  function renderEvents(status,recovery,watchdog,runtime){
    const events=[];
    if(validRuntime(runtime))events.push({title:`P${runtime.page||'—'}：${stateLabel(runtime.state)}`,detail:`${runtime.message||runtime.stage} · ${ageLabel(runtime.updatedAt)}`});
    if(recovery?.action&&recovery.action!=='none')events.push({title:`自动恢复：${recovery.action}`,detail:`${recovery.dictionaryEntryId||recovery.category||'unknown'} · ${ageLabel(recovery.generatedAt)}`});
    if(watchdog?.decision&&watchdog.decision!=='no_action')events.push({title:`看门狗：${watchdog.decision}`,detail:`${watchdog.reason||''} · ${ageLabel(watchdog.generatedAt)}`});
    for(const event of [...(status?.events||[])].reverse().slice(0,3))events.push({title:event.completed?'扫描已完成':'扫描事件',detail:`P${event.page||event.sequence||'—'} · ${event.analysisStatus||event.error||'状态更新'} · ${ageLabel(event.finishedAt||event.startedAt)}`});
    $('eventList').innerHTML=events.length?events.slice(0,5).map(e=>`<div class="event"><b>${esc(e.title)}</b><small>${esc(e.detail)}</small></div>`).join(''):'<div class="empty">等待扫描事件。</div>';
  }
  function render(){
    const status=state.data.status||{};
    const queue=state.data.queue||{};
    const catalog=state.data.catalog||{};
    const runtime=state.data.runtime;
    const recovery=state.data.recovery;
    const watchdog=state.data.watchdog;
    const region=queue.pilotRegion||status.pilotRegion||'当前批次';
    const items=itemsWithRuntime(queue,status,runtime);
    const current=currentItem(items,runtime);
    const mode=deriveState(status,items,runtime,recovery);
    const imported=items.filter(i=>i.state==='imported').length;
    const total=items.length||Number(status?.summary?.total||0);
    const percent=taskPercent(runtime);
    const batchPercent=total?Math.min(100,(imported+(['running','recovery'].includes(mode)?percent/100:0))/total*100):0;
    const catalogTotal=Number(catalog?.catalogStatus?.matchedScanItems||catalog?.items?.length||80);
    const catalogImported=Math.max(Number(catalog?.catalogStatus?.analysisImported||0),Array.isArray(catalog?.items)?catalog.items.filter(i=>i.analysisStatus==='imported').length:0,3+imported);
    $('statusBadge').dataset.state=mode;
    $('statusBadge').querySelector('b').textContent=stateLabel(mode);
    $('heroPercent').textContent=`${Math.round(batchPercent)}%`;
    $('heroBar').style.width=`${batchPercent}%`;
    $('pilotProgress').textContent=`${imported} / ${total}`;
    $('catalogProgress').textContent=`${catalogImported} / ${catalogTotal}`;
    $('attemptCount').textContent=`${Number(current?.attemptCount||recovery?.attemptCount||0)} / ${Number(recovery?.maxAttempts||3)}`;
    $('activeTitle').textContent=current?`P${current.page||current.sequence||'—'} · ${current.partTitle||current.title||'当前任务'}`:mode==='complete'?`${region}已完成`:'当前没有活动任务';
    $('activeDetail').textContent=validRuntime(runtime)?`本期 ${percent.toFixed(1)}% · ${runtime.message||runtime.stage}`:mode==='queued'?'任务已排队，等待GitHub Actions领取。':'等待新的任务事件。';
    const heartbeatAt=validRuntime(runtime)?runtime.updatedAt:status.updatedAt||queue.updatedAt;
    $('heartbeatAge').textContent=ageLabel(heartbeatAt);
    const heartbeatAge=ageSeconds(heartbeatAt);
    const notice=$('freshnessNotice');
    if(mode==='complete'){notice.dataset.level='live';notice.textContent=`当前批次已完成；最后任务事件更新于${ageLabel(heartbeatAt)}。`;}
    else if(validRuntime(runtime)&&heartbeatAge!==null&&heartbeatAge<=HEARTBEAT_WARN){notice.dataset.level='live';notice.textContent=`实时链路正常：页面每10秒核对，任务心跳目标每${HEARTBEAT_EXPECTED}秒一次；当前心跳${ageLabel(heartbeatAt)}。`;}
    else if(['running','recovery'].includes(mode)&&heartbeatAge>HEARTBEAT_FAIL){notice.dataset.level='danger';notice.textContent=`任务已超过${HEARTBEAT_FAIL}秒没有新心跳，自动调查链应当接管。`;}
    else{notice.dataset.level='info';notice.textContent='页面已连接；正在等待新的任务心跳或队列状态。';}
    renderQueue(items,region);
    renderStages(mode,runtime);
    renderTelemetry(runtime,state.previousRuntime);
    renderRecovery(recovery,current);
    renderEvents(status,recovery,watchdog,runtime);
    const origins=[state.origin.status,state.origin.queue,state.origin.runtime].filter(Boolean);
    $('dataOrigin').textContent=`数据源：${origins.length&&origins.every(v=>v===origins[0])?origins[0]:'混合实时源'}${runtime?.heartbeatSequence?` · 心跳 #${runtime.heartbeatSequence}`:''}`;
  }
  function updateClocks(){
    if(state.lastSync){$('lastSync').textContent=`页面同步 ${ageLabel(new Date(state.lastSync).toISOString())}`;}
    const remain=Math.max(0,Math.ceil((state.nextPoll-Date.now())/1000));
    $('nextPoll').textContent=state.refreshing?'正在核对实时数据':`下次核对 ${remain}秒`;
  }
  async function refresh(){
    if(state.refreshing)return;
    state.refreshing=true;
    $('syncState').textContent='同步中';
    $('syncState').dataset.state='syncing';
    updateClocks();
    try{
      const [status,queue,runtime]=await Promise.all([read(paths.status,true),read(paths.queue,true),read(paths.runtime,true)]);
      if(status.data){state.data.status=status.data;state.origin.status=status.origin;}
      if(queue.data){state.data.queue=queue.data;state.origin.queue=queue.origin;}
      if(runtime.data){state.previousRuntime=state.data.runtime;state.data.runtime=runtimeNewer(runtime.data,state.data.runtime);state.origin.runtime=runtime.origin;}
      render();
      state.lastSync=Date.now();
      $('syncState').textContent='已连接';
      $('syncState').dataset.state='connected';
      Promise.all([read(paths.catalog),read(paths.recovery),read(paths.watchdog)]).then(([catalog,recovery,watchdog])=>{
        if(catalog.data){state.data.catalog=catalog.data;state.origin.catalog=catalog.origin;}
        if(recovery.data){state.data.recovery=recovery.data;state.origin.recovery=recovery.origin;}
        if(watchdog.data){state.data.watchdog=watchdog.data;state.origin.watchdog=watchdog.origin;}
        render();
      }).catch(()=>{});
    }catch(error){
      $('syncState').textContent='连接异常';
      $('syncState').dataset.state='failed';
      $('freshnessNotice').dataset.level='danger';
      $('freshnessNotice').textContent=`本轮核心状态读取失败：${error.message||error}。10秒后自动重试。`;
    }finally{
      state.refreshing=false;
      state.nextPoll=Date.now()+POLL_MS;
      updateClocks();
    }
  }
  function start(){
    clearInterval(state.timer);clearInterval(state.clock);
    state.nextPoll=Date.now();
    refresh();
    state.timer=setInterval(refresh,POLL_MS);
    state.clock=setInterval(updateClocks,1000);
  }
  $('forceRefresh')?.addEventListener('click',refresh);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
  addEventListener('online',refresh);
  addEventListener('message',event=>{if(event.data?.type==='atlas-monitor-refresh')refresh();});
  addEventListener('pagehide',()=>{clearInterval(state.timer);clearInterval(state.clock);},{once:true});
  window.AtlasScanMonitor={refresh,version:VERSION};
  start();
})();