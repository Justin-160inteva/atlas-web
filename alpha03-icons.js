'use strict';

function atlasIconType(title=''){
  const t=title.toLowerCase();
  if(/castle|fort|citadel/.test(t))return'castle';
  if(/shrine/.test(t))return'shrine';
  if(/temple/.test(t))return'temple';
  if(/chest|loot/.test(t))return'chest';
  if(/gear|weapon|armor|katana|trinket/.test(t))return'gear';
  if(/quest|contract|mission/.test(t))return'quest';
  if(/merchant|vendor|shop/.test(t))return'merchant';
  if(/viewpoint|sync/.test(t))return'viewpoint';
  if(/kofun|tomb|grave/.test(t))return'tomb';
  if(/target|boss|samurai|ronin/.test(t))return'target';
  if(/scroll|page|letter|document/.test(t))return'scroll';
  if(/key/.test(t))return'key';
  if(/horse|stable/.test(t))return'stable';
  if(/hideout|safehouse/.test(t))return'hideout';
  return'location';
}

function categorySymbol(cat=''){
  return ({castle:'城',shrine:'社',temple:'寺',chest:'箱',gear:'装',quest:'任',merchant:'商',viewpoint:'望',tomb:'墓',target:'敌',scroll:'卷',key:'钥',stable:'马',hideout:'隐',location:'点'})[atlasIconType(cat)];
}

function atlasMarkerColors(type, discovered, selected){
  if(selected)return{fill:'#f34f5c',line:'#fff7ec',icon:'#fff'};
  if(discovered)return{fill:'#5f5b57',line:'#cfc6bc',icon:'#f2ece4'};
  const fills={castle:'#9f1e2b',shrine:'#b9473d',temple:'#8e4937',chest:'#b58a3e',gear:'#8352a8',quest:'#286f87',merchant:'#3d7e61',viewpoint:'#5c739f',tomb:'#66566f',target:'#a83a32',scroll:'#91744d',key:'#9a6b35',stable:'#6b7045',hideout:'#554d45',location:'#9f1e2b'};
  return{fill:fills[type]||fills.location,line:'#fff0df',icon:'#fff'};
}

