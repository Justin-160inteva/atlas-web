(() => {
  'use strict';

  const VERSION='0.9.2.0';
  const root=document.documentElement;
  const canvas=document.getElementById('mapCanvas');
  if(!canvas||typeof state==='undefined'||typeof draw!=='function')return;

  const coarse=matchMedia('(pointer:coarse)').matches||/iPad|iPhone|iPod|Android/i.test(navigator.userAgent);
  const memory=Number(navigator.deviceMemory||8);
  const cores=Number(navigator.hardwareConcurrency||8);
  const lowPower=memory<=4||cores<=4;
  const showHud=new URLSearchParams(location.search).has('perf');
  const qualityNames=['high','balanced','performance'];
  const recentGaps=[];
  const metrics={
    version:VERSION,
    targetFps:60,
    qualityLevel:lowPower?1:0,
    quality:qualityNames[lowPower?1:0],
    dpr:1,
    draws:0,
    slowFrames:0,
    longAnimationFrames:0,
    longTasks:0,
    maxDrawMs:0,
    lastDrawMs:0,
    estimatedFps:60,
    interacting:false
  };
  let rafId=0;
  let lastFrameAt=0;
  let slowStreak=0;
  let goodStreak=0;
  let lastQualityChange=0;
  let resizeTimer=0;
  let eligibleKey='';
  let eligibleCache=[];
  let hud=null;
  let lastHudUpdate=0;

  function interactionActive(){
    return Boolean(
      state.drag||state.pointers?.size||
      root.classList.contains('atlas-button-zooming')||
      root.classList.contains('atlas-interacting')||
      root.classList.contains('atlas-desktop-interacting')
    );
  }

  function updateQualityClasses(){
    qualityNames.forEach(name=>root.classList.toggle(`atlas-quality-${name}`,metrics.quality===name));
    root.classList.toggle('atlas-performance-interacting',metrics.interacting);
  }

  function updateHud(now){
    if(!hud||now-lastHudUpdate<220)return;
    lastHudUpdate=now;
    hud.textContent=`${metrics.estimatedFps} FPS · ${metrics.lastDrawMs.toFixed(1)} ms · DPR ${metrics.dpr.toFixed(2)} · ${metrics.quality}`;
  }

  function targetDpr(){
    const area=Math.max(1,innerWidth*innerHeight);
    const pixelCap=coarse?(lowPower?2_000_000:2_850_000):(lowPower?4_000_000:6_000_000);
    const pixelDpr=Math.sqrt(pixelCap/area);
    const hardwareCap=coarse?(innerWidth>=700?1.6:1.45):(lowPower?1.6:2);
    const multiplier=[1,.84,.7][metrics.qualityLevel];
    return Math.max(1,Math.min(devicePixelRatio||1,pixelDpr,hardwareCap)*multiplier);
  }

  function applyCanvasScale(force=false){
    const rounded=Math.round(targetDpr()*20)/20;
    const width=Math.max(1,Math.floor(innerWidth*rounded));
    const height=Math.max(1,Math.floor(innerHeight*rounded));
    metrics.dpr=rounded;
    if(!force&&canvas.width===width&&canvas.height===height)return;
    canvas.width=width;
    canvas.height=height;
    canvas.style.width=`${innerWidth}px`;
    canvas.style.height=`${innerHeight}px`;
    ctx.setTransform(rounded,0,0,rounded,0,0);
    state.framePending=false;
    scheduleDraw();
  }

  function setQuality(level,reason='runtime'){
    const next=Math.max(0,Math.min(qualityNames.length-1,level));
    if(next===metrics.qualityLevel)return;
    metrics.qualityLevel=next;
    metrics.quality=qualityNames[next];
    metrics.lastQualityReason=reason;
    lastQualityChange=performance.now();
    slowStreak=0;
    goodStreak=0;
    updateQualityClasses();
    applyCanvasScale(true);
  }

  function recordFrame(now,drawMs){
    metrics.draws++;
    metrics.lastDrawMs=Math.round(drawMs*100)/100;
    metrics.maxDrawMs=Math.max(metrics.maxDrawMs,metrics.lastDrawMs);
    metrics.interacting=interactionActive();
    updateQualityClasses();

    if(lastFrameAt){
      const gap=now-lastFrameAt;
      if(gap<120){
        recentGaps.push(gap);
        if(recentGaps.length>45)recentGaps.shift();
        const average=recentGaps.reduce((sum,value)=>sum+value,0)/recentGaps.length;
        metrics.estimatedFps=Math.round(Math.min(240,1000/Math.max(1,average)));
        const slow=drawMs>10.5||gap>22.5;
        const good=drawMs<7.2&&gap<19.5;
        if(metrics.interacting&&slow){
          metrics.slowFrames++;
          slowStreak++;
          goodStreak=0;
        }else if(metrics.interacting&&good){
          goodStreak++;
          slowStreak=Math.max(0,slowStreak-1);
        }
        if(slowStreak>=5&&metrics.qualityLevel<2)setQuality(metrics.qualityLevel+1,'frame-budget');
        if(goodStreak>=150&&metrics.qualityLevel>0&&performance.now()-lastQualityChange>7000){
          setQuality(metrics.qualityLevel-1,'sustained-headroom');
        }
      }
    }
    lastFrameAt=now;
    updateHud(now);
  }

  scheduleDraw=function(){
    if(state.framePending||document.hidden)return;
    state.framePending=true;
    rafId=requestAnimationFrame(now=>{
      state.framePending=false;
      rafId=0;
      const started=performance.now();
      draw();
      recordFrame(now,performance.now()-started);
    });
  };

  const nativeVisibleLocations=visibleLocations;
  visibleLocations=function(){
    const enabled=[...state.enabled].join('|');
    const favorites=state.mode==='favorites'?[...state.favorites].join('|'):'';
    const key=`${state.locations.length};${state.mode};${enabled};${favorites}`;
    if(key!==eligibleKey){
      eligibleKey=key;
      eligibleCache=nativeVisibleLocations();
    }
    return eligibleCache;
  };

  function observeLongFrames(){
    if(!('PerformanceObserver'in window))return;
    const supported=PerformanceObserver.supportedEntryTypes||[];
    try{
      if(supported.includes('long-animation-frame')){
        const observer=new PerformanceObserver(list=>{
          metrics.longAnimationFrames+=list.getEntries().length;
          if(metrics.interacting&&metrics.qualityLevel<2)setQuality(metrics.qualityLevel+1,'long-animation-frame');
        });
        observer.observe({type:'long-animation-frame',buffered:true});
      }else if(supported.includes('longtask')){
        const observer=new PerformanceObserver(list=>{
          metrics.longTasks+=list.getEntries().length;
        });
        observer.observe({type:'longtask',buffered:true});
      }
    }catch(_){/* optional performance telemetry */}
  }

  function installHud(){
    if(!showHud)return;
    hud=document.createElement('div');
    hud.id='atlasPerformanceHud';
    hud.setAttribute('aria-live','off');
    Object.assign(hud.style,{
      position:'fixed',left:'max(10px, env(safe-area-inset-left))',bottom:'max(78px, calc(env(safe-area-inset-bottom) + 68px))',
      zIndex:'9999',padding:'7px 9px',border:'1px solid rgba(255,255,255,.16)',borderRadius:'10px',
      background:'rgba(8,8,8,.82)',backdropFilter:'blur(8px)',color:'#f4ead8',font:'600 10px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace',
      pointerEvents:'none',boxShadow:'0 6px 20px rgba(0,0,0,.24)'
    });
    document.body.appendChild(hud);
    updateHud(performance.now()+300);
  }

  addEventListener('resize',()=>{
    clearTimeout(resizeTimer);
    resizeTimer=setTimeout(()=>applyCanvasScale(true),180);
  },{passive:true});

  document.addEventListener('visibilitychange',()=>{
    if(document.hidden){
      if(rafId)cancelAnimationFrame(rafId);
      rafId=0;
      state.framePending=false;
    }else{
      lastFrameAt=0;
      scheduleDraw();
    }
  });

  canvas.addEventListener('pointerdown',()=>{
    metrics.interacting=true;
    updateQualityClasses();
  },{capture:true,passive:true});
  const settle=()=>{
    clearTimeout(settle.timer);
    settle.timer=setTimeout(()=>{
      metrics.interacting=false;
      updateQualityClasses();
      scheduleDraw();
    },100);
  };
  canvas.addEventListener('pointerup',settle,{capture:true,passive:true});
  canvas.addEventListener('pointercancel',settle,{capture:true,passive:true});
  canvas.addEventListener('wheel',settle,{capture:true,passive:true});

  window.AtlasPerf092={
    metrics,
    get qualityLevel(){return metrics.qualityLevel;},
    get interacting(){return interactionActive();},
    setQuality:(level)=>setQuality(level,'manual'),
    report:()=>({...metrics,recentFrameGaps:[...recentGaps]})
  };

  root.classList.add('atlas-performance-092');
  updateQualityClasses();
  observeLongFrames();
  installHud();
  setTimeout(()=>applyCanvasScale(true),520);
})();
