#!/usr/bin/env python3
"""HESAB_MAYA_DAILY_NIC_V10
Track RX per Asia/Tehran local calendar day from existing trusted host counters.
No XUI, quota ledger or billing writes. Day may start with a partial-day sample.
"""
import fcntl,json,math,os,tempfile,time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path("/opt/vpn-control-center")
METER=ROOT/"maya_extra_sync/phase1/status.json"
OUT=ROOT/"maya_extra_sync/phase1/daily_nic_v10.json"
STATE=Path("/var/lib/hesab-maya-daily-v10/state.json")
LOCK=Path("/var/lib/hesab-maya-daily-v10/collector.lock")
NAMES=("maya1","maya-s3","maya4")
ZONE=ZoneInfo("Asia/Tehran")
def load(p):
    if p.is_symlink() or not p.is_file() or not 0<p.stat().st_size<=65536:
        raise ValueError("invalid meter file")
    obj=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(obj,dict):raise ValueError("invalid JSON")
    return obj
def atomic(p,value,mode):
    p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,tmp=tempfile.mkstemp(prefix=".daily-v10-",dir=p.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(value,f,ensure_ascii=False,separators=(",",":"))
            f.write("\n");f.flush();os.fsync(f.fileno())
        os.chmod(tmp,mode);os.replace(tmp,p)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
def run():
    if os.geteuid()!=0:raise PermissionError("root only")
    LOCK.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(LOCK,"a+") as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        sample=load(METER)
        if sample.get("format")!="HESAB_PHASE1_V1":raise ValueError("meter format")
        captured=sample.get("collected_at")
        if type(captured) not in (int,float) or not 0<=time.time()-captured<=165:
            raise ValueError("meter sample stale")
        day=datetime.fromtimestamp(captured,ZONE).date().isoformat()
        old=load(STATE) if STATE.is_file() else {}
        result={};storage={"format":"HESAB_MAYA_DAILY_TRACKING_V10","day":day,"servers":{}}
        for name in NAMES:
            fresh=sample.get("servers",{}).get(name,{})
            previous=old.get("servers",{}).get(name,{}) if old.get("day")==day else {}
            if (fresh.get("state")!="ok" or fresh.get("counter_uncertain") is not False or
                fresh.get("traffic_state") not in ("direction_unconfirmed","estimated","verified")):
                result[name]={"state":"unavailable"}
                if previous:storage["servers"][name]=previous
                continue
            counter=fresh.get("rx_period_gb")
            if type(counter) not in (float,int) or not math.isfinite(counter) or not 0<=counter<=1e9:
                result[name]={"state":"invalid"};continue
            if not previous:
                previous={"initial_rx_gb":float(counter),"started_at":int(captured)}
            initial=previous.get("initial_rx_gb")
            if type(initial) not in (float,int) or counter<initial-0.001:
                result[name]={"state":"counter_reset"};storage["servers"][name]=previous;continue
            storage["servers"][name]=previous
            daily=round(max(0,float(counter)-initial),3)
            begun=int(previous["started_at"])
            day_start=datetime.fromtimestamp(begun,ZONE).replace(hour=0,minute=0,second=0,microsecond=0)
            partial=(begun-day_start.timestamp())>180
            result[name]={"state":"ok","rx_today_gb":daily,"day":day,
                          "partial_day":partial,"started_at":begun}
        # Persist a successful observed baseline before rendering.
        atomic(STATE,storage,0o600)
        atomic(OUT,{"format":"HESAB_MAYA_DAILY_NIC_V10","collected_at":int(captured),
                    "day":day,"servers":result},0o640)
        print("MAYA_DAILY_NIC_V10_OK",day,
              " ".join(n+":"+str(result[n].get("rx_today_gb","—")) for n in NAMES))
if __name__=="__main__":
    try:run()
    except Exception as error:
        print("MAYA_DAILY_NIC_V10_FAILED",type(error).__name__,str(error)[:120])
        raise SystemExit(1)
