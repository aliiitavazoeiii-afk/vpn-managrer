#!/usr/bin/env python3
"""HESAB_MAYA_USAGE_SAMPLER_V1: local SQLite sampling only, no finance/XUI mutations.
Per-client XUI cumulative counters -> daily deltas and 5m average throughput.
First observation is a baseline, NOT historical usage. Retain last 45 days.
"""
import json,os,socket,sqlite3,sys,time
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
BASE=Path("/opt/vpn-control-center/maya_extra_sync")
DB=BASE/"usage_v1.sqlite3"
SOCK=BASE/"live.sock"
SERVERS=("maya1","maya-s3","maya4")
TEHRAN=ZoneInfo("Asia/Tehran")

def pull(server):
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(80)
        s.connect(str(SOCK))
        s.sendall((json.dumps({"op":"snapshot","server":server})+"\n").encode())
        s.shutdown(socket.SHUT_WR)
        data=bytearray()
        while not data.endswith(b"\n"):
            part=s.recv(65536)
            if not part:break
            data+=part
            if len(data)>3000000:raise RuntimeError("Oversized snapshot")
    if not data.endswith(b"\n"):raise RuntimeError("Partial reply")
    doc=json.loads(data)
    if doc.get("ok") is not True:raise RuntimeError(str(doc.get("error") or "No snapshot")[:150])
    o=doc["snapshot"]
    if o.get("server")!=server or not isinstance(o.get("clients"),list):
        raise RuntimeError("Invalid snapshot")
    return o["clients"]

DDL="""
CREATE TABLE IF NOT EXISTS client_state(
 server TEXT NOT NULL, email TEXT NOT NULL,
 up INTEGER NOT NULL, down INTEGER NOT NULL, measured_at INTEGER NOT NULL,
 rate_bps REAL NOT NULL DEFAULT 0,
 PRIMARY KEY(server,email)
);
CREATE TABLE IF NOT EXISTS daily_usage(
 server TEXT NOT NULL,email TEXT NOT NULL, local_day TEXT NOT NULL,
 up INTEGER NOT NULL DEFAULT 0,down INTEGER NOT NULL DEFAULT 0,
 sample_count INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(server,email,local_day)
);
CREATE INDEX IF NOT EXISTS daily_usage_by_day ON daily_usage(server,local_day);
CREATE TABLE IF NOT EXISTS client_access_state(
 server TEXT NOT NULL, email TEXT NOT NULL,
 client_enabled INTEGER NOT NULL, inbound_enabled INTEGER NOT NULL,
 effective_enabled INTEGER NOT NULL, quota_bytes INTEGER NOT NULL,
 used_bytes INTEGER NOT NULL, traffic_expiry_ms INTEGER NOT NULL,
 sampled_at INTEGER NOT NULL,
 PRIMARY KEY(server,email)
);
CREATE INDEX IF NOT EXISTS client_access_sample_by_server
  ON client_access_state(server,sampled_at);
"""

def record(con,server,clients,now):
    day=datetime.fromtimestamp(now,timezone.utc).astimezone(TEHRAN).date().isoformat()
    count=0
    for c in clients:
        email=str(c.get("email") or "").strip().casefold()
        if not email:continue
        up=max(0,int(c.get("up_bytes") or 0))
        down=max(0,int(c.get("down_bytes") or 0))
        prior=con.execute(
            "SELECT up,down,measured_at FROM client_state WHERE server=? AND email=?",
            (server,email)).fetchone()
        du=dd=0;rate=0.0
        if prior is not None:
            # A reset starts a new counter epoch. The full new value since reset
            # is known, not guessed; initial observation still stays baseline-only.
            du=max(0,up-prior[0]) if up>=prior[0] else up
            dd=max(0,down-prior[1]) if down>=prior[1] else down
            interval=max(1,now-prior[2])
            if 0<interval<=3600:
                rate=(du+dd)/interval
            else:
                # Gap too large: samples cannot tell which day got that traffic.
                du=dd=0
        con.execute("""INSERT INTO client_state(server,email,up,down,measured_at,rate_bps)
          VALUES(?,?,?,?,?,?) ON CONFLICT(server,email) DO UPDATE SET
          up=excluded.up,down=excluded.down,measured_at=excluded.measured_at,
          rate_bps=excluded.rate_bps""",(server,email,up,down,now,rate))
        con.execute("""INSERT INTO daily_usage(server,email,local_day,up,down,sample_count)
          VALUES(?,?,?,?,?,1) ON CONFLICT(server,email,local_day) DO UPDATE SET
          up=daily_usage.up+excluded.up,down=daily_usage.down+excluded.down,
          sample_count=daily_usage.sample_count+1""",(server,email,day,du,dd))
        # Same snapshot already pulled for usage: ZERO extra XUI requests.
        # Access-state samples are observational; the billing workflow is never mutated.
        con.execute("""INSERT INTO client_access_state(
          server,email,client_enabled,inbound_enabled,effective_enabled,
          quota_bytes,used_bytes,traffic_expiry_ms,sampled_at)
          VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(server,email) DO UPDATE SET
          client_enabled=excluded.client_enabled,
          inbound_enabled=excluded.inbound_enabled,
          effective_enabled=excluded.effective_enabled,
          quota_bytes=excluded.quota_bytes,
          used_bytes=excluded.used_bytes,
          traffic_expiry_ms=excluded.traffic_expiry_ms,
          sampled_at=excluded.sampled_at""",(
            server,email,
            int(bool(c.get("client_enabled",c.get("enabled",False)))),
            int(bool(c.get("inbound_enabled",True))),
            int(bool(c.get("enabled",False))),
            max(0,int(c.get("quota_bytes") or 0)),
            up+down,
            max(0,int(c.get("traffic_expiry_ms") or 0)),now))
        count+=1
    return count

def main():
    check="--check" in sys.argv
    snaps={}
    for name in SERVERS:
        try:
            snaps[name]=pull(name)
            print(name,"LIVE",len(snaps[name]))
        except Exception as e:
            print(name,"UNAVAILABLE",str(e)[:130],file=sys.stderr)
    if check:
        print("READ_ONLY_CHECK; no usage DB touched.")
        return 0 if len(snaps)==len(SERVERS) else 1
    if not snaps:raise RuntimeError("No live servers available")
    BASE.mkdir(parents=True,exist_ok=True,mode=0o750)
    import fcntl
    lockpath=BASE/"usage_v1.lock"
    with open(lockpath,"a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        con=sqlite3.connect(str(DB),timeout=25)
        try:
            con.executescript(DDL)
            ts=int(time.time())
            with con:
                for name,clients in snaps.items():
                    # A vanished XUI username is no longer an active connection.
                    # Remove its old status rows before recording the current roster.
                    con.execute("DELETE FROM client_access_state WHERE server=?",(name,))
                    print(name,"RECORDED",record(con,name,clients,ts))
                cutoff=(datetime.fromtimestamp(ts,timezone.utc).astimezone(TEHRAN).date()-
                        timedelta(days=45)).isoformat()
                con.execute("DELETE FROM daily_usage WHERE local_day<?",(cutoff,))
            os.chmod(DB,0o640)
        finally:con.close()
    print("USAGE_SAMPLE_OK; no XUI/client/payment records changed")
    return 0

if __name__=="__main__":
    try:sys.exit(main())
    except Exception as exc:
        print("USAGE_STOP",type(exc).__name__,str(exc)[:170],file=sys.stderr)
        sys.exit(1)
