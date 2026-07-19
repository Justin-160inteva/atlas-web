const CACHE='atlas-alpha-0939-pages-v1';
const ASSETS=['./','./index.html','./styles.css','./alpha03.css','./route.css','./smart-route.css','./atlas-smart-route-0932.css','./performance-071.css','./performance-074.css','./performance-092.css','./atlas-080.css','./atlas-typography-093.css','./atlas-ui-fix-0931.css','./atlas-liquid-nav-0933.css','./atlas-liquid-nav-0934.css','./atlas-nav-layout-0937.css','./atlas-controls-0938.css','./evidence-studio.css','./multiview-091.css','./public-library.css','./atlas-icons.js','./atlas-i18n.js','./location-names.js','./location-title-polish.js','./location-search-patch.js','./route-engine.js','./smart-route.js','./performance-071.js','./performance-074.js','./performance-092.js','./atlas-080.js','./atlas-ui-fix-0931.js','./atlas-liquid-nav-0933.js','./atlas-liquid-nav-0934.js','./atlas-controls-0938.js','./atlas-data-guard-0939.js','./page-zoom-guard.js','./atlas-hd-init.js','./atlas-hd-map.js','./atlas-hd-runtime.js','./atlas-evidence-studio.js','./atlas-evidence-workflow.js','./atlas-multiview-091.js','./atlas-public-library.js','./atlas-analysis-import.js','./app.js','./marker-state.js','./manifest.webmanifest','./icon-180.png','./icon-192.png','./icon-512.png','./assets/world-map-4096.webp','./data/locations.json','./data/categories.json','./data/regions.json','./data/building-templates.json','./data/public-source-library.json','./data/authorizations.json','./data/dada-ac-shadows-catalog.json','./data/analysis-index.json','./data/analysis-results/dada-temples-36.json'];
const CORE_DATA=/\/(?:data\/(?:locations|categories|regions)\.json|assets\/world-map-4096\.webp)(?:\?|$)/;
self.addEventListener('install',event=>{
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE).then(cache=>Promise.allSettled(ASSETS.map(asset=>cache.add(asset)))));
});
self.addEventListener('activate',event=>{
  event.waitUntil(Promise.all([
    caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))),
    self.clients.claim()
  ]));
});
self.addEventListener('fetch',event=>{
  if(event.request.method!=='GET')return;
  const request=event.request;
  if(request.mode==='navigate'){
    event.respondWith(fetch(request,{cache:'no-store'}).then(response=>{
      if(response.ok)caches.open(CACHE).then(cache=>cache.put('./index.html',response.clone()));
      return response;
    }).catch(()=>caches.match('./index.html')));
    return;
  }
  if(CORE_DATA.test(new URL(request.url).pathname)){
    event.respondWith(caches.match(request,{ignoreSearch:true}).then(cached=>{
      const network=fetch(request,{cache:'no-store'}).then(response=>{
        if(response.ok)caches.open(CACHE).then(cache=>cache.put(request,response.clone()));
        return response;
      });
      if(cached){event.waitUntil(network.catch(()=>{}));return cached}
      return network;
    }));
    return;
  }
  event.respondWith(fetch(request).then(response=>{
    if(response.ok)caches.open(CACHE).then(cache=>cache.put(request,response.clone()));
    return response;
  }).catch(()=>caches.match(request,{ignoreSearch:true})));
});
