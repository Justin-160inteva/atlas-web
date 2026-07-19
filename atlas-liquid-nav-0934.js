(() => {
  'use strict';
  const VERSION=window.AtlasRelease?.version||'0.9.4.2';
  const root=document.documentElement;
  const groups=[];
  let frame=0;

  root.classList.toggle('atlas-standalone',Boolean(window.matchMedia?.('(display-mode: standalone)').matches||window.navigator.standalone));
  function schedule(){if(frame)return;frame=requestAnimationFrame(()=>{frame=0;groups.forEach(placeIndicator)})}
  function geometry(group,containerRect,activeRect){
    if(group.name!=='vertical')return{x:activeRect.left-containerRect.left,y:activeRect.top-containerRect.top,width:activeRect.width,height:activeRect.height};
    const insetX=5,insetY=3;
    return{x:activeRect.left-containerRect.left+insetX,y:activeRect.top-containerRect.top+insetY,width:Math.max(0,activeRect.width-insetX*2),height:Math.max(0,activeRect.height-insetY*2)};
  }
  function animateVertical(group,next){
    const {indicator}=group,target=`translate3d(${next.x}px,${next.y}px,0)`;
    indicator.style.setProperty('--liquid-x',`${next.x}px`);indicator.style.setProperty('--liquid-y',`${next.y}px`);indicator.style.setProperty('--liquid-w',`${next.width}px`);indicator.style.setProperty('--liquid-h',`${next.height}px`);
    if(!group.ready||matchMedia('(prefers-reduced-motion: reduce)').matches){group.animation?.cancel();indicator.style.transform=target;group.x=next.x;group.y=next.y;group.ready=true;requestAnimationFrame(()=>indicator.classList.add('is-ready'));return}
    if(group.x===next.x&&group.y===next.y)return;
    const computed=getComputedStyle(indicator).transform;group.animation?.cancel();
    group.animation=indicator.animate([{transform:computed==='none'?`translate3d(${group.x}px,${group.y}px,0)`:computed},{transform:target}],{duration:210,easing:'cubic-bezier(.22,.82,.2,1)',fill:'forwards'});
    group.animation.onfinish=()=>{indicator.style.transform=target;group.animation?.cancel();group.animation=null};group.x=next.x;group.y=next.y;
  }
  function placeIndicator(group){
    const active=group.container.querySelector('button.active');if(!active){group.indicator.classList.remove('is-ready');return}
    const next=geometry(group,group.container.getBoundingClientRect(),active.getBoundingClientRect());
    if(group.name==='vertical'){animateVertical(group,next);return}
    const i=group.indicator;i.style.setProperty('--liquid-x',`${next.x}px`);i.style.setProperty('--liquid-y',`${next.y}px`);
    if(group.width!==next.width){group.width=next.width;i.style.setProperty('--liquid-w',`${next.width}px`)}if(group.height!==next.height){group.height=next.height;i.style.setProperty('--liquid-h',`${next.height}px`)}
    if(!i.classList.contains('is-ready'))requestAnimationFrame(()=>i.classList.add('is-ready'));
  }
  function installGroup(selector,name){
    const container=document.querySelector(selector);if(!container)return;
    container.querySelector('.atlas-liquid-selection')?.remove();const indicator=document.createElement('span');indicator.className=`atlas-liquid-selection atlas-liquid-selection-${name}`;indicator.setAttribute('aria-hidden','true');container.prepend(indicator);
    const group={container,indicator,name,width:-1,height:-1,x:0,y:0,ready:false,animation:null};groups.push(group);
    container.addEventListener('pointerdown',event=>{const button=event.target.closest('button');if(button&&container.contains(button)&&name!=='vertical')indicator.classList.add('is-pressed')},{passive:true});
    const release=()=>indicator.classList.remove('is-pressed');container.addEventListener('pointerup',()=>{release();schedule()},{passive:true});container.addEventListener('pointercancel',release,{passive:true});container.addEventListener('pointerleave',release,{passive:true});container.addEventListener('click',schedule);
    new MutationObserver(records=>{if(records.some(r=>r.type==='attributes'&&r.attributeName==='class'&&r.target instanceof HTMLButtonElement))schedule()}).observe(container,{subtree:true,attributes:true,attributeFilter:['class']});
    if('ResizeObserver'in window)new ResizeObserver(schedule).observe(container);placeIndicator(group);
  }
  function loadControls(){
    document.querySelectorAll('script[data-atlas-controls]').forEach(node=>{if(node.dataset.atlasControls!==VERSION)node.remove()});
    if(!document.querySelector(`script[data-atlas-controls="${VERSION}"]`)){const script=document.createElement('script');script.src=`atlas-controls-0938.js?v=${VERSION}`;script.defer=true;script.dataset.atlasControls=VERSION;document.body.appendChild(script)}
  }
  function init(){installGroup('.bottom-nav','horizontal');installGroup('.quick-rail','vertical');root.dataset.atlasLiquidNav=VERSION;addEventListener('resize',schedule,{passive:true});addEventListener('orientationchange',()=>setTimeout(schedule,80),{passive:true});document.fonts?.ready?.then(schedule,()=>{});setTimeout(schedule,120);loadControls()}
  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',init,{once:true}):init();
})();
