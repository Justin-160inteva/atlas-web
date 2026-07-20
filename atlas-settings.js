(() => {
  'use strict';

  const RELEASE=window.AtlasRelease?.version||'0.9.4.7';
  const MODULE_VERSION='0.5.0';
  const MONITOR_VERSION='0.6.1';
  const REPO='Justin-160inteva/atlas-web';
  const RAW_BASE=`https://raw.githubusercontent.com/${REPO}/main/`;
  const STATUS_PATH='data/batch-analysis/eleven-pilot-scan-status.json';
  const RUNTIME_PATH='data/runtime-progress/eleven-pilot-progress.json';
  const RUNTIME_FRESH_MS=150000;
  const EVIDENCE_STORAGE_KEY='atlas-evidence-project-v1';
  const root=document.documentElement;
  let evidenceBypass=false;
  let statusTimer=0;
  let activeView='database';

  const $=selector=>document.querySelector(selector);

  async function fetchJson(path){
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),7000);
    try{
      for(const url of [`${RAW_BASE}${path}`,path]){
        try{
          const response=await fetch(`${url}?t=${Date.now()}`,{cache:'no-store',signal:controller.signal,headers:{Accept:'application/json'}});
          if(response.ok)return await response.json();
        }catch(error){if(error.name==='AbortError')throw error;}
      }
      throw new Error('status unavailable');
    }finally{clearTimeout(timeout);}
  }

  function ageLabel(value){
    const time=Date.parse(value||'');
    if(!Number.isFinite(time))return '时间未知';
    const seconds=Math.max(0,Math.round((Date.now()-time)/1000));
    if(seconds<60)return `${seconds}秒前`;
    if(seconds<3600)return `${Math.floor(seconds/60)}分钟前`;
    return `${Math.floor(seconds/3600)}小时前`;
  }

  function inject(){
    const shell=$('.app-shell');
    if(!shell||$('#settingsPanel'))return;
    shell.insertAdjacentHTML('beforeend',`
      <section class="settings-panel glass atlas-data-center" id="settingsPanel" aria-hidden="true" aria-label="Atlas 数据与证据中心">
        <header>
          <div class="data-center-heading"><small>ATLAS DATA & EVIDENCE</small><h2>数据与证据中心</h2><span id="dataCenterHeaderState">正在核对数据库</span></div>
          <button class="settings-close" id="closeSettings" aria-label="关闭数据与证据中心">×</button>
        </header>
        <div class="data-center-tabs" role="tablist" aria-label="数据与证据中心视图">
          <button class="active" id="dataCenterDatabaseTab" data-center-tab="database" role="tab" aria-selected="true">数据库</button>
          <button id="dataCenterEvidenceTab" data-center-tab="evidence" role="tab" aria-selected="false">证据工具 <small id="evidenceTabCount">0</small></button>
        </div>
        <div class="settings-scroll">
          <section class="data-center-view active" data-center-view="database" role="tabpanel" aria-labelledby="dataCenterDatabaseTab">
            <div class="data-center-metrics" aria-label="数据库状态摘要">
              <article><b id="dataCenterImported">—</b><small>已导入任务</small></article>
              <article><b id="dataCenterQueue">—</b><small>队列总数</small></article>
              <article><b id="dataCenterActive">—</b><small>当前任务</small></article>
              <article><b id="dataCenterHeartbeat">—</b><small>心跳序号</small></article>
            </div>
            <section class="settings-section">
              <div class="settings-section-title"><b>生产数据库</b><small id="dataCenterUpdated">等待同步</small></div>
              <button class="settings-card settings-primary-card" id="openScanMonitor">
                <span class="settings-card-icon" aria-hidden="true">◫</span>
                <span class="settings-card-copy">
                  <b>扫描、导入与数据库状态</b>
                  <small id="scanMonitorSummary">正在读取 GitHub main…</small>
                  <span class="settings-live" id="scanMonitorLive" data-state="idle"><i></i><em>同步中</em></span>
                </span>
                <span class="settings-card-arrow">›</span>
              </button>
            </section>
            <section class="settings-section">
              <div class="settings-section-title"><b>本机证据库</b><small>仅保存在当前设备</small></div>
              <button class="settings-card" id="openEvidenceWorkspace">
                <span class="settings-card-icon settings-card-icon-evidence" aria-hidden="true">⌁</span>
                <span class="settings-card-copy"><b>证据项目与地图重建</b><small id="localEvidenceSummary">正在读取本机证据项目…</small></span>
                <span class="settings-card-arrow">›</span>
              </button>
            </section>
            <section class="settings-section">
              <div class="settings-section-title"><b>数据边界</b><small>安全与隐私</small></div>
              <div class="settings-about"><p><b>统一状态，分离存储。</b><br>生产扫描只公开脱敏任务状态；本地视频与关键帧不会上传。数据库状态与证据工具共用一个入口，但仍保持各自的数据边界。</p></div>
            </section>
          </section>
          <section class="data-center-view data-center-evidence-view" data-center-view="evidence" role="tabpanel" aria-labelledby="dataCenterEvidenceTab" aria-hidden="true">
            <div class="data-center-evidence-intro"><div><b>证据重建工作区</b><small>本地视频、关键帧、锚点、覆盖与建筑审核</small></div><span>本机存储</span></div>
            <div class="settings-evidence-host" id="settingsEvidenceHost"></div>
          </section>
        </div>
      </section>
      <section class="monitor-overlay" id="scanMonitorOverlay" aria-hidden="true" aria-label="扫描、导入与数据库状态">
        <div class="monitor-toolbar">
          <button class="monitor-close" id="closeScanMonitor" aria-label="返回数据与证据中心">‹</button>
          <div class="monitor-toolbar-copy"><b>扫描、导入与数据库状态</b><small>数据与证据中心 · 11的游戏世界顺序队列</small></div>
          <button class="monitor-refresh" id="refreshScanMonitor" aria-label="重新载入并立即核对 GitHub main">↻</button>
        </div>
        <iframe class="monitor-frame" id="scanMonitorFrame" title="Atlas 扫描、导入与数据库状态" loading="lazy"></iframe>
      </section>`);
  }

  function mountEvidencePanel(){
    const panel=$('#evidencePanel');
    const host=$('#settingsEvidenceHost');
    if(!panel||!host)return false;
    if(panel.parentElement!==host)host.appendChild(panel);
    panel.dataset.unifiedCenter='1';
    panel.setAttribute('aria-label','Atlas 证据重建工作区');
    const legacyClose=$('#closeEvidenceStudio');
    if(legacyClose)legacyClose.hidden=true;
    return true;
  }

  function evidenceProject(){
    try{
      const runtime=window.AtlasEvidence?.project?.();
      if(runtime)return runtime;
      return JSON.parse(localStorage.getItem(EVIDENCE_STORAGE_KEY)||'null');
    }catch(_){return null;}
  }

  function refreshEvidenceSummary(){
    const project=evidenceProject()||{};
    const sources=Array.isArray(project.sources)?project.sources.length:0;
    const frames=Array.isArray(project.frames)?project.frames.length:0;
    const buildings=Array.isArray(project.buildings)?project.buildings.length:0;
    const anchors=Array.isArray(project.anchors)?project.anchors.length:0;
    const summary=`${sources} 个视频 · ${frames} 帧 · ${anchors} 个锚点 · ${buildings} 个建筑`;
    const node=$('#localEvidenceSummary');
    if(node)node.textContent=summary;
    const count=$('#evidenceTabCount');
    if(count)count.textContent=String(frames+anchors+buildings);
  }

  function stateFrom(status,runtime){
    const phase=String(status?.phase||'').toLowerCase();
    const summary=status?.summary||{};
    const runtimeState=String(runtime?.state||'').toLowerCase();
    if(status?.complete)return 'complete';
    if(runtimeState==='blocked'||phase.includes('block')||summary.blocked>0)return 'blocked';
    if(['failed','recovery'].includes(runtimeState)||phase.includes('recover')||summary.retryableFailed>0)return 'recovery';
    if(runtimeState==='running'||phase.includes('run')||summary.running>0)return 'running';
    if(runtimeState==='queued')return 'queued';
    return 'idle';
  }

  function labelFor(state){
    return({running:'运行中',queued:'排队中',recovery:'自动恢复',blocked:'需要检查',complete:'已完成',idle:'等待中'})[state]||'等待中';
  }

  async function refreshDatabaseStatus(){
    try{
      const [status,runtime]=await Promise.all([fetchJson(STATUS_PATH),fetchJson(RUNTIME_PATH).catch(()=>null)]);
      const summary=status.summary||{};
      const imported=Number(summary.imported||0);
      const total=Number(summary.total||status.items?.length||0);
      const ids=new Set((status.items||[]).map(item=>item.externalSourceId));
      const runtimeTime=Date.parse(runtime?.updatedAt||'');
      const runtimeFresh=runtime&&Number.isFinite(runtimeTime)&&ids.has(runtime.externalSourceId)&&Date.now()-runtimeTime<=RUNTIME_FRESH_MS?runtime:null;
      const active=runtimeFresh?.page||status.activeItem?.page||status.items?.find(item=>item.state==='running')?.page||status.items?.find(item=>item.state==='pending')?.page;
      const stateName=stateFrom(status,runtimeFresh);
      const updated=runtimeFresh?.updatedAt||status.updatedAt;
      const heartbeat=Number(runtimeFresh?.heartbeatSequence||0);
      const region=status.pilotRegion||'生产队列';
      const fields={dataCenterImported:imported,dataCenterQueue:total,dataCenterActive:active?`P${active}`:'—',dataCenterHeartbeat:heartbeat?`#${heartbeat}`:'—'};
      Object.entries(fields).forEach(([id,value])=>{const node=document.getElementById(id);if(node)node.textContent=String(value);});
      const summaryNode=$('#scanMonitorSummary');
      if(summaryNode)summaryNode.textContent=`${region} ${imported}/${total}${active?` · P${active}`:''}${heartbeat?` · 心跳 #${heartbeat}`:''}`;
      const live=$('#scanMonitorLive');
      if(live){live.dataset.state=stateName;const text=live.querySelector('em');if(text)text.textContent=labelFor(stateName);}
      const updatedNode=$('#dataCenterUpdated');
      if(updatedNode)updatedNode.textContent=`数据${ageLabel(updated)}`;
      const header=$('#dataCenterHeaderState');
      if(header)header.textContent=`${labelFor(stateName)} · ${ageLabel(updated)}`;
    }catch(_){
      const summaryNode=$('#scanMonitorSummary');
      if(summaryNode)summaryNode.textContent='本轮状态核对失败，10秒后自动重试';
      const live=$('#scanMonitorLive');
      if(live){live.dataset.state='idle';const text=live.querySelector('em');if(text)text.textContent='等待同步';}
      const header=$('#dataCenterHeaderState');
      if(header)header.textContent='数据库暂时不可用';
    }
    refreshEvidenceSummary();
  }

  function setView(view){
    activeView=view==='evidence'?'evidence':'database';
    document.querySelectorAll('[data-center-tab]').forEach(button=>{
      const active=button.dataset.centerTab===activeView;
      button.classList.toggle('active',active);
      button.setAttribute('aria-selected',active?'true':'false');
    });
    document.querySelectorAll('[data-center-view]').forEach(section=>{
      const active=section.dataset.centerView===activeView;
      section.classList.toggle('active',active);
      section.setAttribute('aria-hidden',active?'false':'true');
    });
    $('#settingsPanel')?.classList.toggle('evidence-active',activeView==='evidence');
    if(activeView==='evidence'){
      mountEvidencePanel();
      evidenceBypass=true;
      $('#evidenceStudioBtn')?.click();
      evidenceBypass=false;
      refreshEvidenceSummary();
    }else if($('#evidencePanel')?.classList.contains('open')){
      $('#closeEvidenceStudio')?.click();
    }
  }

  function openSettings(view='database'){
    if(typeof closePanels==='function')closePanels();
    mountEvidencePanel();
    $('#settingsPanel')?.classList.add('open');
    $('#settingsPanel')?.setAttribute('aria-hidden','false');
    setView(view);
    refreshDatabaseStatus();
  }

  function closeSettings(){
    if($('#evidencePanel')?.classList.contains('open'))$('#closeEvidenceStudio')?.click();
    $('#settingsPanel')?.classList.remove('open','evidence-active');
    $('#settingsPanel')?.setAttribute('aria-hidden','true');
  }

  function monitorUrl(force=false){
    return `scan-monitor.html?embedded=1&v=${MONITOR_VERSION}${force?`&reload=${Date.now()}`:''}`;
  }

  function requestMonitorRefresh(forceReload=false){
    const frame=$('#scanMonitorFrame');
    if(forceReload&&frame)frame.src=monitorUrl(true);
    else{try{frame?.contentWindow?.postMessage({type:'atlas-monitor-refresh'},location.origin);}catch(_){/* iframe may still be loading */}}
    refreshDatabaseStatus();
  }

  function openMonitor(){
    const overlay=$('#scanMonitorOverlay');
    const frame=$('#scanMonitorFrame');
    if(frame&&(!frame.src||!frame.src.includes(`v=${MONITOR_VERSION}`)))frame.src=monitorUrl(false);
    overlay?.classList.add('open');
    overlay?.setAttribute('aria-hidden','false');
    setTimeout(()=>requestMonitorRefresh(false),180);
  }

  function closeMonitor(){
    const overlay=$('#scanMonitorOverlay');
    overlay?.classList.remove('open');
    overlay?.setAttribute('aria-hidden','true');
  }

  function bind(){
    const gear=$('#evidenceStudioBtn');
    gear?.addEventListener('click',event=>{
      if(evidenceBypass)return;
      event.preventDefault();event.stopPropagation();event.stopImmediatePropagation();
      openSettings('database');
    },true);
    $('#closeSettings')?.addEventListener('click',closeSettings);
    $('#openScanMonitor')?.addEventListener('click',openMonitor);
    $('#closeScanMonitor')?.addEventListener('click',closeMonitor);
    $('#refreshScanMonitor')?.addEventListener('click',()=>requestMonitorRefresh(true));
    $('#openEvidenceWorkspace')?.addEventListener('click',()=>setView('evidence'));
    document.querySelectorAll('[data-center-tab]').forEach(button=>button.addEventListener('click',()=>setView(button.dataset.centerTab)));
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshDatabaseStatus();});
    document.addEventListener('keydown',event=>{
      if(event.key!=='Escape')return;
      if($('#scanMonitorOverlay')?.classList.contains('open'))closeMonitor();
      else if($('#settingsPanel')?.classList.contains('open'))closeSettings();
    });
  }

  function init(){
    inject();mountEvidencePanel();bind();refreshDatabaseStatus();
    statusTimer=window.setInterval(refreshDatabaseStatus,10000);
    root.dataset.atlasDataCenter=RELEASE;
    window.AtlasSettings={open:openSettings,close:closeSettings,openMonitor,openEvidence:()=>openSettings('evidence'),setView,refresh:refreshDatabaseStatus,version:MODULE_VERSION,release:RELEASE};
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
  addEventListener('pagehide',()=>clearInterval(statusTimer),{once:true});
})();
