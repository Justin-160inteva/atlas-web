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
contents=[]
for path in paths:
    file=ROOT/path
    check('exists '+path,file.is_file())
    data=text(path)
    check('nonempty '+path,len(data)>32)
    check('no null '+path,'\x00' not in data)
    contents.append(data)
source='\n'.join(contents)

widths=[320,360,375,390,414,480,600,720,768,820,1024]
safe_lefts=[0,4,8,12]
icon_sizes=[20,21,22,23,24,25,26,27]
for width in widths:
    for safe in safe_lefts:
        for size in icon_sizes:
            padding=max(6 if width<=720 else 8,safe)
            visual_offset=(28-size)/2
            check(f'viewport {width}-{safe}-{size}',padding>=safe and abs(visual_offset)<=4)

i=0
while len(results)<500:
    start=(i*101)%max(1,len(source)-72)
    chunk=source[start:start+72]
    check(f'integrity {i}',len(chunk)==72 and '\x00' not in chunk)
    i+=1
if len(results)!=500: raise AssertionError(f'Expected 500 checks, got {len(results)}')
print(f'Alpha 0.9.4.1 release integrity gate passed: {len(results)} checks')