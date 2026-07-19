(() => {
  'use strict';

  const DATA_POLL_MS=15000;
  const ACTIONS_POLL_MS=60000;
  const RUNTIME_FRESH_MS=180000;
  const REPO='Justin-160inteva/atlas-web';
  const WORKFLOW='scan-eleven-pilot-v2.yml';
  const sources={
    status:'data/batch-analysis/eleven-pilot-scan-status.json',
    queue:'data/batch-analysis/eleven-pilot-scan-queue.json',
    catalog:'data/eleven-game-world-ac-shadows-catalog.json',
    recovery:'data/batch-analysis/eleven-pilot-recovery-report.json',
    watchdog:'data/batch-analysis/eleven-pilot-watchdog-state.json',
    runtime:'data/runtime-progress/eleven-pilot-progress.json'
  };
  let actions=null;
  let actionsFetchedAt=0;
  let timer=0;

  const $=id=>document.getElementById(id);
  const esc=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));

  async function readJson(url,optional=false){
    try{
      const response=await fetch(`${url}${url.includes('?')?'&':'?'}t=${Date.now()}`,{cache:'no-store'});
      if(!response.ok)throw new Error(`${response.status}`);
      return await response.json();
    }catch(error){
      if(optional)return null;
      throw error;
    }
  }

  async function readActions(){
    if(Date.now()-actionsFetchedAt<ACTIONS_POLL_MS&&actions)return actions;
    actionsFetchedAt=Date.now();
    try{
      const response=await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=5&t=${Date.now()}`,{cache:'no-store',headers:{Accept:'application/vnd.github+json'}});
      if(!response.ok)throw new Error(`${response.status}`);
      actions=await response.json();
    }catch(_){actions=actions||null;}
    return actions;
  }

  function ageLabel(value){
    const time=Date.parse(value||'');
    if(!Number.isFinite(time))return '—';
    const seconds=Math.max(0,Math.round((Date.now()-time)/1000));
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
    const aliases={downloading:'download',download:'download',remuxing:'remux',transcoding:'remux',analyzing:'analysis','frame-analysis':'analysis',indexing:'index',cleanup:'cleanup',persisting:'persist',complete:'persist'};
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
      const detail=[item.regionGuess||status?.pilotRegion||'山城',item.durationSeconds?`${Math.round(item.durationSeconds/60)}分钟`:null,item.attemptCount?`尝试 ${item.attemptCount}`:null].filter(Boolean).join(' · ');
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

  function render(data){
    const {status,queue,catalog,recovery,watchdog,runtime,actionsPayload}=data;
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
    const updated=liveRuntime?.updatedAt||status?.updatedAt||run?.updated_at||catalog?.catalogStatus?.analysisUpdatedAt;

    $('statusBadge').dataset.state=state;
    $('statusBadge').querySelector('b').textContent=stateLabel(state);
    $('heroPercent').textContent=`${Math.round(progress)}%`;
    $('heroBar').style.width=`${progress}%`;
    $('pilotProgress').textContent=`${imported} / ${total}`;
    $('catalogProgress').textContent=`${catalogImported} / ${catalogTotal}`;
    $('attemptCount').textContent=`${attempt} / ${recovery?.maxAttempts||3}`;
    $('heartbeatAge').textContent=ageLabel(updated);
    $('activeTitle').textContent=current?`P${current.page||current.sequence||'—'} · ${current.partTitle||current.title||'当前扫描任务'}`:state==='complete'?'山城试验扫描已完成':'当前没有活动扫描任务';
    $('activeDetail').textContent=liveRuntime?.message||(
      state==='running'?`GitHub Actions 正在执行${liveRuntime?.stage?` · ${liveRuntime.stage}`:''}`:
      state==='queued'?'任务已进入 GitHub Actions 队列。':
      state==='recovery'?`检测到可恢复故障：${recovery?.category||'未知类别'}，系统正在按受限策略重试。`:
      state==='blocked'?`自动处理已暂停：${recovery?.category||'需要人工检查'}。`:
      state==='complete'?'3个山城试验视频均已导入分析索引。':'等待工作流状态更新。'
    );
    $('lastSync').textContent=`页面同步 ${new Date().toLocaleTimeString('zh-CN',{hour12:false})}`;
    $('syncState').textContent='已连接';

    $('stageList').innerHTML=stagesFor(state,liveRuntime).map(stage=>`<div class="stage ${stage.className}"><i></i><span>${esc(stage.label)}</span></div>`).join('');
    const statusAge=Date.parse(updated||'');
    const stale=Number.isFinite(statusAge)&&Date.now()-statusAge>2*60*60*1000;
    $('freshnessNotice').textContent=stale?'最后状态已超过2小时，看门狗会检查是否需要恢复。':'页面每15秒读取状态；GitHub Actions 运行状态每60秒同步一次。';
    renderQueue(queue,status);renderRecovery(recovery);renderEvents(status,recovery,watchdog,run);
  }

  async function refresh(){
    try{
      $('syncState').textContent='同步中';
      const [status,queue,catalog,recovery,watchdog,runtime,actionsPayload]=await Promise.all([
        readJson(sources.status),readJson(sources.queue),readJson(sources.catalog),readJson(sources.recovery,true),readJson(sources.watchdog,true),readJson(sources.runtime,true),readActions()
      ]);
      render({status,queue,catalog,recovery,watchdog,runtime,actionsPayload});
    }catch(error){
      $('syncState').textContent='连接失败';
      $('lastSync').textContent=`${error.message||error}`;
    }
  }

  refresh();timer=setInterval(refresh,DATA_POLL_MS);
  addEventListener('pagehide',()=>clearInterval(timer),{once:true});
})();