(() => {
  'use strict';
  const VERSION='0.3.2';
  const CHECK_MS=10000;
  const EXPECTED_HEARTBEAT_SECONDS=60;
  const FRESH_SECONDS=150;
  const STALE_SECONDS=180;
  const RAW='https://raw.githubusercontent.com/Justin-160inteva/atlas-web/main/';
  const STATUS=`${RAW}data/batch-analysis/eleven-pilot-scan-status.json`;
  const RUNTIME=`${RAW}data/runtime-progress/eleven-pilot-progress.json`;
  let latest=null;
  let lastCheck=0;

  const $=id=>document.getElementById(id);
  const ageSeconds=value=>{
    const time=Date.parse(value||'');
    return Number.isFinite(time)?Math.max(0,Math.round((Date.now()-time)/1000)):null;
  };
  const label=seconds=>seconds===null?'—':seconds<5?'刚刚':seconds<60?`${seconds}秒前`:seconds<3600?`${Math.floor(seconds/60)}分钟前`:`${Math.floor(seconds/3600)}小时前`;

  async function fetchJson(url,optional=false){
    try{
      const response=await fetch(`${url}?health=${Date.now()}`,{cache:'no-store',headers:{Accept:'application/json'}});
      if(!response.ok)throw new Error(String(response.status));
      return await response.json();
    }catch(error){
      if(optional)return null;
      throw error;
    }
  }

  function validRuntime(payload){
    return payload&&payload.schemaVersion>=2&&typeof payload.state==='string'&&typeof payload.stage==='string'&&Number.isFinite(Date.parse(payload.updatedAt||''));
  }

  function activeId(status){
    return status?.activeItem?.externalSourceId||status?.items?.find(item=>item.state==='running')?.externalSourceId||status?.items?.find(item=>item.state==='pending')?.externalSourceId||null;
  }

  function matchedRuntime(status,runtime){
    if(!validRuntime(runtime))return null;
    const id=activeId(status);
    if(!id)return null;
    if(runtime.externalSourceId&&runtime.externalSourceId!==id)return null;
    return runtime;
  }

  function render(){
    if(!latest)return;
    const {status,runtime}=latest;
    const matched=matchedRuntime(status,runtime);
    const summary=status?.summary||{};
    const phase=String(status?.phase||'').toLowerCase();
    const ageSource=matched?.updatedAt||status?.updatedAt;
    const age=ageSeconds(ageSource);
    const notice=$('freshnessNotice');
    const ageNode=$('heartbeatAge');
    if(ageNode)ageNode.textContent=label(age);
    if(!notice)return;

    if(status?.complete){
      notice.dataset.level='live';
      notice.textContent=`系统健康：当前区域批次已完成，状态核对于${label(age)}更新。旧的运行时心跳不会再触发假警报。`;
    }else if(phase.includes('block')||Number(summary.blocked||0)>0||matched?.state==='blocked'){
      notice.dataset.level='danger';
      notice.textContent='系统已停止自动处理：当前问题需要人工检查，未继续修改任务或授权范围。';
    }else if(matched?.state==='failed'||matched?.state==='recovery'||phase.includes('recover')){
      notice.dataset.level='warn';
      notice.textContent='任务已进入自动调查与恢复；系统正在匹配错误字典，并只对确定可安全恢复的问题重试。';
    }else if((matched?.state==='running'||Number(summary.running||0)>0||phase.includes('run'))&&age!==null&&age<=FRESH_SECONDS){
      notice.dataset.level='live';
      notice.textContent=`系统健康：页面每10秒核对；任务端目标每${EXPECTED_HEARTBEAT_SECONDS}秒发布一次。最新心跳${label(age)}。`;
    }else if((Number(summary.running||0)>0||phase.includes('run'))&&age!==null&&age>STALE_SECONDS){
      notice.dataset.level='danger';
      notice.textContent=`系统警报：当前任务已${label(age)}没有匹配心跳，超过${STALE_SECONDS}秒故障阈值。自动恢复器将核对Actions状态、错误字典和队列租约。`;
    }else if(matched?.state==='queued'){
      notice.dataset.level='info';
      notice.textContent='任务正在排队；被GitHub Actions领取前不会产生下载字节心跳。';
    }
    const sync=$('syncState');
    if(sync)sync.title=`Atlas monitor ${VERSION} · last health check ${new Date(lastCheck).toLocaleTimeString()}`;
  }

  async function check(){
    try{
      const [status,runtime]=await Promise.all([fetchJson(STATUS),fetchJson(RUNTIME,true)]);
      if(!status||typeof status.complete!=='boolean'||!status.summary)throw new Error('invalid status schema');
      if(runtime&&!validRuntime(runtime))throw new Error('invalid runtime schema');
      latest={status,runtime};
      lastCheck=Date.now();
      render();
    }catch(error){
      const notice=$('freshnessNotice');
      if(notice){notice.dataset.level='danger';notice.textContent=`监控健康核对失败：${error.message||error}。主监控会保留最后一次有效状态并在10秒后重试。`;}
    }
  }

  if(window.AtlasScanMonitor)window.AtlasScanMonitor.version=VERSION;
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)check();});
  addEventListener('online',check);
  setInterval(render,1000);
  setInterval(check,CHECK_MS);
  check();
})();
