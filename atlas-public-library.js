(() => {
  'use strict';

  const VERSION='0.9.1.1';
  const STATE_KEY='atlas-public-source-state-v1';
  let library=null;
  let sourceState=loadState();

  const $=selector=>document.querySelector(selector);
  const escapeHtml=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));

  function loadState(){
    try{return JSON.parse(localStorage.getItem(STATE_KEY)||'{}')||{}}catch(_){return{}}
  }

  function saveState(){localStorage.setItem(STATE_KEY,JSON.stringify(sourceState))}

  function notify(message){
    const status=$('#evidenceStatus');
    if(status){status.textContent=message;status.classList.add('show');clearTimeout(notify.statusTimer);notify.statusTimer=setTimeout(()=>status.classList.remove('show'),2600);}
    const toast=$('#toast');
    if(toast){toast.textContent=message;toast.classList.add('show');clearTimeout(notify.toastTimer);notify.toastTimer=setTimeout(()=>toast.classList.remove('show'),1800);}
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

  function statusFor(item){return sourceState[item.id]?.status||'uncontacted'}

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
      <div class="evidence-section-title"><b>公开资料库 0.9.1.1</b><small id="publicLibraryCount">正在载入</small></div>
      <div class="public-library-disclaimer" id="publicLibraryDisclaimer">公开可访问不等于允许下载或重新上传。未取得明确授权前，Atlas只保存外部链接和联系线索。</div>
      <div class="public-library-toolbar">
        <input id="publicLibrarySearch" type="search" placeholder="搜索作者、标题或用途" autocomplete="off">
        <select id="publicLibraryRegion" aria-label="筛选地区"><option value="">全部地区</option></select>
        <select id="publicLibraryStatus" aria-label="筛选状态"><option value="">全部状态</option><option value="permission_required">需作者授权</option><option value="reference_only">仅外链参考</option><option value="contacted">我已联系</option><option value="authorized">我已获得授权</option></select>
      </div>
      <div class="public-library-summary"><span>按价值排序，授权状态只保存在当前设备</span><b id="publicLibrarySummary">0 条</b></div>
      <div class="public-source-list" id="publicSourceList"></div>`;
    const firstSection=scroll.querySelector('.evidence-section');
    if(firstSection?.nextSibling)scroll.insertBefore(section,firstSection.nextSibling);else scroll.appendChild(section);
    $('#publicLibrarySearch').addEventListener('input',render);
    $('#publicLibraryRegion').addEventListener('change',render);
    $('#publicLibraryStatus').addEventListener('change',render);
    return true;
  }

  function populateRegions(){
    const select=$('#publicLibraryRegion');
    if(!select||!library)return;
    const current=select.value;
    select.innerHTML='<option value="">全部地区</option>'+library.regions.filter(region=>region!=='全部地区').map(region=>`<option value="${escapeHtml(region)}">${escapeHtml(region)}</option>`).join('');
    select.value=current;
  }

  function matches(item,query,region,statusFilter){
    const localStatus=statusFor(item);
    const haystack=[item.title,item.author,item.platform,item.type,item.quality,item.value,item.contact,...(item.coverage||[])].join(' ').toLowerCase();
    if(query&&!haystack.includes(query))return false;
    if(region&&!(item.coverage||[]).includes(region)&&!(item.coverage||[]).includes('全部地区'))return false;
    if(statusFilter==='contacted'&&localStatus!=='contacted')return false;
    if(statusFilter==='authorized'&&localStatus!=='authorized')return false;
    if(statusFilter&&statusFilter!=='contacted'&&statusFilter!=='authorized'&&item.license!==statusFilter)return false;
    return true;
  }

  function cardHtml(item){
    const localStatus=statusFor(item);
    const effectiveLabel=localStatus==='authorized'?'已获得作者授权':item.licenseLabel;
    const badgeClass=localStatus==='authorized'?'authorized':item.license;
    const coverage=(item.coverage||[]).slice(0,5);
    const extra=(item.coverage||[]).length-coverage.length;
    return `<article class="public-source-card ${localStatus}" data-public-source="${escapeHtml(item.id)}">
      <div class="public-source-head"><div><b>${escapeHtml(item.title)}</b><small>${escapeHtml(item.author)} · ${escapeHtml(item.platform)} · ${escapeHtml(item.type)}</small></div><span class="public-source-license ${badgeClass}">${escapeHtml(effectiveLabel)}</span></div>
      <p class="public-source-value">${escapeHtml(item.value)}</p>
      <div class="public-source-meta"><span>${escapeHtml(item.quality)}</span>${item.episodes?`<span>${item.episodes}期</span>`:''}${coverage.map(region=>`<span>${escapeHtml(region)}</span>`).join('')}${extra>0?`<span>+${extra}</span>`:''}<span>${statusLabel(localStatus)}</span></div>
      <div class="public-source-contact">联系：${escapeHtml(item.contact)}<br>${escapeHtml(item.notes||'')}</div>
      <div class="public-source-actions">
        <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">打开原资料</a>
        <button data-public-action="copy" class="primary">复制授权申请</button>
        <button data-public-action="contacted">${localStatus==='contacted'?'取消已联系':'标记已联系'}</button>
        <button data-public-action="authorized" class="${localStatus==='authorized'?'authorized':''}">${localStatus==='authorized'?'取消已授权':'标记已授权'}</button>
      </div>
    </article>`;
  }

  function bindCards(items){
    const list=$('#publicSourceList');
    list?.querySelectorAll('[data-public-source]').forEach(card=>{
      const item=items.find(entry=>entry.id===card.dataset.publicSource);
      if(!item)return;
      card.querySelector('[data-public-action="copy"]').onclick=async()=>notify(await copyText(authorizationTemplate(item))?'授权申请已复制':'复制失败，请手动复制');
      card.querySelector('[data-public-action="contacted"]').onclick=()=>setStatus(item.id,statusFor(item)==='contacted'?'uncontacted':'contacted');
      card.querySelector('[data-public-action="authorized"]').onclick=()=>setStatus(item.id,statusFor(item)==='authorized'?'uncontacted':'authorized');
    });
  }

  function render(){
    if(!library||!installSection())return;
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
  }

  async function start(){
    try{
      library=await fetch(`data/public-source-library.json?v=${VERSION}`).then(response=>{if(!response.ok)throw new Error(`HTTP ${response.status}`);return response.json();});
    }catch(error){
      library={regions:[],items:[],disclaimer:`资料库载入失败：${error.message}`};
    }
    const wait=()=>{if(!installSection())return setTimeout(wait,120);render();};
    wait();
    const panel=$('#evidencePanel');
    if(panel)new MutationObserver(()=>render()).observe(panel,{attributes:true,attributeFilter:['class']});
    window.AtlasPublicLibrary={items:()=>library.items,state:()=>sourceState,render,version:VERSION};
  }

  start();
})();
