(() => {
  'use strict';
  function install(){
    if(typeof state==='undefined'||typeof smartTokens!=='function'||typeof el!=='function'){
      setTimeout(install,30);
      return;
    }
    runSearch=function(q){
      const tokens=smartTokens(q);
      const scored=state.locations.map(l=>{
        const category=state.categoryMap.get(l.category_id)||{};
        const region=state.regionMap.get(l.region_id)||{};
        const zh=String(l.title_zh||l.title||'');
        const en=String(l.title_en||'');
        const cZh=String(category.title||'');
        const cEn=String(category.title_en||'');
        const rZh=String(region.title||'');
        const rEn=String(region.title_en||'');
        const hay=`${zh} ${en} ${cZh} ${cEn} ${rZh} ${rEn} ${l.description||''}`.toLowerCase();
        let score=0;
        for(const token of tokens){
          if(zh.toLowerCase().includes(token)||en.toLowerCase().includes(token))score+=8;
          if(cZh.toLowerCase().includes(token)||cEn.toLowerCase().includes(token))score+=5;
          if(rZh.toLowerCase().includes(token)||rEn.toLowerCase().includes(token))score+=5;
          if(hay.includes(token))score++;
        }
        return{l,score};
      }).filter(x=>!tokens.length||x.score>=tokens.length)
        .sort((a,b)=>b.score-a.score)
        .slice(0,80)
        .map(x=>x.l);

      el('resultCount').textContent=scored.length+(scored.length===80?'＋':'');
      el('searchResults').innerHTML=scored.map(l=>{
        const c=state.categoryMap.get(l.category_id);
        const r=state.regionMap.get(l.region_id);
        return`<button class="result-item" data-id="${l.id}"><span class="result-icon">${iconMarkup(c?.title,22)}</span><span class="result-copy"><b>${escapeHTML(l.title_zh||l.title)}</b><small>${escapeHTML(c?.title||'')} · ${escapeHTML(r?.title||'未知区域')}</small></span><em>›</em></button>`;
      }).join('')||'<div class="empty-state">没有匹配结果</div>';
      document.querySelectorAll('.result-item').forEach(button=>button.onclick=()=>{
        const location=state.locations.find(x=>x.id===button.dataset.id);
        closeSearch();
        focusLocation(location);
      });
    };
  }
  install();
})();