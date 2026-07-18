(() => {
  'use strict';

  const VERSION='0.9.1.2';
  const STATE_KEY='atlas-public-source-state-v1';
  const PROJECT_KEY='atlas-evidence-project-v1';
  let library=null;
  let authorizations={records:[]};
  let sourceState=loadState();
  let pendingIntakeItem=null;

  const $=selector=>document.querySelector(selector);
  const escapeHtml=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));

  function loadState(){
    try{return JSON.parse(localStorage.getItem(STATE_KEY)||'{}')||{}}catch(_){return{}}
  }

  function saveState(){localStorage.setItem(STATE_KEY,JSON.stringify(sourceState))}

  function officialAuthorization(item){
    return (authorizations.records||[]).find(record=>record.status==='active'&&(record.sourceIds||[]).includes(item.id))||null;
  }

  function notify(message){
    const status=$('#evidenceStatus');
    if(status){status.textContent=message;status.classList.add('show');clearTimeout(notify.statusTimer);notify.statusTimer=setTimeout(()=>status.classList.remove('show'),3000);}
    const toast=$('#toast');
    if(toast){toast.textContent=message;toast.classList.add('show');clearTimeout(notify.toastTimer);notify.toastTimer=setTimeout(()=>toast.classList.remove('show'),2000);}
  }

  async function copyText(text){
    try{
      if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(text);return true;}
      const area=document.createElement('textarea');area.value=text;area.style.position='fixed';area.style.opacity='0';document.body.appendChild(area);area.select();const ok=document.execCommand('copy');area.remove();return ok;
    }catch(_){return false;}
  }

  function authorizationTemplate(item){
    return `你好，${item.author}：\n\n我正在制作一个非商业的《刺客信条：影》原创互动地图项目 Atlas。我们希望使用你的公开视频《${item.title}》作为建筑和道路位置的分析证据。\n\n申请的使用范围如下：\n1. 下载视频并仅在本地进行计算机视觉分析；\n2. 提取部分低分辨率关键帧，保存于非公开审核素材库；\n3. 根据分析结果重新绘制原创二维矢量建筑、道路和覆盖数据；\n4. 不重新发布完整视频，不提供原视频下载；\n5. 公开页面注明作者名称、视频标题和原始链接；\n6. 项目目前不收费、不接广告。\n\n原视频链接：${item.url}\n\n如同意，请明确回复：“同意 Atlas 项目按上述范围使用我的视频素材。”你也可以补充署名方式、期限或其他限制。`;
  }

  function statusFor(item){
    if(officialAuthorization(item))return 'authorized';
    return sourceState[item.id]?.status||'uncontacted';
  }

  function setStatus(id,status){
    sourceState[id]={...(sourceState[id]||{}),status,updatedAt:new Date().toISOString()};
    saveState();render();
  }

  function statusLabel(status){
    return({uncontacted:'未联系',contacted:'已联系',authorized:'已授权',rejected:'未授权'})[status]||status;
  }

  function installSection(){
    if($('#publicSourceLibrary'))return true;
    const scroll=$('#evidencePanel .evidence-scroll');
    if(!scroll)return false;
    const section=document.createElement('section');
    section.className='evidence-section public-library-section';
    section.id='publicSourceLibrary';
    section.innerHTML=`
      <div class="evidence-section-title"><b>公开资料库 0.9.1.2</b><small id="publicLibraryCount">正在载入</small></div>
      <div class="public-library-disclaimer" id="publicLibraryDisclaimer">公开可访问不等于允许下载或重新上传。未取得明确授权前，Atlas只保存外部链接和联系线索。</div>
      <div class="public-library-toolbar">
        <input id="publicLibrarySearch" type="search" placeholder="搜索作者、标题或用途" autocomplete="off">
        <select id="publicLibraryRegion" aria-label="筛选地区"><option value="">全部地区</option></select>
        <select id="publicLibraryStatus" aria-label="筛选状态"><option value="">全部状态</option><option value="permission_required">需作者授权</option><option value="reference_only">仅外链参考</option><option value="contacted">我已联系</option><option value="authorized">已获得授权</option></select>
      </div>
      <div class="public-library-summary"><span>按价值排序，正式授权来自项目授权登记</span><b id="publicLibrarySummary">0 条</b></div>
      <div class="public-source-list" id="publicSourceList"></div>`;
    const firstSection=scroll.querySelector('.evidence-section');
    if(firstSection?.nextSibling)scroll.insertBefore(section,firstSection.nextSibling);else scroll.appendChild(section);
    $('#publicLibrarySearch').addEventListener('input',render);
    $('#publicLibraryRegion').addEventListener('change',render);
    $('#publicLibraryStatus').addEventListener('change',render);
    return true;
  }

  function installAuthorizationRegistry(){
    if($('#authorizationRegistry'))return true;
    const librarySection=$('#publicSourceLibrary');
    if(!librarySection)return false;
    const section=document.createElement('section');
    section.className='evidence-section authorization-registry';
    section.id='authorizationRegistry';
    section.innerHTML=`
      <div class="evidence-section-title"><b>授权素材接入 0.9.1.2</b><small id="authorizationCount">0 条有效授权</small></div>
      <div id="authorizationRecordList"></div>
      <input id="authorizedVideoInput" type="file" accept="video/*" hidden>`;
    librarySection.insertAdjacentElement('afterend',section);
    $('#authorizedVideoInput').addEventListener('change',async event=>{
      const file=event.target.files?.[0];
      event.target.value='';
      if(file&&pendingIntakeItem)await importAuthorizedVideo(pendingIntakeItem,file);
      pendingIntakeItem=null;
    });
    return true;
  }

  function installAuthorizationStyles(){
    if($('#authorizationRegistryStyles'))return;
    const style=document.createElement('style');
    style.id='authorizationRegistryStyles';
    style.textContent=`
      .authorization-record{padding:11px;margin-top:8px;border:1px solid rgba(95,205,139,.28);border-radius:13px;background:rgba(64,151,99,.08)}
      .authorization-record:first-child{margin-top:0}
      .authorization-record-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
      .authorization-record-head b{font-size:11px}.authorization-record-head span{padding:4px 7px;border-radius:999px;background:rgba(75,190,126,.18);color:#9ce0b6;font-size:8px;white-space:nowrap}
      .authorization-record p{margin:7px 0 0;color:var(--muted);font-size:9px;line-height:1.55}
      .authorization-proof{display:block;margin-top:7px;color:rgba(255,255,255,.48);font-size:7px;word-break:break-all}
      .public-source-actions button.authorized-intake{background:rgba(75,190,126,.18);border-color:rgba(95,205,139,.34);color:#a8e7c0}
      .public-source-license.authorized{background:rgba(75,190,126,.18);color:#a8e7c0;border-color:rgba(95,205,139,.34)}
    `;
    document.head.appendChild(style);
  }

  function populateRegions(){
    const select=$('#publicLibraryRegion');
    if(!select||!library)return;
    const current=select.value;
    select.innerHTML='<option value="">全部地区</option>'+library.regions.filter(region=>region!=='全部地区').map(region=>`<option value="${escapeHtml(region)}">${escapeHtml(region)}</option>`).join('');
    select.value=current;
  }

  function matches(item,query,region,statusFilter){
    const effectiveStatus=statusFor(item);
    const haystack=[item.title,item.author,item.platform,item.type,item.quality,item.value,item.contact,...(item.coverage||[])].join(' ').toLowerCase();
    if(query&&!haystack.includes(query))return false;
    if(region&&!(item.coverage||[]).includes(region)&&!(item.coverage||[]).includes('全部地区'))return false;
    if(statusFilter==='contacted'&&effectiveStatus!=='contacted')return false;
    if(statusFilter==='authorized'&&effectiveStatus!=='authorized')return false;
    if(statusFilter==='permission_required'&&(effectiveStatus==='authorized'||item.license!=='permission_required'))return false;
    if(statusFilter==='reference_only'&&item.license!=='reference_only')return false;
    return true;
  }

  function cardHtml(item){
    const localStatus=statusFor(item);
    const authorization=officialAuthorization(item);
    const effectiveLabel=authorization?'已获得作者授权':localStatus==='authorized'?'已获得作者授权':item.licenseLabel;
    const badgeClass=localStatus==='authorized'?'authorized':item.license;
    const coverage=(item.coverage||[]).slice(0,5);
    const extra=(item.coverage||[]).length-coverage.length;
    return `<article class="public-source-card ${localStatus}" data-public-source="${escapeHtml(item.id)}">
      <div class="public-source-head"><div><b>${escapeHtml(item.title)}</b><small>${escapeHtml(item.author)} · ${escapeHtml(item.platform)} · ${escapeHtml(item.type)}</small></div><span class="public-source-license ${badgeClass}">${escapeHtml(effectiveLabel)}</span></div>
      <p class="public-source-value">${escapeHtml(item.value)}</p>
      <div class="public-source-meta"><span>${escapeHtml(item.quality)}</span>${item.episodes?`<span>${item.episodes}期</span>`:''}${coverage.map(region=>`<span>${escapeHtml(region)}</span>`).join('')}${extra>0?`<span>+${extra}</span>`:''}<span>${statusLabel(localStatus)}</span></div>
      <div class="public-source-contact">联系：${escapeHtml(item.contact)}<br>${escapeHtml(authorization?'授权凭证已由项目方留存；聊天截图不公开。':item.notes||'')}</div>
      <div class="public-source-actions">
        <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">打开原资料</a>
        ${authorization?'<button data-public-action="intake" class="authorized-intake">导入已授权视频</button>':'<button data-public-action="copy" class="primary">复制授权申请</button>'}
        ${authorization?'':`<button data-public-action="contacted">${localStatus==='contacted'?'取消已联系':'标记已联系'}</button><button data-public-action="authorized" class="${localStatus==='authorized'?'authorized':''}">${localStatus==='authorized'?'取消已授权':'标记已授权'}</button>`}
      </div>
    </article>`;
  }

  function bindCards(items){
    const list=$('#publicSourceList');
    list?.querySelectorAll('[data-public-source]').forEach(card=>{
      const item=items.find(entry=>entry.id===card.dataset.publicSource);
      if(!item)return;
      const copy=card.querySelector('[data-public-action="copy"]');
      if(copy)copy.onclick=async()=>notify(await copyText(authorizationTemplate(item))?'授权申请已复制':'复制失败，请手动复制');
      const contacted=card.querySelector('[data-public-action="contacted"]');
      if(contacted)contacted.onclick=()=>setStatus(item.id,statusFor(item)==='contacted'?'uncontacted':'contacted');
      const authorized=card.querySelector('[data-public-action="authorized"]');
      if(authorized)authorized.onclick=()=>setStatus(item.id,statusFor(item)==='authorized'?'uncontacted':'authorized');
      const intake=card.querySelector('[data-public-action="intake"]');
      if(intake)intake.onclick=()=>{
        pendingIntakeItem=item;
        const input=$('#authorizedVideoInput');
        if(!input){notify('授权素材接入模块尚未就绪');return;}
        input.click();
      };
    });
  }

  function renderAuthorizationRegistry(){
    if(!installAuthorizationRegistry())return;
    const records=(authorizations.records||[]).filter(record=>record.status==='active');
    const count=$('#authorizationCount');
    if(count)count.textContent=`${records.length} 条有效授权`;
    const list=$('#authorizationRecordList');
    if(!list)return;
    list.innerHTML=records.length?records.map(record=>`
      <article class="authorization-record">
        <div class="authorization-record-head"><b>${escapeHtml(record.author)}</b><span>有效授权</span></div>
        <p>${escapeHtml(record.grantText)}<br>覆盖当前资料条目 ${record.sourceIds?.length||0} 条；允许本地分析、私有低清关键帧和原创二维重建，不允许公开分发完整视频。</p>
        <small class="authorization-proof">凭证 SHA-256：${escapeHtml(record.proof?.fileSha256||'未记录')}</small>
      </article>`).join(''):'<div class="public-source-empty">暂无正式授权记录。</div>';
  }

  async function importAuthorizedVideo(item,file){
    const authorization=officialAuthorization(item);
    if(!authorization){notify('该资料没有正式授权记录');return;}
    const multiview=window.AtlasMultiview091;
    const evidence=window.AtlasEvidence;
    if(!multiview?.denseScanFile||!evidence?.project){notify('多视角扫描模块尚未就绪');return;}
    const data=evidence.project();
    const before=new Set((data.sources||[]).map(source=>source.id));
    notify(`开始扫描已授权素材：${file.name}`);
    await multiview.denseScanFile(file);
    const source=(data.sources||[]).filter(entry=>!before.has(entry.id)).at(-1);
    if(!source){notify('扫描未生成素材记录，请检查视频格式');return;}
    source.authorizationId=authorization.id;
    source.externalSourceId=item.id;
    source.author=item.author;
    source.originalTitle=item.title;
    source.originalUrl=item.url;
    source.license='authorized';
    source.attribution={author:item.author,title:item.title,url:item.url};
    source.usageScope={...authorization.scope};
    data.authorizedIntakes=Array.isArray(data.authorizedIntakes)?data.authorizedIntakes:[];
    data.authorizedIntakes.push({
      id:`intake-${Date.now().toString(36)}`,
      authorizationId:authorization.id,
      externalSourceId:item.id,
      sourceId:source.id,
      fileName:file.name,
      importedAt:new Date().toISOString(),
      scanMode:source.scanMode||'dense-091'
    });
    data.updatedAt=new Date().toISOString();
    localStorage.setItem(PROJECT_KEY,JSON.stringify(data));
    evidence.open?.();
    notify(`已接入授权视频并保留 ${source.frameCount||0} 个关键帧`);
  }

  function render(){
    if(!library||!installSection())return;
    installAuthorizationStyles();
    installAuthorizationRegistry();
    populateRegions();
    const query=($('#publicLibrarySearch')?.value||'').trim().toLowerCase();
    const region=$('#publicLibraryRegion')?.value||'';
    const statusFilter=$('#publicLibraryStatus')?.value||'';
    const items=[...library.items].sort((a,b)=>(b.priority||0)-(a.priority||0)).filter(item=>matches(item,query,region,statusFilter));
    const list=$('#publicSourceList');
    if(list)list.innerHTML=items.length?items.map(cardHtml).join(''):'<div class="public-source-empty">没有符合当前筛选条件的资料。</div>';
    const count=$('#publicLibraryCount');if(count)count.textContent=`${library.items.length} 条已核实入口`;
    const authorized=library.items.filter(item=>statusFor(item)==='authorized').length;
    const contacted=library.items.filter(item=>statusFor(item)==='contacted').length;
    const summary=$('#publicLibrarySummary');if(summary)summary.textContent=`显示 ${items.length} · 已联系 ${contacted} · 已授权 ${authorized}`;
    const disclaimer=$('#publicLibraryDisclaimer');if(disclaimer)disclaimer.textContent=library.disclaimer;
    bindCards(items);
    renderAuthorizationRegistry();
    const brand=document.querySelector('.brand-copy small');
    if(brand)brand.textContent="ASSASSIN'S CREED SHADOWS · ALPHA 0.9.1.2";
  }

  async function start(){
    try{
      [library,authorizations]=await Promise.all([
        fetch(`data/public-source-library.json?v=${VERSION}`).then(response=>{if(!response.ok)throw new Error(`资料库 HTTP ${response.status}`);return response.json();}),
        fetch(`data/authorizations.json?v=${VERSION}`).then(response=>{if(!response.ok)throw new Error(`授权库 HTTP ${response.status}`);return response.json();})
      ]);
    }catch(error){
      library=library||{regions:[],items:[],disclaimer:`资料库载入失败：${error.message}`};
      authorizations=authorizations||{records:[]};
    }
    const wait=()=>{if(!installSection())return setTimeout(wait,120);render();};
    wait();
    const panel=$('#evidencePanel');
    if(panel)new MutationObserver(()=>render()).observe(panel,{attributes:true,attributeFilter:['class']});
    window.AtlasPublicLibrary={items:()=>library.items,state:()=>sourceState,authorizations:()=>authorizations.records,render,version:VERSION};
  }

  start();
})();