function atlasDrawGlyph(type,x,y,size,color){
  ctx.save();ctx.translate(x,y);ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=Math.max(1.5,size*.1);ctx.lineCap='round';ctx.lineJoin='round';
  const s=size;
  if(type==='castle'){
    ctx.strokeRect(-s*.45,-s*.15,s*.9,s*.55);ctx.beginPath();ctx.moveTo(-s*.5,-s*.15);ctx.lineTo(-s*.5,-s*.45);ctx.lineTo(-s*.18,-s*.45);ctx.lineTo(-s*.18,-s*.15);ctx.moveTo(s*.18,-s*.15);ctx.lineTo(s*.18,-s*.45);ctx.lineTo(s*.5,-s*.45);ctx.lineTo(s*.5,-s*.15);ctx.stroke();
  }else if(type==='shrine'){
    ctx.beginPath();ctx.moveTo(-s*.5,-s*.35);ctx.lineTo(s*.5,-s*.35);ctx.moveTo(-s*.36,-s*.5);ctx.lineTo(-s*.28,-s*.35);ctx.moveTo(s*.36,-s*.5);ctx.lineTo(s*.28,-s*.35);ctx.moveTo(-s*.28,-s*.35);ctx.lineTo(-s*.2,s*.45);ctx.moveTo(s*.28,-s*.35);ctx.lineTo(s*.2,s*.45);ctx.moveTo(-s*.35,0);ctx.lineTo(s*.35,0);ctx.stroke();
  }else if(type==='temple'){
    ctx.beginPath();ctx.moveTo(-s*.5,-s*.1);ctx.lineTo(0,-s*.5);ctx.lineTo(s*.5,-s*.1);ctx.moveTo(-s*.38,-s*.08);ctx.lineTo(-s*.38,s*.4);ctx.lineTo(s*.38,s*.4);ctx.lineTo(s*.38,-s*.08);ctx.moveTo(-s*.5,s*.4);ctx.lineTo(s*.5,s*.4);ctx.stroke();
  }else if(type==='chest'){
    ctx.strokeRect(-s*.45,-s*.12,s*.9,s*.52);ctx.beginPath();ctx.arc(0,-s*.12,s*.45,Math.PI,0);ctx.moveTo(0,-s*.1);ctx.lineTo(0,s*.18);ctx.stroke();
  }else if(type==='gear'){
    ctx.beginPath();ctx.moveTo(-s*.38,s*.4);ctx.lineTo(s*.32,-s*.42);ctx.moveTo(-s*.1,-s*.14);ctx.lineTo(s*.38,s*.38);ctx.moveTo(-s*.34,s*.16);ctx.lineTo(-s*.16,s*.34);ctx.stroke();
  }else if(type==='quest'){
    ctx.beginPath();ctx.arc(0,-s*.2,s*.28,Math.PI*1.1,Math.PI*2.2);ctx.lineTo(0,s*.05);ctx.moveTo(0,s*.34);ctx.lineTo(0,s*.35);ctx.stroke();
  }else if(type==='merchant'){
    ctx.beginPath();ctx.arc(0,-s*.28,s*.18,0,Math.PI*2);ctx.moveTo(-s*.4,s*.38);ctx.quadraticCurveTo(0,-s*.02,s*.4,s*.38);ctx.stroke();
  }else if(type==='viewpoint'){
    ctx.beginPath();ctx.moveTo(-s*.48,s*.25);ctx.lineTo(0,-s*.42);ctx.lineTo(s*.48,s*.25);ctx.moveTo(-s*.24,s*.1);ctx.lineTo(0,s*.4);ctx.lineTo(s*.24,s*.1);ctx.stroke();
  }else if(type==='tomb'){
    ctx.beginPath();ctx.arc(0,-s*.12,s*.36,Math.PI,0);ctx.lineTo(s*.36,s*.4);ctx.lineTo(-s*.36,s*.4);ctx.closePath();ctx.stroke();
  }else if(type==='target'){
    ctx.beginPath();ctx.arc(0,0,s*.42,0,Math.PI*2);ctx.moveTo(-s*.58,0);ctx.lineTo(s*.58,0);ctx.moveTo(0,-s*.58);ctx.lineTo(0,s*.58);ctx.stroke();
  }else if(type==='scroll'){
    ctx.beginPath();ctx.moveTo(-s*.32,-s*.42);ctx.lineTo(s*.28,-s*.42);ctx.quadraticCurveTo(s*.45,-s*.42,s*.45,-s*.25);ctx.lineTo(s*.45,s*.32);ctx.lineTo(-s*.22,s*.32);ctx.quadraticCurveTo(-s*.42,s*.32,-s*.42,s*.12);ctx.lineTo(-s*.42,-s*.25);ctx.quadraticCurveTo(-s*.42,-s*.42,-s*.32,-s*.42);ctx.stroke();
  }else if(type==='key'){
    ctx.beginPath();ctx.arc(-s*.2,-s*.08,s*.22,0,Math.PI*2);ctx.moveTo(0,0);ctx.lineTo(s*.45,s*.42);ctx.moveTo(s*.25,s*.22);ctx.lineTo(s*.38,s*.09);ctx.stroke();
  }else if(type==='stable'){
    ctx.beginPath();ctx.moveTo(-s*.42,s*.35);ctx.lineTo(-s*.3,-s*.12);ctx.lineTo(0,-s*.42);ctx.lineTo(s*.34,-s*.08);ctx.lineTo(s*.42,s*.35);ctx.moveTo(-s*.16,s*.35);ctx.lineTo(-s*.16,s*.08);ctx.lineTo(s*.16,s*.08);ctx.lineTo(s*.16,s*.35);ctx.stroke();
  }else if(type==='hideout'){
    ctx.beginPath();ctx.moveTo(-s*.48,-s*.05);ctx.lineTo(0,-s*.45);ctx.lineTo(s*.48,-s*.05);ctx.moveTo(-s*.36,-s*.05);ctx.lineTo(-s*.36,s*.4);ctx.lineTo(s*.36,s*.4);ctx.lineTo(s*.36,-s*.05);ctx.stroke();
  }else{
    ctx.beginPath();ctx.arc(0,0,s*.34,0,Math.PI*2);ctx.fill();
  }
  ctx.restore();
}

