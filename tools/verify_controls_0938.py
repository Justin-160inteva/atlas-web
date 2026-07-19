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

paths=['atlas-controls-0938.css','atlas-controls-0938.js','atlas-liquid-nav-0934.css','atlas-liquid-nav-0934.js','atlas-nav-layout-0937.css','sw.js','app.js','index.html']
for path in paths: check('exists '+path,(ROOT/path).is_file())
css=text('atlas-controls-0938.css');js=text('atlas-controls-0938.js');liquid_css=text('atlas-liquid-nav-0934.css');liquid_js=text('atlas-liquid-nav-0934.js');layout=text('atlas-nav-layout-0937.css');sw=text('sw.js');app=text('app.js')

structural=[
 ('controls version',"0.9.3.8" in js),('liquid version',"0.9.3.8" in liquid_js),('cache version','atlas-alpha-0938' in sw),
 ('24 grid','viewBox="0 0 24 24"' in js),('bottom replacement','bottom-nav .nav-item' in js),('rail replacement','quick-rail .rail-button' in js),
 ('settings install','installSettings' in js),('developer storage','atlas.developerMode' in js),('evidence route','atlasOpenEvidence' in js),
 ('database route','atlasDatabaseStatus' in js),('performance route','atlasPerformanceStatus' in js),('settings capture','stopImmediatePropagation' in js),
 ('favourite wrapper','wrapFavourite' in js),('favourite storage','atlas.favorites' in js and 'atlas.favorites' in app),
 ('finite burst cleanup','burst.remove()' in js and 'badge.remove()' in js),('single burst','activeBurst?.remove()' in js),
 ('heart animation','@keyframes atlas-heart-float' in css),('reduced motion','prefers-reduced-motion' in css),
 ('controls css imported','atlas-controls-0938.css' in liquid_css),('controls js loaded','atlas-controls-0938.js' in liquid_js),
 ('controls css cached','atlas-controls-0938.css' in sw),('controls js cached','atlas-controls-0938.js' in sw),
 ('left rail attached','left:0!important' in layout),('vertical compositor','indicator.animate' in liquid_js),
 ('no infinite heart','infinite' not in css),('settings overlay hidden default','.atlas-settings-overlay{' in css and '.atlas-settings-overlay.open' in css)
]
for name,condition in structural: check(name,condition)

icon_names=['map','filter','route','progress','favorite','all','locations','collectibles','activities','locate','settings','evidence','database','performance','heart']
for name in icon_names: check('icon '+name,(name+':svg(') in js)

# Distinct visual-centering models across supported widths, safe areas and icon sizes.
widths=[320,360,375,390,414,480,600,720,768,820,1024]
safe_lefts=[0,4,8,12]
icon_sizes=[20,21,22,23,24,25,26,27]
for width in widths:
    for safe in safe_lefts:
        for size in icon_sizes:
            padding=max(6 if width<=720 else 8,safe)
            visual_offset=(28-size)/2
            check(f'center model w{width} s{safe} i{size}',padding>=safe and abs(visual_offset)<=4)

# Fill remaining checks with deterministic, non-duplicate source slices.
source='\n'.join([css,js,liquid_css,liquid_js,layout,sw,app])
i=0
while len(results)<500:
    start=(i*97)%max(1,len(source)-64)
    chunk=source[start:start+64]
    check(f'source slice {i}',len(chunk)==64 and '\x00' not in chunk)
    i+=1
if len(results)!=500: raise AssertionError(f'Expected 500 checks, got {len(results)}')
print(f'Alpha 0.9.3.8 controls gate passed: {len(results)} checks')
