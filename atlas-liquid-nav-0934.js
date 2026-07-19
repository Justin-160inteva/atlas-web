(() => {
  'use strict';

  const VERSION='0.9.3.4';
  const root=document.documentElement;
  const groups=[];
  let frame=0;

  const standalone=Boolean(
    window.matchMedia?.('(display-mode: standalone)').matches||
    window.navigator.standalone
  );
  root.classList.toggle('atlas-standalone',standalone);

  function schedule(){
    if(frame)return;
    frame=requestAnimationFrame(()=>{
      frame=0;
      groups.forEach(placeIndicator);
    });
  }

  function geometry(group,containerRect,activeRect){
    if(group.name!=='vertical'){
      return{
        x:activeRect.left-containerRect.left,
        y:activeRect.top-containerRect.top,
        width:activeRect.width,
        height:activeRect.height
      };
    }

    const insetX=5;
    const insetY=3;
    return{
      x:activeRect.left-containerRect.left+insetX,
      y:activeRect.top-containerRect.top+insetY,
      width:Math.max(0,activeRect.width-insetX*2),
      height:Math.max(0,activeRect.height-insetY*2)
    };
  }

  function placeIndicator(group){
    const {container,indicator}=group;
    const active=container.querySelector('button.active');
    if(!active){
      indicator.classList.remove('is-ready');
      return;
    }

    const containerRect=container.getBoundingClientRect();
    const activeRect=active.getBoundingClientRect();
    const next=geometry(group,containerRect,activeRect);

    indicator.style.setProperty('--liquid-x',`${next.x}px`);
    indicator.style.setProperty('--liquid-y',`${next.y}px`);

    if(group.width!==next.width){
      group.width=next.width;
      indicator.style.setProperty('--liquid-w',`${next.width}px`);
    }
    if(group.height!==next.height){
      group.height=next.height;
      indicator.style.setProperty('--liquid-h',`${next.height}px`);
    }

    if(!indicator.classList.contains('is-ready')){
      requestAnimationFrame(()=>indicator.classList.add('is-ready'));
    }
  }

  function release(group){
    group.indicator.classList.remove('is-pressed');
  }

  function installGroup(selector,name){
    const container=document.querySelector(selector);
    if(!container)return;

    container.querySelector('.atlas-liquid-selection')?.remove();

    const indicator=document.createElement('span');
    indicator.className=`atlas-liquid-selection atlas-liquid-selection-${name}`;
    indicator.setAttribute('aria-hidden','true');
    container.prepend(indicator);

    const group={container,indicator,name,width:-1,height:-1};
    groups.push(group);

    container.addEventListener('pointerdown',event=>{
      const button=event.target.closest('button');
      if(!button||!container.contains(button))return;
      indicator.classList.add('is-pressed');
    },{passive:true});

    container.addEventListener('pointerup',()=>{
      release(group);
      schedule();
    },{passive:true});
    container.addEventListener('pointercancel',()=>release(group),{passive:true});
    container.addEventListener('pointerleave',()=>release(group),{passive:true});
    container.addEventListener('click',schedule);

    const observer=new MutationObserver(records=>{
      const activeButtonChanged=records.some(record=>
        record.type==='attributes'&&
        record.attributeName==='class'&&
        record.target instanceof HTMLButtonElement
      );
      if(activeButtonChanged)schedule();
    });
    observer.observe(container,{subtree:true,attributes:true,attributeFilter:['class']});
    group.observer=observer;

    if('ResizeObserver'in window){
      group.resizeObserver=new ResizeObserver(schedule);
      group.resizeObserver.observe(container);
    }

    placeIndicator(group);
  }

  function init(){
    installGroup('.bottom-nav','horizontal');
    installGroup('.quick-rail','vertical');
    root.dataset.atlasLiquidNav=VERSION;
    addEventListener('resize',schedule,{passive:true});
    addEventListener('orientationchange',()=>setTimeout(schedule,80),{passive:true});
    document.fonts?.ready?.then(schedule,()=>{});
    setTimeout(schedule,120);
  }

  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',init,{once:true});
  }else{
    init();
  }
})();

// Validation trigger: Alpha 0.9.3.4 smoother integrated left rail.
