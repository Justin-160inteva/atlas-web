(() => {
  'use strict';

  const FAST_POLL_MS=10000;
  const SLOW_POLL_MS=60000;
  const CLOCK_TICK_MS=1000;
  const RUNTIME_FRESH_MS=240000;
  const RUNNING_STALE_MS=300000;
  const REPO='Justin-160inteva/atlas-web';
  const BRANCH='main';
  const WORKFLOW='scan-eleven-pilot-v2.yml';
  const RAW_BASE=`https://raw.githubusercontent.com/${REPO}/${BRANCH}/`;
  const paths={
    status:'data/batch-analysis/eleven-pilot-scan-status.json',
    queue:'data/batch-analysis/eleven-pilot-scan-queue.json',
    catalog:'data/eleven-game-world-ac-shadows-catalog.json',
    recovery:'data/batch-analysis/eleven-pilot-recovery-report.json',
    watchdog:'data/batch-analysis/eleven-pilot-watchdog-state.json',
    runtime:'data/runtime-progress/eleven-pilot-progress.json'
  };
  let actions=null;
  let actionsFetchedAt=0;
  let fastTimer=0;
  let clockTimer=0;
  let slowFetchedAt=0;
  let slowCache={catalog:null,recovery:null,watchdog:null};
  let refreshing=false;
  let lastSuccessfulSyncAt=0;
  let nextPollAt=0;
  let latestView=null;

  const $=id=>document.getElementById(id);
  const esc=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));

  async function fetchJson(url,timeoutMs=8000){
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),timeoutMs);
    try{
      const response=await fetch(`${url}${url.includes('?')?'&':'?'}t=${Date.now()}`,{cache:'no-store',signal:controller.signal,headers:{Accept:'application/json'}});
      if(!response.ok)throw new Error(`${response.status}`);
      return await response.json();
    }finally{clearTimeout(timeout);}
  }

  async function readFreshJson(path,optional=false){
    const attempts=[
      {origin:'GitHub main',url:`${RAW_BASE}${path}`},
      {origin:'站点回退',url:path}
    ];
    let lastError=null;
    for(const attempt of attempts){
      try{return{data:await fetchJson(attempt.url),origin:attempt.origin,path,fetchedAt:Date.now()};}
      catch(error){lastError=error;}
    }
    if(optional)return{data:null,origin:'不可用',path,fetchedAt:Date.now()};
    throw lastError||new Error(`无法读取 ${path}`);
  }

  async function readActions(force=false){
    if(!force&&Date.now()-actionsFetchedAt<SLOW_POLL_MS&&actions)return actions;
    actionsFetchedAt=Date.now();
    try{
      actions=await fetchJson(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=5`,10000);
    }catch(_){actions=actions||null;}
    return actions;
  }

  function secondsSince(value){
    const time=Date.parse(value||'');
    return Number.isFinite(time)?Math.max(0,Math.round((Date.now()-time)/1000)):null;
  }

  function ageLabel(value){
    const seconds=secondsSince(value);
    if(seconds===null)return '—';
    if(seconds<5)return '刚刚';
    if(seconds<60)return `${seconds}秒前`;
    if(seconds<3600)return `${Math.floor(seconds/60)}分钟前`;
    if(seconds<86400)return `${Math.floor(seconds/3600)}小时前`;
    return `${Math.floor(seconds/86400)}天前`;
  }

  function stateLabel(state){
    return({running:'运行中',queued:'排队中',recovery:'自动恢复',blocked:'需要人工检查',complete:'试验完成',idle:'等待任务'})[state]||'等待任务';
  }

  function queueStateLabel(state){
    return({pending:'等待',running:'运行中',failed:'失败',imported:'已导入'})[state]||state||'等待';
  }

  function latestRun(payload){
    return payload?.workflow_runs?.find(run=>['in_progress','queued'].includes(run.status))||payload?.workflow_runs?.[0]||null;
  }

  function deriveState(status,recovery,run,runtime){
    const summary=status?.summary||{};
    const phase=String(status?.phase||'').toLowerCase();
    const runtimeState=String(runtime?.state||'').toLowerCase();
    if(status?.complete)return 'complete';
    if(recovery?.requiresHumanReview||summary.blocked>0||phase.includes('block'))return 'blocked';
    if(runtimeState==='failed'||recovery?.retryScheduled||phase.includes('recover')||summary.retryableFailed>0)return 'recovery';
    if(run?.status==='in_progress'||runtimeState==='running'||summary.running>0||phase.includes('run'))return 'running';
    if(run?.status==='queued'||runtimeState==='queued')return 'queued';
    return 'idle';
  }

  function stagesFor(state,runtime){
    const order=['queued','download','remux','analysis','index','cleanup','persist'];
    const labels={queued:'任务排队',download:'临时下载',remux:'媒体转封装',analysis:'抽帧与数值分析',index:'写入分析索引',cleanup:'删除临时媒体',persist:'持久化状态'};
    const aliases={downloading:'download',download:'download',remuxing:'remux',transcoding:'remux',analyzing:'analysis','frame-analysis':'analysis',indexing:'index',cleanup:'cleanup',persisting:'persist',complete:'persist',queued:'queued'};
    let active=aliases[String(runtime?.stage||'').toLowerCase()]||'';
    if(!active&&['running','recovery'].includes(state))active='download';
    if(state==='queued')active='queued';
    if(state==='complete')active='persist';
    const activeIndex=order.indexOf(active);
    return order.map((key,index)=>({key,label:labels[key],className:state==='complete'||activeIndex>=0&&index<activeIndex?'done':index===activeIndex?'active':''}));
  }

  function currentItem(status,queue){
    const items=queue?.items||status?.items||[];
    const activeId=status?.activeItem?.externalSourceId||queue?.activeExternalSourceId;
    return items.find(item=>item.externalSourceId===activeId)||items.find(item=>item.state==='running')||items.find(item=>item.state==='pending')||items.find(item=>item.state==='failed')||null;
  }

  function usableRuntime(runtime,current){
    if(!runtime||!current)return null;
    if(runtime.externalSourceId&&runtime.externalSourceId!==current.externalSourceId)return null;
    const updated=Date.parse(runtime.updatedAt||'');
    if(!Number.isFinite(updated)||Date.now()-updated>RUNTIME_FRESH_MS)return null;
    return runtime;
  }

  function renderQueue(queue,status){
    const items=queue?.items||status?.items||[];
    $('queueSummary').textContent=`${items.length} 个任务`;
    $('queueList').innerHTML=items.length?items.map(item=>{
      const state=item.state||'pending';
      const title=item.partTitle||item.title||`第${item.sequence||item.page||'—'}期`;
      const detail=[item.regionGuess||status?.pilotRegion||'山城',item.durationSeconds?`${Math.round(item.durationSeconds/60)}分钟`:null,item.attemptCount?`尝试 ${item.attemptCount}`:null,item.lastFinishedAt?`完成于 ${ageLabel(item.lastFinishedAt)}`:null].filter(Boolean).join(' · ');
      return `<article class="queue-item"><span class="queue-page">P${esc(item.page||item.sequence||'—')}</span><span class="queue-copy"><b>${esc(title)}</b><small>${esc(detail)}</small></span><span class="queue-state ${esc(state)}">${esc(queueStateLabel(state))}</span></article>`;
    }).join(''):'<div class="empty">队列为空。</div>';
  }

  function renderRecovery(recovery){
    if(!recovery){$('recoveryCategory').textContent='未触发';$('recoveryPanel').innerHTML='<div class="empty">当前没有恢复事件。</div>';return;}
    $('recoveryCategory').textContent=recovery.category||'none';
    const changed=Object.entries(recovery.changedRuntimeSettings||{}).map(([key,value])=>`${key}=${value}`).join(' · ')||'未调整运行参数';
    $('recoveryPanel').innerHTML=`<div class="event"><b>${esc(recovery.action||'none')}</b><small>${recovery.retryScheduled?'已安排安全重试':'未安排重试'} · ${recovery.requiresHumanReview?'需要人工检查':'无需人工介入'}</small><small>${esc(changed)}</small></div>`;
  }

  function renderEvents(status,recovery,watchdog,run){
    const events=[];
    if(run)events.push({title:`GitHub Actions：${run.status}${run.conclusion?` / ${run.conclusion}`:''}`,detail:`运行 #${run.run_number||'—'} · ${ageLabel(run.updated_at||run.created_at)}`});
    if(recovery&&recovery.action!=='none')events.push({title:`自动恢复：${recovery.action}`,detail:`${recovery.category||'unknown'} · ${ageLabel(recovery.generatedAt)}`});
    if(watchdog?.action&&watchdog.action!=='none')events.push({title:`看门狗：${watchdog.action}`,detail:`${watchdog.reason||watchdog.state||''} · ${ageLabel(watchdog.generatedAt||watchdog.updatedAt)}`});
    for(const event of [...(status?.events||[])].reverse().slice(0,3))events.push({title:event.completed?'扫描已完成':'扫描事件',detail:`P${event.page||event.sequence||'—'} · ${event.analysisStatus||event.error||'状态已更新'} · ${ageLabel(event.finishedAt||event.startedAt)}`});
    $('eventList').innerHTML=events.length?events.slice(0,5).map(event=>`<div class="event"><b>${esc(event.title)}</b><small>${esc(event.detail)}</small></div>`).join(''):'<div class="empty">等待扫描事件。</div>';
  }

  function describeFreshness(view){
    const age=secondsSince(view.taskUpdatedAt);
    const label=ageLabel(view.taskUpdatedAt);
    if(view.state==='running'){
      if(view.liveRuntime&&age!==null&&age<=RUNTIME_FRESH_MS/1000)return{level:'live',text:`页面联网正常；当前任务心跳更新于${label}。页面每10秒核对数据，任务端最多约90秒发布一次脱敏心跳。`};
      if(age!==null&&age>RUNNING_STALE_MS/1000)return{level:'danger',text:`页面刚刚完成联网核对，但运行中的任务已经${label}没有新心跳。该状态可能是下载阶段长时间无阶段变化，也可能是任务卡住；看门狗将在安全阈值后处理。`};
      return{level:'warn',text:`GitHub Actions 显示任务正在运行，但尚未收到当前分P的新心跳。页面仍会每10秒直接核对 GitHub main。`};
    }
    if(view.state==='queued')return{level:'info',text:`页面联网正常；当前任务仍在 GitHub Actions 队列。排队期间任务数据时间可能保持不变，这不代表监控页面停止刷新。`};
    if(view.state==='recovery')return{level:'warn',text:`页面联网正常；任务处于自动恢复阶段，最后任务事件更新于${label}。恢复器只会在安全策略允许时继续。`};
    if(view.state==='blocked')return{level:'danger',text:`页面联网正常，但任务已暂停并等待人工检查。最后任务事件更新于${label}。`};
    if(view.state==='complete')return{level:'live',text:`页面联网正常；山城试验队列已完成。最后任务事件更新于${label}。`};
    return{level:'info',text:`页面联网正常；任务端暂无新的运行事件。最后任务数据更新于${label}。`};
  }

  function tickClocks(){
    if(lastSuccessfulSyncAt){
      const next=Math.max(0,Math.ceil((nextPollAt-Date.now())/1000));
      $('lastSync').textContent=`页面同步 ${ageLabel(new Date(lastSuccessfulSyncAt).toISOString())}`;
      $('nextPoll').textContent=refreshing?'正在核对 GitHub main':`下次核对 ${next}秒`;
    }
    if(latestView){
      $('heartbeatAge').textContent=ageLabel(latestView.taskUpdatedAt);
      const freshness=describeFreshness(latestView);
      $('freshnessNotice').dataset.level=freshness.level;
      $('freshnessNotice').textContent=freshness.text;
    }
  }

  function render(data){
    const {statusEntry,queueEntry,catalogEntry,recoveryEntry,watchdogEntry,runtimeEntry,actionsPayload}=data;
    const status=statusEntry.data;
    const queue=queueEntry.data;
    const catalog=catalogEntry.data;
    const recovery=recoveryEntry.data;
    const watchdog=watchdogEntry.data;
    const runtime=runtimeEntry.data;
    const run=latestRun(actionsPayload);
    const summary=status?.summary||{};
    const total=Number(summary.total||queue?.items?.length||3);
    const imported=Number(summary.imported||queue?.items?.filter(item=>item.state==='imported').length||0);
    const current=currentItem(status,queue);
    const liveRuntime=usableRuntime(runtime,current);
    const state=deriveState(status,recovery,run,liveRuntime);
    const itemProgress=Number(liveRuntime?.progressPercent||0);
    const progress=Math.max(0,Math.min(100,total?((imported+(itemProgress>0&&state==='running'?itemProgress/100:0))/total)*100:0));
    const catalogTotal=Number(catalog?.catalogStatus?.matchedGameVideos||catalog?.items?.length||80);
    const catalogImported=Number(catalog?.catalogStatus?.analysisImported||catalog?.items?.filter(item=>item.analysisStatus==='imported').length||0);
    const attempt=Number(current?.attemptCount||status?.activeItem?.attemptCount||recovery?.attemptCount||0);
    const taskUpdatedAt=liveRuntime?.updatedAt||run?.updated_at||status?.updatedAt||queue?.updatedAt||catalog?.catalogStatus?.analysisUpdatedAt;
    const origin=[statusEntry.origin,queueEntry.origin,runtimeEntry.origin].every(value=>value==='GitHub main')?'GitHub main':'混合回退';

    $('statusBadge').dataset.state=state;
    $('statusBadge').querySelector('b').textContent=stateLabel(state);
    $('heroPercent').textContent=`${Math.round(progress)}%`;
    $('heroBar').style.width=`${progress}%`;
    $('pilotProgress').textContent=`${imported} / ${total}`;
    $('catalogProgress').textContent=`${catalogImported} / ${catalogTotal}`;
    $('attemptCount').textContent=`${attempt} / ${recovery?.maxAttempts||3}`;
    $('activeTitle').textContent=current?`P${current.page||current.sequence||'—'} · ${current.partTitle||current.title||'当前扫描任务'}`:state==='complete'?'山城试验扫描已完成':'当前没有活动扫描任务';
    $('activeDetail').textContent=liveRuntime?.message||(
      state==='running'?`GitHub Actions 正在执行${liveRuntime?.stage?` · ${liveRuntime.stage}`:''}`:
      state==='queued'?'任务已经排队，等待 GitHub Actions 领取。':
      state==='recovery'?`检测到可恢复故障：${recovery?.category||'未知类别'}，系统正在按受限策略重试。`:
      state==='blocked'?`自动处理已暂停：${recovery?.category||'需要人工检查'}。`:
      state==='complete'?'3个山城试验视频均已导入分析索引。':'等待新的工作流事件。'
    );
    $('syncState').textContent='已连接';
    $('syncState').dataset.state='connected';
    $('dataOrigin').textContent=`数据源：${origin}`;
    $('stageList').innerHTML=stagesFor(state,liveRuntime).map(stage=>`<div class="stage ${stage.className}"><i></i><span>${esc(stage.label)}</span></div>`).join('');
    renderQueue(queue,status);renderRecovery(recovery);renderEvents(status,recovery,watchdog,run);

    lastSuccessfulSyncAt=Date.now();
    nextPollAt=lastSuccessfulSyncAt+FAST_POLL_MS;
    latestView={state,current,liveRuntime,run,taskUpdatedAt};
    tickClocks();
  }

  async function refresh(force=false){
    if(refreshing)return;
    refreshing=true;
    $('syncState').textContent='同步中';
    $('syncState').dataset.state='syncing';
    tickClocks();
    try{
      const fastPromise=Promise.all([
        readFreshJson(paths.status),
        readFreshJson(paths.queue),
        readFreshJson(paths.runtime,true)
      ]);
      const slowDue=force||!slowFetchedAt||Date.now()-slowFetchedAt>=SLOW_POLL_MS;
      let slowPromise;
      if(slowDue){
        slowPromise=Promise.all([
          readFreshJson(paths.catalog),
          readFreshJson(paths.recovery,true),
          readFreshJson(paths.watchdog,true),
          readActions(force)
        ]).then(([catalog,recovery,watchdog,actionsPayload])=>{
          slowFetchedAt=Date.now();
          slowCache={catalog,recovery,watchdog};
          return{catalog,recovery,watchdog,actionsPayload};
        });
      }else{
        slowPromise=Promise.resolve({...slowCache,actionsPayload:actions});
      }
      const [[statusEntry,queueEntry,runtimeEntry],slow]=await Promise.all([fastPromise,slowPromise]);
      render({statusEntry,queueEntry,runtimeEntry,catalogEntry:slow.catalog,recoveryEntry:slow.recovery,watchdogEntry:slow.watchdog,actionsPayload:slow.actionsPayload});
    }catch(error){
      $('syncState').textContent='连接失败';
      $('syncState').dataset.state='failed';
      $('lastSync').textContent=`${error.name==='AbortError'?'请求超时':error.message||error}`;
      $('freshnessNotice').dataset.level='danger';
      $('freshnessNotice').textContent='本轮联网核对失败。页面会保留最后一次成功状态，并在下一轮自动重试。';
      nextPollAt=Date.now()+FAST_POLL_MS;
    }finally{
      refreshing=false;
      tickClocks();
    }
  }

  function schedule(){
    clearInterval(fastTimer);
    clearInterval(clockTimer);
    nextPollAt=Date.now();
    refresh(true);
    fastTimer=setInterval(()=>refresh(false),FAST_POLL_MS);
    clockTimer=setInterval(tickClocks,CLOCK_TICK_MS);
  }

  $('forceRefresh')?.addEventListener('click',()=>refresh(true));
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh(true);});
  addEventListener('online',()=>refresh(true));
  addEventListener('message',event=>{if(event.data?.type==='atlas-monitor-refresh')refresh(true);});
  addEventListener('pagehide',()=>{clearInterval(fastTimer);clearInterval(clockTimer);},{once:true});
  window.AtlasScanMonitor={refresh:()=>refresh(true),version:'0.2.0'};
  schedule();
})();