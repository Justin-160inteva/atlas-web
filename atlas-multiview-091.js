(() => {
  'use strict';

  const VERSION='0.9.1';
  const STORAGE_KEY='atlas-evidence-project-v1';
  const DB_NAME='atlas-evidence-media';
  const DB_VERSION=1;
  const coarse=matchMedia('(pointer:coarse)').matches||/iPad|iPhone|iPod|Android/i.test(navigator.userAgent);
  const MAX_SAMPLES=coarse?180:320;
  const THUMB_WIDTH=coarse?256:320;
  const THUMB_HEIGHT=Math.round(THUMB_WIDTH*9/16);
  const ANALYSIS_WIDTH=72;
  const ANALYSIS_HEIGHT=40;
  const urlCache=new Map();
  let selectedCandidateId='';
  let scanning=false;
  let drawInstalled=false;
  let observer=null;

  const $=selector=>document.querySelector(selector);
  const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
  const uid=prefix=>`${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,9)}`;
  const escapeHtml=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));

  function api(){return window.AtlasEvidence||null}
  function project(){return api()?.project?.()||null}
  function templates(){return api()?.templates?.()||[]}

  function ensureSchema(data){
    data.candidates=Array.isArray(data.candidates)?data.candidates:[];
    data.reconstruction=data.reconstruction||{};
    data.reconstruction.scanSettings={interval:2,clusterRadius:72,...data.reconstruction.scanSettings};
    data.reconstruction.metrics=data.reconstruction.metrics||{};
    data.reconstruction.descriptorVersion=1;
    return data;
  }

  function notify(message){
    const status=$('#evidenceStatus');
    if(status){status.textContent=message;status.classList.add('show');clearTimeout(notify.statusTimer);notify.statusTimer=setTimeout(()=>status.classList.remove('show'),3000);}
    const toast=$('#toast');
    if(toast){toast.textContent=message;toast.classList.add('show');clearTimeout(notify.toastTimer);notify.toastTimer=setTimeout(()=>toast.classList.remove('show'),1900);}
  }

  function persist(message='',rerenderBase=true){
    const data=project();
    if(!data)return;
    data.version=VERSION;
    data.updatedAt=new Date().toISOString();
    localStorage.setItem(STORAGE_KEY,JSON.stringify(data));
    if(typeof scheduleDraw==='function')scheduleDraw();
    if(rerenderBase)api()?.open?.();
    render091();
    if(message)notify(message);
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

  async function getFrameUrl(frameId){
    if(urlCache.has(frameId))return urlCache.get(frameId);
    const db=await openDb();
    const blob=await new Promise((resolve,reject)=>{
      const tx=db.transaction('frames','readonly');
      const request=tx.objectStore('frames').get(frameId);
      request.onsuccess=()=>resolve(request.result||null);
      request.onerror=()=>reject(request.error);
    });
    db.close();
    if(!blob)return '';
    const url=URL.createObjectURL(blob);
    urlCache.set(frameId,url);
    return url;
  }

  function seekVideo(video,time){
    return new Promise((resolve,reject)=>{
      const timeout=setTimeout(()=>reject(new Error('视频定位超时')),7000);
      const finish=()=>{
        clearTimeout(timeout);
        video.removeEventListener('seeked',finish);
        if('requestVideoFrameCallback'in video)video.requestVideoFrameCallback(()=>resolve());
        else requestAnimationFrame(resolve);
      };
      video.addEventListener('seeked',finish,{once:true});
      video.currentTime=clamp(time,0,Math.max(0,(video.duration||0)-.06));
    });
  }

  function toGray(imageData,width,height){
    const gray=new Float32Array(width*height);
    const source=imageData.data;
    for(let i=0,p=0;i<source.length;i+=4,p++)gray[p]=source[i]*.299+source[i+1]*.587+source[i+2]*.114;
    return gray;
  }

  function descriptorFromCanvas(canvas){
    const analysis=document.createElement('canvas');
    analysis.width=ANALYSIS_WIDTH;
    analysis.height=ANALYSIS_HEIGHT;
    const context=analysis.getContext('2d',{willReadFrequently:true});
    context.drawImage(canvas,0,0,ANALYSIS_WIDTH,ANALYSIS_HEIGHT);
    const image=context.getImageData(0,0,ANALYSIS_WIDTH,ANALYSIS_HEIGHT);
    const gray=toGray(image,ANALYSIS_WIDTH,ANALYSIS_HEIGHT);

    const edge=new Array(8).fill(0);
    let gradientTotal=0;
    let gradientStrong=0;
    for(let y=1;y<ANALYSIS_HEIGHT-1;y++){
      for(let x=1;x<ANALYSIS_WIDTH-1;x++){
        const i=y*ANALYSIS_WIDTH+x;
        const gx=-gray[i-ANALYSIS_WIDTH-1]-2*gray[i-1]-gray[i+ANALYSIS_WIDTH-1]+gray[i-ANALYSIS_WIDTH+1]+2*gray[i+1]+gray[i+ANALYSIS_WIDTH+1];
        const gy=-gray[i-ANALYSIS_WIDTH-1]-2*gray[i-ANALYSIS_WIDTH]-gray[i-ANALYSIS_WIDTH+1]+gray[i+ANALYSIS_WIDTH-1]+2*gray[i+ANALYSIS_WIDTH]+gray[i+ANALYSIS_WIDTH+1];
        const magnitude=Math.hypot(gx,gy)/8;
        gradientTotal+=magnitude;
        if(magnitude>24){
          gradientStrong++;
          let angle=(Math.atan2(gy,gx)+Math.PI)%(Math.PI);
          const bin=Math.min(7,Math.floor(angle/Math.PI*8));
          edge[bin]+=magnitude;
        }
      }
    }
    const edgeSum=edge.reduce((sum,value)=>sum+value,0)||1;
    for(let i=0;i<edge.length;i++)edge[i]=Number((edge[i]/edgeSum).toFixed(4));

    const color=new Array(12).fill(0);
    const pixels=image.data;
    const cellsX=4,cellsY=3;
    const counts=new Array(12).fill(0);
    for(let y=0;y<ANALYSIS_HEIGHT;y++){
      for(let x=0;x<ANALYSIS_WIDTH;x++){
        const cell=Math.min(cellsY-1,Math.floor(y/ANALYSIS_HEIGHT*cellsY))*cellsX+Math.min(cellsX-1,Math.floor(x/ANALYSIS_WIDTH*cellsX));
        const index=(y*ANALYSIS_WIDTH+x)*4;
        color[cell]+=(pixels[index]+pixels[index+1]+pixels[index+2])/(3*255);
        counts[cell]++;
      }
    }
    for(let i=0;i<color.length;i++)color[i]=Number((color[i]/Math.max(1,counts[i])).toFixed(4));

    const hashBits=[];
    for(let y=0;y<8;y++){
      for(let x=0;x<8;x++){
        const sx=Math.floor((x+.5)/9*ANALYSIS_WIDTH);
        const nx=Math.floor((x+1.5)/9*ANALYSIS_WIDTH);
        const sy=Math.floor((y+.5)/8*ANALYSIS_HEIGHT);
        hashBits.push(gray[sy*ANALYSIS_WIDTH+sx]>gray[sy*ANALYSIS_WIDTH+nx]?'1':'0');
      }
    }
    let dominant=0;
    for(let i=1;i<edge.length;i++)if(edge[i]>edge[dominant])dominant=i;
    const interior=(ANALYSIS_WIDTH-2)*(ANALYSIS_HEIGHT-2);
    const brightness=color.reduce((sum,value)=>sum+value,0)/color.length;
    return{
      hash:hashBits.join(''),
      color,
      edge,
      sharpness:Number((gradientTotal/interior).toFixed(2)),
      edgeDensity:Number((gradientStrong/interior).toFixed(4)),
      brightness:Number(brightness.toFixed(4)),
      dominantAngle:Number((dominant*180/8).toFixed(1))
    };
  }

  function hamming(a='',b=''){
    if(!a||!b||a.length!==b.length)return 1;
    let different=0;
    for(let i=0;i<a.length;i++)if(a[i]!==b[i])different++;
    return different/a.length;
  }

  function vectorDistance(a=[],b=[]){
    const length=Math.min(a.length,b.length);
    if(!length)return 1;
    let total=0;
    for(let i=0;i<length;i++)total+=Math.abs(a[i]-b[i]);
    return total/length;
  }

  function cosineSimilarity(a=[],b=[]){
    const length=Math.min(a.length,b.length);
    if(!length)return 0;
    let dot=0,aa=0,bb=0;
    for(let i=0;i<length;i++){dot+=a[i]*b[i];aa+=a[i]*a[i];bb+=b[i]*b[i];}
    return aa&&bb?dot/Math.sqrt(aa*bb):0;
  }

  function descriptorSimilarity(a,b){
    if(!a||!b)return 0;
    const hash=1-hamming(a.hash,b.hash);
    const color=1-clamp(vectorDistance(a.color,b.color)*2.4,0,1);
    const edges=clamp(cosineSimilarity(a.edge,b.edge),0,1);
    const brightness=1-clamp(Math.abs((a.brightness||0)-(b.brightness||0))*2,0,1);
    return clamp(hash*.38+color*.22+edges*.30+brightness*.10,0,1);
  }

  function sceneDistance(a,b){return 1-descriptorSimilarity(a,b)}

  function canvasBlob(canvas){return new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.82))}

  async function loadVideo(file){
    const url=URL.createObjectURL(file);
    const video=document.createElement('video');
    video.preload='auto';video.muted=true;video.playsInline=true;video.src=url;
    await new Promise((resolve,reject)=>{video.onloadedmetadata=resolve;video.onerror=()=>reject(new Error('无法读取视频'));});
    return{video,url};
  }

  async function denseScanFile(file){
    if(scanning)return;
    const data=ensureSchema(project());
    if(!data)return;
    scanning=true;
    render091();
    let url='';
    try{
      const loaded=await loadVideo(file);url=loaded.url;
      const video=loaded.video;
      const requested=Number($('#mvScanInterval')?.value||data.reconstruction.scanSettings.interval||2);
      const interval=Math.max(requested,video.duration/Math.max(1,MAX_SAMPLES));
      data.reconstruction.scanSettings.interval=requested;
      const source={
        id:uid('source'),name:file.name,size:file.size,type:file.type,duration:video.duration||0,
        width:video.videoWidth||0,height:video.videoHeight||0,license:'private-local',season:data.season,
        frameCount:0,scanMode:'dense-091',scanInterval:interval,createdAt:new Date().toISOString()
      };
      data.sources.push(source);
      const preview=document.createElement('canvas');preview.width=THUMB_WIDTH;preview.height=THUMB_HEIGHT;
      const context=preview.getContext('2d',{willReadFrequently:true});
      const totalSamples=Math.min(MAX_SAMPLES,Math.ceil(video.duration/interval));
      let previous=null,lastKept=-Infinity,kept=0,blurred=0,duplicates=0,sampled=0;
      for(let index=0;index<totalSamples;index++){
        const time=Math.min(video.duration-.07,index*interval);
        if(time<0)break;
        sampled++;
        try{await seekVideo(video,time);}catch(_){continue;}
        context.drawImage(video,0,0,preview.width,preview.height);
        const descriptor=descriptorFromCanvas(preview);
        const distance=previous?sceneDistance(descriptor,previous):1;
        const tooSoft=descriptor.sharpness<8.5;
        const duplicate=previous&&distance<.145&&(time-lastKept)<10;
        if(tooSoft)blurred++;
        else if(duplicate)duplicates++;
        else{
          const blob=await canvasBlob(preview);
          if(blob){
            const frame={
              id:uid('frame'),sourceId:source.id,time,difference:Number(distance.toFixed(4)),season:source.season,
              anchored:false,descriptor,scanMode:'dense-091',quality:{sharpness:descriptor.sharpness,edgeDensity:descriptor.edgeDensity},
              createdAt:new Date().toISOString()
            };
            await putFrameBlob(frame.id,blob);
            data.frames.push(frame);kept++;lastKept=time;previous=descriptor;
          }
        }
        const progress=$('#mvScanProgress');
        if(progress)progress.textContent=`${Math.round((index+1)/totalSamples*100)}% · 保留 ${kept} · 模糊 ${blurred} · 重复 ${duplicates}`;
        if(index%4===0)await new Promise(resolve=>setTimeout(resolve,0));
      }
      source.frameCount=kept;
      source.scanReport={sampled,kept,blurred,duplicates,effectiveInterval:Number(interval.toFixed(2))};
      data.reconstruction.metrics.lastScan=source.scanReport;
      persist(`密集扫描完成：保留 ${kept} 帧`,true);
      buildCandidates();
    }catch(error){notify(`密集扫描失败：${error.message}`);}
    finally{scanning=false;if(url)URL.revokeObjectURL(url);render091();}
  }

  function anchorForFrame(data,frameId){return data.anchors.find(anchor=>anchor.frameId===frameId)||null}

  function meanDescriptor(frames){
    if(!frames.length)return null;
    const color=new Array(12).fill(0),edge=new Array(8).fill(0);
    let sharpness=0,edgeDensity=0,brightness=0;
    for(const frame of frames){
      const d=frame.descriptor;if(!d)continue;
      d.color?.forEach((value,index)=>color[index]+=value);
      d.edge?.forEach((value,index)=>edge[index]+=value);
      sharpness+=d.sharpness||0;edgeDensity+=d.edgeDensity||0;brightness+=d.brightness||0;
    }
    const count=frames.length;
    return{color:color.map(value=>value/count),edge:edge.map(value=>value/count),sharpness:sharpness/count,edgeDensity:edgeDensity/count,brightness:brightness/count,hash:frames[0]?.descriptor?.hash||''};
  }

  function circularOrientation(frames){
    let x=0,y=0,count=0;
    for(const frame of frames){
      const angle=Number(frame.descriptor?.dominantAngle);
      if(!Number.isFinite(angle))continue;
      const radians=angle*Math.PI/180*2;
      x+=Math.cos(radians);y+=Math.sin(radians);count++;
    }
    if(!count)return 0;
    let angle=Math.atan2(y,x)/2*180/Math.PI;
    if(angle<0)angle+=180;
    return angle;
  }

  function inferOutline(frames,sourceCount,viewCount){
    const list=templates();
    const mean=meanDescriptor(frames)||{edgeDensity:.15,edge:[]};
    const horizontal=(mean.edge?.[0]||0)+(mean.edge?.[7]||0)+(mean.edge?.[1]||0);
    const vertical=(mean.edge?.[3]||0)+(mean.edge?.[4]||0)+(mean.edge?.[5]||0);
    let templateId='house-a';
    if(viewCount>=3&&mean.edgeDensity>.22)templateId='house-l';
    else if(horizontal>vertical*1.22)templateId='house-b';
    else if(mean.edgeDensity<.11)templateId='farmhut-a';
    else if(sourceCount>=3&&mean.edgeDensity>.29)templateId='samurai-a';
    if(!list.some(item=>item.id===templateId))templateId=list[0]?.id||'house-a';
    return{
      templateId,
      rotation:Number(circularOrientation(frames).toFixed(1)),
      scale:Number(clamp(.72+(mean.edgeDensity||.15)*1.8,.65,1.42).toFixed(2)),
      method:'multiview-heuristic-091',
      observedRatio:Number(clamp(.38+sourceCount*.10+viewCount*.08,0,1).toFixed(2)),
      inferredRatio:Number(clamp(.62-sourceCount*.08-viewCount*.05,.08,.55).toFixed(2))
    };
  }

  function viewBin(frame){return Math.round(((frame.descriptor?.dominantAngle||0)%180)/45)%4}

  function buildCandidates(){
    const data=ensureSchema(project());
    if(!data)return;
    const radiusPixels=Number($('#mvClusterRadius')?.value||data.reconstruction.scanSettings.clusterRadius||72);
    data.reconstruction.scanSettings.clusterRadius=radiusPixels;
    const radius=radiusPixels/4096;
    const anchored=data.frames.filter(frame=>frame.descriptor&&anchorForFrame(data,frame.id)).map(frame=>({frame,anchor:anchorForFrame(data,frame.id)}));
    const oldBySignature=new Map((data.candidates||[]).map(candidate=>[candidate.signature,candidate]));
    const clusters=[];
    for(const item of anchored){
      let best=null,bestScore=-Infinity;
      for(const cluster of clusters){
        const spatial=Math.hypot(item.anchor.x-cluster.x,item.anchor.y-cluster.y);
        if(spatial>radius)continue;
        const representative=cluster.frames[0]?.frame;
        const visual=descriptorSimilarity(item.frame.descriptor,representative?.descriptor);
        const score=(1-spatial/radius)*.62+visual*.38;
        if((visual>=.36||spatial<=radius*.32)&&score>bestScore){best=cluster;bestScore=score;}
      }
      if(best){
        best.frames.push(item);
        const count=best.frames.length;
        best.x=(best.x*(count-1)+item.anchor.x)/count;
        best.y=(best.y*(count-1)+item.anchor.y)/count;
      }else clusters.push({x:item.anchor.x,y:item.anchor.y,frames:[item]});
    }

    const candidates=clusters.map(cluster=>{
      const frames=cluster.frames.map(item=>item.frame);
      const frameIds=frames.map(frame=>frame.id).sort();
      const signature=frameIds.join('|');
      const previous=oldBySignature.get(signature);
      const sourceCount=new Set(frames.map(frame=>frame.sourceId)).size;
      const viewCount=new Set(frames.map(viewBin)).size;
      let visualTotal=0,visualPairs=0;
      for(let i=0;i<frames.length;i++)for(let j=i+1;j<frames.length;j++){visualTotal+=descriptorSimilarity(frames[i].descriptor,frames[j].descriptor);visualPairs++;}
      const visualScore=visualPairs?visualTotal/visualPairs:1;
      const confidence=clamp(.24+Math.min(.30,sourceCount*.12)+Math.min(.20,frames.length*.04)+Math.min(.16,viewCount*.05)+visualScore*.10,.25,.97);
      const inference=previous?.inference||inferOutline(frames,sourceCount,viewCount);
      return{
        id:previous?.id||uid('candidate'),signature,frameIds,x:cluster.x,y:cluster.y,
        sourceCount,viewCount,visualScore:Number(visualScore.toFixed(3)),confidence:Number(confidence.toFixed(3)),
        status:previous?.status||'pending',buildingId:previous?.buildingId||'',inference,
        createdAt:previous?.createdAt||new Date().toISOString(),updatedAt:new Date().toISOString()
      };
    });
    const retained=(data.candidates||[]).filter(candidate=>candidate.status!=='pending'&&!candidates.some(item=>item.signature===candidate.signature));
    data.candidates=[...retained,...candidates];
    data.reconstruction.metrics.lastGrouping={anchoredFrames:anchored.length,candidates:candidates.length,radiusPixels,createdAt:new Date().toISOString()};
    persist(`已生成 ${candidates.length} 个建筑候选`,false);
  }

  function selectedCandidate(){return ensureSchema(project())?.candidates.find(candidate=>candidate.id===selectedCandidateId)||null}

  function focusCandidate(candidate){
    if(!candidate||typeof state==='undefined')return;
    const targetScale=Math.max(state.scale,fitScale()*2.15);
    state.scale=clamp(targetScale,minScale(),state.maxScale);
    state.offsetX=innerWidth/2-candidate.x*4096*state.scale;
    state.offsetY=innerHeight/2-candidate.y*4096*state.scale;
    if(typeof updateZoomLabel==='function')updateZoomLabel();
    if(typeof scheduleDraw==='function')scheduleDraw();
  }

  function acceptCandidate(candidate){
    const data=ensureSchema(project());
    if(!candidate||!data)return;
    let building=candidate.buildingId?data.buildings.find(item=>item.id===candidate.buildingId):null;
    if(!building){
      building={
        id:uid('building'),templateId:candidate.inference.templateId,x:candidate.x,y:candidate.y,
        rotation:candidate.inference.rotation||0,scale:candidate.inference.scale||1,season:'all',status:'provisional',
        confidence:candidate.confidence,evidenceIds:[...candidate.frameIds],source:'atlas-original-vector',
        inference:{...candidate.inference,candidateId:candidate.id,sourceCount:candidate.sourceCount,viewCount:candidate.viewCount},
        createdAt:new Date().toISOString()
      };
      data.buildings.push(building);candidate.buildingId=building.id;
    }else{
      building.templateId=candidate.inference.templateId;building.rotation=candidate.inference.rotation;building.scale=candidate.inference.scale;
      building.evidenceIds=[...candidate.frameIds];building.confidence=candidate.confidence;
    }
    candidate.status='accepted';candidate.updatedAt=new Date().toISOString();
    persist('候选已转换为原创二维建筑',true);
  }

  function ignoreCandidate(candidate){if(!candidate)return;candidate.status='ignored';persist('候选已标记为忽略',false)}

  async function renderCandidateReview(){
    const container=$('#mvCandidateReview');
    if(!container)return;
    const candidate=selectedCandidate();
    if(!candidate){container.hidden=true;container.innerHTML='';return;}
    container.hidden=false;
    const data=ensureSchema(project());
    const frames=candidate.frameIds.map(id=>data.frames.find(frame=>frame.id===id)).filter(Boolean).slice(0,6);
    const templateOptions=templates().map(template=>`<option value="${template.id}">${escapeHtml(template.name)}</option>`).join('');
    container.innerHTML=`
      <div class="mv-review-head"><div><b>候选 ${escapeHtml(candidate.id.slice(-6))}</b><small>${candidate.sourceCount} 个来源 · ${candidate.viewCount} 类视角 · ${Math.round(candidate.confidence*100)}%</small></div><button id="mvCloseReview">×</button></div>
      <div class="mv-frame-grid" id="mvReviewFrames"></div>
      <div class="mv-outline-preview" id="mvOutlinePreview"></div>
      <label>建筑模板<select id="mvTemplateSelect">${templateOptions}</select></label>
      <label>推理角度<input id="mvRotation" type="range" min="0" max="179" value="${Math.round(candidate.inference.rotation||0)}"><output>${Math.round(candidate.inference.rotation||0)}°</output></label>
      <label>轮廓比例<input id="mvScale" type="range" min="50" max="180" value="${Math.round((candidate.inference.scale||1)*100)}"><output>${Math.round((candidate.inference.scale||1)*100)}%</output></label>
      <div class="mv-evidence-ratios"><span>直接观察 ${Math.round((candidate.inference.observedRatio||0)*100)}%</span><span>逻辑补全 ${Math.round((candidate.inference.inferredRatio||0)*100)}%</span></div>
      <div class="mv-review-actions"><button id="mvReinfer">重新推理</button><button id="mvIgnore">忽略</button><button class="primary" id="mvAccept">接受为建筑</button></div>`;
    const frameGrid=$('#mvReviewFrames');
    for(const frame of frames){
      const url=await getFrameUrl(frame.id);
      const source=data.sources.find(item=>item.id===frame.sourceId);
      const cell=document.createElement('div');cell.className='mv-review-frame';
      cell.innerHTML=`${url?`<img src="${url}" alt="候选视角">`:'<span>无预览</span>'}<small>${escapeHtml(source?.name||'来源')} · ${Math.round(frame.time)}s</small>`;
      frameGrid.appendChild(cell);
    }
    const select=$('#mvTemplateSelect');select.value=candidate.inference.templateId;
    select.onchange=()=>{candidate.inference.templateId=select.value;saveCandidateLight(candidate);};
    const bind=(id,key,convert,format)=>{
      const input=$(id),output=input?.nextElementSibling;if(!input)return;
      input.oninput=()=>{candidate.inference[key]=convert(Number(input.value));if(output)output.textContent=format(Number(input.value));drawOutlinePreview(candidate);saveCandidateLight(candidate);};
    };
    bind('#mvRotation','rotation',value=>value,value=>`${Math.round(value)}°`);
    bind('#mvScale','scale',value=>value/100,value=>`${Math.round(value)}%`);
    $('#mvCloseReview').onclick=()=>{selectedCandidateId='';render091();scheduleDraw();};
    $('#mvReinfer').onclick=()=>{
      const allFrames=candidate.frameIds.map(id=>data.frames.find(frame=>frame.id===id)).filter(Boolean);
      candidate.inference=inferOutline(allFrames,candidate.sourceCount,candidate.viewCount);persist('已重新计算候选轮廓',false);
    };
    $('#mvIgnore').onclick=()=>ignoreCandidate(candidate);
    $('#mvAccept').onclick=()=>acceptCandidate(candidate);
    drawOutlinePreview(candidate);
  }

  function saveCandidateLight(candidate){
    candidate.updatedAt=new Date().toISOString();
    const data=project();data.updatedAt=new Date().toISOString();data.version=VERSION;
    localStorage.setItem(STORAGE_KEY,JSON.stringify(data));
    if(typeof scheduleDraw==='function')scheduleDraw();
  }

  function polygonPoints(candidate,size=88){
    const template=templates().find(item=>item.id===candidate.inference?.templateId)||templates()[0];
    if(!template?.footprint)return[];
    const rotation=(candidate.inference.rotation||0)*Math.PI/180;
    const scale=(candidate.inference.scale||1)*size;
    const cos=Math.cos(rotation),sin=Math.sin(rotation);
    return template.footprint.map(point=>({x:point[0]*scale*cos-point[1]*scale*sin,y:point[0]*scale*sin+point[1]*scale*cos}));
  }

  function drawOutlinePreview(candidate){
    const node=$('#mvOutlinePreview');if(!node)return;
    const points=polygonPoints(candidate,70);
    if(!points.length){node.innerHTML='无法生成轮廓';return;}
    const coords=points.map(point=>`${100+point.x},${70+point.y}`).join(' ');
    node.innerHTML=`<svg viewBox="0 0 200 140" role="img" aria-label="推理建筑轮廓"><rect width="200" height="140" rx="12" fill="rgba(0,0,0,.18)"/><polygon points="${coords}" fill="rgba(220,182,111,.32)" stroke="rgba(255,232,185,.9)" stroke-width="2" stroke-dasharray="5 3"/><circle cx="100" cy="70" r="3" fill="#df4450"/></svg>`;
  }

  function renderCandidateList(){
    const container=$('#mvCandidateList');if(!container)return;
    const data=ensureSchema(project());
    const candidates=[...data.candidates].sort((a,b)=>{
      const order={pending:0,accepted:1,ignored:2};
      return (order[a.status]??3)-(order[b.status]??3)||b.confidence-a.confidence;
    });
    const pending=candidates.filter(item=>item.status==='pending').length;
    const accepted=candidates.filter(item=>item.status==='accepted').length;
    const ignored=candidates.filter(item=>item.status==='ignored').length;
    const stats=$('#mvCandidateStats');if(stats)stats.textContent=`待审核 ${pending} · 已接受 ${accepted} · 已忽略 ${ignored}`;
    if(!candidates.length){container.innerHTML='<div class="evidence-empty">完成密集扫描并定位关键帧后，点击“生成候选”。</div>';return;}
    container.innerHTML=candidates.slice(0,80).map(candidate=>`<button class="mv-candidate-row ${candidate.status}${selectedCandidateId===candidate.id?' selected':''}" data-mv-candidate="${candidate.id}">
      <span><b>${candidate.status==='accepted'?'已接受':candidate.status==='ignored'?'已忽略':'待审核'} · ${Math.round(candidate.confidence*100)}%</b><small>${candidate.sourceCount} 来源 · ${candidate.viewCount} 视角类 · ${candidate.frameIds.length} 帧</small></span><i>${candidate.inference?.templateId||'未推理'}</i>
    </button>`).join('');
    container.querySelectorAll('[data-mv-candidate]').forEach(button=>button.onclick=()=>{
      selectedCandidateId=button.dataset.mvCandidate;
      const candidate=data.candidates.find(item=>item.id===selectedCandidateId);focusCandidate(candidate);render091();
    });
  }

  function render091(){
    const data=project();if(!data)return;
    ensureSchema(data);
    const section=$('#multiview091Section');if(!section)return;
    const interval=$('#mvScanInterval');if(interval&&!interval.matches(':focus'))interval.value=String(data.reconstruction.scanSettings.interval||2);
    const radius=$('#mvClusterRadius');if(radius&&!radius.matches(':focus'))radius.value=String(data.reconstruction.scanSettings.clusterRadius||72);
    const scanButton=$('#mvDenseScanButton');if(scanButton){scanButton.disabled=scanning;scanButton.textContent=scanning?'正在扫描…':'密集扫描视频';}
    renderCandidateList();renderCandidateReview();
  }

  function installUi(){
    if($('#multiview091Section'))return true;
    const scroll=$('#evidencePanel .evidence-scroll');if(!scroll)return false;
    const section=document.createElement('section');section.className='evidence-section mv091-section';section.id='multiview091Section';
    section.innerHTML=`
      <div class="evidence-section-title"><b>多视角重建 0.9.1</b><small id="mvCandidateStats">待审核 0</small></div>
      <div class="mv-scan-grid">
        <button class="primary" id="mvDenseScanButton">密集扫描视频</button>
        <label>采样间隔<select id="mvScanInterval"><option value="1">1 秒</option><option value="2">2 秒</option><option value="3">3 秒</option><option value="5">5 秒</option></select></label>
        <button id="mvBuildCandidates">生成候选</button>
        <label>归组半径<input id="mvClusterRadius" type="number" min="24" max="180" step="8" value="72"><span>地图像素</span></label>
      </div>
      <input id="mvDenseVideoInput" type="file" accept="video/*" hidden>
      <div class="mv-scan-progress" id="mvScanProgress">尚未运行密集扫描</div>
      <div class="mv-candidate-list" id="mvCandidateList"></div>
      <div class="mv-candidate-review" id="mvCandidateReview" hidden></div>`;
    const tools=scroll.querySelector('.evidence-section:nth-of-type(3)');
    if(tools?.nextSibling)scroll.insertBefore(section,tools.nextSibling);else scroll.appendChild(section);
    $('#mvDenseScanButton').onclick=()=>$('#mvDenseVideoInput').click();
    $('#mvDenseVideoInput').onchange=event=>{const file=event.target.files?.[0];if(file)denseScanFile(file);event.target.value='';};
    $('#mvBuildCandidates').onclick=buildCandidates;
    $('#mvScanInterval').onchange=event=>{ensureSchema(project()).reconstruction.scanSettings.interval=Number(event.target.value);persist('',false);};
    $('#mvClusterRadius').onchange=event=>{ensureSchema(project()).reconstruction.scanSettings.clusterRadius=Number(event.target.value);persist('',false);};
    return true;
  }

  function drawCandidateOverlay(){
    const data=project();
    if(!data?.candidates||typeof state==='undefined'||state.scale/fitScale()<1.25)return;
    ctx.save();ctx.setLineDash([5,4]);
    for(const candidate of data.candidates){
      if(candidate.status==='ignored')continue;
      const centerX=state.offsetX+candidate.x*4096*state.scale;
      const centerY=state.offsetY+candidate.y*4096*state.scale;
      if(centerX<-100||centerY<-100||centerX>innerWidth+100||centerY>innerHeight+100)continue;
      const points=polygonPoints(candidate,clamp(11*(state.scale/fitScale()),15,44));
      if(!points.length)continue;
      ctx.beginPath();points.forEach((point,index)=>{const x=centerX+point.x,y=centerY+point.y;if(index)ctx.lineTo(x,y);else ctx.moveTo(x,y);});ctx.closePath();
      const selected=candidate.id===selectedCandidateId;
      ctx.fillStyle=candidate.status==='accepted'?'rgba(98,190,130,.12)':selected?'rgba(225,69,80,.22)':'rgba(225,184,102,.13)';
      ctx.strokeStyle=selected?'rgba(245,81,94,.95)':candidate.status==='accepted'?'rgba(107,211,147,.72)':'rgba(245,211,145,.72)';
      ctx.lineWidth=selected?2:1.1;ctx.fill();ctx.stroke();
    }
    ctx.restore();
  }

  function installDraw(){
    if(drawInstalled||typeof draw!=='function'||typeof ctx==='undefined')return false;
    const baseDraw=draw;
    const wrapped=function(){baseDraw();drawCandidateOverlay();};
    wrapped.__multiview091=true;draw=wrapped;drawInstalled=true;scheduleDraw();return true;
  }

  function start(){
    if(!api()||!$('#evidencePanel'))return setTimeout(start,120);
    const data=ensureSchema(project());
    data.version=VERSION;
    localStorage.setItem(STORAGE_KEY,JSON.stringify(data));
    api().version=VERSION;
    installUi();installDraw();render091();
    observer=new MutationObserver(()=>{installUi();render091();});
    observer.observe($('#evidencePanel'),{attributes:true,attributeFilter:['class']});
    window.AtlasMultiview091={buildCandidates,denseScanFile,descriptorSimilarity,version:VERSION};
  }

  start();
})();