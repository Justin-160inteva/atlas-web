#!/usr/bin/env python3
"""Discover an authorized Bilibili author's Assassin's Creed Shadows catalog.
No video media or frame pixels are downloaded by this stage.
"""
from __future__ import annotations
import argparse, html, json, pathlib, re
from datetime import datetime, timezone
from urllib.parse import quote
from curl_cffi import requests

ROOT=pathlib.Path(__file__).resolve().parents[1]
HEADERS={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131 Safari/537.36","Referer":"https://www.bilibili.com/","Origin":"https://www.bilibili.com"}

def now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def load(path): return json.loads(path.read_text(encoding="utf-8"))
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(path)
def clean(value): return re.sub(r"\s+"," ",re.sub(r"<[^>]+>","",html.unescape(str(value or "")))).strip()
def norm(value): return re.sub(r"[^0-9a-z\u3400-\u9fff]+","",clean(value).lower())
def get(url):
    response=requests.get(url,headers=HEADERS,impersonate="chrome",timeout=35)
    response.raise_for_status(); payload=response.json()
    if payload.get("code")!=0: raise RuntimeError(f"code={payload.get('code')} {payload.get('message')}")
    return payload

def duration_seconds(value):
    if isinstance(value,str) and ":" in value:
        parts=[int(p) for p in value.split(":") if p.isdigit()]
        return sum(v*(60**i) for i,v in enumerate(reversed(parts)))
    try: return int(value or 0)
    except (TypeError,ValueError): return 0

def video(raw,author):
    bvid=clean(raw.get("bvid"))
    if not bvid:
        match=re.search(r"(BV[0-9A-Za-z]+)",clean(raw.get("arcurl"))); bvid=match.group(1) if match else ""
    if not bvid.startswith("BV"): return None
    raw_author=clean(raw.get("author") or raw.get("up_name") or raw.get("name"))
    if raw_author and norm(raw_author)!=norm(author): return None
    return {"bvid":bvid,"title":clean(raw.get("title")),"author":author,"durationSeconds":duration_seconds(raw.get("duration") or raw.get("length")),"publishedAtUnix":int(raw.get("created") or raw.get("pubdate") or 0),"url":f"https://www.bilibili.com/video/{bvid}/"}

def walk_results(value):
    if isinstance(value,dict):
        if value.get("bvid") or value.get("arcurl"): yield value
        for child in value.values(): yield from walk_results(child)
    elif isinstance(value,list):
        for child in value: yield from walk_results(child)

def seed_info(bvid):
    data=get(f"https://api.bilibili.com/x/web-interface/view?bvid={quote(bvid)}").get("data") or {}
    owner=data.get("owner") or {}
    if not owner.get("mid") or not owner.get("name"): raise RuntimeError("invalid seed owner")
    return {"mid":int(owner["mid"]),"name":clean(owner["name"]),"title":clean(data.get("title")),"bvid":clean(data.get("bvid") or bvid),"durationSeconds":int(data.get("duration") or 0),"publishedAtUnix":int(data.get("pubdate") or 0)}

def discover_space(mid,author,diagnostics):
    found={}
    templates=["https://api.bilibili.com/x/space/arc/search?mid={mid}&ps=50&pn={page}&order=pubdate","https://api.bilibili.com/x/space/wbi/arc/search?mid={mid}&ps=50&pn={page}&order=pubdate"]
    for template in templates:
        imported=0
        try:
            for page in range(1,41):
                data=get(template.format(mid=mid,page=page)).get("data") or {}
                rows=((data.get("list") or {}).get("vlist") or [])
                if not rows: break
                for raw in rows:
                    item=video(raw,author)
                    if item: found[item["bvid"]]=item; imported+=1
                count=int((data.get("page") or {}).get("count") or 0)
                if count and page*50>=count: break
            if imported: diagnostics.append(f"space imported {imported}"); break
        except Exception as exc: diagnostics.append(f"space failed: {exc!r}"[-1200:])
    return found

def discover_search(author,needles,diagnostics):
    found={}
    for query in (f"{author} 刺客信条影",f"{author} 刺客信条：影",f"{author} AC Shadows"):
        try:
            for page in range(1,11):
                payload=get(f"https://api.bilibili.com/x/web-interface/search/type?search_type=video&page={page}&page_size=50&keyword={quote(query)}")
                rows=list(walk_results(payload.get("data")))
                if not rows: break
                accepted=0
                for raw in rows:
                    item=video(raw,author)
                    if item and any(norm(n) in norm(item["title"]) for n in needles): found[item["bvid"]]=item; accepted+=1
                if accepted==0 and page>=2: break
            diagnostics.append(f"search completed: {query}")
        except Exception as exc: diagnostics.append(f"search failed: {query}: {exc!r}"[-1200:])
    return found

def classify(title,duration):
    text=norm(title)
    core=["全任务","全收集","全流程","流程","探索","区域","支线","主线","开放世界"]
    places=["收集","地点","位置","城堡","寺庙","神社","古坟","九字真言","技能点","秘道","瞭望点"]
    low=["boss","配装","武器","流派","伤害","秒杀","结局","片尾","纯剧情"]
    has_core=any(norm(x) in text for x in core); has_places=any(norm(x) in text for x in places); has_low=any(norm(x) in text for x in low)
    if has_core or (duration>=900 and not has_low): scan_class="A"; utility="最高" if duration>=1200 or "全收集" in title else "高"; priority=100 if utility=="最高" else 92
    elif has_places or duration>=360: scan_class="B"; utility="中高"; priority=78
    else: scan_class="C"; utility="低" if has_low else "待核实"; priority=45 if has_low else 58
    return {"scanClass":scan_class,"mapUtility":utility,"priority":priority,"classificationBasis":{"continuousRouteLikely":bool(has_core or duration>=900),"locationEvidenceLikely":has_places,"menuOrCombatHeavyLikely":has_low}}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("manifest"); args=parser.parse_args()
    manifest=load((ROOT/args.manifest).resolve()); diagnostics=[]
    expected=clean(manifest["author"]); needles=[clean(x) for x in manifest.get("titleMustContainAny",[]) if clean(x)] or ["刺客信条影","刺客信条：影","AC Shadows"]
    seed=seed_info(clean(manifest["seedBvid"]))
    if norm(seed["name"])!=norm(expected): raise RuntimeError(f"seed owner mismatch: {seed['name']}")
    merged=discover_space(seed["mid"],seed["name"],diagnostics)
    merged.update(discover_search(seed["name"],needles,diagnostics))
    merged[seed["bvid"]]={"bvid":seed["bvid"],"title":seed["title"],"author":seed["name"],"durationSeconds":seed["durationSeconds"],"publishedAtUnix":seed["publishedAtUnix"],"url":f"https://www.bilibili.com/video/{seed['bvid']}/"}
    matched=[]
    for item in merged.values():
        if any(norm(n) in norm(item["title"]) for n in needles): matched.append(item|classify(item["title"],item["durationSeconds"]))
    matched.sort(key=lambda x:(x.get("publishedAtUnix",0),x["bvid"]))
    items=[]
    for sequence,item in enumerate(matched,1):
        items.append({"id":f"bili-eleven-acshadows-{item['bvid']}","sequence":sequence,"title":item["title"],"author":seed["name"],"platform":"哔哩哔哩","game":"刺客信条：影","type":"待自动细分","quality":"公开视频","durationSeconds":item["durationSeconds"],"publishedAtUnix":item["publishedAtUnix"],"url":item["url"],"bvid":item["bvid"],"exactUrlVerified":True,"authorizationId":manifest["authorizationId"],"scanClass":item["scanClass"],"mapUtility":item["mapUtility"],"priority":item["priority"],"classificationBasis":item["classificationBasis"],"analysisStatus":"pending"})
    ordered=sorted(items,key=lambda x:(-x["priority"],-x["durationSeconds"],x["sequence"])); pilot=ordered[:max(1,int(manifest.get("pilotCount",5)))]; timestamp=now()
    catalog={"schemaVersion":1,"version":"1.0.0","updatedAt":timestamp,"author":seed["name"],"authorMid":seed["mid"],"platform":"哔哩哔哩","game":"刺客信条：影","authorizationId":manifest["authorizationId"],"seedVideo":seed,"catalogStatus":{"discoveryComplete":True,"discoveredAccountVideos":len(merged),"matchedGameVideos":len(items),"analysisImported":0,"analysisRemaining":len(items),"analysisComplete":len(items)==0,"discoveredAt":timestamp},"futureInclusionRule":{"enabled":True,"authorMustEqual":seed["name"],"titleMustContainAny":needles,"authorizationAutomaticallyInherited":True,"catalogEntryStillRequiresTitleAndUrlVerification":True},"recommendedScanOrder":[x["id"] for x in ordered],"items":items}
    queue={"schemaVersion":1,"queueId":"eleven-ac-shadows-pilot-v1","author":seed["name"],"authorizationId":manifest["authorizationId"],"createdAt":timestamp,"status":"ready" if pilot else "empty","strategy":"Start with route-heavy high-value videos before account-wide batch analysis.","items":[{"externalSourceId":x["id"],"sequence":x["sequence"],"title":x["title"],"bvid":x["bvid"],"url":x["url"],"scanClass":x["scanClass"],"mapUtility":x["mapUtility"],"priority":x["priority"],"durationSeconds":x["durationSeconds"],"state":"pending"} for x in pilot]}
    status={"schemaVersion":1,"runId":manifest.get("id","eleven-author-discovery-v1"),"status":"success","author":seed["name"],"authorMid":seed["mid"],"authorizationId":manifest["authorizationId"],"seedBvid":seed["bvid"],"updatedAt":timestamp,"summary":{"accountVideosDiscovered":len(merged),"gameVideosMatched":len(items),"scanClassA":sum(x["scanClass"]=="A" for x in items),"scanClassB":sum(x["scanClass"]=="B" for x in items),"scanClassC":sum(x["scanClass"]=="C" for x in items),"pilotQueued":len(pilot)},"diagnostics":diagnostics[-20:],"privacy":"No video media or frame pixels were downloaded during catalog discovery."}
    write(ROOT/manifest["catalogOutput"],catalog); write(ROOT/manifest["pilotQueueOutput"],queue); write(ROOT/manifest["statusOutput"],status)
    print(json.dumps(status["summary"],ensure_ascii=False)); return 0
if __name__=="__main__": raise SystemExit(main())
