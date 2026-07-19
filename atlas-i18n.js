(function(){'use strict';
const categories={
'Castle':'城堡','Fort':'要塞','Hostile Landmark':'敌对地标','Kakurega':'隐之家','Landmark':'地标','Sub-Region':'子区域','Viewpoint':'观景点','Gear Vendor':'装备商人','Ornament Vendor':'饰品商人','Port Trader':'港口商人','Cultural Discovery':'文化探索','Glyph':'符文','Jizo Statue':'地藏像','Kamon Crest':'家纹','Kano Painting':'狩野派画作','Legendary Chest':'传奇宝箱','Legendary Sumi-e':'传奇水墨画','Local Dish':'地方料理','Music':'乐曲','Origami Butterfly':'折纸蝴蝶','Sumi-e':'水墨画','Tea Bowl':'茶碗','Valuable Object':'贵重物品','Weapon Part':'武器部件','Quest':'任务','Target':'目标','Hidden Trail':'隐秘小径','Horse Archery':'骑射','Kata':'型练习','Kofun':'古坟','Kuji-kiri':'九字切','Rift':'裂隙','Shrine':'神社','Temple':'寺庙','Alarm Bell':'警钟','Chest':'宝箱','Easter Egg':'彩蛋','Keys':'钥匙','Kura Key':'仓库钥匙','Lost Page':'遗失书页','Miscellaneous':'其他','Samurai Daisho':'武士大将','Small Shrine':'小型神社','Stockpile':'物资储备'
};
const regions={'AWAJI':'淡路','HARIMA':'播磨','IGA':'伊贺','IZUMI SETTSU':'和泉·摄津','KII':'纪伊','OMI':'近江','TAMBA':'丹波','WAKASA':'若狭','YAMASHIRO':'山城','YAMATO':'大和'};
const reverse={};Object.entries(categories).forEach(([en,zh])=>{reverse[zh]=en});Object.entries(regions).forEach(([en,zh])=>{reverse[zh]=en});
window.AtlasI18n={category:name=>categories[name]||name,region:name=>regions[String(name||'').toUpperCase()]||name,english:name=>reverse[name]||name,categories,regions};
if(window.AtlasIcons){const nativeType=AtlasIcons.type.bind(AtlasIcons);AtlasIcons.type=name=>nativeType(reverse[name]||name)}
function localizeMetadata(item,path){
  if(!item||typeof item!=='object')return item;
  if(path==='data/categories.json'){
    const original=String(item.title_en||item.title||'');
    item.title_en=original;
    item.title=categories[original]||item.title;
  }else if(path==='data/regions.json'){
    const original=String(item.title_en||item.title||'');
    item.title_en=original;
    item.title=regions[original.toUpperCase()]||item.title;
  }
  return item;
}
localizeMetadata.atlasPaths=['data/categories.json','data/regions.json'];
window.AtlasDataTransforms=window.AtlasDataTransforms||[];
if(!window.AtlasDataTransforms.includes(localizeMetadata))window.AtlasDataTransforms.push(localizeMetadata);
function translateSearch(value){let out=value;for(const [en,zh] of [...Object.entries(categories),...Object.entries(regions)]){out=out.replace(new RegExp(en.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'ig'),zh)}return out}
document.addEventListener('DOMContentLoaded',()=>{const input=document.getElementById('searchInput');if(!input)return;input.addEventListener('input',e=>{const translated=translateSearch(e.target.value);if(translated!==e.target.value)e.target.value=translated},true)});
})();
