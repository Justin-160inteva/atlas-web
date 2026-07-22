(function(){'use strict';
const coarse=matchMedia('(pointer:coarse)').matches||/iPad|iPhone|iPod|Android/i.test(navigator.userAgent);
if(!coarse)return;
const ipad=/iPad/i.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
const largeTouch=navigator.maxTouchPoints>1&&Math.min(screen.width,screen.height)>=700;
// Alpha 0.9.4.8 iPad Canvas hotfix is the sole compositor/gesture owner on large touch devices.
if(ipad||largeTouch)return;
const canvas=document.getElementById('mapCanvas');
const perf={interacting:false,lastFrame:0,settleTimer:0,grid:null,gridSource:null,gridSize:48};
window.AtlasMobilePerf=perf;
document.documentElement.classList.add('atlas-mobile-performance');

function setInteracting(value){
  perf.interacting=value;
  document.documentElement.classList.toggle('atlas-interacting',value);
  clearTimeout(perf.settleTimer);
  if(!value)perf.settleTimer=setTimeout(()=>{scheduleDraw();},70);
}
canvas.addEventListener('pointerdown',()=>setInteracting(true),{capture:true,passive:true});
canvas.addEventListener('pointerup',()=>setInteracting(false),{capture:true,passive:true});
canvas.addEventListener('pointercancel',()=>setInteracting(false),{capture:true,passive:true});
canvas.addEventListener('touchend',()=>setInteracting(false),{capture:true,passive:true});

const originalSchedule=scheduleDraw;
scheduleDraw=function(){
  if(state.framePending)return;
  const now=performance.now();
  const minGap=perf.interacting?22:12;
  const wait=Math.max(0,minGap-(now-perf.lastFrame));
  state.framePending=true;
  setTimeout(()=>requestAnimationFrame(()=>{
    state.framePending=false;
    perf.lastFrame=performance.now();
    draw();
  }),wait);
};

function buildGrid(){
  if(perf.gridSource===state.locations&&perf.grid)return;
  const n=perf.gridSize,grid=Array.from({length:n*n},()=>[]);
  for(const l of state.locations){
    const x=Math.max(0,Math.min(n-1,Math.floor(l.atlas_x*n)));
    const y=Math.max(0,Math.min(n-1,Math.floor(l.atlas_y*n)));
    grid[y*n+x].push(l);
  }
  perf.grid=grid;perf.gridSource=state.locations;
}
function eligible(l){
  if(!state.enabled.has(l.category_id))return false;
  if(state.mode==='all')return true;
  if(state.mode==='favorites')return state.favorites.has(l.id);
  return categoryGroup(state.categoryMap.get(l.category_id)?.title)===state.mode;
}
buildMarkers=function(){
  buildGrid();
  const n=perf.gridSize;
  const left=(-50-state.offsetX)/(4096*state.scale),right=(innerWidth+50-state.offsetX)/(4096*state.scale);
  const top=(-50-state.offsetY)/(4096*state.scale),bottom=(innerHeight+50-state.offsetY)/(4096*state.scale);
  const x0=Math.max(0,Math.floor(Math.min(left,right)*n)),x1=Math.min(n-1,Math.floor(Math.max(left,right)*n));
  const y0=Math.max(0,Math.floor(Math.min(top,bottom)*n)),y1=Math.min(n-1,Math.floor(Math.max(top,bottom)*n));
  const out=[];
  for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++)for(const l of perf.grid[y*n+x]){
    if(!eligible(l))continue;
    const p=mapToScreen(l);
    if(p.x<-40||p.y<-40||p.x>innerWidth+40||p.y>innerHeight+40)continue;
    out.push({x:p.x,y:p.y,count:1,items:[l]});
  }
  return out;
};

const detailedMarker=drawMarker;
drawMarker=function(c,relative){
  if(!perf.interacting)return detailedMarker(c,relative);
  const l=c.items[0],cat=state.categoryMap.get(l.category_id)?.title||'',icon=iconType(cat);
  const discovered=state.discovered.has(l.id),selected=l.id===state.selected?.id;
  const r=selected?14:Math.max(5.5,Math.min(9,5.5+relative*1.8));
  ctx.save();ctx.globalAlpha=discovered?.3:1;
  ctx.beginPath();ctx.arc(c.x,c.y,r,0,Math.PI*2);
  ctx.fillStyle=AtlasIcons.color(icon);ctx.fill();
  ctx.lineWidth=1;ctx.strokeStyle='rgba(255,244,226,.7)';ctx.stroke();
  if(relative>.9||selected)AtlasIcons.draw(ctx,icon,c.x,c.y,selected?17:Math.max(8,r*1.15),{alpha:1});
  ctx.restore();
};

// Static route while touching: avoids a permanent animation loop on iPad Safari.
const detailedRoute=drawRoute;
drawRoute=function(){
  if(!perf.interacting)return detailedRoute();
  if(state.route.length<2)return;
  const pts=state.route.map(mapToScreen);
  ctx.save();ctx.lineCap='round';ctx.lineJoin='round';ctx.beginPath();
  pts.forEach((p,i)=>i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y));
  ctx.strokeStyle='rgba(230,189,112,.82)';ctx.lineWidth=3;ctx.stroke();ctx.restore();
};

function tuneCanvas(){
  const target=innerWidth>=700?1.65:1.4;
  const width=Math.floor(innerWidth*target),height=Math.floor(innerHeight*target);
  if(canvas.width===width&&canvas.height===height)return;
  canvas.width=width;canvas.height=height;canvas.style.width=innerWidth+'px';canvas.style.height=innerHeight+'px';
  ctx.setTransform(target,0,0,target,0,0);scheduleDraw();
}
addEventListener('resize',()=>setTimeout(tuneCanvas,0),{passive:true});
setTimeout(tuneCanvas,350);
})();
