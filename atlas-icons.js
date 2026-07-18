(() => {
  'use strict';
  const NS='http://www.w3.org/2000/svg';
  const COLORS={location:'#b52a35',collectible:'#b28b45',activity:'#7853a6',service:'#397a72',enemy:'#8d2630',other:'#6f6862'};

  const exact=new Map(Object.entries({
    'castle':'castle','城堡':'castle',
    'fort':'fort','要塞':'fort',
    'hostile landmark':'hostile_landmark','敌对地标':'hostile_landmark',
    'kakurega':'hideout','隐之家':'hideout',
    'landmark':'landmark','地标':'landmark',
    'sub-region':'subregion','sub region':'subregion','子区域':'subregion',
    'viewpoint':'viewpoint','观景点':'viewpoint',
    'gear vendor':'gear_vendor','装备商人':'gear_vendor',
    'ornament vendor':'ornament_vendor','饰品商人':'ornament_vendor',
    'port trader':'port_trader','港口商人':'port_trader',
    'cultural discovery':'cultural','文化探索':'cultural',
    'glyph':'glyph','符文':'glyph',
    'jizo statue':'jizo','地藏像':'jizo',
    'kamon crest':'kamon','家纹':'kamon',
    'kano painting':'painting','狩野派画作':'painting',
    'legendary chest':'legendary','传奇宝箱':'legendary',
    'legendary sumi-e':'legendary_sumi','legendary sumi e':'legendary_sumi','传奇水墨画':'legendary_sumi',
    'local dish':'local_dish','地方料理':'local_dish',
    'music':'music','乐曲':'music',
    'origami butterfly':'origami','折纸蝴蝶':'origami',
    'sumi-e':'sumi_e','sumi e':'sumi_e','水墨画':'sumi_e',
    'tea bowl':'tea_bowl','茶碗':'tea_bowl',
    'valuable object':'valuable','贵重物品':'valuable',
    'weapon part':'weapon_part','武器部件':'weapon_part',
    'quest':'quest','任务':'quest',
    'target':'target','目标':'target',
    'hidden trail':'hidden_trail','隐秘小径':'hidden_trail',
    'horse archery':'horse_archery','骑射':'horse_archery',
    'kata':'kata','型练习':'kata',
    'kofun':'tomb','古坟':'tomb',
    'kuji-kiri':'kuji','kuji kiri':'kuji','九字切':'kuji',
    'rift':'rift','裂隙':'rift',
    'shrine':'shrine','神社':'shrine',
    'temple':'temple','寺庙':'temple',
    'alarm bell':'alarm','警钟':'alarm',
    'chest':'chest','宝箱':'chest',
    'easter egg':'easter_egg','彩蛋':'easter_egg',
    'keys':'key','钥匙':'key',
    'kura key':'kura_key','仓库钥匙':'kura_key',
    'lost page':'scroll','遗失书页':'scroll',
    'miscellaneous':'misc','其他':'misc',
    'samurai daisho':'samurai','武士大将':'samurai',
    'small shrine':'small_shrine','小型神社':'small_shrine',
    'stockpile':'stockpile','物资储备':'stockpile'
  }));

  const fallbackRules=[
    [/legendary.*chest|传奇.*宝箱|legendary gear/,'legendary'],
    [/castle|城堡/,'castle'],[/fort|要塞|stronghold/,'fort'],
    [/shrine|神社/,'shrine'],[/temple|寺庙/,'temple'],
    [/viewpoint|观景点|synchron/,'viewpoint'],[/hideout|隐之家|base/,'hideout'],
    [/village|town|settlement|村|镇/,'village'],[/kofun|古坟|tomb|grave|burial/,'tomb'],
    [/chest|宝箱|treasure/,'chest'],[/scroll|page|document|letter|书页/,'scroll'],
    [/key|钥匙/,'key'],[/gear|weapon|katana|tanto|bow|armor|装备|武器/,'gear_vendor'],
    [/merchant|vendor|shop|商人/,'merchant'],[/stable|horse|马/,'horse_archery'],
    [/boss|target|elite|enemy|目标|敌人/,'target'],[/quest|contract|mission|objective|任务/,'quest'],
    [/collect|flower|artifact|trinket|ornament|收集|贵重/,'valuable']
  ];

  function normalize(title=''){return String(title).trim().toLowerCase().replace(/[·_]/g,' ').replace(/\s+/g,' ')}
  function type(title=''){
    const t=normalize(title);
    if(exact.has(t))return exact.get(t);
    for(const [r,n] of fallbackRules)if(r.test(t))return n;
    return 'pin';
  }

  const GROUPS={
    location:new Set(['castle','fort','hostile_landmark','hideout','landmark','subregion','viewpoint','village']),
    collectible:new Set(['chest','legendary','cultural','glyph','jizo','kamon','painting','legendary_sumi','local_dish','music','origami','sumi_e','tea_bowl','valuable','weapon_part','scroll','key','kura_key','easter_egg','stockpile']),
    activity:new Set(['quest','hidden_trail','horse_archery','kata','tomb','kuji','rift','shrine','temple','small_shrine']),
    service:new Set(['gear_vendor','ornament_vendor','port_trader','merchant']),
    enemy:new Set(['target','samurai','alarm']),
    other:new Set(['misc','pin'])
  };
  function group(icon){for(const [name,set] of Object.entries(GROUPS))if(set.has(icon))return name;return'other'}
  function color(icon){return COLORS[group(icon)]||COLORS.other}

  const paths={
    pin:'<path d="M12 21s6-5.1 6-11a6 6 0 1 0-12 0c0 5.9 6 11 6 11Z"/><circle cx="12" cy="10" r="2.2"/>',
    castle:'<path d="M4 21V9h3V5h3v4h4V5h3v4h3v12Z"/><path d="M8 21v-5h8v5M3 9h18M10 13h4"/>',
    fort:'<path d="M4 21V8h3V5h3v3h4V5h3v3h3v13Z"/><path d="M3 12h18M8 21v-5h8v5M7 8h10"/><path d="M2 5h4M18 5h4"/>',
    hostile_landmark:'<path d="m12 3 8 4v6c0 4.5-3.2 7-8 8-4.8-1-8-3.5-8-8V7Z"/><path d="m8 9 8 8M16 9l-8 8"/>',
    hideout:'<path d="m3 11 9-8 9 8M5 10v11h14V10M9 21v-6h6v6"/><path d="m8 10 4 3 4-3"/>',
    landmark:'<path d="M12 3v18M6 8h12M8 5h8M7 21h10"/><path d="M9 8v8m6-8v8M6 16h12"/>',
    subregion:'<path d="M4 6h6l2 3h8v9H4Z"/><path d="M7 11h10M7 14h7"/>',
    viewpoint:'<path d="M3 13c3-1 5-3 7-6l2 3 2-3c2 3 4 5 7 6-4 0-6 1-9 4-3-3-5-4-9-4Z"/><path d="M12 10v10M9 20h6"/>',
    village:'<path d="m2 12 5-5 5 5v9H3v-9m9-2 4-4 6 6v9h-10"/><path d="M6 21v-5h3v5m7 0v-5h3v5"/>',
    shrine:'<path d="M4 6h16M6 6l1-3m10 3-1-3M7 8v13m10-13v13M4 11h16M9 11v10m6-10v10"/><path d="M3 8h18"/>',
    small_shrine:'<path d="M6 8h12M8 8l1-3m6 3-1-3M9 10v10m6-10v10M7 12h10M7 20h10"/>',
    temple:'<path d="m3 9 9-6 9 6M5 10h14M6 10v9m4-9v9m4-9v9m4-9v9M4 20h16"/>',
    tomb:'<path d="M7 21V9a5 5 0 0 1 10 0v12M5 21h14M9 12h6M12 9v6"/>',
    chest:'<path d="M3 9h18v11H3Z"/><path d="M4 9V6h16v3M3 13h18M10 13v3h4v-3"/>',
    legendary:'<path d="M3 10h18v10H3Z"/><path d="M4 10V7h16v3M3 14h18"/><path d="m12 3 1.1 2.2L16 6l-2.1 1.8.6 2.7-2.5-1.3-2.5 1.3.6-2.7L8 6l2.9-.8Z"/>',
    cultural:'<path d="M5 20h14M7 20v-8h10v8M6 12l6-8 6 8"/><path d="M10 15h4M12 12v6"/>',
    glyph:'<path d="M12 3c-4 0-7 3-7 7s3 7 7 7c3 0 5-2 5-5 0-2-1-3-3-3-1.7 0-3 1.3-3 3 0 1.3.7 2.3 2 3"/><path d="M12 17v4"/>',
    jizo:'<circle cx="12" cy="7" r="3"/><path d="M7 21c0-6 1.8-10 5-10s5 4 5 10M8 17h8M10 4h4"/>',
    kamon:'<circle cx="12" cy="12" r="8"/><path d="m12 5 2 4 4 .5-3 3 1 4.5-4-2-4 2 1-4.5-3-3 4-.5Z"/>',
    painting:'<rect x="4" y="4" width="16" height="16" rx="1"/><path d="m7 16 4-5 3 3 3-4 2 6M8 8h.01"/>',
    legendary_sumi:'<path d="M5 19c4-1 7-5 9-11 1 5 3 8 5 10"/><path d="M7 16c2 1 4 1 6 0M12 4l1-2 1 2 2 .5-1.5 1.4.5 2.1-2-1-2 1 .5-2.1L10 4.5Z"/>',
    local_dish:'<path d="M4 13h16a8 8 0 0 1-16 0Z"/><path d="M7 10c0-2 2-2 2-4m3 4c0-2 2-2 2-4m3 4c0-2 2-2 2-4M3 13h18"/>',
    music:'<path d="M9 18V6l10-2v12"/><circle cx="6" cy="18" r="3"/><circle cx="16" cy="16" r="3"/><path d="M9 9l10-2"/>',
    origami:'<path d="M3 12 10 4l2 6 2-6 7 8-6 1 3 7-6-4-6 4 3-7Z"/><path d="m10 4 2 12 2-12M6 20l6-4 6 4"/>',
    sumi_e:'<path d="M5 19c4-1 7-5 9-11 1 5 3 8 5 10"/><path d="M7 16c2 1 4 1 6 0M14 8c2 1 3 0 4-2"/>',
    tea_bowl:'<path d="M5 11h14c0 6-2 9-7 9s-7-3-7-9Z"/><path d="M8 20h8M8 8c0-2 2-2 2-4m4 4c0-2 2-2 2-4"/>',
    valuable:'<path d="m12 3 7 6-7 12L5 9Z"/><path d="m5 9 7 4 7-4M9 5l3 8 3-8"/>',
    weapon_part:'<path d="m4 20 5-5M7 17l3 3M10 14l7-10 3 3-10 7Z"/><path d="m14 7 3 3M4 8l4-4 3 3-4 4Z"/>',
    scroll:'<path d="M6 4h11a2 2 0 0 1 0 4H8v12a2 2 0 0 1-4 0V6a2 2 0 0 1 2-2Z"/><path d="M8 8h10v11a2 2 0 0 1-2 2H6M11 12h4m-4 4h4"/>',
    key:'<circle cx="8" cy="11" r="4"/><path d="m11 14 8 7m-4-4 2-2m0 4 2-2"/>',
    kura_key:'<path d="M4 9h10v11H4Z"/><path d="M6 9V6h6v3M14 14h6m-2-2v4M7 13h4"/>',
    gear_vendor:'<path d="m5 19 11-11 3 3L8 22H5v-3Z"/><path d="m13 7 2-2 4 4-2 2M4 5l6 6M4 5h4M4 5v4"/>',
    ornament_vendor:'<path d="M12 3 9 8l3 3 3-3Z"/><path d="M7 10c0 6 2 10 5 11 3-1 5-5 5-11M7 10l5 4 5-4"/>',
    port_trader:'<path d="M3 17c3 2 5 2 9 0 4 2 6 2 9 0M5 14h14l-2-7H7Z"/><path d="M12 3v11M8 7h8"/>',
    merchant:'<circle cx="12" cy="7" r="3"/><path d="M5 21v-3a7 7 0 0 1 14 0v3M8 13l4 4 4-4"/><path d="M4 9h16"/>',
    target:'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><path d="M12 2v4m0 12v4M2 12h4m12 0h4"/>',
    samurai:'<path d="M6 10V7l3 2 3-5 3 5 3-2v3"/><path d="M6 10h12v5a6 6 0 0 1-12 0Z"/><path d="M9 14h.01M15 14h.01m-6 5 3-2 3 2"/>',
    quest:'<path d="M6 3h12v18H6Z"/><path d="M9 7h6M9 11h6M9 15h3"/><path d="m15 16 2 2 4-5"/>',
    hidden_trail:'<path d="M4 20c1-5 4-7 8-7s6-3 8-9"/><path d="M5 7h5l-2-3m7 13h5l-2 3"/><circle cx="12" cy="13" r="1"/>',
    horse_archery:'<path d="M4 16c2-5 6-7 11-5l4 3-3 4H9l-3 3"/><path d="M7 11 5 7l3-2 3 3M14 6c3 2 4 5 4 8M15 6l4-2"/>',
    kata:'<path d="M7 5h10M12 5v5M8 10l4 2 4-2M6 21l4-7m8 7-4-7"/><circle cx="12" cy="4" r="2"/>',
    kuji:'<path d="M5 4v16M9 4v16M15 4v16M19 4v16M3 7h18M3 12h18M3 17h18"/>',
    rift:'<path d="m13 2-4 8 4 2-4 10M17 3l-2 6 3 2-3 10M7 4l-2 5 3 3-2 8"/>',
    alarm:'<path d="M7 17h10M9 17V9a3 3 0 0 1 6 0v8M6 20h12M12 3v2M5 6l2 2m12-2-2 2"/>',
    easter_egg:'<path d="M12 3c4 0 7 6 7 11a7 7 0 0 1-14 0c0-5 3-11 7-11Z"/><path d="m7 10 3 2 3-2 4 2M6 15l3-2 3 2 3-2 3 2"/>',
    stockpile:'<path d="M4 9h16v11H4Z"/><path d="M3 9l3-5h12l3 5M8 13h8M8 17h8M12 9v11"/>',
    misc:'<circle cx="6" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="18" cy="12" r="1.5"/>',
    favorite:'<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8l1.1 1.1L12 21l7.8-7.5 1.1-1.1a5.5 5.5 0 0 0-.1-7.8Z"/>',
    discovered:'<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    route:'<circle cx="5" cy="18" r="2"/><circle cx="19" cy="6" r="2"/><path d="M7 18c7 0 3-12 10-12"/>'
  };

  function svg(icon,size=24,cls='atlas-svg'){
    const p=paths[icon]||paths.pin;
    return `<svg class="${cls}" viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
  }
  const cache=new Map();
  function image(icon){
    if(cache.has(icon))return cache.get(icon);
    const img=new Image();
    img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(`<svg xmlns="${NS}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${paths[icon]||paths.pin}</svg>`);
    cache.set(icon,img);
    return img;
  }
  function draw(ctx,icon,x,y,size,opts={}){
    const img=image(icon);
    if(!img.complete)return false;
    ctx.save();
    ctx.globalAlpha=opts.alpha??1;
    ctx.drawImage(img,x-size/2,y-size/2,size,size);
    ctx.restore();
    return true;
  }
  window.AtlasIcons={type,group,color,svg,draw,paths,colors:COLORS};
})();