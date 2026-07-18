(() => {
  'use strict';

  const coarse=matchMedia('(pointer:coarse)').matches||/iPad|iPhone|iPod|Android/i.test(navigator.userAgent);
  const memory=Number(navigator.deviceMemory||8);
  const cores=Number(navigator.hardwareConcurrency||8);
  const lowPower=memory<=4||cores<=4;
  const TILE_SOURCE=512;
  const GRID=4096/TILE_SOURCE;
  const OUTPUT_SIZE=coarse?(lowPower?576:704):(lowPower?768:896);
  const MAX_CACHE=coarse?6:(lowPower?9:12);
  const HD_THRESHOLD=coarse?2.3:2;
  const PRELOAD_MARGIN=coarse?0:1;
  const SHARPEN_AMOUNT=!coarse&&!lowPower?.06:0;
  const cache=new Map();
  const queue=[];
  const queued=new Set();
  let workerPending=false;
  let generationPaused=false;
  let visibleCount=-1;

  const now=()=>performance.now();
  const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
  const interactionActive=()=>Boolean(
    document.documentElement.classList.contains('atlas-button-zooming')||
    window.AtlasPerf092?.interacting||
    window.AtlasMobilePerf?.interacting||
    window.AtlasDesktopPerf?.interacting||
    state.drag||state.pointers?.size
  );
  const performanceMode=()=>Number(window.AtlasPerf092?.qualityLevel||0)>=2;

  function key(x,y){return `${x}:${y}`}
  function clampByte(value){return value<0?0:value>255?255:value}

  function sharpen(canvas){
    if(SHARPEN_AMOUNT<=0)return;
    const context=canvas.getContext('2d',{willReadFrequently:true});
    let image;
    try{image=context.getImageData(0,0,canvas.width,canvas.height)}catch(_){return}
    const data=image.data;
    const source=new Uint8ClampedArray(data);
    const row=canvas.width*4;
    for(let y=1;y<canvas.height-1;y++){
      let index=y*row+4;
      const end=y*row+(canvas.width-1)*4;
      for(;index<end;index+=4){
        for(let channel=0;channel<3;channel++){
          const i=index+channel;
          const lap=4*source[i]-source[i-4]-source[i+4]-source[i-row]-source[i+row];
          data[i]=clampByte(source[i]+lap*SHARPEN_AMOUNT);
        }
      }
    }
    context.putImageData(image,0,0);
  }

  function generateTile(tileX,tileY){
    if(!state.imageReady||interactionActive()||performanceMode()||document.hidden)return false;
    const tileCanvas=typeof OffscreenCanvas==='function'?new OffscreenCanvas(OUTPUT_SIZE,OUTPUT_SIZE):document.createElement('canvas');
    tileCanvas.width=OUTPUT_SIZE;
    tileCanvas.height=OUTPUT_SIZE;
    const context=tileCanvas.getContext('2d',{alpha:false,willReadFrequently:SHARPEN_AMOUNT>0});
    context.imageSmoothingEnabled=true;
    context.imageSmoothingQuality='high';
    context.fillStyle='#11110f';
    context.fillRect(0,0,OUTPUT_SIZE,OUTPUT_SIZE);
    context.filter='contrast(1.045) saturate(1.02) brightness(1.008)';
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
    sharpen(tileCanvas);
    cache.set(key(tileX,tileY),{canvas:tileCanvas,lastUsed:now(),readyAt:now()});
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
    if(generationPaused||interactionActive()||performanceMode()||document.hidden)return;
    let generated=0;
    while(queue.length){
      if(deadline&&generated>0&&deadline.timeRemaining()<6)break;
      const item=queue.shift();
      queued.delete(item.key);
      if(cache.has(item.key))continue;
      if(generateTile(item.x,item.y))generated++;
      if(generated>=1)break;
    }
    if(queue.length)scheduleWorker();
  }

  function scheduleWorker(){
    if(workerPending||generationPaused||interactionActive()||performanceMode()||!queue.length||document.hidden)return;
    workerPending=true;
    if('requestIdleCallback'in window){
      requestIdleCallback(processQueue);
    }else{
      setTimeout(()=>processQueue(null),80);
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
    if(!state.imageReady||interactionActive()||performanceMode())return;
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

  function drawBaseMap(context){
    if(!state.imageReady)return;
    const scale=state.scale;
    const sourceX=clamp((-state.offsetX)/scale,0,4096);
    const sourceY=clamp((-state.offsetY)/scale,0,4096);
    const sourceRight=clamp((innerWidth-state.offsetX)/scale,0,4096);
    const sourceBottom=clamp((innerHeight-state.offsetY)/scale,0,4096);
    const sourceWidth=sourceRight-sourceX;
    const sourceHeight=sourceBottom-sourceY;
    if(sourceWidth<=0||sourceHeight<=0)return;
    const screenX=state.offsetX+sourceX*scale;
    const screenY=state.offsetY+sourceY*scale;
    context.save();
    context.globalAlpha=.92;
    context.imageSmoothingEnabled=true;
    context.imageSmoothingQuality=interactionActive()?'low':'high';
    context.drawImage(
      state.image,
      sourceX,sourceY,sourceWidth,sourceHeight,
      screenX,screenY,sourceWidth*scale,sourceHeight*scale
    );
    context.restore();
  }

  function drawVisible(context){
    if(!state.imageReady||interactionActive()||performanceMode())return;
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

  draw=function(){
    ctx.fillStyle='#070707';
    ctx.fillRect(0,0,innerWidth,innerHeight);
    drawBaseMap(ctx);
    drawVisible(ctx);
    drawRoute();
    const list=visibleLocations();
    const relative=state.scale/fitScale();
    state.markers=buildMarkers(list);
    for(const marker of state.markers)drawMarker(marker,relative);
    if(list.length!==visibleCount){
      visibleCount=list.length;
      el('visibleCount').textContent=String(visibleCount);
    }
  };

  const pause=()=>{generationPaused=true};
  const resume=()=>{
    generationPaused=false;
    clearTimeout(resume._timer);
    resume._timer=setTimeout(()=>{prepareVisible();scheduleDraw()},110);
  };
  mapCanvas.addEventListener('pointerdown',pause,{capture:true,passive:true});
  mapCanvas.addEventListener('pointerup',resume,{capture:true,passive:true});
  mapCanvas.addEventListener('pointercancel',resume,{capture:true,passive:true});
  mapCanvas.addEventListener('wheel',()=>{pause();clearTimeout(resume._wheel);resume._wheel=setTimeout(resume,170)},{capture:true,passive:true});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();else resume()});

  window.AtlasHDMap={cache,queue,prepareVisible,threshold:HD_THRESHOLD,outputSize:OUTPUT_SIZE};
  setTimeout(()=>{prepareVisible();scheduleDraw()},560);
})();
