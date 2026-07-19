(() => {
  'use strict';
  const VERSION=window.AtlasRelease?.version||'0.9.4.4';
  const root=document.documentElement;
  let lastMapPoint={x:innerWidth/2,y:innerHeight/2};
  let activeBurst=null;

  const svg=(body,fill='none')=>`<svg class="atlas-control-icon" viewBox="0 0 24 24" aria-hidden="true" fill="${fill}">${body}</svg>`;
  const icons={
    map:svg('<path d="M4 7.2 9 4l6 3 5-3v12.8L15 20l-6-3-5 3Z"/><path d="M9 4v13m6-10v13"/>'),
    filter:svg('<path d="M4 7h10m4 0h2M4 12h4m4 0h8M4 17h8m4 0h4"/><circle cx="16" cy="7" r="1.5"/><circle cx="10" cy="12" r="1.5"/><circle cx="14" cy="17" r="1.5"/>'),
    route:svg('<circle cx="5" cy="17" r="2"/><circle cx="19" cy="7" r="2"/><path d="M7 17c4 0 3-7 7-7h3"/>'),
    progress:svg('<path d="M12 4a8 8 0 1 1-7.2 4.5"/><path d="M12 4v8l5 3"/>'),
    favorite:svg('<path d="M12 20s-7-4.1-7-9.5A4.5 4.5 0 0 1 12 7a4.5 4.5 0 0 1 7 3.5C19 15.9 12 20 12 20Z"/>'),
    all:svg('<path d="M12 3l1.7 4.3L18 9l-4.3 1.7L12 15l-1.7-4.3L6 9l4.3-1.7Z"/><path d="M18.5 14.5 19.4 17l2.6.9-2.6.9-.9 2.6-.9-2.6-2.6-.9 2.6-.9Z"/>'),
    locations:svg('<path d="M12 21s6-5.1 6-11a6 6 0 1 0-12 0c0 5.9 6 11 6 11Z"/><circle cx="12" cy="10" r="2.2"/>'),
    collectibles:svg('<path d="m12 3 7 6-7 12L5 9Z"/><path d="m5 9 7 4 7-4M9 5l3 8 3-8"/>'),
    activities:svg('<path d="m5 4 15 15M19 4 4 19"/><path d="m4 4 4 1-3 3m15-4-4 1 3 3M4 20l1-4 3 3m12 1-1-4-3 3"/>'),
    locate:svg('<path d="M12 3v3m0 12v3M3 12h3m12 0h3"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>'),
    settings:svg('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.12 2.12-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.04 1.56V20h-3v-.08a1.7 1.7 0 0 0-1.04-1.56 1.7 1.7 0 0 0-1.88.34l-.06.06-2.12-2.12.06-.06A1.7 1.7 0 0 0 7 14.7a1.7 1.7 0 0 0-1.56-1.04H5v-3h.44A1.7 1.7 0 0 0 7 9.62a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.12-2.12.06.06A1.7 1.7 0 0 0 10.66 6a1.7 1.7 0 0 0 1.04-1.56V4h3v.44A1.7 1.7 0 0 0 15.74 6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.12 2.12-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.56 1.04H21v3h-.04A1.7 1.7 0 0 0 19.4 15Z"/>'),
    heart:svg('<path d="M12 20s-7-4.1-7-9.5A4.5 4.5 0 0 1 12 7a4.5 4.5 0 0 1 7 3.5C19 15.9 12 20 12 20Z"/>','currentColor')
  };

  function replaceIcons(){
    const nav={map:'map',filter:'filter',route:'route',progress:'progress',favorites:'favorite'};
    document.querySelectorAll('.bottom-nav .nav-item').forEach(button=>{const slot=button.querySelector(':scope>span');if(slot)slot.innerHTML=icons[nav[button.dataset.panel]]||icons.map});
    const rail={all:'all',locations:'locations',collectibles:'collectibles',activities:'activities',favorites:'favorite'};
    document.querySelectorAll('.quick-rail .rail-button').forEach(button=>{const slot=button.querySelector('.rail-icon');if(slot)slot.innerHTML=icons[rail[button.dataset.mode]]||icons.locations});
    const locate=document.getElementById('locateBtn');if(locate)locate.innerHTML=icons.locate;
    const settings=document.getElementById('evidenceStudioBtn');if(settings){settings.innerHTML=icons.settings;settings.classList.add('atlas-settings-button');settings.setAttribute('aria-label','打开设置');settings.setAttribute('aria-expanded','false')}
  }

  function rememberPoint(){document.getElementById('mapCanvas')?.addEventListener('pointerup',event=>{lastMapPoint={x:event.clientX,y:event.clientY}},{capture:true,passive:true})}
  function burst(point){activeBurst?.remove();const host=document.querySelector('.app-shell');if(!host)return;const burstNode=document.createElement('span');burstNode.className='atlas-heart-burst';burstNode.style.left=`${point.x}px`;burstNode.style.top=`${point.y}px`;const values=[[-26,-52,-12,13,0],[-8,-68,8,15,70],[16,-57,14,12,130],[30,-45,-6,10,190]];for(const [x,y,r,size,delay] of values){const particle=document.createElement('span');particle.className='atlas-heart-particle';particle.style.setProperty('--heart-x',`${x}px`);particle.style.setProperty('--heart-y',`${y}px`);particle.style.setProperty('--heart-rotate',`${r}deg`);particle.style.setProperty('--heart-size',`${size}px`);particle.style.setProperty('--heart-delay',`${delay}ms`);particle.innerHTML=icons.heart;burstNode.appendChild(particle)}const badge=document.createElement('span');badge.className='atlas-favourite-badge';badge.style.left=`${point.x+15}px`;badge.style.top=`${point.y-15}px`;badge.innerHTML=icons.heart;host.append(burstNode,badge);activeBurst=burstNode;setTimeout(()=>burstNode.remove(),1300);setTimeout(()=>badge.remove(),1150)}
  function wrapFavourite(){let attempts=0;const timer=setInterval(()=>{attempts++;const original=window.toggleFavorite;if(typeof original!=='function'||original.__atlasFavoriteWrapped||original.__atlas0938){if(attempts>40)clearInterval(timer);return}const wrapped=id=>{const before=new Set(JSON.parse(localStorage.getItem('atlas.favorites')||'[]'));original(id);const after=new Set(JSON.parse(localStorage.getItem('atlas.favorites')||'[]'));if(!before.has(id)&&after.has(id))burst(lastMapPoint)};wrapped.__atlasFavoriteWrapped=true;window.toggleFavorite=wrapped;clearInterval(timer)},100)}
  function loadIPadLayer(){
    document.querySelectorAll('link[data-atlas-ipad-nav],script[data-atlas-ipad-nav]').forEach(node=>{if(node.dataset.atlasIpadNav!==VERSION)node.remove()});
    if(!document.querySelector(`link[data-atlas-ipad-nav="${VERSION}"]`)){const link=document.createElement('link');link.rel='stylesheet';link.href=`atlas-ipad-nav-0940.css?v=${VERSION}`;link.dataset.atlasIpadNav=VERSION;document.head.appendChild(link)}
    if(!document.querySelector(`script[data-atlas-ipad-nav="${VERSION}"]`)){const script=document.createElement('script');script.src=`atlas-ipad-nav-0940.js?v=${VERSION}`;script.defer=true;script.dataset.atlasIpadNav=VERSION;document.body.appendChild(script)}
  }
  function init(){replaceIcons();rememberPoint();wrapFavourite();loadIPadLayer();root.dataset.atlasControls=VERSION;root.dataset.atlasSettingsOwner='atlas-settings.js'}
  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',init,{once:true}):init();
})();
