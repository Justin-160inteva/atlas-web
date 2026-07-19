(() => {
  'use strict';

  const VERSION='0.1.0';
  const STATUS_URL='data/batch-analysis/eleven-pilot-scan-status.json';
  let evidenceBypass=false;
  let statusTimer=0;

  const $=selector=>document.querySelector(selector);

  function inject(){
    const shell=$('.app-shell');
    if(!shell||$('#settingsPanel'))return;
    shell.insertAdjacentHTML('beforeend',`
      <section class="settings-panel glass" id="settingsPanel" aria-hidden="true" aria-label="Atlas 设置">
        <header>
          <div><small>ATLAS SETTINGS</small><h2>设置</h2></div>
          <button class="settings-close" id="closeSettings" aria-label="关闭设置">×</button>
        </header>
        <div class="settings-scroll">
          <section class="settings-section">
            <div class="settings-section-title"><b>开发者选项</b><small>重建与导入工具</small></div>
            <button class="settings-card" id="openScanMonitor">
              <span class="settings-card-icon">◫</span>
              <span class="settings-card-copy">
                <b>扫描与导入进度</b>
                <small id="scanMonitorSummary">正在读取任务状态…</small>
                <span class="settings-live" id="scanMonitorLive" data-state="idle"><i></i><em>同步中</em></span>
              </span>
              <span class="settings-card-arrow">›</span>
            </button>
            <button class="settings-card" id="openEvidenceLab">
              <span class="settings-card-icon">⌁</span>
              <span class="settings-card-copy"><b>证据重建实验室</b><small>本地视频、关键帧、锚点与建筑审核</small></span>
              <span class="settings-card-arrow">›</span>
            </button>
          </section>
          <section class="settings-section">
            <div class="settings-section-title"><b>关于</b><small>开发预览</small></div>
            <div class="settings-about"><p><b>Atlas · 刺客信条：影</b><br>扫描监控模块 ${VERSION}。公开页面只显示脱敏进度，不展示授权凭证、Cookie、媒体地址或原始视频画面。</p></div>
          </section>
        </div>
      </section>
      <section class="monitor-overlay" id="scanMonitorOverlay" aria-hidden="true" aria-label="扫描与导入进度">
        <div class="monitor-toolbar">
          <button class="monitor-close" id="closeScanMonitor" aria-label="返回设置">‹</button>
          <div class="monitor-toolbar-copy"><b>扫描与导入进度</b><small>11的游戏世界 · 山城试验队列</small></div>
          <button class="monitor-refresh" id="refreshScanMonitor" aria-label="刷新进度">↻</button>
        </div>
        <iframe class="monitor-frame" id="scanMonitorFrame" title="Atlas 扫描与导入进度" loading="lazy"></iframe>
      </section>`);
  }

  function stateFrom(status){
    const phase=String(status?.phase||'').toLowerCase();
    const summary=status?.summary||{};
    if(status?.complete)return 'complete';
    if(phase.includes('recover')||summary.retryableFailed>0)return 'recovery';
    if(phase.includes('block')||summary.blocked>0)return 'blocked';
    if(phase.includes('run')||summary.running>0)return 'running';
    return 'idle';
  }

  function labelFor(state){
    return({running:'运行中',recovery:'自动恢复',blocked:'需要检查',complete:'已完成',idle:'等待中'})[state]||'等待中';
  }

  async function refreshBadge(){
    try{
      const response=await fetch(`${STATUS_URL}?t=${Date.now()}`,{cache:'no-store'});
      if(!response.ok)throw new Error(String(response.status));
      const status=await response.json();
      const summary=status.summary||{};
      const imported=Number(summary.imported||0);
      const total=Number(summary.total||3);
      const active=status.activeItem?.page||status.items?.find(item=>item.state==='running')?.page||status.items?.find(item=>item.state==='pending')?.page;
      const stateName=stateFrom(status);
      const summaryNode=$('#scanMonitorSummary');
      const live=$('#scanMonitorLive');
      if(summaryNode)summaryNode.textContent=`山城试验 ${imported}/${total}${active?` · 当前 P${active}`:''}`;
      if(live){live.dataset.state=stateName;const text=live.querySelector('em');if(text)text.textContent=labelFor(stateName);}
    }catch(_){
      const summaryNode=$('#scanMonitorSummary');
      const live=$('#scanMonitorLive');
      if(summaryNode)summaryNode.textContent='暂时无法读取远端状态';
      if(live){live.dataset.state='idle';const text=live.querySelector('em');if(text)text.textContent='等待同步';}
    }
  }

  function openSettings(){
    if(typeof closePanels==='function')closePanels();
    $('#settingsPanel')?.classList.add('open');
    $('#settingsPanel')?.setAttribute('aria-hidden','false');
    refreshBadge();
  }

  function closeSettings(){
    $('#settingsPanel')?.classList.remove('open');
    $('#settingsPanel')?.setAttribute('aria-hidden','true');
  }

  function openMonitor(){
    const overlay=$('#scanMonitorOverlay');
    const frame=$('#scanMonitorFrame');
    if(frame&&!frame.src)frame.src='scan-monitor.html?embedded=1';
    overlay?.classList.add('open');
    overlay?.setAttribute('aria-hidden','false');
  }

  function closeMonitor(){
    const overlay=$('#scanMonitorOverlay');
    overlay?.classList.remove('open');
    overlay?.setAttribute('aria-hidden','true');
  }

  function openEvidence(){
    closeSettings();
    evidenceBypass=true;
    $('#evidenceStudioBtn')?.click();
    evidenceBypass=false;
  }

  function bind(){
    const gear=$('#evidenceStudioBtn');
    gear?.addEventListener('click',event=>{
      if(evidenceBypass)return;
      event.preventDefault();event.stopPropagation();event.stopImmediatePropagation();
      openSettings();
    },true);
    $('#closeSettings')?.addEventListener('click',closeSettings);
    $('#openScanMonitor')?.addEventListener('click',openMonitor);
    $('#closeScanMonitor')?.addEventListener('click',closeMonitor);
    $('#openEvidenceLab')?.addEventListener('click',openEvidence);
    $('#refreshScanMonitor')?.addEventListener('click',()=>{
      const frame=$('#scanMonitorFrame');
      if(frame)frame.src=`scan-monitor.html?embedded=1&t=${Date.now()}`;
      refreshBadge();
    });
    document.addEventListener('keydown',event=>{
      if(event.key!=='Escape')return;
      if($('#scanMonitorOverlay')?.classList.contains('open'))closeMonitor();
      else if($('#settingsPanel')?.classList.contains('open'))closeSettings();
    });
  }

  function init(){
    inject();bind();refreshBadge();
    statusTimer=window.setInterval(refreshBadge,30000);
    window.AtlasSettings={open:openSettings,close:closeSettings,openMonitor,refresh:refreshBadge,version:VERSION};
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
  addEventListener('pagehide',()=>clearInterval(statusTimer),{once:true});
})();
