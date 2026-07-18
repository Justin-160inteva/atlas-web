(() => {
  'use strict';

  const coarse=matchMedia('(pointer:coarse)').matches||/iPad|iPhone|iPod|Android/i.test(navigator.userAgent);
  const TILE_SOURCE=512;
  const GRID=4096/TILE_SOURCE;
  const OUTPUT_SIZE=coarse?768:1024;
  const MAX_CACHE=coarse?7:16;
  const HD_THRESHOLD=coarse?2.15:1.85;
  const PRELOAD_MARGIN=coarse?0:1;
  const SHARPEN_AMOUNT=coarse?.10:.17;
  const cache=new Map();
  const queue=[];
  const queued=new Set();
  let workerPending=false;
  let generationPaused=false;

  const now=()=>performance.now();
  const interactionActive=()=>Boolean(
    document.documentElement.classList.contains('atlas-button-zooming')||
    window.AtlasMobilePerf?.interacting||
    window.AtlasDesktopPerf?.interacting||
    state.drag||state.pointers?.size
  );

  function key(x,y){return `${x}:${y}`}
  function clampByte(value){return value<0?0:value>255?255:value}

  function sharpen(canvas){
    const context=canvas.getContext('2d',{willReadFrequently:true});
    let image;
    try{image=context.getImageData(0,0,canvas.width,canvas.height)}catch(_){return}
    const data=image.data;
    const source=new Uint8ClampedArray(data);
    const row=canvas.width*4;
    const amount=SHARPEN_AMOUNT;
    for(let y=1;y<canvas.height-1;y++){
      let index=y*row+4;
      const end=y*row+(canvas.width-1)*4;
      for(;index<end;index+=4){
        for(let channel=0;channel<3;channel++){
          const i=index+channel;
          const lap=4*source[i]-source[i-4]-source[i+4]-source[i-row]-source[i+row];
          data[i]=clampByte(source[i]+lap*amount);
        }
      }
    }
    context.putImageData(image,0,0);
  }

  function generateTile(tileX,tileY){
    if(!state.imageReady||interactionActive()||document.hidden)return false;
    const canvas=document.createElement('canvas');
    canvas.width=OUTPUT_SIZE;
    canvas.height=OUTPUT_SIZE;
    const context=canvas.getContext('2d',{alpha:false,willReadFrequently:true});
    context.imageSmoothingEnabled=true;
    context.imageSmoothingQuality='high';
    context.fillStyle='#11110f';
    context.fillRect(0,0,OUTPUT_SIZE,OUTPUT_SIZE);
    context.filter='contrast(1.055) saturate(1.025) brightness(1.01)';
    context.drawImage(
      state.image,
      tileX*TILE_SOURCE,
      tileY*TILE_SOURCE,
      TILE_SOURCE,
      TILE_SOURCE,
      0,
      0,
      OUTPUT_SIZE,
      OUTPUT_SIZE
    );
    context.filter='none';
    sharpen(canvas);
    cache.set(key(tileX,tileY),{canvas,lastUsed:now(),readyAt:now()});
    trimCache();
    scheduleDraw();
    return true;
  }

  function trimCache(){
    if(cache.size<=MAX_CACHE)return;
    const entries=[...cache.entries()].sort((a,b)=>a[1].lastUsed-b[1].lastUsed);
    while(cache.size>MAX_CACHE&&entries.length){
      const [oldKey]=entries.shift();
      cache.delete(oldKey);
    }
  }

  function processQueue(deadline){
    workerPending=false;
    if(generationPaused||interactionActive()||document.hidden)return;
    let generated=0;
    while(queue.length){
      if(deadline&&generated>0&&deadline.timeRemaining()<5)break;
      const item=queue.shift();
      queued.delete(item.key);
      if(cache.has(item.key))continue;
      if(generateTile(item.x,item.y))generated++;
      if(generated>=1)break;
    }
    if(queue.length)scheduleWorker();
  }

  function scheduleWorker(){
    if(workerPending||generationPaused||interactionActive()||!queue.length)return;
    workerPending=true;
    if('requestIdleCallback'in window){
      requestIdleCallback(processQueue,{timeout:550});
    }else{
      setTimeout(()=>processQueue(null),48);
    }
  }

  function queueTile(x,y,priority){
    if(x<0||y<0||x>=GRID||y>=GRID)return;
    const tileKey=key(x,y);
    if(cache.has(tileKey)||queued.has(tileKey))return;
    queued.add(tileKey);
    const item={x,y,key:tileKey,priority};
    let index=queue.findIndex(existing=>existing.priority>priority);
    if(index<0)index=queue.length;
    queue.splice(index,0,item);
  }

  function visibleRange(margin=0){
    const left=(-state.offsetX)/(4096*state.scale);
    const right=(innerWidth-state.offsetX)/(4096*state.scale);
    const top=(-state.offsetY)/(4096*state.scale);
    const bottom=(innerHeight-state.offsetY)/(4096*state.scale);
    return{
      x0:Math.max(0,Math.floor(Math.min(left,right)*GRID)-margin),
      x1:Math.min(GRID-1,Math.floor(Math.max(left,right)*GRID)+margin),
      y0:Math.max(0,Math.floor(Math.min(top,bottom)*GRID)-margin),
      y1:Math.min(GRID-1,Math.floor(Math.max(top,bottom)*GRID)+margin)
    };
  }

  function prepareVisible(){
    if(!state.imageReady)return;
    const relative=state.scale/fitScale();
    if(relative<HD_THRESHOLD)return;
    const range=visibleRange(PRELOAD_MARGIN);
    const centerX=(range.x0+range.x1)/2;
    const centerY=(range.y0+range.y1)/2;
    for(let y=range.y0;y<=range.y1;y++){
      for(let x=range.x0;x<=range.x1;x++){
        queueTile(x,y,Math.hypot(x-centerX,y-centerY));
      }
    }
    scheduleWorker();
  }

  function drawVisible(context){
    if(!state.imageReady)return;
    const relative=state.scale/fitScale();
    if(relative<HD_THRESHOLD)return;
    const range=visibleRange(0);
    const size=TILE_SOURCE*state.scale;
    const stamp=now();
    context.save();
    context.imageSmoothingEnabled=true;
    context.imageSmoothingQuality='high';
    for(let y=range.y0;y<=range.y1;y++){
      for(let x=range.x0;x<=range.x1;x++){
        const entry=cache.get(key(x,y));
        if(!entry)continue;
        entry.lastUsed=stamp;
        const age=stamp-entry.readyAt;
        const alpha=Math.min(.96,.96*Math.max(0,age/170));
        const screenX=state.offsetX+x*TILE_SOURCE*state.scale;
        const screenY=state.offsetY+y*TILE_SOURCE*state.scale;
        context.globalAlpha=alpha;
        context.drawImage(entry.canvas,screenX-.45,screenY-.45,size+.9,size+.9);
      }
    }
    context.restore();
    prepareVisible();
  }

  const previousDraw=draw;
  draw=function(){
    ctx.fillStyle='#070707';
    ctx.fillRect(0,0,innerWidth,innerHeight);
    if(state.imageReady){
      ctx.save();
      ctx.globalAlpha=.92;
      ctx.imageSmoothingEnabled=true;
      ctx.imageSmoothingQuality='high';
      ctx.drawImage(state.image,state.offsetX,state.offsetY,4096*state.scale,4096*state.scale);
      ctx.restore();
      drawVisible(ctx);
    }
    drawRoute();
    const list=visibleLocations();
    const relative=state.scale/fitScale();
    state.markers=buildMarkers(list);
    for(const marker of state.markers)drawMarker(marker,relative);
    el('visibleCount').textContent=list.length;
  };

  const pause=()=>{generationPaused=true};
  const resume=()=>{
    generationPaused=false;
    clearTimeout(resume._timer);
    resume._timer=setTimeout(()=>{prepareVisible();scheduleDraw()},90);
  };
  mapCanvas.addEventListener('pointerdown',pause,{capture:true,passive:true});
  mapCanvas.addEventListener('pointerup',resume,{capture:true,passive:true});
  mapCanvas.addEventListener('pointercancel',resume,{capture:true,passive:true});
  mapCanvas.addEventListener('wheel',()=>{pause();clearTimeout(resume._wheel);resume._wheel=setTimeout(resume,150)},{capture:true,passive:true});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();else resume()});

  window.AtlasHDMap={cache,queue,prepareVisible,threshold:HD_THRESHOLD,outputSize:OUTPUT_SIZE};
  setTimeout(()=>{prepareVisible();scheduleDraw()},500);
})();