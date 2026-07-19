(() => {
  'use strict';
  const VERSION='0.4.0';
  const FALLBACK_POLL_MS=30000;
  const REPO='Justin-160inteva/atlas-web';
  const URL=`https://raw.githubusercontent.com/${REPO}/main/data/runtime-progress/eleven-pilot-progress.json`;
  let timer=0;
  let lastRuntime=null;
  const $=id=>document.getElementById(id);
  const mbNumber=value=>Number(value||0)/1048576;
  const mb=value=>Number.isFinite(Number(value))?`${mbNumber(value).toFixed(1)} MB`:'—';
  const speed=value=>Number.isFinite(Number(value))?`${mbNumber(value).toFixed(2)} MB/s`:'—';
  const eta=value=>{
    const seconds=Math.max(0,Number(value)||0);
    if(!seconds)return '—';
    if(seconds<60)return `${Math.ceil(seconds)}秒`;
    if(seconds<3600)return `${Math.ceil(seconds/60)}分钟`;
    return `${Math.floor(seconds/3600)}小时 ${Math.ceil((seconds%3600)/60)}分钟`;
  };
  const ageSeconds=value=>{
    const time=Date.parse(value||'');
    return Number.isFinite(time)?Math.max(0,Math.round((Date.now()-time)/1000)):null;
  };
  const valid=data=>data&&Number(data.schemaVersion)>=2&&typeof data.state==='string'&&typeof data.stage==='string'&&Number.isFinite(Date.parse(data.updatedAt||''));

  function render(data,previous=null,origin='GitHub main'){
    if(!valid(data))return;
    const downloaded=Number(data.downloadedBytes||0);
    const total=Number(data.totalBytes||0);
    const segmentDownloaded=Number(data.segmentDownloadedBytes||0);
    const segmentTotal=Number(data.segmentTotalBytes||0);
    const ratio=total>0?Math.min(100,downloaded/total*100):0;
    const segmentRatio=segmentTotal>0?Math.min(100,segmentDownloaded/segmentTotal*100):0;
    const rolling=Number(data.speedBytesPerSecond||0);
    const average=Number(data.averageSpeedBytesPerSecond||0);
    const age=ageSeconds(data.updatedAt);
    const sequence=Number(data.heartbeatSequence||0);
    const previousBytes=previous&&previous.externalSourceId===data.externalSourceId?Number(previous.downloadedBytes||0):downloaded;
    const delta=Math.max(0,downloaded-previousBytes);
    const stalled=Math.max(Number(data.stalledSeconds||0),age||0);

    $('downloadedAmount').textContent=total>0?`${mb(downloaded)} / ${mb(total)}`:mb(downloaded);
    $('downloadSpeed').textContent=average>0?`${speed(rolling)} · 平均 ${speed(average)}`:speed(rolling);
    $('downloadSegment').textContent=data.segmentCount?`${data.segmentIndex||0} / ${data.segmentCount}`:'—';
    $('downloadEta').textContent=eta(data.etaSeconds);
    $('downloadBar').style.width=`${ratio}%`;
    $('segmentBar').style.width=`${segmentRatio}%`;
    const meta=$('downloadHeartbeatMeta');
    if(meta)meta.textContent=sequence?`心跳 #${sequence} · ${origin}`:`等待任务心跳 · ${origin}`;

    let detail='等待下载遥测';
    let health='idle';
    if(data.stage==='download'){
      health='live';
      if(downloaded===0&&stalled<120){
        detail=`已连接下载任务，等待媒体服务器返回首字节 · 心跳 #${sequence||'—'} · ${age??'—'}秒前`;
      }else if(stalled>=180){
        health='danger';
        detail=`下载数据已停滞约${Math.round(stalled)}秒，超过故障阈值；自动调查器应立即核对网络、分片与任务租约`;
      }else if(delta>0){
        detail=`下载正常 · 本次心跳新增 ${mb(delta)} · 总进度 ${ratio.toFixed(1)}% · 当前分片 ${segmentRatio.toFixed(1)}%`;
      }else if(downloaded>0){
        health=stalled>=120?'warn':'live';
        detail=`心跳正常但本轮未增加字节 · 已下载 ${mb(downloaded)} · 停滞 ${Math.round(stalled)}秒 · 心跳 #${sequence||'—'}`;
      }
    }else if(['remuxing','remux','transcoding'].includes(data.stage))detail='下载完成，正在转封装';
    else if(['frame-analysis','analysis','analyzing'].includes(data.stage))detail='下载完成，正在抽帧与数值分析';
    else if(['indexing','persisting','cleanup','complete'].includes(data.stage))detail='下载与分析已完成，正在写入或持久化状态';

    $('downloadDetail').textContent=detail;
    $('downloadDetail').dataset.health=health;
    $('downloadTelemetry').dataset.active=data.stage==='download'?'true':'false';
    lastRuntime=data;
  }

  async function fallbackRefresh(){
    try{
      const response=await fetch(`${URL}?t=${Date.now()}`,{cache:'no-store',headers:{Accept:'application/json'}});
      if(!response.ok)throw new Error(String(response.status));
      const data=await response.json();
      render(data,lastRuntime,'GitHub main直连');
    }catch(error){
      if(!lastRuntime){
        $('downloadDetail').textContent=`下载遥测读取失败：${error.message||error}`;
        $('downloadDetail').dataset.health='danger';
        $('downloadTelemetry').dataset.active='false';
      }
    }
  }

  addEventListener('atlas-runtime-update',event=>{
    const detail=event.detail||{};
    render(detail.runtime,detail.previous||lastRuntime,detail.origin||'统一监控通道');
  });
  document.addEventListener('visibilitychange',()=>{
    if(document.hidden)return;
    const runtime=window.AtlasRuntimeCoherence?.getRuntime?.()||window.AtlasScanMonitor?.getRuntime?.();
    if(runtime)render(runtime,lastRuntime,'统一监控通道');
    else fallbackRefresh();
  });
  addEventListener('message',event=>{if(event.data?.type==='atlas-monitor-refresh')fallbackRefresh();});
  addEventListener('pagehide',()=>clearInterval(timer),{once:true});

  const initial=window.AtlasRuntimeCoherence?.getRuntime?.()||window.AtlasScanMonitor?.getRuntime?.();
  if(initial)render(initial,null,'统一监控通道');
  else fallbackRefresh();
  timer=setInterval(()=>{if(!(window.AtlasRuntimeCoherence?.getRuntime?.()||window.AtlasScanMonitor?.getRuntime?.()))fallbackRefresh();},FALLBACK_POLL_MS);
  window.AtlasDownloadMonitor={render,version:VERSION};
})();