function atlasDrawMarker(cluster){
  const l=cluster.items[0],cat=state.categoryMap.get(l.category_id)?.title||'',type=atlasIconType(cat),selected=l.id===state.selected?.id,discovered=state.discovered.has(l.id),r=selected?18:13,colors=atlasMarkerColors(type,discovered,selected);
  ctx.save();ctx.shadowColor='rgba(0,0,0,.42)';ctx.shadowBlur=10;ctx.shadowOffsetY=3;ctx.beginPath();ctx.arc(cluster.x,cluster.y,r,0,Math.PI*2);ctx.fillStyle=colors.fill;ctx.fill();ctx.shadowColor='transparent';ctx.lineWidth=selected?3:2;ctx.strokeStyle=colors.line;ctx.stroke();atlasDrawGlyph(type,cluster.x,cluster.y,r*.92,colors.icon);ctx.restore();
}

function atlasDrawCluster(cluster){
  const r=clamp(17+Math.log2(cluster.count)*3,19,33);ctx.save();ctx.shadowColor='rgba(0,0,0,.5)';ctx.shadowBlur=14;ctx.shadowOffsetY=4;ctx.beginPath();ctx.arc(cluster.x,cluster.y,r,0,Math.PI*2);ctx.fillStyle='rgba(92,15,23,.96)';ctx.fill();ctx.shadowColor='transparent';ctx.lineWidth=3;ctx.strokeStyle='rgba(255,241,225,.92)';ctx.stroke();ctx.beginPath();ctx.arc(cluster.x,cluster.y,r-5,0,Math.PI*2);ctx.strokeStyle='rgba(216,177,108,.5)';ctx.lineWidth=1.5;ctx.stroke();ctx.fillStyle='#fff';ctx.font='800 12px -apple-system,BlinkMacSystemFont,sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(cluster.count>999?'999+':String(cluster.count),cluster.x,cluster.y);ctx.restore();
}

function draw(){
  ctx.fillStyle='#171512';ctx.fillRect(0,0,innerWidth,innerHeight);
  if(state.imageReady){ctx.save();ctx.globalAlpha=.94;ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';ctx.drawImage(state.image,state.offsetX,state.offsetY,4096*state.scale,4096*state.scale);ctx.restore();}
  const list=visibleLocations();state.clusters=buildClusters(list);
  for(const c of state.clusters){if(c.x<-44||c.y<-44||c.x>innerWidth+44||c.y>innerHeight+44)continue;c.count>1?atlasDrawCluster(c):atlasDrawMarker(c)}
  el('visibleCount').textContent=list.length;
}

function updateZoomLabel(){
  const fit=Math.min(innerWidth/4096,innerHeight/4096)*1.1;
  const relative=Math.max(.1,state.scale/fit);
  el('zoomLabel').textContent='×'+relative.toFixed(relative<10?1:0);
}

const atlasOriginalRenderProgress=renderProgress;
renderProgress=function(){
  const validIds=new Set(state.locations.map(l=>String(l.id)));
  for(const id of [...state.discovered])if(!validIds.has(String(id)))state.discovered.delete(id);
  localStorage.setItem('atlas.discovered',JSON.stringify([...state.discovered]));
  atlasOriginalRenderProgress();
};

scheduleDraw();
