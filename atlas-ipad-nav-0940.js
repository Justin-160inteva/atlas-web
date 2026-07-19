(() => {
  'use strict';
  const root=document.documentElement;
  const isIPad=/iPad/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
  root.classList.toggle('atlas-ipad',isIPad);

  const iconMap={map:'map',filter:'filter',route:'route',progress:'progress',favorites:'favorite'};
  const railMap={all:'all',locations:'locations',collectibles:'collectibles',activities:'activities',favorites:'favorite'};

  function cleanIconHost(host){
    if(!host)return;
    const svgs=[...host.querySelectorAll(':scope > svg.atlas-control-icon')];
    svgs.slice(1).forEach(svg=>svg.remove());
    [...host.childNodes].forEach(node=>{if(node.nodeType===Node.TEXT_NODE)node.remove()});
  }

  function dedupeIcons(){
    document.querySelectorAll('.bottom-nav .nav-item>span,.quick-rail .rail-icon').forEach(cleanIconHost);
  }

  function findGroup(container){
    return container?.querySelector('.atlas-liquid-selection')||null;
  }

  function geometry(container,button,vertical){
    const c=container.getBoundingClientRect(),b=button.getBoundingClientRect();
    const insetX=vertical?5:0,insetY=vertical?3:0;
    return{x:b.left-c.left+insetX,y:b.top-c.top+insetY,w:b.width-insetX*2,h:b.height-insetY*2};
  }

  function moveNow(container,button,vertical){
    const indicator=findGroup(container);if(!indicator||!button)return;
    const g=geometry(container,button,vertical);
    const target=`translate3d(${g.x}px,${g.y}px,0)`;
    indicator.style.setProperty('--liquid-x',`${g.x}px`);
    indicator.style.setProperty('--liquid-y',`${g.y}px`);
    indicator.style.setProperty('--liquid-w',`${g.w}px`);
    indicator.style.setProperty('--liquid-h',`${g.h}px`);
    indicator.getAnimations().forEach(a=>a.cancel());
    const from=getComputedStyle(indicator).transform;
    indicator.animate([{transform:from==='none'?target:from},{transform:target}],{
      duration:vertical?165:190,
      easing:'cubic-bezier(.2,.78,.2,1)',
      fill:'forwards'
    }).onfinish=()=>{indicator.style.transform=target};
    root.classList.add('atlas-nav-moving');
    clearTimeout(root._atlasNavTimer);
    root._atlasNavTimer=setTimeout(()=>root.classList.remove('atlas-nav-moving'),220);
  }

  function installCapture(selector,vertical){
    const container=document.querySelector(selector);if(!container)return;
    container.addEventListener('pointerdown',event=>{
      const button=event.target.closest('button');
      if(!button||!container.contains(button))return;
      moveNow(container,button,vertical);
    },{capture:true,passive:true});
  }

  function stamp(){
    const brand=document.querySelector('.brand-copy small');
    if(brand)brand.textContent="ASSASSIN'S CREED SHADOWS · ALPHA 0.9.4.0";
  }

  function init(){
    dedupeIcons();
    installCapture('.bottom-nav',false);
    installCapture('.quick-rail',true);
    stamp();
    root.dataset.atlasIpadNav='0.9.4.0';
    setTimeout(dedupeIcons,250);
    setTimeout(dedupeIcons,900);
  }
  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',init,{once:true}):init();
})();
