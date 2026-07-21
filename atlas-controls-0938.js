(() => {
  'use strict';

  const RELEASE_VERSION=window.AtlasRelease?.version||'0.9.4.10';
  const DESIGN_VERSION='0.9.4.12b-2';
  const root=document.documentElement;
  let lastMapPoint={x:innerWidth/2,y:innerHeight/2};
  let activeBurst=null;
  let repairFrame=0;

  const svg=(name,body,fill='none')=>`<svg class="atlas-control-icon atlas-control-icon-${name}" viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="${fill}">${body}</svg>`;
  const icons=Object.freeze({
    map:svg('map','<path d="m3.8 6.8 5.1-2.7 6.2 2.7 5.1-2.7v13.1l-5.1 2.7-6.2-2.7-5.1 2.7Z"/><path d="M8.9 4.1v13.1m6.2-10.4v13.1"/><circle cx="15.1" cy="11.2" r="1.25"/>'),
    filter:svg('filter','<path d="M4 6.5h7.5m4 0H20M4 12h3.5m4 0H20M4 17.5h8.5m4 0H20"/><circle cx="13.5" cy="6.5" r="1.45"/><circle cx="9.5" cy="12" r="1.45"/><circle cx="14.5" cy="17.5" r="1.45"/>'),
    route:svg('route','<circle cx="5.2" cy="17.5" r="2.1"/><circle cx="18.8" cy="6.5" r="2.1"/><path d="M7.3 17.5c4.8 0 2.7-8.9 7.6-8.9h1.8"/><path d="m14.8 6.7 1.9 1.9-1.9 1.9"/>'),
    progress:svg('progress','<path d="M12 3.5a8.5 8.5 0 1 1-7.6 4.7"/><path d="M4.4 4.3v3.9h3.9"/><path d="m8.4 12.2 2.3 2.3 4.9-5"/>'),
    favorite:svg('favorite','<path d="M20.1 5.4a5.15 5.15 0 0 0-7.3 0L12 6.2l-.8-.8a5.15 5.15 0 0 0-7.3 7.3l.8.8L12 20.3l7.3-6.8.8-.8a5.15 5.15 0 0 0 0-7.3Z"/>'),
    all:svg('all','<rect x="4" y="4" width="6.2" height="6.2" rx="1.65"/><rect x="13.8" y="4" width="6.2" height="6.2" rx="1.65"/><rect x="4" y="13.8" width="6.2" height="6.2" rx="1.65"/><rect x="13.8" y="13.8" width="6.2" height="6.2" rx="1.65"/>'),
    locations:svg('locations','<path d="M12 21s6-5.2 6-11a6 6 0 1 0-12 0c0 5.8 6 11 6 11Z"/><circle cx="12" cy="10" r="2.15"/>'),
    collectibles:svg('collectibles','<path d="m12 3.2 7 6.5-7 11.1L5 9.7Z"/><path d="m5 9.7 7 3.7 7-3.7M8.6 6.35 12 13.4l3.4-7.05"/>'),
    activities:svg('activities','<path d="m5.1 4.1 5.6 5.6M3.5 2.8l3.4.4.4 3.4M10.7 9.7 5 15.4l-1.6 4.8 4.8-1.6 5.7-5.7"/><path d="m18.9 4.1-5.6 5.6m7.2-6.9-3.4.4-.4 3.4m-3.4 3.1 5.7 5.7 1.6 4.8-4.8-1.6-5.7-5.7"/>'),
    locate:svg('locate','<circle cx="12" cy="12" r="6.25"/><circle cx="12" cy="12" r="1.65" fill="currentColor" stroke="none"/><path d="M12 2.8v3M12 18.2v3M2.8 12h3M18.2 12h3"/>'),
    settings:svg('settings','<circle cx="12" cy="12" r="3.05"/><path d="M9.7 3.5h4.6l.5 2.1 1.5.9 2-.6 2.3 4-1.6 1.5v1.8l1.6 1.5-2.3 4-2-.6-1.5.9-.5 2.1H9.7l-.5-2.1-1.5-.9-2 .6-2.3-4L5 13.8V12l-1.6-1.5 2.3-4 2 .6 1.5-.9Z"/>'),
    zoomIn:svg('zoom-in','<path d="M12 6v12M6 12h12"/>'),
    zoomOut:svg('zoom-out','<path d="M6 12h12"/>'),
    reset:svg('reset','<path d="M5.1 8.4A7.8 7.8 0 1 1 4.6 15"/><path d="M4.8 4.6v4.2H9"/><circle cx="12" cy="12" r="1.35" fill="currentColor" stroke="none"/>'),
    search:svg('search','<circle cx="10.7" cy="10.7" r="6.1"/><path d="m15.2 15.2 4.2 4.2"/>'),
    close:svg('close','<path d="m7 7 10 10M17 7 7 17"/>'),
    heart:svg('heart','<path d="M20.1 5.4a5.15 5.15 0 0 0-7.3 0L12 6.2l-.8-.8a5.15 5.15 0 0 0-7.3 7.3l.8.8L12 20.3l7.3-6.8.8-.8a5.15 5.15 0 0 0 0-7.3Z"/>','currentColor')
  });

  function loadStyle(){
    document.querySelectorAll('link[data-atlas-control-icons]').forEach(node=>{if(node.dataset.atlasControlIcons!==DESIGN_VERSION)node.remove()});
    if(document.querySelector(`link[data-atlas-control-icons="${DESIGN_VERSION}"]`))return;
    const link=document.createElement('link');
    link.rel='stylesheet';
    link.href=`atlas-controls-0938.css?v=${encodeURIComponent(RELEASE_VERSION)}&build=controls-09412b2`;
    link.dataset.atlasControlIcons=DESIGN_VERSION;
    document.head.appendChild(link);
  }

  function directSvg(host){return host?.querySelector(':scope > svg.atlas-control-icon')||null}
  function installIcon(host,key,extraClass=''){
    if(!host||!icons[key])return false;
    const current=directSvg(host);
    const valid=host.dataset.atlasIconKey===key&&host.children.length===1&&current?.classList.contains(`atlas-control-icon-${key}`);
    if(valid)return false;
    host.innerHTML=icons[key];
    host.dataset.atlasIconKey=key;
    if(extraClass)directSvg(host)?.classList.add(...extraClass.split(/\s+/).filter(Boolean));
    return true;
  }

  function replaceIcons(){
    const nav={map:'map',filter:'filter',route:'route',progress:'progress',favorites:'favorite'};
    document.querySelectorAll('.bottom-nav .nav-item').forEach(button=>installIcon(button.querySelector(':scope > span'),nav[button.dataset.panel]||'map'));
    const rail={all:'all',locations:'locations',collectibles:'collectibles',activities:'activities',favorites:'favorite'};
    document.querySelectorAll('.quick-rail .rail-button').forEach(button=>installIcon(button.querySelector('.rail-icon'),rail[button.dataset.mode]||'locations'));
    installIcon(document.getElementById('zoomIn'),'zoomIn');
    installIcon(document.getElementById('zoomOut'),'zoomOut');
    installIcon(document.getElementById('resetView'),'reset');
    installIcon(document.getElementById('locateBtn'),'locate');
    installIcon(document.querySelector('#searchTrigger > .icon'),'search');
    installIcon(document.querySelector('#searchOverlay .search-input-row > span'),'search');

    const settings=document.getElementById('evidenceStudioBtn');
    if(settings){
      installIcon(settings,'settings','atlas-settings-icon-09411a atlas-settings-icon-09412b2');
      settings.classList.add('atlas-settings-button');
      settings.setAttribute('aria-label','打开设置与数据中心');
      if(!settings.hasAttribute('aria-expanded'))settings.setAttribute('aria-expanded','false');
      settings.dataset.iconDesign='clean-radial-09411a';
      settings.dataset.controlIconDesign='precision-gear-09412b2';
    }

    document.querySelectorAll('.close-panel,.close-route,.close-progress').forEach(button=>installIcon(button,'close'));
  }

  function scheduleRepair(){
    if(repairFrame)return;
    repairFrame=requestAnimationFrame(()=>{repairFrame=0;replaceIcons()});
  }

  function observeIconHosts(){
    const hosts=['.bottom-nav','.quick-rail','.map-controls','.top-bar','#searchOverlay'].map(selector=>document.querySelector(selector)).filter(Boolean);
    hosts.forEach(host=>new MutationObserver(scheduleRepair).observe(host,{childList:true,subtree:true}));
    new MutationObserver(records=>{if(records.some(record=>[...record.addedNodes].some(node=>node.nodeType===1)))scheduleRepair()}).observe(document.body,{childList:true});
  }

  function rememberPoint(){document.getElementById('mapCanvas')?.addEventListener('pointerup',event=>{lastMapPoint={x:event.clientX,y:event.clientY}},{capture:true,passive:true})}
  function burst(point){
    activeBurst?.remove();
    const host=document.querySelector('.app-shell');if(!host)return;
    const burstNode=document.createElement('span');burstNode.className='atlas-heart-burst';burstNode.style.left=`${point.x}px`;burstNode.style.top=`${point.y}px`;
    const values=[[-26,-52,-12,13,0],[-8,-68,8,15,70],[16,-57,14,12,130],[30,-45,-6,10,190]];
    for(const [x,y,r,size,delay] of values){const particle=document.createElement('span');particle.className='atlas-heart-particle';particle.style.setProperty('--heart-x',`${x}px`);particle.style.setProperty('--heart-y',`${y}px`);particle.style.setProperty('--heart-rotate',`${r}deg`);particle.style.setProperty('--heart-size',`${size}px`);particle.style.setProperty('--heart-delay',`${delay}ms`);particle.innerHTML=icons.heart;burstNode.appendChild(particle)}
    const badge=document.createElement('span');badge.className='atlas-favourite-badge';badge.style.left=`${point.x+15}px`;badge.style.top=`${point.y-15}px`;badge.innerHTML=icons.heart;
    host.append(burstNode,badge);activeBurst=burstNode;setTimeout(()=>burstNode.remove(),1300);setTimeout(()=>badge.remove(),1150);
  }
  function wrapFavourite(){let attempts=0;const timer=setInterval(()=>{attempts++;const original=window.toggleFavorite;if(typeof original!=='function'||original.__atlasFavoriteWrapped||original.__atlas0938){if(attempts>40)clearInterval(timer);return}const wrapped=id=>{const before=new Set(JSON.parse(localStorage.getItem('atlas.favorites')||'[]'));original(id);const after=new Set(JSON.parse(localStorage.getItem('atlas.favorites')||'[]'));if(!before.has(id)&&after.has(id))burst(lastMapPoint)};wrapped.__atlasFavoriteWrapped=true;window.toggleFavorite=wrapped;clearInterval(timer)},100)}
  function loadIPadLayer(){
    document.querySelectorAll('link[data-atlas-ipad-nav],script[data-atlas-ipad-nav]').forEach(node=>{if(node.dataset.atlasIpadNav!==RELEASE_VERSION)node.remove()});
    if(!document.querySelector(`link[data-atlas-ipad-nav="${RELEASE_VERSION}"]`)){const link=document.createElement('link');link.rel='stylesheet';link.href=`atlas-ipad-nav-0940.css?v=${RELEASE_VERSION}`;link.dataset.atlasIpadNav=RELEASE_VERSION;document.head.appendChild(link)}
    if(!document.querySelector(`script[data-atlas-ipad-nav="${RELEASE_VERSION}"]`)){const script=document.createElement('script');script.src=`atlas-ipad-nav-0940.js?v=${RELEASE_VERSION}`;script.defer=true;script.dataset.atlasIpadNav=RELEASE_VERSION;document.body.appendChild(script)}
  }

  function audit(){
    const groups={
      bottom:[...document.querySelectorAll('.bottom-nav .nav-item > span')],
      rail:[...document.querySelectorAll('.quick-rail .rail-icon')],
      map:[...document.querySelectorAll('.map-controls > button')],
      top:[document.getElementById('locateBtn'),document.getElementById('evidenceStudioBtn')].filter(Boolean),
      search:[document.querySelector('#searchTrigger > .icon'),document.querySelector('#searchOverlay .search-input-row > span')].filter(Boolean)
    };
    const entries=Object.values(groups).flat();
    const settings=document.getElementById('evidenceStudioBtn');
    const valid=entries.every(host=>host.children.length===1&&Boolean(directSvg(host))&&!([...host.childNodes].some(node=>node.nodeType===Node.TEXT_NODE&&node.textContent.trim())));
    return {releaseVersion:RELEASE_VERSION,designVersion:DESIGN_VERSION,valid,total:entries.length,groups:Object.fromEntries(Object.entries(groups).map(([key,value])=>[key,value.length])),repairScheduled:Boolean(repairFrame),settingsDesign:settings?.dataset.iconDesign||'',precisionSettingsDesign:settings?.dataset.controlIconDesign||''};
  }

  function init(){
    loadStyle();replaceIcons();observeIconHosts();rememberPoint();wrapFavourite();loadIPadLayer();
    root.dataset.atlasControls=RELEASE_VERSION;
    root.dataset.atlasControlIconDesign=DESIGN_VERSION;
    root.dataset.atlasSettingsOwner='atlas-settings.js';
    window.AtlasControlIcons=Object.freeze({releaseVersion:RELEASE_VERSION,designVersion:DESIGN_VERSION,icons,replaceIcons,scheduleRepair,audit});
  }

  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',init,{once:true}):init();
})();