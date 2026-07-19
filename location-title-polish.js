(() => {
  'use strict';

  const VERSION='0.9.3.9';
  const exact = new Map(Object.entries({
    'Mibuno Castle':'壬生野城','Katano Castle':'交野城','Osaka Castle':'大阪城','Amagasaki Castle':'尼崎城',
    'Takatsuki Castle':'高槻城','Yamazaki Castle':'山崎城','Shoryuji Castle':'胜龙寺城','Nijo Palace':'二条城',
    'Himeji Castle':'姬路城','Takeda Castle':'竹田城','Miki Castle':'三木城','Azuchi Castle':'安土城',
    'Kameyama Castle':'龟山城','Sakamoto Castle':'坂本城','Odani Castle':'小谷城','Nagahama Castle':'长滨城',
    'Hikone Castle':'彦根城','Kiyomizudera Temple':'清水寺','Lost Page - Kiyomizudera Temple':'遗失书页·清水寺',
    'Mount Uchinakao':'内中尾山','Mount Hiei':'比叡山','Mount Koya':'高野山','Mount Yoshino':'吉野山',
    'Mount Kurama':'鞍马山','Lake Biwa':'琵琶湖','Fushimi Inari Shrine':'伏见稻荷大社','Todai-ji Temple':'东大寺',
    'Todaiji Temple':'东大寺','Kofuku-ji Temple':'兴福寺','Byodo-in Temple':'平等院','Enryakuji Temple':'延历寺',
    'Miidera Temple':'三井寺','Ishiyamadera Temple':'石山寺','Honnoji Temple':'本能寺','Kinkakuji Temple':'金阁寺',
    'Ginkakuji Temple':'银阁寺','Nanzenji Temple':'南禅寺'
  }));

  function polish(item){
    if(!item || typeof item!=='object') return item;
    const original=String(item.title_en || item.title || '').trim();
    let chinese=exact.get(original) || String(item.title_zh || item.title || '').trim();
    if(/[A-Za-z]/.test(chinese) && window.AtlasLocationNames) chinese=AtlasLocationNames.translate(original);
    chinese=chinese.replace(/大坂城/g,'大阪城').replace(/寺寺庙|寺寺/g,'寺').replace(/城城堡|城城/g,'城')
      .replace(/山山/g,'山').replace(/神社神社/g,'神社').replace(/\s+/g,' ').trim();
    item.title_en=original;
    item.title_zh=chinese || '未命名地点';
    item.title=item.title_zh;
    return item;
  }

  window.AtlasLocationTitlePolish={polish,exact,version:VERSION};
  const previousFetch=window.fetch.bind(window);
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const isLocations=input=>/data\/locations\.json(?:\?|$)/.test(typeof input==='string'?input:(input&&input.url)||'');

  async function parseLocations(response){
    if(!response || !response.ok) throw new Error(`locations HTTP ${response?.status||0}`);
    const text=await response.clone().text();
    if(!text.trim()) throw new Error('locations response empty');
    const data=JSON.parse(text);
    if(!Array.isArray(data) || data.length<3000) throw new Error(`locations count invalid: ${data?.length||0}`);
    data.forEach(polish);
    return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json','X-Atlas-Recovery':VERSION}});
  }

  async function cachedLocations(input){
    if(!('caches' in window)) return null;
    const url=new URL(typeof input==='string'?input:input.url,location.href);
    url.search='';
    for(const candidate of [input,url.href,'data/locations.json']){
      const response=await caches.match(candidate).catch(()=>null);
      if(!response) continue;
      try{return await parseLocations(response)}catch{}
    }
    return null;
  }

  window.fetch=async function(input,init){
    if(!isLocations(input)) return previousFetch(input,init);
    let lastError;
    for(let attempt=0;attempt<4;attempt++){
      try{return await parseLocations(await previousFetch(input,{...init,cache:attempt?'reload':'default'}))}
      catch(error){lastError=error;if(attempt<3)await sleep(180*(attempt+1))}
    }
    const cached=await cachedLocations(input);
    if(cached) return cached;
    throw lastError || new Error('locations unavailable');
  };
})();
