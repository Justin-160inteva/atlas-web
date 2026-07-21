import { chromium } from 'playwright';

const baseURL=process.env.ATLAS_URL||'http://127.0.0.1:4173/';
const ipadUA='Mozilla/5.0 (iPad; CPU OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1';
const iphoneUA='Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1';
const profiles=[
  {name:'desktop',viewport:{width:1440,height:900},isMobile:false,hasTouch:false},
  {name:'ipad-landscape',viewport:{width:1180,height:820},isMobile:true,hasTouch:true,userAgent:ipadUA},
  {name:'mobile',viewport:{width:390,height:844},isMobile:true,hasTouch:true,userAgent:iphoneUA}
];

const browser=await chromium.launch({headless:true});
const reports=[];
let failed=false;

for(const profile of profiles){
  const context=await browser.newContext({
    viewport:profile.viewport,
    isMobile:profile.isMobile,
    hasTouch:profile.hasTouch,
    userAgent:profile.userAgent,
    deviceScaleFactor:profile.hasTouch?2:1,
    serviceWorkers:'block'
  });
  const page=await context.newPage();
  const checks=[];
  const errors=[];
  const check=(name,value,detail='')=>{const passed=Boolean(value);checks.push({name,passed,detail});if(!passed)failed=true};
  page.on('pageerror',error=>errors.push(`pageerror: ${error.message}`));
  page.on('console',message=>{if(message.type()==='error')errors.push(`console: ${message.text()}`)});

  try{
    await page.goto(`${baseURL}?control-icons=09412b2-${profile.name}`,{waitUntil:'domcontentloaded',timeout:45_000});
    await page.waitForFunction(()=>Number(document.getElementById('visibleCount')?.textContent||0)>=3000,null,{timeout:45_000});
    await page.waitForFunction(()=>window.AtlasControlIcons?.designVersion==='0.9.4.12b-2',null,{timeout:20_000});
    await page.waitForTimeout(300);

    const state=await page.evaluate(()=>{
      const inspect=selector=>[...document.querySelectorAll(selector)].map(host=>{
        const direct=[...host.children].filter(node=>node.matches?.('svg.atlas-control-icon'));
        const text=[...host.childNodes].filter(node=>node.nodeType===Node.TEXT_NODE&&node.textContent.trim()).map(node=>node.textContent.trim());
        const svg=direct[0];
        const style=svg?getComputedStyle(svg):null;
        return {key:host.dataset.atlasIconKey||'',svgCount:direct.length,text,width:Number.parseFloat(style?.width||'0'),height:Number.parseFloat(style?.height||'0'),stroke:Number.parseFloat(style?.strokeWidth||'0'),classes:svg?.getAttribute('class')||''};
      });
      const settings=document.getElementById('evidenceStudioBtn');
      const settingsSvg=settings?.querySelector(':scope > svg.atlas-control-icon');
      return {
        audit:window.AtlasControlIcons.audit(),
        rootDesign:document.documentElement.dataset.atlasControlIconDesign,
        groups:{
          bottom:inspect('.bottom-nav .nav-item > span'),
          rail:inspect('.quick-rail .rail-icon'),
          map:inspect('.map-controls > button'),
          top:inspect('#locateBtn,#evidenceStudioBtn'),
          search:inspect('#searchTrigger > .icon,#searchOverlay .search-input-row > span:first-child')
        },
        settings:{circles:settingsSvg?.querySelectorAll('circle').length||0,paths:settingsSvg?.querySelectorAll('path').length||0,newClass:settingsSvg?.classList.contains('atlas-settings-icon-09412b2')||false},
        styleLoaded:Boolean(document.querySelector('link[data-atlas-control-icons="0.9.4.12b-2"]'))
      };
    });

    check('runtime audit valid',state.audit.valid,JSON.stringify(state.audit));
    check('runtime audit counts seventeen',state.audit.total===17,JSON.stringify(state.audit));
    check('design dataset current',state.rootDesign==='0.9.4.12b-2',state.rootDesign);
    check('control stylesheet loaded',state.styleLoaded);
    check('settings uses one circle',state.settings.circles===1,JSON.stringify(state.settings));
    check('settings uses one path',state.settings.paths===1,JSON.stringify(state.settings));
    check('settings uses precision class',state.settings.newClass,JSON.stringify(state.settings));

    for(const [group,entries] of Object.entries(state.groups)){
      const expected={bottom:5,rail:5,map:3,top:2,search:2}[group];
      check(`${group} count`,entries.length===expected,JSON.stringify(entries));
      entries.forEach((entry,index)=>{
        check(`${group} ${index+1} has one svg`,entry.svgCount===1,JSON.stringify(entry));
        check(`${group} ${index+1} has no text`,entry.text.length===0,JSON.stringify(entry));
        check(`${group} ${index+1} has icon key`,Boolean(entry.key),JSON.stringify(entry));
        check(`${group} ${index+1} visible size`,entry.width>=18&&entry.height>=18,JSON.stringify(entry));
        check(`${group} ${index+1} consistent stroke`,entry.stroke>=1.55&&entry.stroke<=1.75,JSON.stringify(entry));
      });
    }

    await page.locator('.bottom-nav .nav-item[data-panel="route"]').click({timeout:5000});
    await page.waitForTimeout(100);
    check('route icon remains single',await page.locator('.bottom-nav .nav-item[data-panel="route"] > span > svg.atlas-control-icon-route').count()===1);
    await page.locator('.bottom-nav .nav-item[data-panel="map"]').click({timeout:5000});
    await page.locator('.quick-rail .rail-button[data-mode="collectibles"]').click({timeout:5000});
    check('rail collectible icon remains single',await page.locator('.quick-rail .rail-button[data-mode="collectibles"] .atlas-control-icon-collectibles').count()===1);

    const beforeZoom=await page.locator('#zoomLabel').textContent();
    await page.locator('#zoomIn').click({timeout:5000});
    await page.waitForTimeout(360);
    const afterZoom=await page.locator('#zoomLabel').textContent();
    check('zoom control still works',beforeZoom!==afterZoom,`${beforeZoom} -> ${afterZoom}`);
    await page.locator('#resetView').click({timeout:5000});

    await page.locator('#searchTrigger').click({timeout:5000});
    check('search opens with svg icon',await page.locator('#searchOverlay.open .search-input-row > span > svg.atlas-control-icon-search').count()===1);
    await page.locator('#closeSearch').click({timeout:5000});

    await page.locator('#evidenceStudioBtn').click({timeout:5000});
    await page.waitForTimeout(120);
    check('settings opens',await page.locator('.settings-panel.open,.atlas-settings-overlay.open').count()===1);
    const close=page.locator('.settings-close,.atlas-settings-close').first();
    if(await close.count())await close.click({timeout:5000});

    const finalAudit=await page.evaluate(()=>window.AtlasControlIcons.audit());
    check('icons remain valid after interactions',finalAudit.valid,JSON.stringify(finalAudit));
    check('no runtime errors',errors.length===0,errors.join('\n'));
  }catch(error){
    failed=true;
    errors.push(String(error?.stack||error));
  }

  reports.push({profile:profile.name,checks,errors});
  await context.close();
}

await browser.close();
for(const report of reports){
  const passed=report.checks.filter(item=>item.passed).length;
  console.log(`${report.profile}: ${passed}/${report.checks.length}; errors=${report.errors.length}`);
}
console.log(JSON.stringify({schemaVersion:1,version:'0.9.4.12b-2',passed:!failed,profiles:reports},null,2));
if(failed)process.exit(1);
