(() => {
  'use strict';

  const VERSION='0.9.0';
  const STORAGE_KEY='atlas-evidence-project-v1';
  const DB_NAME='atlas-evidence-media';
  const DB_VERSION=1;
  const GRID_SIZE=32;
  const runtimeVideos=new Map();
  const runtimeFrameUrls=new Map();
  let templates=[];
  let project=loadProject();
  let activeTool='none';
  let selectedFrameId='';
  let selectedBuildingId='';
  let selectedTemplateId='house-a';
  let pointerStart=null;
  let panelOpen=false;

  const $=selector=>document.querySelector(selector);
  const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
  const uid=prefix=>`${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,8)}`;

  function defaultProject(){
    return{
      schemaVersion:1,
      version:VERSION,
      season:'spring',
      sources:[],
      frames:[],
      anchors:[],
      buildings:[],
      coverage:{grid:GRID_SIZE,cells:{}},
      settings:{showCoverage:true,showBuildings:true,showAnchors:false},
      updatedAt:new Date().toISOString()
    };
  }

  function loadProject(){
    try{
      const parsed=JSON.parse(localStorage.getItem(STORAGE_KEY)||'null');
      if(parsed&&parsed.schemaVersion===1){
        parsed.coverage=parsed.coverage||{grid:GRID_SIZE,cells:{}};
        parsed.coverage.cells=parsed.coverage.cells||{};
        parsed.settings={showCoverage:true,showBuildings:true,showAnchors:false,...parsed.settings};
        parsed.sources=Array.isArray(parsed.sources)?parsed.sources:[];
        parsed.frames=Array.isArray(parsed.frames)?parsed.frames:[];
        parsed.anchors=Array.isArray(parsed.anchors)?parsed.anchors:[];
        parsed.buildings=Array.isArray(parsed.buildings)?parsed.buildings:[];
        return parsed;
      }
    }catch(_){/* ignore corrupt local draft */}
    return defaultProject();
  }

  function saveProject(redraw=true){
    project.version=VERSION;
    project.updatedAt=new Date().toISOString();
    localStorage.setItem(STORAGE_KEY,JSON.stringify(project));
    renderAll();
    if(redraw&&typeof scheduleDraw==='function')scheduleDraw();
  }

  function notify(message){
    const node=$('#evidenceStatus');
    if(node){node.textContent=message;node.classList.add('show');clearTimeout(notify.timer);notify.timer=setTimeout(()=>node.classList.remove('show'),2600);}
    const toast=$('#toast');
    if(toast){toast.textContent=message;toast.classList.add('show');clearTimeout(notify.toastTimer);notify.toastTimer=setTimeout(()=>toast.classList.remove('show'),1800);}
  }

  function openDb(){
    return new Promise((resolve,reject)=>{
      const request=indexedDB.open(DB_NAME,DB_VERSION);
      request.onupgradeneeded=()=>{
        const db=request.result;
        if(!db.objectStoreNames.contains('frames'))db.createObjectStore('frames');
      };
      request.onsuccess=()=>resolve(request.result);
      request.onerror=()=>reject(request.error);
    });
  }

  async function putFrameBlob(id,blob){
    const db=await openDb();
    await new Promise((resolve,reject)=>{
      const tx=db.transaction('frames','readwrite');
      tx.objectStore('frames').put(blob,id);
      tx.oncomplete=resolve;
      tx.onerror=()=>reject(tx.error);
    });
    db.close();
  }

  async function getFrameBlob(id){
    const db=await openDb();
    const blob=await new Promise((resolve,reject)=>{
      const tx=db.transaction('frames','readonly');
      const request=tx.objectStore('frames').get(id);
      request.onsuccess=()=>resolve(request.result||null);
      request.onerror=()=>reject(request.error);
    });
    db.close();
    return blob;
  }

  async function deleteFrameBlobs(ids){
    if(!ids.length)return;
    const db=await openDb();
    await new Promise((resolve,reject)=>{
      const tx=db.transaction('frames','readwrite');
      const store=tx.objectStore('frames');
      ids.forEach(id=>store.delete(id));
      tx.oncomplete=resolve;
      tx.onerror=()=>reject(tx.error);
    });
    db.close();
  }

  function secondsLabel(value){
    const total=Math.max(0,Math.round(value||0));
    const minutes=Math.floor(total/60);
    const seconds=String(total%60).padStart(2,'0');
    return `${minutes}:${seconds}`;
  }

  function formatBytes(bytes){
    if(!Number.isFinite(bytes))return '—';
    if(bytes<1024*1024)return `${Math.round(bytes/1024)} KB`;
    return `${(bytes/1024/1024).toFixed(1)} MB`;
  }

  function loadVideoMetadata(file){
    return new Promise((resolve,reject)=>{
      const url=URL.createObjectURL(file);
      const video=document.createElement('video');
      video.preload='metadata';
      video.muted=true;
      video.playsInline=true;
      video.src=url;
      video.onloadedmetadata=()=>resolve({url,duration:video.duration||0,width:video.videoWidth||0,height:video.videoHeight||0});
      video.onerror=()=>{URL.revokeObjectURL(url);reject(new Error('无法读取视频信息'));};
    });
  }

  async function registerVideos(files){
    const list=[...files].filter(file=>file.type.startsWith('video/'));
    if(!list.length){notify('没有检测到可用视频');return;}
    for(const file of list){
      try{
        const meta=await loadVideoMetadata(file);
        const source={
          id:uid('source'),name:file.name,size:file.size,type:file.type,duration:meta.duration,
          width:meta.width,height:meta.height,license:'private-local',season:project.season,
          frameCount:0,createdAt:new Date().toISOString()
        };
        project.sources.push(source);
        runtimeVideos.set(source.id,{file,url:meta.url});
      }catch(error){notify(`${file.name}：${error.message}`);}
    }
    saveProject(false);
    notify(`已登记 ${list.length} 个本地视频；文件不会上传`);
  }

  function seekVideo(video,time){
    return new Promise((resolve,reject)=>{
      const timeout=setTimeout(()=>reject(new Error('视频定位超时')),6000);
      const done=()=>{clearTimeout(timeout);video.removeEventListener('seeked',done);resolve();};
      video.addEventListener('seeked',done,{once:true});
      video.currentTime=Math.min(Math.max(0,time),Math.max(0,(video.duration||0)-.05));
    });
  }

  function frameDifference(current,previous){
    if(!previous)return 999;
    let total=0,count=0;
    for(let i=0;i<current.length;i+=16){
      total+=Math.abs(current[i]-previous[i]);
      total+=Math.abs(current[i+1]-previous[i+1]);
      total+=Math.abs(current[i+2]-previous[i+2]);
      count+=3;
    }
    return count?total/count:0;
  }

  function canvasBlob(canvas){
    return new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.72));
  }

  async function extractFrames(sourceId){
    const runtime=runtimeVideos.get(sourceId);
    const source=project.sources.find(item=>item.id===sourceId);
    if(!source)return;
    if(!runtime){notify('本地视频未连接，请重新选择该文件');return;}
    const progress=$(`[data-source-progress="${sourceId}"]`);
    const video=document.createElement('video');
    video.preload='auto';video.muted=true;video.playsInline=true;video.src=runtime.url;
    await new Promise((resolve,reject)=>{video.onloadedmetadata=resolve;video.onerror=()=>reject(new Error('视频加载失败'));});
    const canvas=document.createElement('canvas');
    canvas.width=240;canvas.height=135;
    const context=canvas.getContext('2d',{willReadFrequently:true});
    const maxSamples=48;
    const interval=Math.max(2,video.duration/maxSamples);
    let previous=null,kept=0,sampled=0;
    const existing=project.frames.filter(frame=>frame.sourceId===sourceId).map(frame=>frame.id);
    await deleteFrameBlobs(existing);
    project.frames=project.frames.filter(frame=>frame.sourceId!==sourceId);
    project.anchors=project.anchors.filter(anchor=>!existing.includes(anchor.frameId));
    for(let time=0;time<video.duration&&sampled<maxSamples;time+=interval){
      sampled++;
      try{await seekVideo(video,time);}catch(_){continue;}
      context.drawImage(video,0,0,canvas.width,canvas.height);
      const pixels=context.getImageData(0,0,canvas.width,canvas.height).data;
      const difference=frameDifference(pixels,previous);
      previous=new Uint8ClampedArray(pixels);
      if(difference>=10.5||kept===0){
        const blob=await canvasBlob(canvas);
        if(blob){
          const frame={id:uid('frame'),sourceId,time,difference,season:source.season||project.season,anchored:false,createdAt:new Date().toISOString()};
          await putFrameBlob(frame.id,blob);
          project.frames.push(frame);
          kept++;
        }
      }
      if(progress)progress.textContent=`${Math.round(Math.min(1,time/video.duration)*100)}% · 已保留 ${kept} 帧`;
      await new Promise(resolve=>setTimeout(resolve,0));
    }
    source.frameCount=kept;
    if(progress)progress.textContent=`完成 · ${kept} 帧`;
    saveProject(false);
    await renderFrames();
    notify(`关键帧提取完成：${kept} 帧`);
  }

  function coverageStats(){
    const values=Object.values(project.coverage.cells).map(cell=>Number(cell.hits||cell)||0);
    const covered=values.filter(value=>value>0).length;
    const strong=values.filter(value=>value>=3).length;
    const total=project.coverage.grid*project.coverage.grid;
    return{covered,strong,total,percent:total?covered/total*100:0};
  }

  function renderStats(){
    const stats=coverageStats();
    const map={
      evidenceSources:project.sources.length,
      evidenceFrames:project.frames.length,
      evidenceBuildings:project.buildings.length,
      evidenceCoverage:`${stats.percent.toFixed(1)}%`
    };
    Object.entries(map).forEach(([id,value])=>{const node=document.getElementById(id);if(node)node.textContent=value;});
  }

  function renderSources(){
    const container=$('#evidenceSourcesList');
    if(!container)return;
    if(!project.sources.length){container.innerHTML='<div class="evidence-empty">尚未登记视频。选择本地视频后可提取关键帧，文件不会上传。</div>';return;}
    container.innerHTML=project.sources.map(source=>{
      const connected=runtimeVideos.has(source.id);
      return `<article class="evidence-source">
        <div><b>${escapeHtml(source.name)}</b><small>${source.width}×${source.height} · ${secondsLabel(source.duration)} · ${formatBytes(source.size)}</small><small data-source-progress="${source.id}">${connected?'本次会话已连接':'需重新选择原文件'} · ${source.frameCount||0} 帧</small></div>
        <button data-extract-source="${source.id}" ${connected?'':'disabled'}>提取关键帧</button>
      </article>`;
    }).join('');
    container.querySelectorAll('[data-extract-source]').forEach(button=>button.onclick=()=>extractFrames(button.dataset.extractSource));
  }

  async function frameUrl(frameId){
    if(runtimeFrameUrls.has(frameId))return runtimeFrameUrls.get(frameId);
    const blob=await getFrameBlob(frameId);
    if(!blob)return '';
    const url=URL.createObjectURL(blob);
    runtimeFrameUrls.set(frameId,url);
    return url;
  }

  async function renderFrames(){
    const container=$('#evidenceFrames');
    if(!container)return;
    const frames=[...project.frames].sort((a,b)=>new Date(b.createdAt)-new Date(a.createdAt)).slice(0,24);
    if(!frames.length){container.innerHTML='<div class="evidence-empty">关键帧将在这里显示。选择一帧后点击地图，可以建立位置锚点。</div>';return;}
    container.innerHTML='';
    for(const frame of frames){
      const url=await frameUrl(frame.id);
      const source=project.sources.find(item=>item.id===frame.sourceId);
      const button=document.createElement('button');
      button.className=`evidence-frame${selectedFrameId===frame.id?' selected':''}`;
      button.dataset.frameId=frame.id;
      button.innerHTML=`${url?`<img src="${url}" alt="视频关键帧"/>`:'<span class="frame-missing">无预览</span>'}<small>${escapeHtml(source?.name||'未知来源')} · ${secondsLabel(frame.time)}${frame.anchored?' · 已定位':''}</small>`;
      button.onclick=()=>{selectedFrameId=frame.id;activeTool='anchor';syncToolButtons();renderFrames();notify('已选择关键帧，请点击地图中的对应位置');};
      container.appendChild(button);
    }
  }

  function renderTemplates(){
    const select=$('#evidenceTemplateSelect');
    if(!select)return;
    select.innerHTML=templates.map(template=>`<option value="${template.id}">${escapeHtml(template.name)}</option>`).join('');
    if(!templates.some(item=>item.id===selectedTemplateId)&&templates[0])selectedTemplateId=templates[0].id;
    select.value=selectedTemplateId;
    select.onchange=()=>{selectedTemplateId=select.value;};
  }

  function renderBuildings(){
    const container=$('#evidenceBuildingsList');
    if(!container)return;
    if(!project.buildings.length){container.innerHTML='<div class="evidence-empty">尚未放置建筑。选择模板并启用“放置建筑”，然后点击地图。</div>';return;}
    container.innerHTML=project.buildings.slice(-40).reverse().map(building=>{
      const template=templates.find(item=>item.id===building.templateId);
      return `<button class="evidence-building-row${selectedBuildingId===building.id?' selected':''}" data-building-id="${building.id}">
        <span><b>${escapeHtml(template?.name||building.templateId)}</b><small>${Math.round(building.confidence*100)}% · ${building.status==='verified'?'已复核':'待复核'} · ${seasonLabel(building.season)}</small></span><i>${building.evidenceIds?.length||0} 条证据</i>
      </button>`;
    }).join('');
    container.querySelectorAll('[data-building-id]').forEach(button=>button.onclick=()=>{selectedBuildingId=button.dataset.buildingId;renderBuildings();renderBuildingEditor();scheduleDraw();});
  }

  function renderBuildingEditor(){
    const editor=$('#evidenceBuildingEditor');
    const building=project.buildings.find(item=>item.id===selectedBuildingId);
    if(!editor)return;
    if(!building){editor.hidden=true;return;}
    editor.hidden=false;
    editor.innerHTML=`
      <label>旋转角度<input id="buildingRotation" type="range" min="0" max="359" value="${building.rotation||0}"><output>${Math.round(building.rotation||0)}°</output></label>
      <label>缩放比例<input id="buildingScale" type="range" min="50" max="180" value="${Math.round((building.scale||1)*100)}"><output>${Math.round((building.scale||1)*100)}%</output></label>
      <label>可信度<input id="buildingConfidence" type="range" min="0" max="100" value="${Math.round((building.confidence||0)*100)}"><output>${Math.round((building.confidence||0)*100)}%</output></label>
      <div class="evidence-editor-actions"><button id="verifyBuilding">${building.status==='verified'?'取消复核':'标记已复核'}</button><button id="deleteBuilding" class="danger">删除建筑</button></div>`;
    const bind=(id,apply,format)=>{
      const input=document.getElementById(id);const output=input.nextElementSibling;
      input.oninput=()=>{apply(Number(input.value));output.textContent=format(Number(input.value));saveProject();};
    };
    bind('buildingRotation',value=>building.rotation=value,value=>`${Math.round(value)}°`);
    bind('buildingScale',value=>building.scale=value/100,value=>`${Math.round(value)}%`);
    bind('buildingConfidence',value=>building.confidence=value/100,value=>`${Math.round(value)}%`);
    $('#verifyBuilding').onclick=()=>{building.status=building.status==='verified'?'provisional':'verified';saveProject();};
    $('#deleteBuilding').onclick=()=>{project.buildings=project.buildings.filter(item=>item.id!==building.id);selectedBuildingId='';saveProject();};
  }

  function seasonLabel(season){
    return({all:'全年',spring:'春',summer:'夏',autumn:'秋',winter:'冬'})[season]||season;
  }

  function renderSeason(){
    document.querySelectorAll('[data-evidence-season]').forEach(button=>button.classList.toggle('active',button.dataset.evidenceSeason===project.season));
  }

  function renderToggles(){
    const coverage=$('#toggleEvidenceCoverage');
    const buildings=$('#toggleEvidenceBuildings');
    const anchors=$('#toggleEvidenceAnchors');
    if(coverage)coverage.checked=project.settings.showCoverage;
    if(buildings)buildings.checked=project.settings.showBuildings;
    if(anchors)anchors.checked=project.settings.showAnchors;
  }

  function syncToolButtons(){
    document.querySelectorAll('[data-evidence-tool]').forEach(button=>button.classList.toggle('active',button.dataset.evidenceTool===activeTool));
    const label=$('#evidenceToolLabel');
    if(label)label.textContent=({none:'浏览地图',anchor:'定位证据帧',coverage:'标注视频覆盖',building:'放置建筑'})[activeTool]||activeTool;
  }

  function renderAll(){
    renderStats();renderSources();renderTemplates();renderBuildings();renderBuildingEditor();renderSeason();renderToggles();syncToolButtons();renderFrames();
  }

  function escapeHtml(value){
    return String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  }

  function mapPointFromEvent(event){
    const rect=mapCanvas.getBoundingClientRect();
    const screenX=event.clientX-rect.left;
    const screenY=event.clientY-rect.top;
    const mapX=(screenX-state.offsetX)/state.scale;
    const mapY=(screenY-state.offsetY)/state.scale;
    if(mapX<0||mapY<0||mapX>4096||mapY>4096)return null;
    return{x:mapX/4096,y:mapY/4096,mapX,mapY};
  }

  function handleToolClick(event){
    if(!panelOpen||activeTool==='none')return;
    if(pointerStart&&Math.hypot(event.clientX-pointerStart.x,event.clientY-pointerStart.y)>8)return;
    const point=mapPointFromEvent(event);
    if(!point)return;
    event.preventDefault();
    event.stopPropagation();
    if(event.stopImmediatePropagation)event.stopImmediatePropagation();

    if(activeTool==='anchor'){
      const frame=project.frames.find(item=>item.id===selectedFrameId);
      if(!frame){notify('请先选择一张关键帧');return;}
      project.anchors=project.anchors.filter(anchor=>anchor.frameId!==frame.id);
      project.anchors.push({id:uid('anchor'),frameId:frame.id,x:point.x,y:point.y,season:frame.season||project.season,confidence:.6,createdAt:new Date().toISOString()});
      frame.anchored=true;
      const cellKey=coverageKey(point.x,point.y);
      const cell=normalizeCell(project.coverage.cells[cellKey]);
      cell.hits+=1;cell.sourceIds=[...new Set([...cell.sourceIds,frame.sourceId])];
      project.coverage.cells[cellKey]=cell;
      activeTool='none';
      saveProject();
      notify('证据帧已锚定到地图');
      return;
    }

    if(activeTool==='coverage'){
      const cellKey=coverageKey(point.x,point.y);
      const cell=normalizeCell(project.coverage.cells[cellKey]);
      cell.hits+=1;
      if(selectedFrameId){
        const frame=project.frames.find(item=>item.id===selectedFrameId);
        if(frame)cell.sourceIds=[...new Set([...cell.sourceIds,frame.sourceId])];
      }
      project.coverage.cells[cellKey]=cell;
      saveProject();
      notify(`覆盖强度 +1（当前 ${cell.hits}）`);
      return;
    }

    if(activeTool==='building'){
      const evidenceIds=selectedFrameId?[selectedFrameId]:[];
      const building={
        id:uid('building'),templateId:selectedTemplateId,x:point.x,y:point.y,rotation:0,scale:1,
        season:'all',status:'provisional',confidence:evidenceIds.length?.62:.35,evidenceIds,
        source:'atlas-original-vector',createdAt:new Date().toISOString()
      };
      project.buildings.push(building);
      selectedBuildingId=building.id;
      saveProject();
      notify('已放置原创矢量建筑，可在审核面板调整');
    }
  }

  function coverageKey(x,y){
    const grid=project.coverage.grid||GRID_SIZE;
    return `${clamp(Math.floor(x*grid),0,grid-1)}:${clamp(Math.floor(y*grid),0,grid-1)}`;
  }

  function normalizeCell(value){
    if(typeof value==='number')return{hits:value,sourceIds:[]};
    return{hits:Number(value?.hits||0),sourceIds:Array.isArray(value?.sourceIds)?value.sourceIds:[]};
  }

  function drawCoverageOverlay(){
    if(!project.settings.showCoverage)return;
    const grid=project.coverage.grid||GRID_SIZE;
    const cellMapSize=4096/grid;
    ctx.save();
    for(const [cellKey,raw] of Object.entries(project.coverage.cells)){
      const cell=normalizeCell(raw);
      if(cell.hits<=0)continue;
      const [cx,cy]=cellKey.split(':').map(Number);
      const x=state.offsetX+cx*cellMapSize*state.scale;
      const y=state.offsetY+cy*cellMapSize*state.scale;
      const size=cellMapSize*state.scale;
      if(x+size<0||y+size<0||x>innerWidth||y>innerHeight)continue;
      const level=clamp(cell.hits/4,0,1);
      ctx.fillStyle=cell.hits>=3?`rgba(75,190,126,${.08+.16*level})`:cell.hits>=2?`rgba(224,181,83,${.08+.15*level})`:`rgba(216,70,76,${.07+.13*level})`;
      ctx.fillRect(x,y,size,size);
      if(panelOpen&&state.scale/fitScale()>1.4){
        ctx.strokeStyle='rgba(255,255,255,.12)';ctx.lineWidth=.7;ctx.strokeRect(x+.35,y+.35,size-.7,size-.7);
      }
    }
    ctx.restore();
  }

  function drawBuildingOverlay(){
    if(!project.settings.showBuildings||state.scale/fitScale()<1.45)return;
    const season=project.season;
    ctx.save();
    for(const building of project.buildings){
      if(building.season!=='all'&&building.season!==season)continue;
      const template=templates.find(item=>item.id===building.templateId);
      if(!template?.footprint?.length)continue;
      const centerX=state.offsetX+building.x*4096*state.scale;
      const centerY=state.offsetY+building.y*4096*state.scale;
      if(centerX<-100||centerY<-100||centerX>innerWidth+100||centerY>innerHeight+100)continue;
      const baseSize=clamp(12*(state.scale/fitScale()),15,46)*(building.scale||1);
      const angle=(building.rotation||0)*Math.PI/180;
      const cos=Math.cos(angle),sin=Math.sin(angle);
      ctx.beginPath();
      template.footprint.forEach((point,index)=>{
        const px=point[0]*baseSize,py=point[1]*baseSize;
        const x=centerX+px*cos-py*sin;
        const y=centerY+px*sin+py*cos;
        if(index===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);
      });
      ctx.closePath();
      const verified=building.status==='verified';
      const selected=building.id===selectedBuildingId;
      ctx.fillStyle=verified?'rgba(229,211,171,.72)':'rgba(216,173,99,.44)';
      ctx.strokeStyle=selected?'rgba(238,70,82,.95)':verified?'rgba(255,245,221,.84)':'rgba(255,221,162,.68)';
      ctx.lineWidth=selected?2.2:1.1;
      ctx.fill();ctx.stroke();
      if(template.roofAxis){
        ctx.beginPath();
        ctx.moveTo(centerX-cos*baseSize*.35,centerY-sin*baseSize*.35);
        ctx.lineTo(centerX+cos*baseSize*.35,centerY+sin*baseSize*.35);
        ctx.strokeStyle='rgba(83,50,34,.65)';ctx.lineWidth=.9;ctx.stroke();
      }
    }
    ctx.restore();
  }

  function drawAnchorsOverlay(){
    if(!project.settings.showAnchors)return;
    ctx.save();
    for(const anchor of project.anchors){
      const x=state.offsetX+anchor.x*4096*state.scale;
      const y=state.offsetY+anchor.y*4096*state.scale;
      if(x<-20||y<-20||x>innerWidth+20||y>innerHeight+20)continue;
      ctx.beginPath();ctx.arc(x,y,5,0,Math.PI*2);ctx.fillStyle='rgba(98,195,220,.9)';ctx.fill();
      ctx.strokeStyle='#eefcff';ctx.lineWidth=1;ctx.stroke();
    }
    ctx.restore();
  }

  function installDrawLayer(){
    if(typeof draw!=='function'||typeof ctx==='undefined')return setTimeout(installDrawLayer,120);
    if(draw.__evidenceWrapped)return;
    const baseDraw=draw;
    const wrapped=function(){baseDraw();drawCoverageOverlay();drawBuildingOverlay();drawAnchorsOverlay();};
    wrapped.__evidenceWrapped=true;
    draw=wrapped;
    scheduleDraw();
  }

  function exportProject(){
    const payload={...project,exportedAt:new Date().toISOString(),note:'原始视频和关键帧二进制文件不会包含在导出文件中'};
    const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'});
    const url=URL.createObjectURL(blob);
    const link=document.createElement('a');
    link.href=url;link.download=`atlas-evidence-${new Date().toISOString().slice(0,10)}.json`;link.click();
    setTimeout(()=>URL.revokeObjectURL(url),500);
  }

  async function importProject(file){
    try{
      const parsed=JSON.parse(await file.text());
      if(parsed.schemaVersion!==1)throw new Error('不支持的数据版本');
      project={...defaultProject(),...parsed,settings:{...defaultProject().settings,...parsed.settings}};
      selectedBuildingId='';selectedFrameId='';activeTool='none';saveProject();notify('证据项目已导入');
    }catch(error){notify(`导入失败：${error.message}`);}
  }

  function clearProject(){
    if(!confirm('清除本机的证据项目、建筑和关键帧？此操作不能撤销。'))return;
    const ids=project.frames.map(frame=>frame.id);
    deleteFrameBlobs(ids).catch(()=>{});
    runtimeFrameUrls.forEach(url=>URL.revokeObjectURL(url));runtimeFrameUrls.clear();
    project=defaultProject();selectedFrameId='';selectedBuildingId='';activeTool='none';saveProject();notify('本地证据项目已清空');
  }

  function bindUi(){
    const panel=$('#evidencePanel');
    const openButton=$('#evidenceStudioBtn');
    const closeButton=$('#closeEvidenceStudio');
    const videoInput=$('#evidenceVideoInput');
    const importInput=$('#evidenceImportInput');
    openButton?.addEventListener('click',()=>{panelOpen=true;panel?.classList.add('open');panel?.setAttribute('aria-hidden','false');renderAll();});
    closeButton?.addEventListener('click',()=>{panelOpen=false;panel?.classList.remove('open');panel?.setAttribute('aria-hidden','true');activeTool='none';syncToolButtons();scheduleDraw();});
    $('#addEvidenceVideos')?.addEventListener('click',()=>videoInput?.click());
    videoInput?.addEventListener('change',()=>{registerVideos(videoInput.files);videoInput.value='';});
    $('#exportEvidenceProject')?.addEventListener('click',exportProject);
    $('#importEvidenceProject')?.addEventListener('click',()=>importInput?.click());
    importInput?.addEventListener('change',()=>{if(importInput.files[0])importProject(importInput.files[0]);importInput.value='';});
    $('#clearEvidenceProject')?.addEventListener('click',clearProject);
    document.querySelectorAll('[data-evidence-season]').forEach(button=>button.onclick=()=>{project.season=button.dataset.evidenceSeason;saveProject();});
    document.querySelectorAll('[data-evidence-tool]').forEach(button=>button.onclick=()=>{const tool=button.dataset.evidenceTool;activeTool=activeTool===tool?'none':tool;syncToolButtons();notify(activeTool==='none'?'已退出编辑工具':$('#evidenceToolLabel')?.textContent||'工具已启用');});
    $('#toggleEvidenceCoverage')?.addEventListener('change',event=>{project.settings.showCoverage=event.target.checked;saveProject();});
    $('#toggleEvidenceBuildings')?.addEventListener('change',event=>{project.settings.showBuildings=event.target.checked;saveProject();});
    $('#toggleEvidenceAnchors')?.addEventListener('change',event=>{project.settings.showAnchors=event.target.checked;saveProject();});
    mapCanvas.addEventListener('pointerdown',event=>{pointerStart={x:event.clientX,y:event.clientY};},{capture:true,passive:true});
    mapCanvas.addEventListener('pointerup',handleToolClick,{capture:true,passive:false});
  }

  async function init(){
    try{templates=await fetch('data/building-templates.json?v=0.9.0').then(response=>response.json());}catch(_){templates=[];}
    bindUi();renderAll();installDrawLayer();
    window.AtlasEvidence={project:()=>project,templates:()=>templates,open:()=>$('#evidenceStudioBtn')?.click(),version:VERSION};
  }

  init();
})();
