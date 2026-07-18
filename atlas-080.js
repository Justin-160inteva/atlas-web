(() => {
  'use strict';

  const root=document.documentElement;
  const mapCanvas=document.getElementById('mapCanvas');
  const clamp080=(value,min,max)=>Math.max(min,Math.min(max,value));

  const railIcons={
    all:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.8c.9 4.2 3.2 6.5 7.4 7.4-4.2.9-6.5 3.2-7.4 7.4-.9-4.2-3.2-6.5-7.4-7.4 4.2-.9 6.5-3.2 7.4-7.4Z"/><path d="M19 3.8c.3 1.4 1.1 2.2 2.5 2.5-1.4.3-2.2 1.1-2.5 2.5-.3-1.4-1.1-2.2-2.5-2.5 1.4-.3 2.2-1.1 2.5-2.5Z"/></svg>',
    locations:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s6-5.3 6-11a6 6 0 1 0-12 0c0 5.7 6 11 6 11Z"/><circle cx="12" cy="10" r="2.2"/></svg>',
    collectibles:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 7 7-7 11L5 10Z"/><path d="m5 10 7 3.8L19 10M8.5 5.8 12 13.8l3.5-8"/></svg>',
    activities:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 4 6.5 6.5M3.5 2.5 7 3l.5 3.5M11.5 10.5 5 17l-2 4 4-2 6.5-6.5"/><path d="m19 4-6.5 6.5M20.5 2.5 17 3l-.5 3.5M12.5 10.5 19 17l2 4-4-2-6.5-6.5"/></svg>',
    favorites:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.3 5.1a5.2 5.2 0 0 0-7.4 0L12 6l-.9-.9a5.2 5.2 0 0 0-7.4 7.4l.9.9L12 20.5l7.4-7.1.9-.9a5.2 5.2 0 0 0 0-7.4Z"/></svg>'
  };

  function installRailIcons(){
    document.querySelectorAll('.quick-rail .rail-button').forEach(button=>{
      const slot=button.querySelector('span');
      const icon=railIcons[button.dataset.mode];
      if(!slot||!icon)return;
      slot.className='rail-icon';
      slot.replaceChildren();
      slot.insertAdjacentHTML('afterbegin',icon);
    });
  }
  installRailIcons();

  function pinGeometry(tipY,r,tipHeight){
    return{centerY:tipY-tipHeight-r*.35};
  }

  function tracePin(context,x,tipY,r,tipHeight){
    const {centerY}=pinGeometry(tipY,r,tipHeight);
    const leftAngle=Math.PI*2/3;
    const rightAngle=Math.PI/3;
    const leftX=x+Math.cos(leftAngle)*r;
    const leftY=centerY+Math.sin(leftAngle)*r;
    const rightX=x+Math.cos(rightAngle)*r;
    const rightY=centerY+Math.sin(rightAngle)*r;
    context.beginPath();
    context.moveTo(x,tipY);
    context.bezierCurveTo(x-r*.2,tipY-tipHeight*.26,leftX-r*.08,leftY+r*.08,leftX,leftY);
    context.arc(x,centerY,r,leftAngle,rightAngle,false);
    context.bezierCurveTo(rightX+r*.08,rightY+r*.08,x+r*.2,tipY-tipHeight*.26,x,tipY);
    context.closePath();
    return centerY;
  }

  function interactionActive(){
    return Boolean(
      root.classList.contains('atlas-button-zooming')||
      window.AtlasMobilePerf?.interacting||
      window.AtlasDesktopPerf?.interacting
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
    const radius=selected?18:clamp080(6.5+relative*3.2,7,12.5);
    const tipHeight=selected?9:clamp080(5+relative*1.35,5,8);
    const iconSize=selected?22:clamp080(9+relative*4,10,15);
    const base=AtlasIcons.color(icon);
    const centerY=pinGeometry(cluster.y,radius,tipHeight).centerY;

    ctx.save();
    ctx.globalAlpha=discovered?.3:1;

    if(lightweight){
      tracePin(ctx,cluster.x,cluster.y,radius,tipHeight);
      ctx.fillStyle=base;
      ctx.fill();
      ctx.lineWidth=inRoute?1.7:.9;
      ctx.strokeStyle=inRoute?'#edc574':'rgba(255,244,226,.58)';
      ctx.stroke();
      if(selected||relative>.95)AtlasIcons.draw(ctx,icon,cluster.x,centerY,selected?17:Math.max(8,radius*1.08),{alpha:1});
      ctx.restore();
      return;
    }

    ctx.shadowColor=selected?'rgba(224,60,72,.34)':'rgba(0,0,0,.16)';
    ctx.shadowBlur=selected?10:2;
    ctx.shadowOffsetY=1;
    tracePin(ctx,cluster.x,cluster.y,radius+1.25,tipHeight+1.1);
    ctx.fillStyle=selected?'rgba(255,245,228,.9)':'rgba(18,16,15,.55)';
    ctx.fill();

    ctx.shadowColor='transparent';
    ctx.shadowBlur=0;
    ctx.shadowOffsetY=0;
    tracePin(ctx,cluster.x,cluster.y,radius,tipHeight);
    const gradient=ctx.createRadialGradient(cluster.x-radius*.35,centerY-radius*.42,1,cluster.x,centerY,radius*1.08);
    gradient.addColorStop(0,lighten(base,24));
    gradient.addColorStop(1,base);
    ctx.fillStyle=gradient;
    ctx.fill();
    ctx.lineWidth=selected?2:1;
    ctx.strokeStyle=inRoute?'#edc574':selected?'#fff7e8':'rgba(255,239,218,.58)';
    ctx.stroke();

    AtlasIcons.draw(ctx,icon,cluster.x,centerY,iconSize,{alpha:1});

    if(favorite){
      ctx.beginPath();
      ctx.arc(cluster.x+radius*.72,centerY-radius*.74,3.6,0,Math.PI*2);
      ctx.fillStyle='#d9af62';
      ctx.fill();
      ctx.strokeStyle='rgba(255,245,230,.86)';
      ctx.lineWidth=.9;
      ctx.stroke();
    }

    if(selected){
      tracePin(ctx,cluster.x,cluster.y,radius+6,tipHeight+4);
      ctx.strokeStyle='rgba(236,74,86,.55)';
      ctx.lineWidth=1.8;
      ctx.stroke();
    }
    ctx.restore();
  };

  pickTarget=function(x,y){
    let best=null;
    let bestScore=Infinity;
    const relative=state.scale/fitScale();
    for(const cluster of state.markers){
      const location=cluster.items[0];
      const selected=location.id===state.selected?.id;
      const radius=selected?18:clamp080(6.5+relative*3.2,7,12.5);
      const tipHeight=selected?9:clamp080(5+relative*1.35,5,8);
      const centerY=pinGeometry(cluster.y,radius,tipHeight).centerY;
      const circleDistance=Math.hypot(cluster.x-x,centerY-y);
      const tipDistance=Math.hypot(cluster.x-x,cluster.y-y);
      const score=Math.min(circleDistance,tipDistance+radius*.5);
      if((circleDistance<=radius+14||tipDistance<=14)&&score<bestScore){
        bestScore=score;
        best=cluster;
      }
    }
    return best;
  };

  let zoomFrame=0;
  let zoomToken=0;
  const reducedMotion=matchMedia('(prefers-reduced-motion: reduce)');

  function setZoomInteraction(active){
    root.classList.toggle('atlas-button-zooming',active);
    const mobile=window.AtlasMobilePerf;
    const desktop=window.AtlasDesktopPerf;
    if(mobile){mobile.interacting=active;root.classList.toggle('atlas-interacting',active);}
    if(desktop){desktop.interacting=active;root.classList.toggle('atlas-desktop-interacting',active);}
  }

  function cancelButtonZoom(preserveExternalInteraction=false){
    zoomToken++;
    if(zoomFrame)cancelAnimationFrame(zoomFrame);
    zoomFrame=0;
    root.classList.remove('atlas-button-zooming');
    if(!preserveExternalInteraction)setZoomInteraction(false);
  }

  function animateButtonZoom(factor){
    cancelButtonZoom(false);
    const startScale=state.scale;
    const targetScale=clamp080(startScale*factor,minScale(),state.maxScale);
    if(Math.abs(targetScale-startScale)<1e-7)return;

    const centerX=innerWidth/2;
    const centerY=innerHeight/2;
    const mapX=(centerX-state.offsetX)/startScale;
    const mapY=(centerY-state.offsetY)/startScale;
    const startOffsetX=state.offsetX;
    const startOffsetY=state.offsetY;
    const targetOffsetX=centerX-mapX*targetScale;
    const targetOffsetY=centerY-mapY*targetScale;

    if(reducedMotion.matches){
      state.scale=targetScale;
      state.offsetX=targetOffsetX;
      state.offsetY=targetOffsetY;
      updateZoomLabel();
      scheduleDraw();
      return;
    }

    const token=++zoomToken;
    const startTime=performance.now();
    const duration=270;
    setZoomInteraction(true);

    const step=now=>{
      if(token!==zoomToken)return;
      const progress=clamp080((now-startTime)/duration,0,1);
      const eased=1-Math.pow(1-progress,3);
      state.scale=startScale+(targetScale-startScale)*eased;
      state.offsetX=startOffsetX+(targetOffsetX-startOffsetX)*eased;
      state.offsetY=startOffsetY+(targetOffsetY-startOffsetY)*eased;
      updateZoomLabel();
      scheduleDraw();
      if(progress<1){
        zoomFrame=requestAnimationFrame(step);
      }else{
        zoomFrame=0;
        setZoomInteraction(false);
        scheduleDraw();
      }
    };
    zoomFrame=requestAnimationFrame(step);
  }

  const zoomInButton=document.getElementById('zoomIn');
  const zoomOutButton=document.getElementById('zoomOut');
  if(zoomInButton)zoomInButton.onclick=()=>animateButtonZoom(1.25);
  if(zoomOutButton)zoomOutButton.onclick=()=>animateButtonZoom(.8);

  mapCanvas.addEventListener('pointerdown',()=>cancelButtonZoom(true),{capture:true,passive:true});
  mapCanvas.addEventListener('wheel',()=>cancelButtonZoom(true),{capture:true,passive:true});

  window.Atlas080={animateButtonZoom,cancelButtonZoom,tracePin,installRailIcons};
  scheduleDraw();
})();