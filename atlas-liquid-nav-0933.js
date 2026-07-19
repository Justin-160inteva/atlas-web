(() => {
  'use strict';

  const VERSION='0.9.3.3';
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

  function placeIndicator(group){
    const {container,indicator}=group;
    const active=container.querySelector('button.active');
    if(!active){
      indicator.classList.remove('is-ready');
      return;
    }

    const containerRect=container.getBoundingClientRect();
    const activeRect=active.getBoundingClientRect();
    const x=activeRect.left-containerRect.left;
    const y=activeRect.top-containerRect.top;

    indicator.style.setProperty('--liquid-x',`${x}px`);
    indicator.style.setProperty('--liquid-y',`${y}px`);
    indicator.style.setProperty('--liquid-w',`${activeRect.width}px`);
    indicator.style.setProperty('--liquid-h',`${activeRect.height}px`);

    if(!indicator.classList.contains('is-ready')){
      requestAnimationFrame(()=>indicator.classList.add('is-ready'));
    }
  }

  function release(group){
    group.indicator.classList.remove('is-pressed');
  }

  function installGroup(selector,name){
    const container=document.querySelector(selector);
    if(!container||container.querySelector('.atlas-liquid-selection'))return;

    const indicator=document.createElement('span');
    indicator.className=`atlas-liquid-selection atlas-liquid-selection-${name}`;
    indicator.setAttribute('aria-hidden','true');
    container.prepend(indicator);

    const group={container,indicator};
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
      if(records.some(record=>record.type==='attributes'&&record.attributeName==='class'))schedule();
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
    document.fonts?.ready?.then(schedule).catch(()=>{});
    setTimeout(schedule,120);
  }

  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',init,{once:true});
  }else{
    init();
  }
})();
