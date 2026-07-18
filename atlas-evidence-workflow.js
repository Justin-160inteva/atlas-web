(() => {
  'use strict';

  const STORAGE_KEY='atlas-evidence-project-v1';
  const $=selector=>document.querySelector(selector);
  const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
  const uid=prefix=>`${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,8)}`;
  let applying=false;

  function getProject(){return window.AtlasEvidence?.project?.()||null}
  function selectedBuilding(project){
    const id=$('.evidence-building-row.selected')?.dataset.buildingId;
    return project?.buildings?.find(item=>item.id===id)||null;
  }
  function selectedFrameId(){return $('.evidence-frame.selected')?.dataset.frameId||''}

  function recalculate(building,project){
    const ids=Array.isArray(building.evidenceIds)?building.evidenceIds:[];
    const frames=ids.map(id=>project.frames.find(frame=>frame.id===id)).filter(Boolean);
    const sourceCount=new Set(frames.map(frame=>frame.sourceId)).size;
    const anchoredCount=frames.filter(frame=>project.anchors.some(anchor=>anchor.frameId===frame.id)).length;
    const evidenceCount=frames.length;
    const score=.30+Math.min(.30,sourceCount*.12)+Math.min(.20,anchoredCount*.07)+Math.min(.10,evidenceCount*.025)+(building.status==='verified'?.08:0);
    building.confidence=clamp(score,.25,.98);
    building.metrics={sourceCount,anchoredCount,evidenceCount,calculatedAt:new Date().toISOString()};
  }

  function persist(project,message){
    project.updatedAt=new Date().toISOString();
    localStorage.setItem(STORAGE_KEY,JSON.stringify(project));
    if(typeof scheduleDraw==='function')scheduleDraw();
    const toast=$('#toast');
    if(toast){toast.textContent=message;toast.classList.add('show');clearTimeout(persist.timer);persist.timer=setTimeout(()=>toast.classList.remove('show'),1700);}
    setTimeout(()=>document.getElementById('evidenceStudioBtn')?.click(),0);
  }

  function installWorkflow(){
    if(applying)return;
    const editor=$('#evidenceBuildingEditor');
    const project=getProject();
    const building=selectedBuilding(project);
    if(!editor||editor.hidden||!building||editor.querySelector('.evidence-workflow'))return;
    applying=true;
    recalculate(building,project);
    localStorage.setItem(STORAGE_KEY,JSON.stringify(project));
    const metrics=building.metrics||{sourceCount:0,anchoredCount:0,evidenceCount:0};
    const section=document.createElement('section');
    section.className='evidence-workflow';
    section.innerHTML=`
      <div class="evidence-confidence-summary"><b>${metrics.sourceCount}</b><span>独立来源</span><b>${metrics.anchoredCount}</b><span>已定位视角</span><b>${metrics.evidenceCount}</b><span>证据帧</span></div>
      <label class="evidence-season-editor">季节层<select><option value="all">全年</option><option value="spring">春</option><option value="summer">夏</option><option value="autumn">秋</option><option value="winter">冬</option></select><output>${Math.round(building.confidence*100)}%</output></label>
      <div class="evidence-editor-actions"><button data-workflow="attach">关联当前帧</button><button data-workflow="duplicate">复制建筑</button></div>`;
    const select=section.querySelector('select');select.value=building.season||'all';
    select.onchange=()=>{building.season=select.value;persist(project,'建筑季节层已更新');};
    section.querySelector('[data-workflow="attach"]').onclick=()=>{
      const frameId=selectedFrameId();
      if(!frameId){persist(project,'请先选择一张关键帧');return;}
      building.evidenceIds=[...new Set([...(building.evidenceIds||[]),frameId])];
      recalculate(building,project);persist(project,'当前关键帧已关联到建筑');
    };
    section.querySelector('[data-workflow="duplicate"]').onclick=()=>{
      const copy={...building,id:uid('building'),x:clamp(building.x+.003,0,1),y:clamp(building.y+.003,0,1),status:'provisional',evidenceIds:[...(building.evidenceIds||[])],createdAt:new Date().toISOString()};
      recalculate(copy,project);project.buildings.push(copy);persist(project,'已复制建筑模板实例');
    };
    editor.prepend(section);
    applying=false;
  }

  const style=document.createElement('style');
  style.textContent=`
    .evidence-confidence-summary{display:grid;grid-template-columns:repeat(6,auto);align-items:center;gap:5px;padding:8px;margin-bottom:8px;border-radius:10px;background:rgba(255,255,255,.035);font-size:8px;color:var(--muted)}
    .evidence-confidence-summary b{font-size:12px;color:var(--gold)}
    .evidence-season-editor select{width:100%;height:30px;border:1px solid var(--line);border-radius:9px;background:#201d1b;color:var(--text);font-size:9px;padding:0 6px}
  `;
  document.head.appendChild(style);

  const observer=new MutationObserver(()=>installWorkflow());
  const start=()=>{
    const panel=$('#evidencePanel');
    if(!panel)return setTimeout(start,100);
    observer.observe(panel,{subtree:true,childList:true,attributes:true,attributeFilter:['class','hidden']});
    panel.addEventListener('click',event=>{
      if(event.target?.id==='verifyBuilding')setTimeout(()=>{
        const project=getProject();const building=selectedBuilding(project);if(!project||!building)return;
        recalculate(building,project);localStorage.setItem(STORAGE_KEY,JSON.stringify(project));
      },0);
    },true);
    installWorkflow();
  };
  start();
})();
