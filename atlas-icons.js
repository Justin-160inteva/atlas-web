(() => {
  'use strict';
  const NS='http://www.w3.org/2000/svg';
  const COLORS={location:'#b52a35',collectible:'#b28b45',activity:'#7853a6',service:'#397a72',enemy:'#8d2630',other:'#6f6862'};
  const rules=[
    [/legendary.*chest|chest.*legendary|legendary gear/,'legendary'],[/castle|fort|stronghold/,'castle'],[/shrine/,'shrine'],[/temple/,'temple'],[/viewpoint|synchron/,'viewpoint'],[/hideout|base/,'hideout'],[/village|town|settlement/,'village'],[/kofun|tomb|grave|burial/,'tomb'],[/chest|treasure/,'chest'],[/scroll|page|document|letter/,'scroll'],[/key/,'key'],[/gear|weapon|katana|tanto|bow|armor/,'gear'],[/merchant|vendor|shop/,'merchant'],[/stable|horse/,'stable'],[/boss|target|elite|enemy/,'boss'],[/quest|contract|mission|objective|activity|event/,'quest'],[/collect|flower|artifact|trinket|ornament/,'collectible']
  ];
  function type(title=''){const t=String(title).toLowerCase();for(const [r,n] of rules)if(r.test(t))return n;return 'pin'}
  function group(icon){if(['castle','shrine','temple','viewpoint','hideout','village','tomb'].includes(icon))return'location';if(['chest','legendary','scroll','key','gear','collectible'].includes(icon))return'collectible';if(['quest'].includes(icon))return'activity';if(['merchant','stable'].includes(icon))return'service';if(icon==='boss')return'enemy';return'other'}
  function color(icon){return COLORS[group(icon)]||COLORS.other}
  const paths={
    pin:'<path d="M12 21s6-5.1 6-11a6 6 0 1 0-12 0c0 5.9 6 11 6 11Z"/><circle cx="12" cy="10" r="2.2"/>',
    castle:'<path d="M4 21V9h3V5h3v4h4V5h3v4h3v12Z"/><path d="M8 21v-5h8v5M3 9h18M10 13h4"/>',
    shrine:'<path d="M4 6h16M6 6l1-3m10 3-1-3M7 8v13m10-13v13M4 11h16M9 11v10m6-10v10"/><path d="M3 8h18"/>',
    temple:'<path d="m3 9 9-6 9 6M5 10h14M6 10v9m4-9v9m4-9v9m4-9v9M4 20h16"/>',
    viewpoint:'<path d="M3 13c3-1 5-3 7-6l2 3 2-3c2 3 4 5 7 6-4 0-6 1-9 4-3-3-5-4-9-4Z"/><path d="M12 10v10M9 20h6"/>',
    hideout:'<path d="m3 11 9-8 9 8M5 10v11h14V10M9 21v-6h6v6"/><path d="m8 10 4 3 4-3"/>',
    village:'<path d="m2 12 5-5 5 5v9H3v-9m9-2 4-4 6 6v9h-10"/><path d="M6 21v-5h3v5m7 0v-5h3v5"/>',
    tomb:'<path d="M7 21V9a5 5 0 0 1 10 0v12M5 21h14M9 12h6M12 9v6"/>',
    chest:'<path d="M3 9h18v11H3Z"/><path d="M4 9V6h16v3M3 13h18M10 13v3h4v-3"/>',
    legendary:'<path d="M3 10h18v10H3Z"/><path d="M4 10V7h16v3M3 14h18"/><path d="m12 3 1.1 2.2L16 6l-2.1 1.8.6 2.7-2.5-1.3-2.5 1.3.6-2.7L8 6l2.9-.8Z"/>',
    scroll:'<path d="M6 4h11a2 2 0 0 1 0 4H8v12a2 2 0 0 1-4 0V6a2 2 0 0 1 2-2Z"/><path d="M8 8h10v11a2 2 0 0 1-2 2H6M11 12h4m-4 4h4"/>',
    key:'<circle cx="8" cy="11" r="4"/><path d="m11 14 8 7m-4-4 2-2m0 4 2-2"/>',
    gear:'<path d="m5 19 11-11 3 3L8 22H5v-3Z"/><path d="m13 7 2-2 4 4-2 2M4 5l6 6M4 5h4M4 5v4"/>',
    merchant:'<circle cx="12" cy="7" r="3"/><path d="M5 21v-3a7 7 0 0 1 14 0v3M8 13l4 4 4-4"/><path d="M4 9h16"/>',
    stable:'<path d="M4 21V8l8-5 8 5v13M8 21v-7h8v7"/><path d="M9 10c2-2 5-2 7 0l-1 3H9Z"/>',
    boss:'<path d="M6 10V7l3 2 3-5 3 5 3-2v3"/><path d="M6 10h12v5a6 6 0 0 1-12 0Z"/><circle cx="9" cy="14" r="1"/><circle cx="15" cy="14" r="1"/><path d="m9 19 3-2 3 2"/>',
    quest:'<path d="M6 3h12v18H6Z"/><path d="M9 7h6M9 11h6M9 15h3"/><path d="m15 16 2 2 4-5"/>',
    collectible:'<path d="M12 2c1.2 4 3.5 6.2 7 7-3.5.8-5.8 3-7 7-1.2-4-3.5-6.2-7-7 3.5-.8 5.8-3 7-7Z"/><path d="M5 15c.7 2.3 2 3.7 4 4-2 .3-3.3 1.7-4 4-.7-2.3-2-3.7-4-4 2-.3 3.3-1.7 4-4Z"/>',
    favorite:'<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8l1.1 1.1L12 21l7.8-7.5 1.1-1.1a5.5 5.5 0 0 0-.1-7.8Z"/>',
    discovered:'<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    route:'<circle cx="5" cy="18" r="2"/><circle cx="19" cy="6" r="2"/><path d="M7 18c7 0 3-12 10-12"/>'
  };
  function svg(icon,size=24,cls='atlas-svg'){const p=paths[icon]||paths.pin;return `<svg class="${cls}" viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`}
  const cache=new Map();
  function image(icon){if(cache.has(icon))return cache.get(icon);const img=new Image();img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(`<svg xmlns="${NS}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${paths[icon]||paths.pin}</svg>`);cache.set(icon,img);return img}
  function draw(ctx,icon,x,y,size,opts={}){const img=image(icon);if(!img.complete)return false;ctx.save();ctx.globalAlpha=opts.alpha??1;ctx.drawImage(img,x-size/2,y-size/2,size,size);ctx.restore();return true}
  window.AtlasIcons={type,group,color,svg,draw,paths,colors:COLORS};
})();