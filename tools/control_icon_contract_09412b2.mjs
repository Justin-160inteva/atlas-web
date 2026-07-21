import fs from 'node:fs/promises';

const read=path=>fs.readFile(new URL(`../${path}`,import.meta.url),'utf8');
const [controller,css,liquid,manifestText,worker]=await Promise.all([
  read('atlas-controls-0938.js'),
  read('atlas-controls-0938.css'),
  read('atlas-liquid-nav-0934.js'),
  read('release-manifest.json'),
  read('sw.js')
]);
const manifest=JSON.parse(manifestText);
const checks=[];
const check=(name,condition,detail='')=>checks.push({name,passed:Boolean(condition),detail});

check('design version is 09412b2',/DESIGN_VERSION='0\.9\.4\.12b-2'/.test(controller));
check('release version remains canonical',/window\.AtlasRelease\?\.version/.test(controller));
check('control runtime remains manifest owner',manifest.runtimeOwners.controlIcons==='atlas-controls-0938.js');
check('control script remains release asset',manifest.releaseAssets.includes('atlas-controls-0938.js'));
check('liquid navigation loads control owner once',/atlas-controls-0938\.js/.test(liquid));
check('service worker caches control js',worker.includes("'./atlas-controls-0938.js'"));
check('service worker caches control css',worker.includes("'./atlas-controls-0938.css'"));
check('stylesheet is loaded by controller',/atlas-controls-0938\.css\?v=/.test(controller)&&/data-atlas-control-icons/.test(controller));

for(const key of ['map','filter','route','progress','favorite','all','locations','collectibles','activities','locate','settings','zoomIn','zoomOut','reset','search','close']){
  check(`icon ${key} exists`,new RegExp(`\\b${key}:svg\\(`).test(controller));
}
check('all fixed groups are installed',/bottom-nav[\s\S]*quick-rail[\s\S]*zoomIn[\s\S]*zoomOut[\s\S]*resetView[\s\S]*locateBtn[\s\S]*searchTrigger[\s\S]*evidenceStudioBtn/.test(controller));
check('legacy character controls absent from controller',!/[⌕⌖⚙＋－↺]/u.test(controller));
check('settings glyph is precision gear',/precision-gear-09412b2/.test(controller)&&/atlas-settings-icon-09412b2/.test(controller));
const settingsBody=controller.match(/settings:svg\('settings','([\s\S]*?)'\),/)?.[1]||'';
check('settings glyph has one circle',(settingsBody.match(/<circle\b/g)||[]).length===1);
check('settings glyph has one path',(settingsBody.match(/<path\b/g)||[]).length===1);
check('settings keeps navigation compatibility class',/atlas-settings-icon-09411a atlas-settings-icon-09412b2/.test(controller));
check('repair is frame coalesced',/if\(repairFrame\)return;\s*repairFrame=requestAnimationFrame/s.test(controller));
check('icon install is idempotent',/host\.dataset\.atlasIconKey===key/.test(controller)&&/if\(valid\)return false/.test(controller));
check('runtime audit is exposed',/window\.AtlasControlIcons=Object\.freeze/.test(controller)&&/function audit\(\)/.test(controller));
check('runtime dataset is exposed',/dataset\.atlasControlIconDesign=DESIGN_VERSION/.test(controller));

check('shared stroke width is precise',/stroke-width:1\.65/.test(css));
check('icons use geometric precision',/shape-rendering:geometricPrecision/.test(css));
check('active icon motion is bounded',/scale\(1\.065\)/.test(css));
check('reduced motion fallback exists',/@media\(prefers-reduced-motion:reduce\)/.test(css));
check('no infinite animation added',!/animation[^;]*infinite/.test(css));
check('no filter blur added',!/[^-]filter:\s*blur\(/.test(css));
check('no external image icon dependency',!/(?:url\(|data:image|\.png|\.webp)/.test(controller));

const failed=checks.filter(item=>!item.passed);
console.log(JSON.stringify({schemaVersion:1,version:'0.9.4.12b-2',passed:failed.length===0,totalChecks:checks.length,checks},null,2));
if(failed.length)process.exit(1);
