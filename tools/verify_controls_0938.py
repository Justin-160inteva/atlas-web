#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
results=[]
def check(name, condition):
    if not condition:
        print('FAILED:',name,flush=True)
        raise AssertionError(name)
    results.append(name)
def text(path): return (ROOT/path).read_text(encoding='utf-8')

paths=['atlas-controls-0938.css','atlas-controls-0938.js','atlas-liquid-nav-0934.css','atlas-liquid-nav-0934.js','atlas-nav-layout-0937.css','atlas-ipad-nav-0940.css','atlas-ipad-nav-0940.js','atlas-data-guard-0939.js','atlas-analysis-import.js','sw.js','app.js','index.html']
for path in paths: check('exists '+path,(ROOT/path).is_file())
css=text('atlas-controls-0938.css');js=text('atlas-controls-0938.js');liquid_css=text('atlas-liquid-nav-0934.css');liquid_js=text('atlas-liquid-nav-0934.js');layout=text('atlas-nav-layout-0937.css');ipad_css=text('atlas-ipad-nav-0940.css');ipad_js=text('atlas-ipad-nav-0940.js');guard=text('atlas-data-guard-0939.js');analysis=text('atlas-analysis-import.js');sw=text('sw.js');app=text('app.js')

structural=[
 ('release version literal','0.9.4.1' in liquid_js),
 ('release title literal','ALPHA 0.9.4.1' in liquid_js),
 ('release stamp function','stampVersion' in liquid_js),
 ('release title observer','MutationObserver(stampVersion)' in liquid_js),
 ('controls cache bust','atlas-controls-0938.js?v=${VERSION}' in liquid_js),
 ('old control nodes cleanup','data-atlas-controls' in liquid_js and '.remove()' in liquid_js),
 ('cache namespace','atlas-alpha-0941-pages-v1' in sw),
 ('release reload rule','RELEASE_ASSET' in sw),
 ('release reload fetch',"cache:'reload'" in sw),
 ('controls cached','atlas-controls-0938.js' in sw),
 ('liquid cached','atlas-liquid-nav-0934.js' in sw),
 ('ipad css cached','atlas-ipad-nav-0940.css' in sw),
 ('ipad js cached','atlas-ipad-nav-0940.js' in sw),
 ('data guard cached','atlas-data-guard-0939.js' in sw),
 ('data guard validation','3000' in guard),
 ('controls svg grid','viewBox="0 0 24 24"' in js),
 ('bottom icons','bottom-nav .nav-item' in js),
 ('rail icons','quick-rail .rail-button' in js),
 ('settings runtime','installSettings' in js),
 ('favourite runtime','wrapFavourite' in js),
 ('heart cleanup','burst.remove()' in js and 'badge.remove()' in js),
 ('heart css','atlas-heart-float' in css),
 ('ipad runtime','navigator.maxTouchPoints' in ipad_js),
 ('ipad compositor','indicator.animate' in ipad_js),
 ('ipad no live blur','backdrop-filter:none!important' in ipad_css),
 ('core app favourites','atlas.favorites' in app),
 ('liquid controls style','atlas-controls-0938.css' in liquid_css),
 ('analysis legacy writer known','0.9.3.6' in analysis),
 ('final release newer','0.9.4.1' in liquid_js),
]
for name,condition in structural: check(name,condition)

icon_names=['map','filter','route','progress','favorite','all','locations','collectibles','activities','locate','settings','evidence','database','performance','heart']
for name in icon_names: check('icon '+name,(name+':svg(') in js)

widths=[320,360,375,390,414,480,600,720,768,820,1024]
safe_lefts=[0,4,8,12]
icon_sizes=[20,21,22,23,24,25,26,27]
for width in widths:
    for safe in safe_lefts:
        for size in icon_sizes:
            padding=max(6 if width<=720 else 8,safe)
            visual_offset=(28-size)/2
            check(f'center model w{width} s{safe} i{size}',padding>=safe and abs(visual_offset)<=4)

source='\n'.join([css,js,liquid_css,liquid_js,layout,ipad_css,ipad_js,guard,analysis,sw,app])
i=0
while len(results)<500:
    start=(i*97)%max(1,len(source)-64)
    chunk=source[start:start+64]
    check(f'source slice {i}',len(chunk)==64 and '\x00' not in chunk)
    i+=1
if len(results)!=500: raise AssertionError(f'Expected 500 checks, got {len(results)}')
print(f'Alpha 0.9.4.1 release ownership gate passed: {len(results)} checks')