#!/usr/bin/env python3
"""HESAB_PROVIDER_ESTIMATE_V7_INITIALIZER
Freeze the CURRENT meter counters, pairing them with the last user-reported
(non-current) provider balance. No recalculation of historic overnight usage.
No modification to NIC counters, XUI, payments or traffic quotas.
"""
import json,os,sys,time,tempfile
from pathlib import Path
ROOT=Path("/opt/vpn-control-center")
SNAP=ROOT/"maya_extra_sync/phase1/status.json"
PROVIDER=ROOT/"maya_extra_sync/phase1/provider_balance_reference_v1.json"
OUT=ROOT/"maya_extra_sync/phase1/provisional_meter_baseline_v7.json"
NAMES=("maya1","maya-s3","maya4")
def valid(path,expected):
    if not path.is_file() or path.is_symlink() or path.stat().st_size>60000:
        raise RuntimeError("missing or invalid local telemetry: "+path.name)
    d=json.loads(path.read_text(encoding="utf8"))
    if d.get("format")!=expected:raise RuntimeError("unexpected format: "+path.name)
    return d
def initialize():
    if os.geteuid()!=0:raise PermissionError("root required")
    if OUT.exists():raise RuntimeError("baseline already exists; do not silently reset history")
    sample=valid(SNAP,"HESAB_PHASE1_V1")
    reported=valid(PROVIDER,"HESAB_PROVIDER_BALANCE_REFERENCE_V1")
    now=time.time()
    if not isinstance(sample.get("collected_at"),(int,float)) or not 0<=now-sample["collected_at"]<=150:
        raise RuntimeError("fresh meter snapshot needed")
    rows={}
    for name in NAMES:
        s=sample["servers"][name]
        p=reported["servers"][name]
        if s.get("state")!="ok" or s.get("traffic_state")!="direction_unconfirmed":
            raise RuntimeError(name+" meter not healthy/unconfigured; preserve existing calibrated period")
        rx=s.get("rx_period_gb");tx=s.get("tx_period_gb")
        remaining=p.get("remaining_gb")
        if any(type(x) not in (int,float) or x<0 or x>1e9 for x in (rx,tx,remaining)):
            raise RuntimeError(name+" invalid measured or reported numbers")
        rows[name]={"starting_reported_remaining_gb":remaining,
                    "rx_baseline_gb":rx,"tx_baseline_gb":tx,
                    "baseline_meter_time":sample["collected_at"]}
    data={"format":"HESAB_MAYA_PROVISIONAL_BASELINE_V7",
          "created_at":int(now),"direction_assumption":"rx",
          "provider_observation_time_known":False,
          "alert_eligible":False,"servers":rows}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=OUT.parent,prefix=".meter-baseline-v7-")
    try:
        with os.fdopen(fd,"w",encoding="utf8") as stream:
            json.dump(data,stream,ensure_ascii=False,separators=(",",":"))
            stream.write("\n");stream.flush();os.fsync(stream.fileno())
        os.chmod(tmp,0o640)
        os.replace(tmp,OUT)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    for name,row in rows.items():
        print("PROVISIONAL_BASELINE",name,row["starting_reported_remaining_gb"],
              "GB; RX since_now",row["rx_baseline_gb"],"GB")
    print("BASELINE_SAVED_NO_HISTORICAL_BACKFILL")
if __name__=="__main__":
    try:initialize()
    except Exception as exc:
        print("PROVISIONAL_BASELINE_STOP",type(exc).__name__,str(exc)[:140],file=sys.stderr)
        raise SystemExit(1)
