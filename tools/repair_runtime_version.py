#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.9.3.6"
CACHE_VERSION = "0936"


def replace_required(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Required text not found in {path}: {old}")
    path.write_text(text.replace(old, new), encoding="utf-8")


index = ROOT / "index.html"
text = index.read_text(encoding="utf-8")
text = text.replace("0.9.1.4", VERSION)
text = text.replace("ALPHA 0.9.3.5", f"ALPHA {VERSION}")
text = text.replace("ALPHA 0.9.3.4", f"ALPHA {VERSION}")
index.write_text(text, encoding="utf-8")

analysis = ROOT / "atlas-analysis-import.js"
text = analysis.read_text(encoding="utf-8")
for old in ("0.9.3.5", "0.9.3.4"):
    text = text.replace(old, VERSION)
analysis.write_text(text, encoding="utf-8")

liquid = ROOT / "atlas-liquid-nav-0934.js"
text = liquid.read_text(encoding="utf-8").replace("0.9.3.5", VERSION)
liquid.write_text(text, encoding="utf-8")

sw = ROOT / "sw.js"
text = sw.read_text(encoding="utf-8")
start = text.splitlines()[0]
assets = text.splitlines()[1]
new_sw = f"""const CACHE='atlas-alpha-{CACHE_VERSION}-pages-v1';
{assets}
self.addEventListener('install',event=>{{self.skipWaiting();event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS)))}});
self.addEventListener('activate',event=>{{event.waitUntil(Promise.all([caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))),self.clients.claim()]))}});
self.addEventListener('fetch',event=>{{
  if(event.request.method!=='GET')return;
  const request=event.request;
  if(request.mode==='navigate'){{
    event.respondWith(fetch(request,{{cache:'no-store'}}).then(response=>{{
      const copy=response.clone();
      caches.open(CACHE).then(cache=>cache.put('./index.html',copy));
      return response;
    }}).catch(()=>caches.match('./index.html')));
    return;
  }}
  event.respondWith(fetch(request).then(response=>{{
    const copy=response.clone();
    caches.open(CACHE).then(cache=>cache.put(request,copy));
    return response;
  }}).catch(()=>caches.match(request)));
}});
"""
sw.write_text(new_sw, encoding="utf-8")

print(f"Repaired runtime version to {VERSION} and cache to {CACHE_VERSION}")
