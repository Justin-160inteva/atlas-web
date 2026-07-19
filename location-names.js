(() => {
  'use strict';

  const exactTitles = new Map(Object.entries({
    'Lost Page - Kiyomizudera Temple':'遗失书页·清水寺','Kiyomizudera Temple':'清水寺','Mount Uchinakao':'内中尾山','Lake Biwa':'琵琶湖','Mount Hiei':'比叡山','Mount Koya':'高野山','Mount Yoshino':'吉野山','Mount Kurama':'鞍马山','Osaka Castle':'大坂城','Azuchi Castle':'安土城','Himeji Castle':'姬路城','Nijo Palace':'二条御所','Imperial Palace':'京都御所','Fushimi Inari Shrine':'伏见稻荷大社','Kumano Nachi Taisha':'熊野那智大社','Iwashimizu Hachimangu':'石清水八幡宫','Todai-ji Temple':'东大寺','Todaiji Temple':'东大寺','Byodo-in Temple':'平等院','Enryakuji Temple':'延历寺','Ishiyama Honganji':'石山本愿寺'
  }));
  const phrases = new Map(Object.entries({
    'Legendary Sumi-e':'传奇水墨画','Legendary Chest':'传奇宝箱','Cultural Discovery':'文化探索','Origami Butterfly':'折纸蝴蝶','Valuable Object':'贵重物品','Weapon Part':'武器部件','Ornament Vendor':'饰品商人','Gear Vendor':'装备商人','Port Trader':'港口商人','Hostile Landmark':'敌对地标','Hidden Trail':'隐秘小径','Horse Archery':'骑射','Jizo Statue':'地藏像','Kamon Crest':'家纹','Kano Painting':'狩野派画作','Local Dish':'地方料理','Small Shrine':'小型神社','Lost Page':'遗失书页','Kura Key':'仓库钥匙','Alarm Bell':'警钟','Samurai Daisho':'武士大将','Sub-Region':'子区域','Easter Egg':'彩蛋','Tea Bowl':'茶碗','Sumi-e':'水墨画','Kuji-kiri':'九字切','Burial Mound':'古坟','Rice Field':'稻田','Hot Spring':'温泉','Tea House':'茶屋','Watch Tower':'瞭望塔','Watchtower':'瞭望塔'
  }));
  const places = new Map(Object.entries({
    'Kiyomizudera':'清水寺','Kiyomizu':'清水','Nijo':'二条','Osaka':'大坂','Sakai':'堺','Himeji':'姬路','Azuchi':'安土','Amagasaki':'尼崎','Miki':'三木','Takeda':'竹田','Yamazaki':'山崎','Otsu':'大津','Sakamoto':'坂本','Kyoto':'京都','Heian':'平安','Gion':'祇园','Fushimi':'伏见','Uji':'宇治','Nara':'奈良','Asuka':'飞鸟','Yoshino':'吉野','Koya':'高野','Hiei':'比叡','Katsura':'桂','Arashiyama':'岚山','Kurama':'鞍马','Kameyama':'龟山','Kameoka':'龟冈','Biwa':'琵琶','Kinkakuji':'金阁寺','Ginkakuji':'银阁寺','Todaiji':'东大寺','Todai-ji':'东大寺','Kofukuji':'兴福寺','Kasuga Taisha':'春日大社','Byodoin':'平等院','Byodo-in':'平等院','Enryakuji':'延历寺','Honganji':'本愿寺','Daitokuji':'大德寺','Tenryuji':'天龙寺','Kenninji':'建仁寺','Toji':'东寺','Ryoanji':'龙安寺','Daigoji':'醍醐寺','Sanjusangendo':'三十三间堂','Inari':'稻荷','Hachimangu':'八幡宫','Hachiman':'八幡','Kamigamo':'上贺茂','Shimogamo':'下鸭','Chionin':'知恩院','Nanzenji':'南禅寺','Eikando':'永观堂','Shorenin':'青莲院','Yasaka':'八坂','Maruyama':'圆山','Rokkaku':'六角','Honnoji':'本能寺','Kumano':'熊野','Nachi':'那智','Shingu':'新宫','Tanabe':'田边','Wakayama':'和歌山','Kobe':'神户','Hyogo':'兵库','Akashi':'明石','Uchinakao':'内中尾','Kannonji':'观音寺','Komyoji':'光明寺','Hasedera':'长谷寺','Miidera':'三井寺','Mii-dera':'三井寺','Katsuragi':'葛城','Awaji':'淡路','Harima':'播磨','Iga':'伊贺','Izumi':'和泉','Settsu':'摄津','Kii':'纪伊','Omi':'近江','Tamba':'丹波','Wakasa':'若狭','Yamashiro':'山城','Yamato':'大和'
  }));
  const common = new Map(Object.entries({
    'Castle':'城堡','Fort':'要塞','Temple':'寺庙','Shrine':'神社','Palace':'御所','Viewpoint':'观景点','Landmark':'地标','Kakurega':'隐之家','Chest':'宝箱','Music':'乐曲','Glyph':'符文','Quest':'任务','Target':'目标','Kata':'型练习','Kofun':'古坟','Rift':'裂隙','Keys':'钥匙','Key':'钥匙','Stockpile':'物资储备','Miscellaneous':'其他','Village':'村落','Town':'城镇','Settlement':'聚落','Mount':'山','Mountain':'山','River':'河','Lake':'湖','Forest':'森林','Woods':'林地','Pass':'山口','Valley':'山谷','Plain':'平原','Plains':'平原','Coast':'海岸','Beach':'海滩','Island':'岛','Ruins':'遗迹','Camp':'营地','Estate':'宅邸','Manor':'庄园','Residence':'宅邸','House':'住宅','District':'区域','Market':'市集','Dojo':'道场','Pagoda':'佛塔','Cemetery':'墓地','Bridge':'桥','Port':'港口','Harbor':'港口','Cave':'洞穴','Mine':'矿洞','Warehouse':'仓库','Outpost':'前哨','Hideout':'据点','Battlefield':'战场','Garden':'庭园','Waterfall':'瀑布','Orchard':'果园','Farm':'农场','Road':'道路','Path':'小径','Gate':'门','Tower':'塔','Spring':'泉','Falls':'瀑布','Upper':'上部','Lower':'下部','North':'北部','South':'南部','East':'东部','West':'西部','Old':'旧','New':'新','Great':'大','Little':'小','Main':'主','Secret':'秘密','Hidden':'隐秘','The':'','of':'之','at':'·','near':'附近','and':'与','to':'至'
  }));
  const syllables={kya:'佳',kyu:'久',kyo:'京',sha:'社',shu:'修',sho:'昭',cha:'茶',chu:'中',cho:'町',nya:'娘',nyu:'纽',nyo:'鸟',hya:'早',hyu:'休',hyo:'兵',mya:'宫',myu:'缪',myo:'明',rya:'良',ryu:'龙',ryo:'辽',gya:'贺',gyu:'牛',gyo:'行',ja:'加',ju:'寿',jo:'城',bya:'白',byu:'武',byo:'庙',pya:'平',pyu:'普',pyo:'表',shi:'志',chi:'千',tsu:'津',fu:'富',ka:'加',ki:'木',ku:'久',ke:'庆',ko:'古',sa:'佐',su:'须',se:'濑',so:'曾',ta:'多',te:'手',to:'户',na:'奈',ni:'仁',nu:'努',ne:'根',no:'野',ha:'羽',hi:'日',he:'部',ho:'保',ma:'间',mi:'美',mu:'武',me:'目',mo:'茂',ya:'矢',yu:'由',yo:'与',ra:'良',ri:'里',ru:'留',re:'礼',ro:'路',wa:'和',wo:'尾',ga:'贺',gi:'义',gu:'具',ge:'下',go:'五',za:'座',ji:'治',zu:'津',ze:'濑',zo:'藏',da:'田',de:'出',do:'土',ba:'场',bi:'比',bu:'部',be:'部',bo:'保',pa:'波',pi:'比',pu:'普',pe:'部',po:'保',a:'阿',i:'伊',u:'宇',e:'江',o:'尾',n:'恩'};
  const syllableKeys=Object.keys(syllables).sort((a,b)=>b.length-a.length);
  const suffixes=[['taisha','大社'],['hachimangu','八幡宫'],['jinja','神社'],['dera','寺'],['machi','町'],['shima','岛'],['jima','岛'],['kawa','川'],['gawa','川'],['yama','山'],['mura','村'],['zaki','崎'],['saki','崎'],['tani','谷'],['dani','谷'],['hara','原'],['bara','原'],['mori','森'],['hama','滨'],['zaka','坂'],['saka','坂'],['oka','冈'],['ike','池'],['numa','沼'],['ji','寺'],['jo','城']];

  function phonetic(word){
    let source=String(word||'').toLowerCase().replace(/[^a-z]/g,'');if(!source)return word;let suffix='';
    for(const [ending,zh] of suffixes){if(source.length>ending.length+1&&source.endsWith(ending)){source=source.slice(0,-ending.length);suffix=zh;break}}
    let out='';while(source){if(source.length>1&&source[0]===source[1]&&/[bcdfghjklmpqrstvwxyz]/.test(source[0])){source=source.slice(1);continue}const key=syllableKeys.find(k=>source.startsWith(k));if(key){out+=syllables[key];source=source.slice(key.length)}else source=source.slice(1)}return(out||'地点')+suffix;
  }
  const phraseList=[...phrases.entries(),...places.entries()].sort((a,b)=>b[0].length-a[0].length);
  function escapeRegExp(value){return value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}
  function translateTitle(original){
    const raw=String(original||'').trim();if(!raw)return'未命名地点';if(exactTitles.has(raw))return exactTitles.get(raw);if(/[\u3400-\u9fff]/.test(raw)&&!/[A-Za-z]/.test(raw))return raw;
    let text=raw.replace(/[–—]/g,' - ').replace(/&/g,' 与 ');for(const[en,zh]of phraseList)text=text.replace(new RegExp(`\\b${escapeRegExp(en)}\\b`,'gi'),zh);
    text=text.replace(/[A-Za-z][A-Za-z'’-]*/g,word=>{const hit=[...common.entries()].find(([en])=>en.toLowerCase()===word.toLowerCase());return hit?hit[1]:phonetic(word)});
    text=text.replace(/\s*-\s*/g,'·').replace(/\s*:\s*/g,'：').replace(/\(/g,'（').replace(/\)/g,'）').replace(/\s+/g,' ').replace(/\s*·\s*/g,'·').trim();
    return text.replace(/寺寺庙/g,'寺').replace(/城城堡/g,'城').replace(/山山/g,'山').replace(/神社神社/g,'神社')||'未命名地点';
  }
  const cache=new Map();
  function localize(item){if(!item||typeof item!=='object')return item;const original=String(item.title_en||item.title||'');if(!cache.has(original))cache.set(original,translateTitle(original));item.title_en=original;item.title_zh=cache.get(original);item.title=item.title_zh;return item}

  window.AtlasLocationNames={translate:translateTitle,localize};
  window.AtlasDataTransforms=window.AtlasDataTransforms||[];
  if(!window.AtlasDataTransforms.includes(localize))window.AtlasDataTransforms.push(localize);
})();
