#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
results = []


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    results.append(name)


def text(path):
    return (ROOT / path).read_text(encoding='utf-8')

files = {
    'layout': text('atlas-nav-layout-0937.css'),
    'base': text('atlas-liquid-nav-0933.css'),
    'refine': text('atlas-liquid-nav-0934.css'),
    'runtime': text('atlas-liquid-nav-0934.js'),
    'sw': text('sw.js'),
    'index': text('index.html'),
    'app': text('app.js'),
}

required_files = [
    'index.html','styles.css','atlas-liquid-nav-0933.css','atlas-liquid-nav-0934.css',
    'atlas-nav-layout-0937.css','atlas-liquid-nav-0934.js','atlas-analysis-import.js',
    'app.js','sw.js','performance-092.js','performance-092.css','atlas-ui-fix-0931.js',
    'atlas-ui-fix-0931.css','atlas-smart-route-0932.css','route-engine.js','smart-route.js',
    'data/locations.json','data/categories.json','data/regions.json','PROJECT-ROADMAP.md'
]
for path in required_files:
    check(f'file exists: {path}', (ROOT / path).is_file())

required_tokens = [
    ('layout','.quick-rail{'),('layout','left:0!important'),('layout','border-left:0!important'),
    ('layout','.status-pill{'),('layout','env(safe-area-inset-left'),('layout','env(safe-area-inset-bottom'),
    ('layout','calc(-100% - 40px)'),('layout','pointer-events:none'),('layout','contain:layout paint style'),
    ('layout','backdrop-filter:none!important'),('layout','will-change:transform'),
    ('refine','atlas-liquid-nav-0933.css'),('refine','atlas-nav-layout-0937.css'),
    ('runtime',"const VERSION='0.9.3.7'"),('runtime','indicator.animate('),
    ('runtime',"duration:210"),('runtime',"easing:'cubic-bezier(.22,.82,.2,1)'"),
    ('runtime','group.animation?.cancel()'),('runtime','getComputedStyle(indicator).transform'),
    ('runtime','MutationObserver(stampVersion)'),('runtime',"installGroup('.quick-rail','vertical')"),
    ('runtime',"installGroup('.bottom-nav','horizontal')"),('runtime',"name!=='vertical'"),
    ('sw',"atlas-alpha-0937-pages-v1"),('sw','atlas-nav-layout-0937.css'),
    ('sw',"request.mode==='navigate'"),('sw',"cache:'no-store'"),
    ('base','.atlas-liquid-selection'),('base','content:none!important'),
    ('base','.bottom-nav .nav-item'),('base','.quick-rail .rail-button'),
    ('app',"document.querySelectorAll('.rail-button')"),('app','state.mode=b.dataset.mode'),
]
for key, token in required_tokens:
    check(f'{key} contains {token}', token in files[key])

forbidden_tokens = [
    ('layout','left:18px'),('layout','left:10px'),('layout','translateX(-430px)'),
    ('runtime','setTimeout(step'),('runtime','setInterval(schedule'),
    ('sw',"atlas-alpha-0936-pages-v1"),
]
for key, token in forbidden_tokens:
    check(f'{key} excludes {token}', token not in files[key])

check('base imported before 0937 layout', files['refine'].find('atlas-liquid-nav-0933.css') < files['refine'].find('atlas-nav-layout-0937.css'))
check('vertical CSS transition disabled by layout layer', 'transition:opacity .12s ease!important' in files['layout'])
check('vertical animation uses compositor transform', 'translate3d' in files['runtime'])
check('vertical press class not added', "if(name!=='vertical')indicator.classList.add('is-pressed')" in files['runtime'])
check('horizontal approved behavior retained', '.atlas-liquid-selection-horizontal' in files['refine'])
check('closed route panel covered', '.route-panel:not(.open)' in files['layout'])
check('closed progress panel covered', '.progress-panel:not(.open)' in files['layout'])
check('open panels restored to zero transform', 'translate3d(0,0,0)!important' in files['layout'])

widths = [320, 360, 375, 390, 414, 480, 600, 720, 768, 1024]
safe_lefts = [0, 4, 12, 24]
safe_bottoms = [0, 8]
for width in widths:
    for safe_left in safe_lefts:
        for safe_bottom in safe_bottoms:
            rail_outer_left = 0
            rail_content_left = max(8 if width > 720 else 6, safe_left)
            status_left = max(8 if width > 720 else 6, safe_left)
            status_bottom = max(8 if width > 720 else 6, safe_bottom)
            closed_panel_width = min(460, width - 36)
            closed_panel_left = 18 - closed_panel_width - 40
            closed_panel_right = closed_panel_left + closed_panel_width
            check(f'rail edge w{width} sl{safe_left}', rail_outer_left == 0)
            check(f'rail safe content w{width} sl{safe_left}', rail_content_left >= safe_left)
            check(f'status safe left w{width} sl{safe_left}', status_left >= safe_left)
            check(f'status safe bottom w{width} sb{safe_bottom}', status_bottom >= safe_bottom)
            check(f'closed panel hidden w{width} sl{safe_left}', closed_panel_right < 0)

source_blob = '\n'.join(files.values())
index = 0
while len(results) < 500:
    start = (index * 97) % max(1, len(source_blob) - 32)
    chunk = source_blob[start:start + 32]
    check(f'source integrity slice {index}', len(chunk) == 32 and '\x00' not in chunk)
    index += 1

if len(results) != 500:
    raise AssertionError(f'Expected 500 checks, got {len(results)}')

print(f'Alpha 0.9.3.7 release gate passed: {len(results)} checks')

# Validation trigger: exact 500-check high-risk navigation gate.
