(() => {
  'use strict';

  if(typeof state==='undefined'||typeof ctx==='undefined')return;

  const VERSION=window.AtlasRelease?.version||'0.9.4.6';
  const root=document.documentElement;
  const panelIds={filter:'filterPanel',route:'routePanel',progress:'progressPanel'};
  const SELECTED_SCALE=1.28;
  const SELECTION_DURATION=190;
  const MIN_SELECTION_FRAMES=2;
  const selectionMotions=new Map();
  let lastBrowseMode=state.mode==='favorites'?'all':state.mode;
  let visualSelectedId=state.selected?.id??null;
  let selectionFrame=0;

  function setPanelOpen(panel,open){
    if(!panel)return;
    panel.classList.toggle('open',open);
    panel.setAttribute('aria-hidden',open?'false':'true');
  }

  function setBottomActive(name){
    document.querySelectorAll('.nav-item').forEach(button=>{
      const active=button.dataset.panel===name;
      button.classList.toggle('active',active);
      button.setAttribute('aria-pressed',active?'true':'false');
    });
    root.dataset.activePanel=name;
  }

  function setRailActive(mode){
    document.querySelectorAll('.rail-button').forEach(button=>{
      const active=button.dataset.mode===mode;
      button.classList.toggle('active',active);
      button.setAttribute('aria-pressed',active?'true':'false');
    });
  }

  function closePanelsFixed(){
    Object.values(panelIds).forEach(id=>setPanelOpen(document.getElementById(id),false));
  }

  function closeDetail(){
    const sheet=document.getElementById('detailSheet');
    if(!sheet?.classList.contains('open'))return;
    sheet.classList.remove('open');
    sheet.setAttribute('aria-hidden','true');
    state.selected=null;
  }

  function openPanelFixed(name){
    const next=panelIds[name]?name:(name==='favorites'?'favorites':'map');
    closePanelsFixed();
    closeDetail();
    setBottomActive(next);

    if(next==='map'){
      state.mode=lastBrowseMode;
      setRailActive(lastBrowseMode);
      scheduleDraw();
      return;
    }

    if(next==='favorites'){
      state.mode='favorites';
      setRailActive('');
      scheduleDraw();
      if(typeof toast==='function')toast(state.favorites.size?'仅显示收藏地点':'还没有收藏地点');
      return;
    }

    state.mode=lastBrowseMode;
    setRailActive(lastBrowseMode);
    if(next==='route'&&typeof renderRoute==='function')renderRoute();
    if(next==='progress'&&typeof renderProgress==='function')renderProgress();
    if(next==='filter'&&typeof renderCategories==='function')renderCategories();
    setPanelOpen(document.getElementById(panelIds[next]),true);
    scheduleDraw();
  }

  window.closePanels=closePanelsFixed;
  window.openPanel=openPanelFixed;

  document.querySelectorAll('.nav-item').forEach(button=>{
    button.onclick=()=>openPanelFixed(button.dataset.panel);
  });

  document.querySelectorAll('.rail-button').forEach(button=>{
    button.onclick=()=>{
      const mode=button.dataset.mode||'all';
      lastBrowseMode=mode;
      state.mode=mode;
      closePanelsFixed();
      closeDetail();
      setRailActive(mode);
      setBottomActive('map');
      scheduleDraw();
    };
  });

  document.querySelector('.close-panel')?.addEventListener('click',()=>openPanelFixed('map'));
  document.querySelector('.close-progress')?.addEventListener('click',()=>openPanelFixed('map'));
  document.querySelector('.close-route')?.addEventListener('click',()=>openPanelFixed('map'));
  document.getElementById('openRouteBadge')?.addEventListener('click',()=>openPanelFixed('route'));

  function clampValue(value,min,max){return Math.max(min,Math.min(max,value));}
  function easeOutCubic(value){return 1-Math.pow(1-clampValue(value,0,1),3);}
  function pinCenter(tipY,radius,tipHeight){return tipY-tipHeight-radius*.58;}
  function tracePin(context,x,tipY,radius,tipHeight){
    const centerY=pinCenter(tipY,radius,tipHeight);
    const topY=centerY-radius;
    const shoulderY=centerY+radius*.16;
    const lowerY=centerY+radius*.58;
    context.beginPath();
    context.moveTo(x,tipY);
    context.bezierCurveTo(x-radius*.18,tipY-tipHeight*.2,x-radius*.72,lowerY,x-radius*.92,shoulderY);
    context.bezierCurveTo(x-radius*1.08,centerY-radius*.34,x-radius*.72,topY,x,topY);
    context.bezierCurveTo(x+radius*.72,topY,x+radius*1.08,centerY-radius*.34,x+radius*.92,shoulderY);
    context.bezierCurveTo(x+radius*.72,lowerY,x+radius*.18,tipY-tipHeight*.2,x,tipY);
    context.closePath();
    return centerY;
  }

  function motionProgress(motion,now=performance.now()){
    const timeProgress=clampValue((now-motion.startedAt)/SELECTION_DURATION,0,1);
    const frameProgress=clampValue((motion.frames||0)/MIN_SELECTION_FRAMES,0,1);
    return Math.min(timeProgress,frameProgress);
  }

  function resolvedSelectionScale(id,now=performance.now()){
    const motion=selectionMotions.get(id);
    if(!motion)return id===visualSelectedId?SELECTED_SCALE:1;
    const progress=motionProgress(motion,now);
    const scale=motion.from+(motion.to-motion.from)*easeOutCubic(progress);
    if(progress>=1)selectionMotions.delete(id);
    return scale;
  }

  function pruneSelectionMotions(now=performance.now()){
    for(const [id,motion] of selectionMotions){
      if(motionProgress(motion,now)>=1)selectionMotions.delete(id);
    }
  }

  function keepSelectionAnimationAlive(){
    pruneSelectionMotions();
    if(!selectionMotions.size||selectionFrame)return;
    selectionFrame=requestAnimationFrame(()=>{
      selectionFrame=0;
      for(const motion of selectionMotions.values())motion.frames=(motion.frames||0)+1;
      pruneSelectionMotions();
      scheduleDraw();
    });
  }

  function syncSelectionMotion(now=performance.now()){
    const nextId=state.selected?.id??null;
    if(nextId===visualSelectedId){
      keepSelectionAnimationAlive();
      return;
    }
    const previousId=visualSelectedId;
    if(previousId!==null){
      selectionMotions.set(previousId,{from:resolvedSelectionScale(previousId,now),to:1,startedAt:now,frames:0});
    }
    if(nextId!==null){
      selectionMotions.set(nextId,{from:resolvedSelectionScale(nextId,now),to:SELECTED_SCALE,startedAt:now,frames:0});
    }
    visualSelectedId=nextId;
    keepSelectionAnimationAlive();
  }

  function interactionActive(){
    return Boolean(
      root.classList.contains('atlas-button-zooming')||
      window.AtlasMobilePerf?.interacting||
      window.AtlasDesktopPerf?.interacting||
      window.AtlasPerf092?.interacting
    );
  }

  drawMarker=function(cluster,relative){
    const now=performance.now();
    syncSelectionMotion(now);
    const location=cluster.items[0];
    const category=state.categoryMap.get(location.category_id)?.title||'';
    const icon=iconType(category);
    const discovered=state.discovered.has(location.id);
    const favorite=state.favorites.has(location.id);
    const inRoute=state.route.some(item=>item.id===location.id);
    const lightweight=interactionActive();
    const visualScale=resolvedSelectionScale(location.id,now);
    const baseRadius=clampValue(6.5+relative*3.2,7,12.5);
    const baseTipHeight=clampValue(5.8+relative*1.55,5.8,8.8);
    const radius=baseRadius*visualScale;
    const tipHeight=baseTipHeight*visualScale;
    const centerY=pinCenter(cluster.y,radius,tipHeight);
    const iconSize=clampValue(9+relative*4,10,15)*visualScale;
    const base=AtlasIcons.color(icon);

    ctx.save();
    ctx.globalAlpha=discovered?.32:1;

    if(!lightweight){
      ctx.shadowColor='rgba(0,0,0,.18)';
      ctx.shadowBlur=3;
      ctx.shadowOffsetY=2;
      tracePin(ctx,cluster.x,cluster.y,radius+1.15,tipHeight+1.05);
      ctx.fillStyle='rgba(18,16,15,.58)';
      ctx.fill();
      ctx.shadowColor='transparent';
    }

    tracePin(ctx,cluster.x,cluster.y,radius,tipHeight);
    if(lightweight){
      ctx.fillStyle=base;
    }else{
      const gradient=ctx.createRadialGradient(cluster.x-radius*.34,centerY-radius*.43,1,cluster.x,centerY,radius*1.06);
      gradient.addColorStop(0,lighten(base,24));
      gradient.addColorStop(1,base);
      ctx.fillStyle=gradient;
    }
    ctx.fill();
    ctx.lineWidth=inRoute?1.8:1;
    ctx.strokeStyle=inRoute?'#edc574':'rgba(255,239,218,.62)';
    ctx.stroke();

    if(!lightweight||visualScale>1.03||relative>.95){
      AtlasIcons.draw(ctx,icon,cluster.x,centerY,iconSize,{alpha:1});
    }

    if(favorite){
      ctx.beginPath();
      ctx.arc(cluster.x+radius*.7,centerY-radius*.72,3.6,0,Math.PI*2);
      ctx.fillStyle='#d9af62';
      ctx.fill();
      ctx.strokeStyle='rgba(255,248,232,.92)';
      ctx.lineWidth=1;
      ctx.stroke();
    }

    ctx.restore();
    keepSelectionAnimationAlive();
  };

  window.AtlasMarkerVisuals={
    version:VERSION,
    selectedScale:SELECTED_SCALE,
    selectionDuration:SELECTION_DURATION,
    minimumSelectionFrames:MIN_SELECTION_FRAMES,
    selectionUsesScaleOnly:true,
    selectionDecorationLayers:0,
    tipAnchorStable:true,
    pinCenter,
    scaleFor:id=>resolvedSelectionScale(id),
    activeMotionCount:()=>selectionMotions.size,
    geometry:{centerOffsetRadius:.58,shoulderRatio:.16,lowerCurveRatio:.58}
  };
  root.dataset.atlasMarkerVisuals=VERSION;
  setBottomActive('map');
  setRailActive(lastBrowseMode);
  root.dataset.atlasUiFix=VERSION;
  scheduleDraw();
})();
