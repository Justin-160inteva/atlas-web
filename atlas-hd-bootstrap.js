'use strict';
var mapCanvas=document.getElementById('mapCanvas');
(() => {
  let knownSize=0;
  let fadeTimer=0;
  function watch(){
    const hd=window.AtlasHDMap;
    if(hd&&hd.cache){
      if(hd.cache.size!==knownSize){
        knownSize=hd.cache.size;
        clearInterval(fadeTimer);
        let frames=0;
        fadeTimer=setInterval(()=>{
          if(typeof scheduleDraw==='function')scheduleDraw();
          if(++frames>=6)clearInterval(fadeTimer);
        },34);
      }
    }
    requestAnimationFrame(watch);
  }
  requestAnimationFrame(watch);
})();