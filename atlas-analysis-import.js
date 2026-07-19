(() => {
  'use strict';

  const VERSION='0.9.3.6';
  const TYPOGRAPHY_VERSION='0.9.3.0';
  const PERFORMANCE_VERSION='0.9.2.0';
  const UI_FIX_VERSION='0.9.3.1';
  const SMART_ROUTE_VERSION='0.9.3.2';
  const LIQUID_NAV_VERSION='0.9.3.6';
  let analysisIndex={items:[]};
  const $=selector=>document.querySelector(selector);
  const escapeHtml=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));

  function loadPerformanceLayer(){
    if(!document.querySelector(`link[data-atlas-performance="${PERFORMANCE_VERSION}"]`)){
      const link=document.createElement('link');
      link.rel='stylesheet';
      link.href=`performance-092.css?v=${PERFORMANCE_VERSION}`;
      link.dataset.atlasPerformance=PERFORMANCE_VERSION;
      document.head.appendChild(link);
    }
    if(!document.querySelector(`script[data-atlas-performance="${PERFORMANCE_VERSION}"]`)){
      const script=document.createElement('script');
      script.src=`performance-092.js?v=${PERFORMANCE_VERSION}`;
      script.dataset.atlasPerformance=PERFORMANCE_VERSION;
      document.body.appendChild(script);
    }
  }

  function loadTypographyLayer(){
    if(document.querySelector(`link[data-atlas-typography="${TYPOGRAPHY_VERSION}"]`))return;
    const link=document.createElement('link');
    link.rel='stylesheet';
    link.href=`atlas-typography-093.css?v=${TYPOGRAPHY_VERSION}`;
    link.dataset.atlasTypography=TYPOGRAPHY_VERSION;
    document.head.appendChild(link);
    document.documentElement.dataset.atlasTypography=TYPOGRAPHY_VERSION;
  }

  function loadUiFixLayer(){
    if(!document.querySelector(`link[data-atlas-ui-fix="${UI_FIX_VERSION}"]`)){
      const link=document.createElement('link');
      link.rel='stylesheet';
      link.href=`atlas-ui-fix-0931.css?v=${UI_FIX_VERSION}`;
      link.dataset.atlasUiFix=UI_FIX_VERSION;
      document.head.appendChild(link);
    }
    if(!document.querySelector(`script[data-atlas-ui-fix="${UI_FIX_VERSION}"]`)){
      const script=document.createElement('script');
      script.src=`atlas-ui-fix-0931.js?v=${UI_FIX_VERSION}`;
      script.dataset.atlasUiFix=UI_FIX_VERSION;
      script.defer=true;
      document.body.appendChild(script);
    }
  }

  function loadSmartRouteLayer(){
    if(document.querySelector(`link[data-atlas-smart-route="${SMART_ROUTE_VERSION}"]`))return;
    const link=document.createElement('link');
    link.rel='stylesheet';
    link.href=`atlas-smart-route-0932.css?v=${SMART_ROUTE_VERSION}`;
    link.dataset.atlasSmartRoute=SMART_ROUTE_VERSION;
    document.head.appendChild(link);
    document.documentElement.dataset.atlasSmartRoute=SMART_ROUTE_VERSION;
  }

  function loadLiquidNavigationLayer(){
    if(!document.querySelector(`link[data-atlas-liquid-nav="${LIQUID_NAV_VERSION}"]`)){
      const link=document.createElement('link');
      link.rel='stylesheet';
      link.href=`atlas-liquid-nav-0934.css?v=${LIQUID_NAV_VERSION}`;
      link.dataset.atlasLiquidNav=LIQUID_NAV_VERSION;
      document.head.appendChild(link);
    }
    if(!document.querySelector(`script[data-atlas-liquid-nav="${LIQUID_NAV_VERSION}"]`)){
      const script=document.createElement('script');
      script.src=`atlas-liquid-nav-0934.js?v=${LIQUID_NAV_VERSION}`;
      script.dataset.atlasLiquidNav=LIQUID_NAV_VERSION;
      script.defer=true;
      document.body.appendChild(script);
    }
  }

  function installStyles(){
    if($('#analysisImportStyles'))return;
    const style=document.createElement('style');
    style.id='analysisImportStyles';
    style.textContent=`
      .analysis-import-registry{border-color:rgba(100,175,255,.2)}
      .analysis-import-card{padding:11px;margin-top:8px;border:1px solid rgba(100,175,255,.22);border-radius:13px;background:rgba(65,126,190,.08)}
      .analysis-import-card:first-child{margin-top:0}
      .analysis-import-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
      .analysis-import-head b{font-size:11px;line-height:1.35}
      .analysis-import-head span,.analysis-import-chip{padding:4px 7px;border-radius:999px;background:rgba(74,160,242,.16);color:#a9d5ff;font-size:8px;white-space:nowrap}
      .analysis-import-card p{margin:7px 0 0;color:var(--muted);font-size:9px;line-height:1.55}
      .analysis-import-metrics{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}
      .analysis-import-metrics span{padding:4px 6px;border:1px solid rgba(255,255,255,.08);border-radius:999px;color:rgba(255,255,255,.66);font-size:8px}
      .public-source-card.analysis-imported{border-color:rgba(100,175,255,.26)}
      .public-source-card.analysis-imported .authorized-intake{opacity:.7}
    `;
    document.head.appendChild(style);
  }

  function formatDuration(seconds){
    const value=Math.max(0,Math.round(Number(seconds)||0));
    return `${Math.floor(value/60)}分${String(value%60).padStart(2,'0')}秒`;
  }

  function installRegistry(){
    if($('#analysisImportRegistry'))return $('#analysisImportRegistry');
    const anchor=$('#authorizationRegistry')||$('#publicSourceLibrary');
    if(!anchor)return null;
    const section=document.createElement('section');
    section.className='evidence-section analysis-import-registry';
    section.id='analysisImportRegistry';
    section.innerHTML=`<div class="evidence-section-title"><b>自动分析导入 ${VERSION}</b><small id="analysisImportCount">0 条已导入</small></div><div id="analysisImportList"></div>`;
    anchor.insertAdjacentElement('afterend',section);
    return section;
  }

  function renderRegistry(){
    if(!installRegistry())return;
    const imported=(analysisIndex.items||[]).filter(item=>item.status==='imported');
    const count=$('#analysisImportCount');
    if(count)count.textContent=`${imported.length} 条已导入`;
    const list=$('#analysisImportList');
    if(!list)return;
    list.innerHTML=imported.length?imported.map(item=>{
      const scan=item.scan||{};
      const media=item.media||{};
      return `<article class="analysis-import-card">
        <div class="analysis-import-head"><b>${escapeHtml(item.title)}</b><span>导入完成</span></div>
        <p>${escapeHtml(item.author)} · ${formatDuration(media.durationSeconds)} · ${media.width||0}×${media.height||0}<br>原视频和画面像素已删除，Atlas仅保留数值特征和时间戳。</p>
        <div class="analysis-import-metrics"><span>采样 ${scan.sampled||0}</span><span>保留 ${scan.kept||0}</span><span>重复过滤 ${scan.duplicates||0}</span><span>清晰度过滤 ${scan.blurred||0}</span></div>
      </article>`;
    }).join(''):'<div class="public-source-empty">暂无完成的自动分析。</div>';
  }

  function annotateCards(){
    for(const item of analysisIndex.items||[]){
      if(item.status!=='imported'||!item.externalSourceId)continue;
      const card=document.querySelector(`[data-public-source="${CSS.escape(item.externalSourceId)}"]`);
      if(!card)continue;
      card.classList.add('analysis-imported');
      const meta=card.querySelector('.public-source-meta');
      if(meta&&!meta.querySelector('.analysis-import-chip')){
        const chip=document.createElement('span');
        chip.className='analysis-import-chip';
        chip.textContent=`已导入 · ${item.scan?.kept||0}帧`;
        meta.appendChild(chip);
      }
      const button=card.querySelector('.authorized-intake');
      if(button){
        button.textContent='已自动导入';
        button.disabled=true;
        button.title='该授权视频已由自动流水线完成下载、分析和资料库导入';
      }
    }
    const summary=$('#publicLibrarySummary');
    if(summary&&!summary.dataset.analysisImport){
      const imported=(analysisIndex.items||[]).filter(item=>item.status==='imported').length;
      summary.textContent=`${summary.textContent} · 已导入 ${imported}`;
      summary.dataset.analysisImport='1';
    }
  }

  function apply(){
    installStyles();
    renderRegistry();
    annotateCards();
    const brand=document.querySelector('.brand-copy small');
    if(brand)brand.textContent="ASSASSIN'S CREED SHADOWS · ALPHA 0.9.3.6";
  }

  async function start(){
    try{
      const response=await fetch(`data/analysis-index.json?v=${VERSION}`);
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      analysisIndex=await response.json();
    }catch(error){
      analysisIndex={items:[],error:String(error)};
    }
    let attempts=0;
    const timer=setInterval(()=>{
      apply();
      attempts+=1;
      if(attempts>=24&&$('#analysisImportRegistry'))clearInterval(timer);
    },250);
    const panel=$('#evidencePanel');
    if(panel)new MutationObserver(()=>setTimeout(apply,0)).observe(panel,{attributes:true,attributeFilter:['class']});
    window.AtlasAnalysisImport={index:()=>analysisIndex,render:apply,version:VERSION};
  }

  loadTypographyLayer();
  loadPerformanceLayer();
  loadUiFixLayer();
  loadSmartRouteLayer();
  loadLiquidNavigationLayer();
  start();
})();
