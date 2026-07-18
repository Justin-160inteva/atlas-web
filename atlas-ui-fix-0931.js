(() => {
  'use strict';

  if(typeof state==='undefined'||typeof ctx==='undefined')return;

  const root=document.documentElement;
  const panelIds={filter:'filterPanel',route:'routePanel',progress:'progressPanel'};
  let lastBrowseMode=state.mode==='favorites'?'all':state.mode;

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
  function pinCenter(tipY,radius,tipHeight){return tipY-tipHeight-radius*.35;}
  function tracePin(context,x,tipY,radius,tipHeight){
    const centerY=pinCenter(tipY,radius,tipHeight);
    const leftAngle=Math.PI*2/3;
    const rightAngle=Math.PI/3;
    const leftX=x+Math.cos(leftAngle)*radius;
    const leftY=centerY+Math.sin(leftAngle)*radius;
    const rightX=x+Math.cos(rightAngle)*radius;
    const rightY=centerY+Math.sin(rightAngle)*radius;
    context.beginPath();
    context.moveTo(x,tipY);
    context.bezierCurveTo(x-radius*.2,tipY-tipHeight*.26,leftX-radius*.08,leftY+radius*.08,leftX,leftY);
    context.arc(x,centerY,radius,leftAngle,rightAngle,false);
    context.bezierCurveTo(rightX+radius*.08,rightY+radius*.08,x+radius*.2,tipY-tipHeight*.26,x,tipY);
    context.closePath();
    return centerY;
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
    const location=cluster.items[0];
    const category=state.categoryMap.get(location.category_id)?.title||'';
    const icon=iconType(category);
    const selected=location.id===state.selected?.id;
    const discovered=state.discovered.has(location.id);
    const favorite=state.favorites.has(location.id);
    const inRoute=state.route.some(item=>item.id===location.id);
    const lightweight=interactionActive();
    const radius=selected?17:clampValue(6.5+relative*3.2,7,12.5);
    const tipHeight=selected?8.5:clampValue(5+relative*1.35,5,8);
    const centerY=pinCenter(cluster.y,radius,tipHeight);
    const iconSize=selected?21:clampValue(9+relative*4,10,15);
    const base=AtlasIcons.color(icon);

    ctx.save();
    ctx.globalAlpha=discovered&&!selected?.32:1;

    if(selected){
      ctx.shadowColor='rgba(0,0,0,.5)';
      ctx.shadowBlur=18;
      ctx.shadowOffsetY=5;
      tracePin(ctx,cluster.x,cluster.y,radius+4.2,tipHeight+3.2);
      ctx.fillStyle='rgba(20,17,14,.78)';
      ctx.fill();

      ctx.shadowColor='rgba(223,186,110,.34)';
      ctx.shadowBlur=13;
      ctx.shadowOffsetY=0;
      tracePin(ctx,cluster.x,cluster.y,radius+2.4,tipHeight+1.8);
      ctx.fillStyle='rgba(247,238,218,.96)';
      ctx.fill();
      ctx.lineWidth=1.5;
      ctx.strokeStyle='rgba(218,181,105,.96)';
      ctx.stroke();
      ctx.shadowColor='transparent';
    }else if(!lightweight){
      ctx.shadowColor='rgba(0,0,0,.18)';
      ctx.shadowBlur=3;
      ctx.shadowOffsetY=2;
      tracePin(ctx,cluster.x,cluster.y,radius+1.2,tipHeight+1);
      ctx.fillStyle='rgba(18,16,15,.58)';
      ctx.fill();
      ctx.shadowColor='transparent';
    }

    tracePin(ctx,cluster.x,cluster.y,radius,tipHeight);
    if(lightweight){
      ctx.fillStyle=base;
    }else{
      const gradient=ctx.createRadialGradient(cluster.x-radius*.35,centerY-radius*.42,1,cluster.x,centerY,radius*1.08);
      gradient.addColorStop(0,lighten(base,selected?30:24));
      gradient.addColorStop(1,base);
      ctx.fillStyle=gradient;
    }
    ctx.fill();
    ctx.lineWidth=inRoute?1.8:selected?1.5:1;
    ctx.strokeStyle=inRoute?'#edc574':selected?'rgba(255,252,242,.92)':'rgba(255,239,218,.62)';
    ctx.stroke();

    AtlasIcons.draw(ctx,icon,cluster.x,centerY,iconSize,{alpha:1});

    if(selected){
      ctx.beginPath();
      ctx.ellipse(cluster.x,cluster.y+5.2,7.5,2.4,0,0,Math.PI*2);
      ctx.fillStyle='rgba(222,183,105,.76)';
      ctx.fill();
      ctx.beginPath();
      ctx.arc(cluster.x,centerY-radius-4.2,2.1,0,Math.PI*2);
      ctx.fillStyle='#f5dfaa';
      ctx.fill();
    }

    if(favorite){
      ctx.beginPath();
      ctx.arc(cluster.x+radius*.72,centerY-radius*.74,3.6,0,Math.PI*2);
      ctx.fillStyle='#d9af62';
      ctx.fill();
      ctx.strokeStyle='rgba(255,248,232,.92)';
      ctx.lineWidth=1;
      ctx.stroke();
    }

    ctx.restore();
  };

  setBottomActive('map');
  setRailActive(lastBrowseMode);
  root.dataset.atlasUiFix='0.9.3.1';
  scheduleDraw();
})();