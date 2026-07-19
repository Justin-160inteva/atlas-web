(() => {
  'use strict';
  const REPO='Justin-160inteva/atlas-web';
  const URL=`https://raw.githubusercontent.com/${REPO}/main/data/runtime-progress/eleven-pilot-progress.json`;
  const POLL_MS=10000;
  let timer=0;
  const $=id=>document.getElementById(id);
  const mb=value=>Number.isFinite(Number(value))?`${(Number(value)/1048576).toFixed(1)} MB`:'—';
  const speed=value=>Number.isFinite(Number(value))?`${(Number(value)/1048576).toFixed(2)} MB/s`:'—';
  const eta=value=>{
    const seconds=Math.max(0,Number(value)||0);
    if(!seconds)return '—';
    if(seconds<60)return `${Math.ceil(seconds)}秒`;
    if(seconds<3600)return `${Math.ceil(seconds/60)}分钟`;
    return `${Math.floor(seconds/3600)}小时 ${Math.ceil((seconds%3600)/60)}分钟`;
  };
  async function refresh(){
    try{
      const response=await fetch(`${URL}?t=${Date.now()}`,{cache:'no-store',headers:{Accept:'application/json'}});
      if(!response.ok)throw new Error(String(response.status));
      const data=await response.json();
      const downloaded=Number(data.downloadedBytes||0);
      const total=Number(data.totalBytes||0);
      const segmentDownloaded=Number(data.segmentDownloadedBytes||0);
      const segmentTotal=Number(data.segmentTotalBytes||0);
      const ratio=total>0?Math.min(100,downloaded/total*100):0;
      const segmentRatio=segmentTotal>0?Math.min(100,segmentDownloaded/segmentTotal*100):0;
      $('downloadedAmount').textContent=total>0?`${mb(downloaded)} / ${mb(total)}`:mb(downloaded);
      $('downloadSpeed').textContent=speed(data.speedBytesPerSecond);
      $('downloadSegment').textContent=data.segmentCount?`${data.segmentIndex||0} / ${data.segmentCount}`:'—';
      $('downloadEta').textContent=eta(data.etaSeconds);
      $('downloadBar').style.width=`${ratio}%`;
      $('segmentBar').style.width=`${segmentRatio}%`;
      $('downloadDetail').textContent=data.stage==='download'
        ?`总下载 ${ratio.toFixed(1)}% · 当前分片 ${segmentRatio.toFixed(1)}% · 每60秒至少写入一次公开心跳`
        :data.stage==='remuxing'?'下载完成，正在转封装':data.stage==='frame-analysis'||data.stage==='analysis'?'下载完成，正在数值分析':'等待下载遥测';
      $('downloadTelemetry').dataset.active=data.stage==='download'?'true':'false';
    }catch(error){
      $('downloadDetail').textContent=`下载遥测读取失败：${error.message||error}`;
      $('downloadTelemetry').dataset.active='false';
    }
  }
  refresh();
  timer=setInterval(refresh,POLL_MS);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
  addEventListener('message',event=>{if(event.data?.type==='atlas-monitor-refresh')refresh();});
  addEventListener('pagehide',()=>clearInterval(timer),{once:true});
})();
