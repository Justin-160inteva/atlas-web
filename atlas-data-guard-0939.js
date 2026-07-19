(() => {
  'use strict';
  const VERSION='0.9.3.9';
  const nativeFetch=window.fetch.bind(window);
  const guarded=new Set(['data/locations.json','data/categories.json','data/regions.json']);
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const pathOf=input=>{
    try{return new URL(typeof input==='string'?input:input.url,location.href).pathname.replace(/^.*\/atlas-web\//,'')}catch{return String(input)}
  };
  async function validJsonResponse(response,path){
    if(!response||!response.ok)return null;
    const text=await response.clone().text();
    if(!text.trim())return null;
    try{
      const value=JSON.parse(text);
      if(!Array.isArray(value))return null;
      if(path==='data/locations.json'&&value.length<3000)return null;
      if(path!=='data/locations.json'&&value.length<1)return null;
      return new Response(text,{status:200,headers:{'Content-Type':'application/json','X-Atlas-Data-Guard':VERSION}});
    }catch{return null}
  }
  async function cacheFallback(request,path){
    if(!('caches'in window))return null;
    const candidates=[request,new Request(new URL(path,location.href).href),path];
    for(const candidate of candidates){
      const cached=await caches.match(candidate).catch(()=>null);
      const valid=await validJsonResponse(cached,path);
      if(valid)return valid;
    }
    return null;
  }
  window.fetch=async function atlasGuardedFetch(input,init){
    const path=pathOf(input);
    if(!guarded.has(path))return nativeFetch(input,init);
    let lastError;
    for(let attempt=0;attempt<4;attempt++){
      try{
        const response=await nativeFetch(input,{...init,cache:attempt===0?'default':'reload'});
        const valid=await validJsonResponse(response,path);
        if(valid)return valid;
        lastError=new Error(`${path} returned invalid data`);
      }catch(error){lastError=error}
      if(attempt<3)await sleep(180*(attempt+1));
    }
    const cached=await cacheFallback(input instanceof Request?input:new Request(new URL(String(input),location.href).href),path);
    if(cached)return cached;
    throw lastError||new Error(`${path} unavailable`);
  };
  document.documentElement.dataset.atlasDataGuard=VERSION;
})();
