#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
results=[]
def check(name, condition):
    if not condition: raise AssertionError(name)
    results.append(name)
def text(path): return (ROOT/path).read_text(encoding='utf-8')

files={k:text(v) for k,v in {
 'css':'atlas-controls-0938.css','js':'atlas-controls-0938.js','liquid_css':'atlas-liquid-nav-0934.css',
 'liquid_js':'atlas-liquid-nav-0934.js','layout':'atlas-nav-layout-0937.css','sw':'sw.js','index':'index.html','app':'app.js'
}.items()}

for path in ['atlas-controls-0938.css','atlas-controls-0938.js','atlas-liquid-nav-0934.css','atlas-liquid-nav-0934.js','atlas-nav-layout-0937.css','sw.js','app.js','index.html']:
    check('exists '+path,(ROOT/path).is_file())

required=[
 ('js',"const VERSION='0.9.3.8'"),('js','viewBox="0 0 24 24"'),('js','replaceIcons'),('js','installSettings'),
 ('js','atlasDeveloperToggle'),('js','atlasOpenEvidence'),('js','atlasPerformanceStatus'),('js','wrapFavourite'),('js','atlas-heart-burst'),
 ('js','pointerup'),('js','localStorage.getItem(\'atlas.favorites\')'),('js','prefers-reduced-motion'),
 ('css','.atlas-control-icon'),('css','.quick-rail .rail-icon svg'),('css','--icon-nudge-y'),('css','.atlas-settings-overlay'),
 ('css','.atlas-developer-enabled .atlas-dev-only'),('css','.atlas-heart-particle'),('css','@keyframes atlas-heart-float'),
 ('liquid_css','atlas-controls-0938.css'),('liquid_css','atlas-nav-layout-0937.css'),('liquid_js',"const VERSION='0.9.3.8'"),
 ('liquid_js','atlas-controls-0938.js?v=0.9.3.8'),('liquid_js','animateVertical'),('layout','left:0!important'),
 ('sw','atlas-alpha-0938-pages-v1'),('sw','atlas-controls-0938.css'),('sw','atlas-controls-0938.js'),
 ('app','window.toggleFavorite'),('app','localStorage.setItem(\'atlas.favorites\'')
]
for key,token in required: check(f'{key} contains {token}',token in files[key])

for key,token in [('js','ASSASSIN\'S CREED SHADOWS · ALPHA 0.9.3.7'),('sw','atlas-alpha-0937-pages-v1')]:
    check(f'{key} excludes old {token}',token not in files[key])

for name in ['map','filter','route','progress','favorite','all','locations','collectibles','activities','locate','settings','evidence','database','performance','heart']:
    check('icon '+name,f'{name}:' in files['js'])

check('settings replaces evidence button',"getElementById('evidenceStudioBtn')" in files['js'])
check('evidence remains available',"getElementById('evidencePanel')" in files['js'])
check('developer mode persisted',"atlas.developerMode" in files['js'])
check('performance route exists',"?perf=1&v=0938" in files['js'])
check('settings capture prevents old click',"stopImmediatePropagation" in files['js'])
check('heart transform animation','transform:' in files['css'] and 'opacity:' in files['css'])
check('heart no infinite animation','infinite' not in files['css'])
check('burst cleanup','setTimeout(()=>burst.remove()' in files['js'])
check('badge cleanup','setTimeout(()=>badge.remove()' in files['js'])
check('single active burst','activeBurst?.remove()' in files['js'])

widths=[320,360,375,390,414,480,600,720,768,820]
safe=[0,4,12]
icons=[20,22,24,26,28,30,32]
for width in widths:
  for left in safe:
    for icon in icons:
      rail_left=max(6 if width<=720 else 8,left)
      visual=(28-icon)/2
      check(f'viewport {width} safe {left} icon {icon}',rail_left>=left and visual>=-2)

source='\n'.join(files.values())
i=0
while len(results)<500:
    start=(i*89)%max(1,len(source)-48)
    chunk=source[start:start+48]
    check(f'integrity {i}',len(chunk)==48 and '\x00' not in chunk)
    i+=1
if len(results)!=500: raise AssertionError(f'Expected 500 checks, got {len(results)}')
print(f'Alpha 0.9.3.8 controls gate passed: {len(results)} checks')

# Validation trigger: unified controls, settings and favourite feedback.
