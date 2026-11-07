#!/usr/bin/env python3
"""HESAB_MAYA_XUI_DAILY_V11
Account host ONLY. Read cumulative per-client up+down via existing local
hesab-maya-live Unix socket; write local SQLite history and a read-only JSON
view. Nothing on Iran nodes, x-ui, traffic routing, quotas or finances changes.

A calendar day's totals contain only observed INTRA-DAY positive deltas;
the interval crossing midnight is deliberately unassigned, never estimated.
A new client's initial cumulative counter is a baseline, NOT daily use.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import ipaddress
import urllib.parse
import fcntl
import json
import os
import socket
import sqlite3
import sys
import tempfile
import time

ROOT=Path("/opt/vpn-control-center")
ROOT_SYNC=ROOT/"maya_extra_sync"
SOCKET=ROOT_SYNC/"live.sock"
DB=ROOT_SYNC/"maya_user_daily_v11.sqlite3"
OUT=ROOT_SYNC/"phase1/maya_user_daily_v11.json"
LOCK=ROOT_SYNC/"maya_user_daily_v11.lock"
SERVERS=("maya1","maya-s3","maya4")
TZ=ZoneInfo("Asia/Tehran")
FORMAT="HESAB_MAYA_XUI_USER_DAILY_V11"
RETENTION=45
SAMPLE_STALE_SECONDS=360
COUNTER_MAX=(1<<63)-1
XUI_CONFIG=Path("/root/.config/hesab-maya-extra.json")
EXPECTED_HOSTS={"maya1":"94.184.4.38",
                "maya-s3":"185.215.230.221",
                "maya4":"5.10.249.206"}

def verify_source_identity():
    """Do not silently count Maya4 users under Maya3 because of stale mapping.
    No secret material printed; no configuration is modified.
    """
    if (XUI_CONFIG.is_symlink() or not XUI_CONFIG.is_file()
        or XUI_CONFIG.stat().st_mode & 0o077):
        raise ValueError("Unsafe or missing XUI source configuration")
    obj=json.loads(XUI_CONFIG.read_text(encoding="utf8"))
    if not isinstance(obj,dict):
        raise ValueError("Invalid XUI host map")
    status={}
    for name,expected in EXPECTED_HOSTS.items():
        item=obj.get(name)
        if not isinstance(item,dict):
            raise ValueError("Unconfigured XUI host: "+name)
        if item.get("server") not in (None,name):
            raise ValueError("XUI identity label mismatch: "+name)
        transport=item.get("transport","https")
        if transport=="ssh":
            address=str(item.get("ssh_host") or "")
            if address!=expected:
                raise ValueError("XUI SSH endpoint mismatch for "+name+
                                 " (check host mapping before daily accounting)")
            status[name]="SSH_EXPECTED_HOST"
        elif transport=="https":
            url=urllib.parse.urlsplit(str(item.get("url") or ""))
            if url.scheme!="https" or not url.hostname:
                raise ValueError("Invalid XUI HTTPS URL: "+name)
            try:
                address=str(ipaddress.ip_address(url.hostname))
                addresses={address}
            except ValueError:
                # Read-only DNS check, never assume a domain belongs to Maya3.
                try:
                    addresses={row[4][0] for row in socket.getaddrinfo(
                        url.hostname,url.port or 443,
                        family=socket.AF_INET,type=socket.SOCK_STREAM)}
                except OSError:
                    addresses=set()
            if addresses!={expected}:
                raise ValueError("XUI HTTPS endpoint identity unverified: "+name)
            status[name]="HTTPS_EXPECTED_IP"
        else:
            raise ValueError("Unsupported XUI transport: "+name)
    return status

DDL="""
CREATE TABLE IF NOT EXISTS last_client_v11 (
 server TEXT NOT NULL, email TEXT NOT NULL, up INTEGER NOT NULL,
 down INTEGER NOT NULL, observed_at INTEGER NOT NULL,
 PRIMARY KEY(server,email)
);
CREATE TABLE IF NOT EXISTS day_v11 (
 server TEXT NOT NULL, day TEXT NOT NULL,
 up INTEGER NOT NULL DEFAULT 0,down INTEGER NOT NULL DEFAULT 0,
 samples INTEGER NOT NULL DEFAULT 0,first_sample INTEGER,
 last_sample INTEGER, reset_count INTEGER NOT NULL DEFAULT 0,
 gap_count INTEGER NOT NULL DEFAULT 0,
 boundary_unassigned INTEGER NOT NULL DEFAULT 0,
 new_baselines INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(server,day)
);
"""

def local_day(ts):
    return datetime.fromtimestamp(ts,TZ).date().isoformat()

def midnight(ts):
    dt=datetime.fromtimestamp(ts,TZ).replace(hour=0,minute=0,second=0,microsecond=0)
    return int(dt.timestamp())

def payload(server):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as conn:
        conn.settimeout(85)
        conn.connect(str(SOCKET))
        conn.sendall((json.dumps({"op":"snapshot","server":server})+"\n").encode("utf8"))
        conn.shutdown(socket.SHUT_WR)
        raw=bytearray()
        while not raw.endswith(b"\n"):
            piece=conn.recv(65536)
            if not piece:break
            raw.extend(piece)
            if len(raw)>4000000:raise ValueError("Snapshot too large")
    if not raw.endswith(b"\n"):raise ValueError("Incomplete live reply")
    doc=json.loads(raw)
    if not isinstance(doc,dict) or doc.get("ok") is not True:
        raise ValueError("XUI live API snapshot unavailable")
    snap=doc.get("snapshot")
    if not isinstance(snap,dict) or snap.get("server")!=server or not isinstance(snap.get("clients"),list):
        raise ValueError("Incorrect live XUI roster source")
    try:
        sampled=datetime.fromisoformat(snap["synced_at"].replace("Z","+00:00"))
    except (ValueError,TypeError,KeyError,AttributeError):
        raise ValueError("Snapshot timestamp invalid")
    if sampled.tzinfo is None:raise ValueError("Naive XUI timestamp")
    ts=int(sampled.timestamp())
    if not -45<=time.time()-ts<=180:raise ValueError("Stale live XUI response")
    rows={}
    for c in snap["clients"]:
        if not isinstance(c,dict):raise ValueError("Invalid client")
        email=str(c.get("email") or "").strip().casefold()
        if not email or len(email)>255 or email in rows:
            raise ValueError("Missing or duplicate XUI user")
        up,down=c.get("up_bytes"),c.get("down_bytes")
        if (type(up) is not int or type(down) is not int
            or not 0<=up<=COUNTER_MAX or not 0<=down<=COUNTER_MAX):
            raise ValueError("Missing/untrusted client usage counters")
        rows[email]=(up,down)
    if not 1<=len(rows)<=5000:raise ValueError("XUI roster empty/oversized")
    return {"server":server,"observed_at":ts,"clients":rows}

def update(con,sample):
    server=sample["server"]
    now=sample["observed_at"];day=local_day(now)
    current=sample["clients"]
    state=con.execute("SELECT email,up,down,observed_at FROM last_client_v11 WHERE server=?",
                      (server,)).fetchall()
    previous={name:(up,down,ts) for name,up,down,ts in state}
    if any(ts>=now for _name,_up,_down,ts in state):
        raise ValueError("XUI sample timestamp did not increase")
    last=con.execute("SELECT last_sample FROM day_v11 WHERE server=? AND day=?",
                     (server,day)).fetchone()
    if last and last[0] is not None and now<=last[0]:
        raise ValueError("Day sample not newer")
    du=dd=0;resets=gaps=boundaries=new_baselines=0
    for email,(up,down) in current.items():
        p=previous.get(email)
        if p is None:
            new_baselines+=1
            continue
        old_up,old_down,last_at=p
        if local_day(last_at)!=day:
            # Crossing midnight means timing of these bytes is unknowable.
            boundaries+=1
            continue
        if now-last_at>15*60:
            # Keep observed delta in today's bucket if monotonic and both
            # ends are today; note risk of unobserved reset/recreation.
            gaps+=1
        if up>=old_up:du+=up-old_up
        else:
            # Reset epoch: new counter is a lower bound since reset.
            du+=up;resets+=1
        if down>=old_down:dd+=down-old_down
        else:
            dd+=down;resets+=1
    con.execute("""INSERT INTO day_v11(server,day,up,down,samples,
       first_sample,last_sample,reset_count,gap_count,boundary_unassigned,new_baselines)
       VALUES(?,?,?,?,1,?,?,?,?,?,?)
       ON CONFLICT(server,day) DO UPDATE SET
        up=day_v11.up+excluded.up,down=day_v11.down+excluded.down,
        samples=day_v11.samples+1,
        last_sample=excluded.last_sample,
        reset_count=day_v11.reset_count+excluded.reset_count,
        gap_count=day_v11.gap_count+excluded.gap_count,
        boundary_unassigned=day_v11.boundary_unassigned+excluded.boundary_unassigned,
        new_baselines=day_v11.new_baselines+excluded.new_baselines""",
       (server,day,du,dd,now,now,resets,gaps,boundaries,new_baselines))
    # Deleting vanished entries prevents accidental inclusion when a previously
    # removed username reappears with a new unrelated cumulative counter.
    con.execute("DELETE FROM last_client_v11 WHERE server=?",(server,))
    con.executemany("INSERT INTO last_client_v11(server,email,up,down,observed_at) VALUES(?,?,?,?,?)",
                     [(server,email,up,down,now) for email,(up,down) in current.items()])
    return {"up":du,"down":dd,"resets":resets,"gap":gaps,"boundary":boundaries,
            "new_baselines":new_baselines}

def collect(today=None,errors=None):
    today=today or local_day(int(time.time()))
    errors=errors or {}
    now=int(time.time())
    records={}
    if not DB.exists():return {"format":FORMAT,"collected_at":now,"day":today,
                                "servers":{s:{"state":"not_measured"} for s in SERVERS}}
    con=sqlite3.connect(f"file:{DB}?mode=ro",uri=True,timeout=5)
    try:
        for server in SERVERS:
            row=con.execute("""SELECT up,down,samples,first_sample,last_sample,
                   reset_count,gap_count,boundary_unassigned,new_baselines
                   FROM day_v11 WHERE server=? AND day=?""",(server,today)).fetchone()
            if row is None:
                records[server]={"state":"not_measured" if server not in errors else "unavailable"}
                continue
            up,down,samples,first,last,resets,gaps,boundary,baselines=row
            age=max(0,now-last)
            near_boundary=(first-midnight(first)<=120)
            # Missing or ambiguous intervals mean total is a measured LOWER
            # BOUND, not an exact full calendar-day reconstruction.
            partial=(not near_boundary or resets>0 or gaps>0 or baselines>0 or boundary>0)
            records[server]={
                "state":"stale" if age>SAMPLE_STALE_SECONDS else "partial" if partial else "measured",
                "up_bytes":up,"down_bytes":down,"total_bytes":up+down,
                "samples":samples,"first_sample_at":first,
                "last_sample_at":last,"age_seconds":age,
                "reset_count":resets,"gap_count":gaps,
                "midnight_boundary_unassigned":boundary,"new_baselines":baselines,
                "complete_day_exact":False,
                "source":"xui_client_up_down_cumulative_deltas"}
            # Even a 'measured' state never claims second-exact 00:00
            # correctness; no day-boundary sample is guaranteed.
    finally:con.close()
    return {"format":FORMAT,"collected_at":now,"day":today,"servers":records}

def atomic(path,data):
    path.parent.mkdir(mode=0o750,exist_ok=True,parents=True)
    fd,tmp=tempfile.mkstemp(prefix=".maya-xui-daily-",dir=str(path.parent))
    try:
        os.fchmod(fd,0o640)
        with os.fdopen(fd,"w",encoding="utf8") as out:
            json.dump(data,out,ensure_ascii=False,separators=(",",":"))
            out.flush();os.fsync(out.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def run(argv):
    check="--check" in argv
    verified=verify_source_identity()
    for name in SERVERS:
        print(name,"SOURCE_HOST",verified[name])
    if check:
        results={}
        with ThreadPoolExecutor(max_workers=3) as pool:
            tasks={name:pool.submit(payload,name) for name in SERVERS}
            for name,job in tasks.items():
                try:
                    snap=job.result(timeout=92)
                    results[name]={"status":"XUI_READ_OK","clients":len(snap["clients"]),
                                   "sampled_at":snap["observed_at"]}
                except Exception as ex:
                    results[name]={"status":"XUI_READ_FAILED","error":type(ex).__name__}
        for name in SERVERS:
            print(name,results[name])
        print("READ_ONLY_XUI_CHECK=YES")
        print("NO_TRAFFIC_OR_FINANCIAL_CHANGES=YES")
        return 0 if all(r["status"]=="XUI_READ_OK" for r in results.values()) else 3
    if os.geteuid()!=0:raise PermissionError("Host root required")
    ROOT_SYNC.mkdir(mode=0o750,parents=True,exist_ok=True)
    with LOCK.open("a+") as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        data={};errors={}
        with ThreadPoolExecutor(max_workers=3) as pool:
            tasks={name:pool.submit(payload,name) for name in SERVERS}
            for name,job in tasks.items():
                try:data[name]=job.result(timeout=92)
                except Exception as ex:
                    errors[name]=type(ex).__name__
        con=sqlite3.connect(DB,timeout=20)
        try:
            con.executescript(DDL)
            with con:
                for name,sample in data.items():
                    try:
                        # Reject all counter/sample discontinuities atomically
                        # per server, without losing other hosts' progress.
                        with con:
                            info=update(con,sample)
                            print(name,"CAPTURED",len(sample["clients"]),
                                  "new_delta_bytes",info["up"]+info["down"],
                                  "uncertain",info["gap"]+info["resets"]+info["boundary"])
                    except (ValueError,sqlite3.DatabaseError) as ex:
                        errors[name]=type(ex).__name__
                cutoff=(datetime.fromtimestamp(time.time(),TZ).date()).toordinal()-RETENTION
                # Keep 45 days of daily history; do not edit preexisting sampler DB.
                import datetime as _date
                oldest=_date.date.fromordinal(cutoff).isoformat()
                con.execute("DELETE FROM day_v11 WHERE day<?",(oldest,))
            os.chmod(DB,0o640)
        finally:con.close()
        status=collect(errors=errors)
        atomic(OUT,status)
        for name in SERVERS:
            r=status["servers"][name]
            print(name,"daily",r["state"],"bytes",r.get("total_bytes","—"),
                  "last",r.get("last_sample_at","—"),
                  "poll",errors.get(name,"ok"))
        print("MAYA_XUI_USER_DAILY_V11_OK; no XUI/tunnel/finance writes")
        return 0 if data else 2

if __name__=="__main__":
    try:sys.exit(run(sys.argv[1:]))
    except (ValueError,OSError,sqlite3.DatabaseError,BlockingIOError) as ex:
        print("MAYA_XUI_DAILY_STOP",type(ex).__name__,str(ex)[:150],file=sys.stderr)
        sys.exit(1)
