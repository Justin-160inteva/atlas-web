(() => {
  'use strict';

  const coarse=matchMedia('(pointer:coarse)').matches||/iPad|iPhone|iPod|Android/i.test(navigator.userAgent);
  if(coarse)return;

  const canvas=document.getElementById('mapCanvas');
  const perf={
    interacting:false,
    pointerActive:false,
    wheelTimer:0,
    settleTimer:0,
    frameTimer:0,
    lastFrame:0,
    grid:null,
    gridSource:null,
    gridSize:64,
    maxCanvasPixels:8_000_000,
    dpr:1
  };

  window.AtlasDesktopPerf=perf;
  document.documentElement.classList.add('atlas-desktop-performance');

  function setInteracting(value,settle=90){
    perf.interacting=value;
    document.documentElement.classList.toggle('atlas-desktop-interacting',value);
    clearTimeout(perf.settleTimer);
    if(!value){
      perf.settleTimer=setTimeout(()=>{
        scheduleDraw();
      },settle);
    }
  }

  canvas.addEventListener('pointerdown',()=>{
    perf.pointerActive=true;
    setInteracting(true);
  },{capture:true,passive:true});

  const endPointer=()=>{
    perf.pointerActive=false;
    setInteracting(false,70);
  };
  canvas.addEventListener('pointerup',endPointer,{capture:true,passive:true});
  canvas.addEventListener('pointercancel',endPointer,{capture:true,passive:true});
  addEventListener('blur',endPointer,{passive:true});

  canvas.addEventListener('wheel',()=>{
    setInteracting(true);
    clearTimeout(perf.wheelTimer);
    perf.wheelTimer=setTimeout(()=>setInteracting(false,80),130);
  },{capture:true,passive:true});

  scheduleDraw=function(){
    if(state.framePending)return;
    const now=performance.now();
    const minGap=perf.interacting?16.7:8;
    const wait=Math.max(0,minGap-(now-perf.lastFrame));
    state.framePending=true;
    clearTimeout(perf.frameTimer);
    perf.frameTimer=setTimeout(()=>requestAnimationFrame(()=>{
      state.framePending=false;
      perf.lastFrame=performance.now();
      draw();
    }),wait);
  };

  function buildGrid(){
    if(perf.gridSource===state.locations&&perf.grid)return;
    const n=perf.gridSize;
    const grid=Array.from({length:n*n},()=>[]);
    for(const location of state.locations){
      const x=Math.max(0,Math.min(n-1,Math.floor(location.atlas_x*n)));
      const y=Math.max(0,Math.min(n-1,Math.floor(location.atlas_y*n)));
      grid[y*n+x].push(location);
    }
    perf.grid=grid;
    perf.gridSource=state.locations;
  }

  function eligible(location){
    if(!state.enabled.has(location.category_id))return false;
    if(state.mode==='all')return true;
    if(state.mode==='favorites')return state.favorites.has(location.id);
    return categoryGroup(state.categoryMap.get(location.category_id)?.title)===state.mode;
  }

  buildMarkers=function(){
    buildGrid();
    const n=perf.gridSize;
    const margin=perf.interacting?28:48;
    const left=(-margin-state.offsetX)/(4096*state.scale);
    const right=(innerWidth+margin-state.offsetX)/(4096*state.scale);
    const top=(-margin-state.offsetY)/(4096*state.scale);
    const bottom=(innerHeight+margin-state.offsetY)/(4096*state.scale);
    const x0=Math.max(0,Math.floor(Math.min(left,right)*n));
    const x1=Math.min(n-1,Math.floor(Math.max(left,right)*n));
    const y0=Math.max(0,Math.floor(Math.min(top,bottom)*n));
    const y1=Math.min(n-1,Math.floor(Math.max(top,bottom)*n));
    const output=[];

    for(let y=y0;y<=y1;y++){
      for(let x=x0;x<=x1;x++){
        for(const location of perf.grid[y*n+x]){
          if(!eligible(location))continue;
          const point=mapToScreen(location);
          if(point.x<-margin||point.y<-margin||point.x>innerWidth+margin||point.y>innerHeight+margin)continue;
          output.push({x:point.x,y:point.y,count:1,items:[location]});
        }
      }
    }
    return output;
  };

  const detailedMarker=drawMarker;
  drawMarker=function(cluster,relative){
    if(!perf.interacting)return detailedMarker(cluster,relative);

    const location=cluster.items[0];
    const category=state.categoryMap.get(location.category_id)?.title||'';
    const icon=iconType(category);
    const discovered=state.discovered.has(location.id);
    const selected=location.id===state.selected?.id;
    const inRoute=state.route.some(item=>item.id===location.id);
    const radius=selected?13:Math.max(4.8,Math.min(8.5,5+relative*1.6));

    ctx.save();
    ctx.globalAlpha=discovered?.3:1;
    ctx.beginPath();
    ctx.arc(cluster.x,cluster.y,radius,0,Math.PI*2);
    ctx.fillStyle=AtlasIcons.color(icon);
    ctx.fill();
    ctx.lineWidth=inRoute?1.8:1;
    ctx.strokeStyle=inRoute?'#edc574':'rgba(255,244,226,.68)';
    ctx.stroke();

    if(selected||relative>.95){
      AtlasIcons.draw(ctx,icon,cluster.x,cluster.y,selected?16:Math.max(7.5,radius*1.12),{alpha:1});
    }
    ctx.restore();
  };

  // Desktop routes stay static. The original implementation requested another
  // animation frame after every draw, keeping the entire map in a permanent loop.
  drawRoute=function(){
    if(state.route.length<2)return;
    const points=state.route.map(mapToScreen);
    ctx.save();
    ctx.lineCap='round';
    ctx.lineJoin='round';

    ctx.beginPath();
    points.forEach((point,index)=>index?ctx.lineTo(point.x,point.y):ctx.moveTo(point.x,point.y));
    ctx.strokeStyle='rgba(19,14,11,.8)';
    ctx.lineWidth=perf.interacting?6:8;
    ctx.stroke();

    if(!perf.interacting)ctx.setLineDash([10,8]);
    ctx.beginPath();
    points.forEach((point,index)=>index?ctx.lineTo(point.x,point.y):ctx.moveTo(point.x,point.y));
    ctx.strokeStyle='#e6bd70';
    ctx.lineWidth=3;
    ctx.stroke();
    ctx.setLineDash([]);

    if(!perf.interacting){
      points.forEach((point,index)=>{
        ctx.beginPath();
        ctx.arc(point.x,point.y,index===0||index===points.length-1?10:8,0,Math.PI*2);
        ctx.fillStyle=index===0?'#d6aa56':index===points.length-1?'#f2e7d3':'#a9212e';
        ctx.fill();
        ctx.lineWidth=2;
        ctx.strokeStyle='#fff4df';
        ctx.stroke();
        ctx.fillStyle=index===0||index===points.length-1?'#20170d':'white';
        ctx.font='800 10px -apple-system,BlinkMacSystemFont,sans-serif';
        ctx.textAlign='center';
        ctx.textBaseline='middle';
        ctx.fillText(String(index+1),point.x,point.y+.5);
      });
    }
    ctx.restore();
  };

  function tuneCanvas(){
    const area=Math.max(1,innerWidth*innerHeight);
    const pixelLimitDpr=Math.sqrt(perf.maxCanvasPixels/area);
    const hardwareDpr=devicePixelRatio||1;
    const target=Math.max(1,Math.min(hardwareDpr,pixelLimitDpr,2));
    const rounded=Math.round(target*20)/20;
    const width=Math.floor(innerWidth*rounded);
    const height=Math.floor(innerHeight*rounded);
    perf.dpr=rounded;
    if(canvas.width===width&&canvas.height===height)return;
    canvas.width=width;
    canvas.height=height;
    canvas.style.width=innerWidth+'px';
    canvas.style.height=innerHeight+'px';
    ctx.setTransform(rounded,0,0,rounded,0,0);
    scheduleDraw();
  }

  let resizeTimer=0;
  addEventListener('resize',()=>{
    clearTimeout(resizeTimer);
    resizeTimer=setTimeout(tuneCanvas,100);
  },{passive:true});

  document.addEventListener('visibilitychange',()=>{
    if(document.hidden){
      clearTimeout(perf.frameTimer);
      state.framePending=false;
    }else scheduleDraw();
  });

  setTimeout(tuneCanvas,380);
})();