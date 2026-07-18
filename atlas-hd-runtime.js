(() => {
  'use strict';
  const hd=window.AtlasHDMap;
  if(!hd||!hd.cache)return;
  const nativeSet=hd.cache.set.bind(hd.cache);
  let settleTimer=0;
  hd.cache.set=function(...args){
    const result=nativeSet(...args);
    if(typeof scheduleDraw==='function')scheduleDraw();
    clearTimeout(settleTimer);
    settleTimer=setTimeout(()=>{
      if(typeof scheduleDraw==='function')scheduleDraw();
    },180);
    return result;
  };
})();
