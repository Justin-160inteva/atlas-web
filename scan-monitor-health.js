(() => {
  'use strict';
  const VERSION='0.3.1';
  const CHECK_MS=10000;
  const EXPECTED_HEARTBEAT_SECONDS=60;
  const FRESH_SECONDS=150;
  const STALE_SECONDS=180;
  const RUNTIME='https://raw.githubusercontent.com/Justin-160inteva/atlas-web/main/data/runtime-progress/eleven-pilot-progress.json';
  let latest=null;
  let lastCheck=0;

  const $=id=>document.getElementById(id);
  const ageSeconds=value=>{
    const time=Date.parse(value||'');
    return Number.isFinite(time)?Math.max(0,Math.round((Date.now()-time)/1000)):null;
  };
  const label=seconds=>seconds===null?'—':seconds<5?'刚刚':seconds<60?`${seconds}秒前`:seconds<3600?`${Math.floor(seconds/60)}分钟前`:`${Math.floor(seconds/3600)}小时前`;

  function valid(payload){
    return payload&&payload.schemaVersion>=2&&typeof payload.state==='string'&&typeof payload.stage==='string'&&typeof payload.updatedAt==='string';
  }

  function render(){
    if(!latest)return;
    const age=ageSeconds(latest.updatedAt);
    const notice=$('freshnessNotice');
    const ageNode=$('heartbeatAge');
    if(ageNode)ageNode.textContent=label(age);
    if(!notice)return;

    if(latest.state==='running'&&age!==null&&age<=FRESH_SECONDS){
      notice.dataset.level='live';
      notice.textContent=`系统健康：页面每10秒核对；任务端目标每${EXPECTED_HEARTBEAT_SECONDS}秒发布一次。最新心跳${label(age)}。`;
    }else if(latest.state==='running'&&age!==null&&age>STALE_SECONDS){
      notice.dataset.level='danger';
      notice.textContent=`系统警报：运行任务已${label(age)}没有心跳，超过${STALE_SECONDS}秒故障阈值。自动恢复器应立即核对任务结果、错误字典和队列租约。`;
    }else if(latest.state==='failed'){
      notice.dataset.level='warn';
      notice.textContent='任务已报告失败；系统正在读取错误字典并执行受限自动调查与重试。';
    }
    const sync=$('syncState');
    if(sync)sync.title=`Atlas monitor ${VERSION} · last health check ${new Date(lastCheck).toLocaleTimeString()}`;
  }

  async function check(){
    try{
      const response=await fetch(`${RUNTIME}?health=${Date.now()}`,{cache:'no-store',headers:{Accept:'application/json'}});
      if(!response.ok)throw new Error(String(response.status));
      const payload=await response.json();
      if(!valid(payload))throw new Error('invalid runtime schema');
      latest=payload;
      lastCheck=Date.now();
      render();
    }catch(error){
      const notice=$('freshnessNotice');
      if(notice){notice.dataset.level='danger';notice.textContent=`监控健康核对失败：${error.message||error}。主监控仍会保留最后一次有效状态并继续重试。`;}
    }
  }

  if(window.AtlasScanMonitor)window.AtlasScanMonitor.version=VERSION;
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)check();});
  addEventListener('online',check);
  setInterval(render,1000);
  setInterval(check,CHECK_MS);
  check();
})();
