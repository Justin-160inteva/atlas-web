(() => {
  'use strict';
  const hd=window.AtlasHDMap;
  if(!hd||!hd.cache)return;
  const nativeSet=hd.cache.set.bind(hd.cache);
  hd.cache.set=function(...args){
    const result=nativeSet(...args);
    [0,40,90,160,240].forEach(delay=>setTimeout(()=>{
      if(typeof scheduleDraw==='function')scheduleDraw();
    },delay));
    return result;
  };
})();