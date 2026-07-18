(() => {
  'use strict';

  const viewport=document.querySelector('meta[name="viewport"]');
  if(viewport){
    viewport.setAttribute('content','width=device-width,initial-scale=1,minimum-scale=1,maximum-scale=1,viewport-fit=cover,user-scalable=no');
  }

  const preventNativeZoom=event=>{
    if(event.cancelable)event.preventDefault();
  };

  document.addEventListener('dblclick',preventNativeZoom,{capture:true,passive:false});
  ['gesturestart','gesturechange','gestureend'].forEach(type=>{
    document.addEventListener(type,preventNativeZoom,{capture:true,passive:false});
  });

  const style=document.createElement('style');
  style.textContent=`
    html,body,.app-shell{-webkit-text-size-adjust:100%;overscroll-behavior:none}
    button,.map-controls,.map-controls button{touch-action:manipulation}
    .map-controls button{-webkit-user-select:none;user-select:none}
  `;
  document.head.appendChild(style);

  const controls=document.querySelector('.map-controls');
  if(!controls)return;

  controls.addEventListener('dblclick',preventNativeZoom,{capture:true,passive:false});

  controls.querySelectorAll('button').forEach(button=>{
    button.addEventListener('touchend',event=>{
      if(event.cancelable)event.preventDefault();
      event.stopPropagation();
      button.click();
    },{capture:true,passive:false});
  });
})();