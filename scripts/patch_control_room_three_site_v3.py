#!/usr/bin/env python3
"""Strict additive patch to already deployed Maya3 dual-backhaul Control Room.

Only edits the in-process admin Python overlay. Existing route/CSRF, manual
refresh button, historic traffic, Maya4 legacy roles remain intact.
No remote commands, no tunnel or gateway writes.
"""
import ast
import sys
from pathlib import Path

MARK="# HESAB_CONTROL_ROOM_THREE_SITE_V3"
MAYA3="# HESAB_MAYA3_DUAL_BACKHAUL_VISUAL_V1"
ROOT="# HESAB_CONTROL_ROOM_DUAL_HOURLY_SIMPLE_V1"

def replace_once(source,old,new,label):
    if source.count(old)!=1:
        raise ValueError("STOP: unexpected installed overlay layout at "+label)
    return source.replace(old,new,1)

def transform(source):
    if MARK in source:
        raise ValueError("STOP: Three-site V3 Control Room already installed")
    if source.count(MAYA3)!=1 or source.count(ROOT)!=1:
        raise ValueError("STOP: dual-role management overlay is not installed")
    # API sanitize: accept ONLY three named boolean flags, never raw remote text.
    source=replace_once(source,
        '''    return {"ip": ip, "state": state, "https_avg_ms": ms,
            "https_passed": passed, "https_total": total}''',
        '''    supplied=data.get("https_sites")
    sites=None
    if (isinstance(supplied,dict) and set(supplied)==
            {"google","cloudflare","apple"} and
            all(type(supplied[k]) is bool for k in supplied)):
        sites={key:supplied[key] for key in ("google","cloudflare","apple")}
    return {"ip": ip, "state": state, "https_avg_ms": ms,
            "https_passed": passed, "https_total": total,
            "https_sites": sites,
            "site_warning": bool(sites is not None and not all(sites.values()))}''',
        "api sanitizer")
    source=replace_once(source,
        '''                        "mode": "dual_backhaul" if info.get("mode") == "dual_backhaul" else "legacy",
                        "paths": {role: _dh1_clean_path(paths.get(role))''',
        '''                        "mode": "dual_backhaul" if info.get("mode") == "dual_backhaul" else "legacy",
                        "health_interval_s": (600 if info.get("health_interval_s")==600 else 30),
                        "controller_age_s": (info.get("controller_age_s")
                            if type(info.get("controller_age_s")) is int and
                            0<=info["controller_age_s"]<=86400 else None),
                        "paths": {role: _dh1_clean_path(paths.get(role))''',
        "api 10min snapshot fields")
    source=replace_once(source,
        "بررسی خودکار هر ساعت · زمان پاسخ HTTPS، نه پینگ ICMP",
        "دریافت وضعیت هر ۱۰ دقیقه · سلامت HTTPS سه مقصد",
        "collection cadence caption")
    # Server reports every 10min and management collection is cached.
    # Never show green from a snapshot whose actual underlying probe is >25min.
    source=replace_once(source,
        '''                    output[sid] = {
                        "state": state, "age_s": age,''',
        '''                    observed_age=info.get("controller_age_s")
                    if (info.get("health_interval_s")==600 and
                        (type(observed_age) is not int or observed_age<0 or
                         observed_age+age>1500)):
                        state="stale"
                        # Do not claim current health from an expired probe.
                    output[sid] = {
                        "state": state, "age_s": age,''',
        "cached probe age check")
    # Deliberately do not mutate the cached JSON or any path references above.
    # UI only paints positive green when the server itself is fresh.
    source=replace_once(source,
        "#c2-root .dh1-meta{font-size:10px;color:#aeb5d2;margin-top:8px}",
        "#c2-root .dh1-meta{font-size:10px;color:#aeb5d2;margin-top:8px}\n#c2-root .dh3-sites.warn{color:#f1c876}",
        "partial HTTPS warning style")
    source=replace_once(source,
        '''   add(card,"div",title+" · میانگین HTTPS: "+latency,"dh1-meta");''',
        '''   if(item.health_interval_s===600 && item.mode==="dual_backhaul"){
     const sites=valid&&raw.https_sites;
     const symbols={google:"Google",cloudflare:"Cloudflare",apple:"Apple"};
     const checks=sites&&["google","cloudflare","apple"].every(k=>typeof sites[k]==="boolean");
     if(checks){
       const note=["google","cloudflare","apple"].map(k=>symbols[k]+": "+(sites[k]?"OK":"FAIL")).join(" · ");
       add(card,"div",note,raw.site_warning?"dh1-meta dh3-sites warn":"dh1-meta dh3-sites");
     }else{
       add(card,"div","وضعیت سه مقصد: نامشخص","dh1-meta");
     }
   }else{
     add(card,"div",title+" · میانگین HTTPS: "+latency,"dh1-meta");
   }''',
        "three-site card display")
    source=replace_once(source,
        '''    item.state==="ok"&&age!=null?"آخرین بررسی: "+age+" دقیقه پیش":"در انتظار دریافت";''',
        '''    item.state==="ok"&&age!=null?"آخرین دریافت پنل: "+age+" دقیقه پیش":"در انتظار دریافت";''',
        "collector timestamp label")
    source=replace_once(source,
        '''  add(card,"div",note,"dh1-meta");
 }
}''',
        '''  add(card,"div",note,"dh1-meta");
  if(item.mode==="dual_backhaul"&&item.health_interval_s===600){
    const observed=Number.isFinite(item.controller_age_s)&&Number.isFinite(item.age_s)?
      Math.max(0,Math.floor((item.controller_age_s+item.age_s)/60)):null;
    add(card,"div","سنجش مسیرها: هر ۱۰ دقیقه · سن آخرین آزمون: "+
       (observed===null?"نامشخص":observed+" دقیقه"),"dh1-meta");
  }
 }
}''',
        "health freshness note")
    source += "\n"+MARK+"\n"
    ast.parse(source)
    return source

def main():
    if len(sys.argv)!=2:
        raise SystemExit("Usage: patch_control_room_three_site_v3.py ADMIN_OVERLAY")
    p=Path(sys.argv[1])
    if not p.is_file() or p.is_symlink():
        raise SystemExit("STOP: overlay absent or symlink")
    updated=transform(p.read_text(encoding="utf8"))
    p.write_text(updated,encoding="utf8")
    print("CONTROL_ROOM_THREE_SITE_V3_UI_PATCHED")

if __name__=="__main__":
    main()
