#!/usr/bin/env python3
"""HESAB_MAYA_XUI_HOST_METRICS_V1
Read-only admin-host collector for 3x-ui /panel/api/server/status.
Reuses existing STRICT HTTPS or verified SSH loopback tunnel credentials.
Never reads users/payments, never persists XUI credentials or raw status,
never changes XUI state. Output sanitized host metrics only.
"""
import json, math, os, sys, tempfile, time
from pathlib import Path

ROOT=Path("/opt/vpn-control-center")
OUT=ROOT/"maya_extra_sync/phase1/xui_status_v1.json"
sys.path.insert(0,str(ROOT/"scripts"))
import maya_multi_panel_sync as maya

def bounded(value,minval,maxval):
    if type(value) not in (float,int) or not math.isfinite(value):
        return None
    value=float(value)
    if minval<=value<=maxval:return round(value,2)
    return None

def probe(name,settings):
    with maya.panel_connection(settings) as (opener,base,headers):
        document=maya.request_json(opener,base+"panel/api/server/status",
                                  headers=headers)
    payload=document.get("obj")
    if not isinstance(payload,dict):
        raise ValueError("3x-ui status payload unavailable")
    cpu=bounded(payload.get("cpu"),0,100)
    mem=payload.get("mem")
    ram=None
    if isinstance(mem,dict):
        used=bounded(mem.get("current"),0,1e17)
        total=bounded(mem.get("total"),1,1e17)
        if used is not None and total is not None and used<=total:
            ram=round(100*used/total,1)
    # xray state is only a process report, never an end-to-end VPN health check.
    xray=payload.get("xray")
    state=str(xray.get("state","")).lower() if isinstance(xray,dict) else ""
    if state not in ("running","stopped","unknown"):state="unknown"
    if cpu is None and ram is None:
        raise ValueError("unsupported or incomplete status schema")
    return {"state":"ok","cpu_pct":cpu,"ram_pct":ram,
            "xray_process":state,"sampled_at":int(time.time())}

def atomic(doc):
    OUT.parent.mkdir(mode=0o750,parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix="xui-metrics.",dir=OUT.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as output:
            json.dump(doc,output,ensure_ascii=False,separators=(",",":"))
            output.flush();os.fsync(output.fileno())
        os.chmod(tmp,0o640)
        os.replace(tmp,OUT)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def main():
    if os.geteuid()!=0:raise PermissionError("root required for protected panel config")
    cfg=maya.config()
    now=int(time.time())
    servers={}
    for key in maya.SERVERS:
        if key not in cfg:
            servers[key]={"state":"not_configured"}
            continue
        try:
            servers[key]=probe(key,cfg[key])
            print("XUI_METRICS_OK",key,flush=True)
        except Exception as exc:
            servers[key]={"state":"unavailable"}
            print("XUI_METRICS_UNAVAILABLE",key,type(exc).__name__,flush=True)
    atomic({"format":"HESAB_MAYA_XUI_METRICS_V1","collected_at":now,
            "servers":servers})
    print("XUI_METRICS_SNAPSHOT_SAVED",str(OUT),flush=True)

if __name__=="__main__":
    try:main()
    except Exception as err:
        print("XUI_METRICS_FATAL",type(err).__name__,flush=True)
        raise SystemExit(1)
