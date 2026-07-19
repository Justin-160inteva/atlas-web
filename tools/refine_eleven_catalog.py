#!/usr/bin/env python3
"""Refine 11 game world multipart items and build a coherent regional pilot queue."""
from __future__ import annotations
import argparse, json, pathlib, re
from collections import Counter
from datetime import datetime, timezone

ROOT=pathlib.Path(__file__).resolve().parents[1]
REGIONS=["山城","近江","播磨","大和","若狭","纪伊","丹波","伊贺","和泉","摄津","淡路"]
LOW=["BOSS","boss","结局","片尾","过场","配装","武器","流派","秒杀"]

def now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def load(path): return json.loads(path.read_text(encoding="utf-8"))
def write(path,value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
def part_title(title):
    match=re.search(r"·\s*P\d+\s+(.*)$",title)
    return match.group(1).strip() if match else title

def classify(item):
    part=part_title(item["title"]); region=next((name for name in REGIONS if name in part),"")
    low=any(term in part for term in LOW); collection=any(term in part for term in ("收集","探索","地点","位置","地图"))
    route=any(term in part for term in ("任务","主线","支线","章节","刺杀","调查"))
    duration=int(item.get("durationSeconds") or 0)
    if collection:
        scan_class="A"; utility="最高"; priority=100
    elif low:
        scan_class="C"; utility="低"; priority=42
    elif route or duration>=1200:
        scan_class="B"; utility="高" if region else "中高"; priority=82 if region else 74
    else:
        scan_class="C"; utility="待核实"; priority=55
    item.update({"partTitle":part,"regionGuess":region or None,"scanClass":scan_class,"mapUtility":utility,"priority":priority,"classificationBasis":{"partTitleUsed":True,"collectionRouteLikely":collection,"missionRouteLikely":route,"menuOrCombatHeavyLikely":low}})

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("manifest"); args=parser.parse_args(); manifest=load((ROOT/args.manifest).resolve())
    catalog_path=ROOT/manifest["catalogOutput"]; queue_path=ROOT/manifest["pilotQueueOutput"]
    catalog=load(catalog_path)
    for item in catalog["items"]: classify(item)
    ordered=sorted(catalog["items"],key=lambda item:(-item["priority"],item.get("regionGuess") or "~",item["sequence"]))
    collection=[item for item in ordered if item["scanClass"]=="A"]
    counts=Counter(item.get("regionGuess") for item in collection if item.get("regionGuess"))
    pilot_region="山城" if counts.get("山城") else (counts.most_common(1)[0][0] if counts else None)
    pilot=[item for item in collection if item.get("regionGuess")==pilot_region][:int(manifest.get("pilotCount",5))]
    if len(pilot)<int(manifest.get("pilotCount",5)):
        chosen={item["id"] for item in pilot}
        pilot.extend(item for item in collection if item["id"] not in chosen)
        pilot=pilot[:int(manifest.get("pilotCount",5))]
    catalog["recommendedScanOrder"]=[item["id"] for item in ordered]
    catalog["catalogStatus"]["scanClassA"]=sum(item["scanClass"]=="A" for item in catalog["items"])
    catalog["catalogStatus"]["scanClassB"]=sum(item["scanClass"]=="B" for item in catalog["items"])
    catalog["catalogStatus"]["scanClassC"]=sum(item["scanClass"]=="C" for item in catalog["items"])
    catalog["catalogStatus"]["pilotRegion"]=pilot_region
    catalog["updatedAt"]=now()
    queue={"schemaVersion":3,"queueId":"eleven-ac-shadows-pilot-v2","author":catalog["author"],"authorizationId":catalog["authorizationId"],"createdAt":now(),"status":"ready" if pilot else "empty","pilotRegion":pilot_region,"strategy":"Scan a coherent group of collection-heavy episodes from one region before account-wide processing.","items":[{"externalSourceId":item["id"],"sequence":item["sequence"],"title":item["title"],"partTitle":item["partTitle"],"regionGuess":item.get("regionGuess"),"bvid":item["bvid"],"page":item.get("page"),"cid":item.get("cid"),"url":item["url"],"scanClass":item["scanClass"],"mapUtility":item["mapUtility"],"priority":item["priority"],"durationSeconds":item["durationSeconds"],"state":"pending"} for item in pilot]}
    write(catalog_path,catalog); write(queue_path,queue)
    print(json.dumps({"A":catalog["catalogStatus"]["scanClassA"],"B":catalog["catalogStatus"]["scanClassB"],"C":catalog["catalogStatus"]["scanClassC"],"pilotRegion":pilot_region,"pilot":len(pilot)},ensure_ascii=False)); return 0
if __name__=="__main__": raise SystemExit(main())
