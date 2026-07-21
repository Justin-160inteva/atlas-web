'use strict';

const ATLAS_MARKER_DESIGN_VERSION='0.9.4.12b-1';
const ATLAS_MARKER_SELECTED_SCALE=1.28;
const ATLAS_MARKER_SELECTION_MS=190;
const ATLAS_MARKER_SELECTION_HARD_LIMIT=222;
const atlasMarkerAnimations=new Map();
let atlasMarkerLastSelectedId=null;

function atlasMarkerEase(t){return 1-Math.pow(1-t,3)}
function atlasMarkerTone(hex,amount){
  const n=parseInt(String(hex).replace('#',''),16);
  const r=clamp((n>>16)+amount,0,255),g=clamp(((n>>8)&255)+amount,0,255),b=clamp((n&255)+amount,0,255);
  return`rgb(${Math.round(r)},${Math.round(g)},${Math.round(b)})`;
}
function atlasMarkerSyncSelection(){
  const nextId=state.selected?.id??null;
  if(nextId===atlasMarkerLastSelectedId)return;
  const now=performance.now();
  const previousId=atlasMarkerLastSelectedId;
  atlasMarkerAnimations.clear();
  if(previousId)atlasMarkerAnimations.set(previousId,{from:ATLAS_MARKER_SELECTED_SCALE,to:1,start:now});
  if(nextId)atlasMarkerAnimations.set(nextId,{from:1,to:ATLAS_MARKER_SELECTED_SCALE,start:now});
  atlasMarkerLastSelectedId=nextId;
  scheduleDraw();
}
function atlasMarkerScale(id,selected){
  const animation=atlasMarkerAnimations.get(id);
  if(!animation)return selected?ATLAS_MARKER_SELECTED_SCALE:1;
  const reduceMotion=matchMedia('(prefers-reduced-motion: reduce)').matches;
  const duration=reduceMotion?0:ATLAS_MARKER_SELECTION_MS;
  const elapsed=performance.now()-animation.start;
  const t=duration?clamp(elapsed/duration,0,1):1;
  const value=animation.from+(animation.to-animation.from)*atlasMarkerEase(t);
  if(t>=1)atlasMarkerAnimations.delete(id);else scheduleDraw();
  return value;
}
function atlasMarkerDropletPath(radius){
  const shoulder=radius*.98,top=-radius*2.58;
  ctx.beginPath();
  ctx.moveTo(0,0);
  ctx.bezierCurveTo(-radius*.2,-radius*.34,-shoulder,-radius*.8,-shoulder,-radius*1.48);
  ctx.bezierCurveTo(-shoulder,-radius*2.14,-radius*.54,top,0,top);
  ctx.bezierCurveTo(radius*.54,top,shoulder,-radius*2.14,shoulder,-radius*1.48);
  ctx.bezierCurveTo(shoulder,-radius*.8,radius*.2,-radius*.34,0,0);
  ctx.closePath();
}
function atlasMarkerBadge(x,y,color){
  ctx.beginPath();
  ctx.arc(x,y,3.05,0,Math.PI*2);
  ctx.fillStyle=color;
  ctx.fill();
  ctx.lineWidth=.8;
  ctx.strokeStyle='rgba(255,255,255,.62)';
  ctx.stroke();
}

function drawMarker(c,relative){
  atlasMarkerSyncSelection();
  const location=c.items[0];
  const category=state.categoryMap.get(location.category_id)?.title||'';
  const icon=iconType(category);
  const selected=location.id===state.selected?.id;
  const discovered=state.discovered.has(location.id);
  const favorite=state.favorites.has(location.id);
  const inRoute=state.route.some(item=>item.id===location.id);
  const radius=clamp(7.8+relative*2.8,8.5,12.8);
  const iconSize=clamp(9.8+relative*3.6,11,16);
  const scale=atlasMarkerScale(location.id,selected);
  const base=AtlasIcons.color(icon);

  ctx.save();
  ctx.translate(c.x,c.y);
  ctx.scale(scale,scale);
  ctx.globalAlpha=discovered?.38:1;
  ctx.shadowColor='rgba(0,0,0,.38)';
  ctx.shadowBlur=7;
  ctx.shadowOffsetY=3;

  atlasMarkerDropletPath(radius);
  const fill=ctx.createLinearGradient(-radius*.8,-radius*2.5,radius*.7,-radius*.05);
  fill.addColorStop(0,atlasMarkerTone(base,40));
  fill.addColorStop(.42,atlasMarkerTone(base,13));
  fill.addColorStop(1,atlasMarkerTone(base,-18));
  ctx.fillStyle=fill;
  ctx.fill();

  ctx.shadowColor='transparent';
  atlasMarkerDropletPath(radius);
  ctx.lineWidth=1;
  ctx.strokeStyle='rgba(255,247,244,.58)';
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(-radius*.54,-radius*2.06);
  ctx.bezierCurveTo(-radius*.8,-radius*1.72,-radius*.78,-radius*1.25,-radius*.62,-radius*.96);
  ctx.strokeStyle='rgba(255,255,255,.34)';
  ctx.lineWidth=1.05;
  ctx.lineCap='round';
  ctx.stroke();

  AtlasIcons.draw(ctx,icon,0,-radius*1.48,iconSize,{alpha:1});
  if(inRoute)atlasMarkerBadge(-radius*.7,-radius*2.13,'#efc76f');
  if(favorite)atlasMarkerBadge(radius*.7,-radius*2.13,'#d59a55');
  ctx.restore();
}

window.AtlasMarkerDesign=Object.freeze({
  version:ATLAS_MARKER_DESIGN_VERSION,
  selectedScale:ATLAS_MARKER_SELECTED_SCALE,
  durationMs:ATLAS_MARKER_SELECTION_MS,
  render:drawMarker,
  scaleFor:id=>atlasMarkerScale(id,id===state.selected?.id),
  audit:()=>({
    version:ATLAS_MARKER_DESIGN_VERSION,
    shape:'anchored-long-tail-droplet',
    anchor:'bottom-tip',
    selectedScale:ATLAS_MARKER_SELECTED_SCALE,
    durationMs:ATLAS_MARKER_SELECTION_MS,
    selectionFeedback:'scale-only',
    selectionRing:false,
    selectionBorder:false,
    activeAnimations:atlasMarkerAnimations.size,
    selectedId:atlasMarkerLastSelectedId
  })
});

window.AtlasMarkerVisuals=Object.freeze({
  version:window.AtlasRelease?.version||'0.9.4.10',
  selectedScale:ATLAS_MARKER_SELECTED_SCALE,
  selectionDuration:ATLAS_MARKER_SELECTION_MS,
  selectionHardLimit:ATLAS_MARKER_SELECTION_HARD_LIMIT,
  minimumSelectionFrames:2,
  selectionUsesScaleOnly:true,
  selectionDecorationLayers:0,
  tipAnchorStable:true,
  scaleFor:id=>window.AtlasMarkerDesign.scaleFor(id),
  activeMotionCount:()=>atlasMarkerAnimations.size,
  geometry:Object.freeze({centerOffsetRadius:.58,shoulderRatio:.16,lowerCurveRatio:.58})
});
document.documentElement.dataset.atlasMarkerVisuals=window.AtlasMarkerVisuals.version;
document.documentElement.dataset.atlasMarkerOwner='marker-state.js';
