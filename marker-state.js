'use strict';
function drawMarker(c,relative){
  const l=c.items[0];
  const cat=state.categoryMap.get(l.category_id)?.title||'';
  const icon=iconType(cat);
  const selected=l.id===state.selected?.id;
  const discovered=state.discovered.has(l.id);
  const favorite=state.favorites.has(l.id);
  const inRoute=state.route.some(x=>x.id===l.id);
  const r=selected?18:clamp(6.5+relative*3.2,7,12.5);
  const iconSize=selected?22:clamp(9+relative*4,10,15);
  const base=AtlasIcons.color(icon);
  ctx.save();
  ctx.globalAlpha=discovered?.3:1;
  ctx.shadowColor=selected?'rgba(224,60,72,.62)':'rgba(0,0,0,.46)';
  ctx.shadowBlur=selected?18:6;
  ctx.shadowOffsetY=selected?0:2;
  ctx.beginPath();ctx.arc(c.x,c.y,r+2.5,0,Math.PI*2);
  ctx.fillStyle=selected?'rgba(255,245,228,.95)':'rgba(18,16,15,.86)';ctx.fill();
  ctx.shadowColor='transparent';
  ctx.beginPath();ctx.arc(c.x,c.y,r,0,Math.PI*2);
  const grad=ctx.createRadialGradient(c.x-r*.35,c.y-r*.4,1,c.x,c.y,r);
  grad.addColorStop(0,lighten(base,26));grad.addColorStop(1,base);
  ctx.fillStyle=grad;ctx.fill();
  ctx.lineWidth=selected?2.3:1.15;
  ctx.strokeStyle=inRoute?'#edc574':selected?'#fff7e8':'rgba(255,239,218,.72)';ctx.stroke();
  AtlasIcons.draw(ctx,icon,c.x,c.y,iconSize,{alpha:1});
  if(favorite){ctx.beginPath();ctx.arc(c.x+r*.72,c.y-r*.74,3.8,0,Math.PI*2);ctx.fillStyle='#d9af62';ctx.fill();ctx.strokeStyle='#fff5e6';ctx.stroke()}
  if(selected){ctx.beginPath();ctx.arc(c.x,c.y,r+7,0,Math.PI*2);ctx.strokeStyle='rgba(236,74,86,.62)';ctx.lineWidth=2;ctx.stroke()}
  ctx.restore();
}
