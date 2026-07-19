(() => {
  'use strict';

  const VERSION=window.AtlasRelease?.version||'0.9.4.2';
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
  polish.atlasPaths=['data/locations.json'];

  window.AtlasLocationTitlePolish={polish,exact,version:VERSION};
  window.AtlasDataTransforms=window.AtlasDataTransforms||[];
  if(!window.AtlasDataTransforms.includes(polish))window.AtlasDataTransforms.push(polish);
})();
