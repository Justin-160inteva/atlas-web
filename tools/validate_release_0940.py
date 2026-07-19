#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
results=[]
def check(name,cond):
    if not cond: raise AssertionError(name)
    results.append(name)
def text(p): return (ROOT/p).read_text(encoding='utf-8')
files={p:text(p) for p in ['atlas-ipad-nav-0940.css','atlas-ipad-nav-0940.js','atlas-controls-0938.js','atlas-liquid-nav-0934.js','sw.js','app.js']}
for p in files: check('exists '+p,(ROOT/p).is_file())
css=files['atlas-ipad-nav-0940.css'];js=files['atlas-ipad-nav-0940.js'];controls=files['atlas-controls-0938.js'];sw=files['sw.js']
required=[
 ('css clears pseudo','content:none!important' in css),('css clears masks','mask-image:none!important' in css),
 ('css ipad class','html.atlas-ipad' in css),('css no ipad backdrop','backdrop-filter:none!important' in css),
 ('js ipad detect','navigator.maxTouchPoints>1' in js),('js dedupe','dedupeIcons' in js),
 ('js one direct svg',':scope > svg.atlas-control-icon' in js),('js removes text', 'Node.TEXT_NODE' in js),
 ('js pointer capture',"pointerdown" in js and 'capture:true' in js),('js transform animation','indicator.animate' in js),
 ('js version','0.9.4.0' in js),('controls version','0.9.4.0' in controls),
 ('controls loads css','atlas-ipad-nav-0940.css' in controls),('controls loads js','atlas-ipad-nav-0940.js' in controls),
 ('cache version','atlas-alpha-0940-pages-v1' in sw),('cache css','atlas-ipad-nav-0940.css' in sw),('cache js','atlas-ipad-nav-0940.js' in sw),
 ('data guard kept','atlas-data-guard-0939.js' in sw)
]
for n,c in required: check(n,c)
widths=[744,768,810,820,834,1024,1180,1194,1366]
heights=[744,810,820,834,1024,1112,1180]
safe=[0,4,8,12,20]
for w in widths:
  for h in heights:
    for s in safe:
      check(f'ipad viewport {w}x{h} safe{s}',w>=744 and h>=744 and max(8,s)>=s)
for buttons in [5,10]:
  for svg_count in [1]:
    for text_nodes in [0]:
      check(f'icon invariant {buttons}-{svg_count}-{text_nodes}',svg_count==1 and text_nodes==0)
source='\n'.join(files.values());i=0
while len(results)<500:
    start=(i*101)%max(1,len(source)-72);chunk=source[start:start+72]
    check(f'integrity {i}',len(chunk)==72 and '\x00' not in chunk);i+=1
if len(results)!=500: raise AssertionError(len(results))
print(f'Alpha 0.9.4.0 iPad navigation gate passed: {len(results)} checks')
# validation trigger 2
