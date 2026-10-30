#!/usr/bin/env python3
"""HESAB_PROVIDER_BALANCE_REFERENCE_V1
Local operator-entered NON-LIVE datacenter balance only.
Does not touch quota config, XUI, network counters, payments or alerts.
"""
import json, math, os, sys, tempfile, time
from pathlib import Path

ROOT=Path("/opt/vpn-control-center")
DEST=ROOT/"maya_extra_sync/phase1/provider_balance_reference_v1.json"
IDS=("maya1","maya-s3","maya4")

def check(n):
    x=float(n)
    if not math.isfinite(x) or not 0<=x<=1e9:
        raise ValueError("invalid non-negative GB")
    return round(x,3)

def atomic(path,data):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o750)
    fd,temp=tempfile.mkstemp(prefix=".provider-ref-",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(data,stream,ensure_ascii=False,separators=(",",":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp,0o640)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def write(values):
    if os.geteuid()!=0:
        raise PermissionError("root on management server required")
    if len(values)!=3:raise ValueError("expected balances: Maya1 Maya3 Maya4")
    parsed=[check(v) for v in values]
    if DEST.exists():
        if DEST.is_symlink():raise ValueError("unsafe destination symlink")
        # Back up previous user-supplied balance report without modifying
        # any NIC usage ledger or automatic billing-period configuration.
        backup=DEST.with_name(DEST.name+".bak."+str(time.time_ns()))
        backup.write_bytes(DEST.read_bytes())
        backup.chmod(0o600)
    d={"format":"HESAB_PROVIDER_BALANCE_REFERENCE_V1",
       "recorded_at":int(time.time()),
       "provider_observed_at_known":False,
       "source":"operator_report",
       "servers":{key:{"remaining_gb":value} for key,value in zip(IDS,parsed)}}
    atomic(DEST,d)
    for id,val in zip(IDS,parsed):
        print("PROVIDER_REPORTED_BALANCE",id,val,"GB",
              "(NOT LIVE / PROVIDER OBSERVATION TIME UNKNOWN)")
    print("REFERENCE_SAVED","no quota/billing/meter state changed")

def show():
    if not DEST.is_file():
        print("NO_REPORTED_BALANCE_REFERENCE")
        return
    d=json.loads(DEST.read_text(encoding="utf-8"))
    if d.get("format")!="HESAB_PROVIDER_BALANCE_REFERENCE_V1":
        raise ValueError("unexpected report format")
    for key in IDS:
        print(key,d.get("servers",{}).get(key,{}).get("remaining_gb","—"),
              "GB (historical operator report, NOT live)")

def main():
    if len(sys.argv)==2 and sys.argv[1]=="show":return show()
    if len(sys.argv)==5 and sys.argv[1]=="set":return write(sys.argv[2:])
    raise ValueError("Usage: set MAYA1_GB MAYA3_GB MAYA4_GB | show")

if __name__=="__main__":
    try:main()
    except Exception as error:
        print("REFERENCE_STOP",type(error).__name__,str(error)[:110],file=sys.stderr)
        raise SystemExit(1)
