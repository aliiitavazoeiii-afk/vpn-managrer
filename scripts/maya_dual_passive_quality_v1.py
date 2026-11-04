#!/usr/bin/env python3
"""Passive Dual quality analysis for Hesab Control Room.

Reads ONLY the existing account-side Dual V1 JSON snapshot; no remote access,
sockets, curl, 'dual health', HAProxy commands, or tunnel configuration changes.
Records a bounded local history. Per-backend throughput is unavailable until
trusted counters are actually present in source snapshots. Never fabricates it.
"""
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT=Path("/opt/vpn-control-center")
INPUT=ROOT/"maya_extra_sync/dual_hourly_v1.json"
STORE=ROOT/"maya_extra_sync/dual_quality_v1"
HISTORY=STORE/"history.json"
OUTPUT=STORE/"status.json"
LOCK=STORE/"lock"
FORMAT="HESAB_DUAL_PASSIVE_QUALITY_V1"
SOURCE_FORMAT="HESAB_DUAL_HOURLY_V1"
SERVERS=("maya1","maya-s3","maya4")
ROLES=("backhaul","mieru")
MAX_HISTORY=720
MAX_SNAPSHOT_BYTES=16000
STALE_AFTER=4500
# Counters can only be used when optional future snapshots explicitly declare
# origin/scope/epoch. Original V1 snapshots do NOT contain these fields.
COUNTER_SOURCE="haproxy_stats_readonly"
COUNTER_SCOPE="backend"
COUNTER_FIELDS=("bytes_in","bytes_out","sessions_total","sessions_current",
                "connection_errors_total","response_errors_total")
MIN_WINDOW=15
MAX_WINDOW=4500

def is_nonnegative_int(v, upper=2**64-1):
    return type(v) is int and 0<=v<=upper

def validate_counters(value):
    if not isinstance(value,dict):
        return None
    if (value.get("source")!=COUNTER_SOURCE or value.get("scope")!=COUNTER_SCOPE
        or not isinstance(value.get("epoch"),str) or not 1<=len(value["epoch"])<=100):
        return None
    for key in COUNTER_FIELDS:
        if not is_nonnegative_int(value.get(key)):
            return None
    return {k:value[k] for k in COUNTER_FIELDS}|{
        "source":COUNTER_SOURCE,"scope":COUNTER_SCOPE,"epoch":value["epoch"]}

def validate_snapshot(doc, now):
    if not isinstance(doc,dict) or doc.get("format")!=SOURCE_FORMAT:
        raise ValueError("Unknown source snapshot")
    ts=doc.get("collected_at")
    if not is_nonnegative_int(ts,2**40) or not -60<=now-ts<=7*86400:
        raise ValueError("Bad source timestamp")
    raw=doc.get("servers")
    if not isinstance(raw,dict):
        raise ValueError("Missing servers")
    entries={}
    for sid in SERVERS:
        data=raw.get(sid,{})
        if not isinstance(data,dict):
            data={}
        state=data.get("state","unavailable")
        if state not in ("ok","stale","unavailable","not_configured"):
            state="unavailable"
        out={"state":state,"paths":{}}
        for role in ROLES:
            rawpath=data.get("paths",{}).get(role,{}) if isinstance(data.get("paths"),dict) else {}
            if not isinstance(rawpath,dict):
                rawpath={}
            health=rawpath.get("state")
            if health not in ("healthy","down","stale","unknown"):
                health="unknown"
            ip=rawpath.get("ip")
            if not isinstance(ip,str) or len(ip)>45:
                ip=None
            passed=rawpath.get("https_passed")
            total=rawpath.get("https_total")
            if not(is_nonnegative_int(passed,50) and is_nonnegative_int(total,50)
                   and passed<=total):
                passed=total=None
            avg=rawpath.get("https_avg_ms")
            if not is_nonnegative_int(avg,120000):
                avg=None
            out["paths"][role]={
                "ip":ip,"health":health,"https_passed":passed,
                "https_total":total,"https_avg_ms":avg,
                "counters":validate_counters(rawpath.get("haproxy_counters")),
            }
        entries[sid]=out
    return {"at":ts,"servers":entries}

def deltas(previous,current,dt):
    """Valid signed rate only between same process epochs and monotonic counters."""
    if not previous or not current:
        return None
    if previous["source"]!=current["source"] or previous["scope"]!=current["scope"]:
        return None
    if previous["epoch"]!=current["epoch"] or not MIN_WINDOW<=dt<=MAX_WINDOW:
        return {"state":"reset_or_gap","seconds":dt}
    increasing=("bytes_in","bytes_out","sessions_total",
                "connection_errors_total","response_errors_total")
    if any(current[k]<previous[k] for k in increasing):
        return {"state":"counter_reset","seconds":dt}
    changes={k:current[k]-previous[k] for k in increasing}
    return {
        "state":"ok","seconds":dt,
        "bytes_in_delta":changes["bytes_in"],
        "bytes_out_delta":changes["bytes_out"],
        "bytes_in_per_s":round(changes["bytes_in"]/dt,2),
        "bytes_out_per_s":round(changes["bytes_out"]/dt,2),
        "new_connections":changes["sessions_total"],
        "active_connections":current["sessions_current"],
        "connection_errors_delta":changes["connection_errors_total"],
        "response_errors_delta":changes["response_errors_total"],
    }

def transfer_test(test):
    """Offline/imported measured evidence only; never executes a download."""
    if not isinstance(test,dict) or test.get("source")!="explicit_transfer_test_v1":
        return None
    keys=("requested_bytes","received_bytes","duration_ms","ttfb_ms",
          "http_status","exit_code","at")
    if any(not is_nonnegative_int(test.get(k),2**40) for k in keys):
        return None
    if not(0<test["requested_bytes"]<=2**30
           and 0<=test["received_bytes"]<=test["requested_bytes"]
           and 1<=test["duration_ms"]<=600000
           and test["ttfb_ms"]<=test["duration_ms"]
           and 100<=test["http_status"]<=599 and 0<=test["exit_code"]<=255):
        return None
    full=(test["exit_code"]==0 and test["http_status"]==200
          and test["received_bytes"]==test["requested_bytes"])
    return {
        "state":"completed" if full else "failed",
        "http_status":test["http_status"],
        "requested_bytes":test["requested_bytes"],
        "received_bytes":test["received_bytes"],
        "duration_ms":test["duration_ms"],
        "ttfb_ms":test["ttfb_ms"],
        "exit_code":test["exit_code"],
        "bytes_per_second":round(test["received_bytes"]*1000/test["duration_ms"],2),
        "at":test["at"],
        "reason":("timeout" if test["exit_code"]==28
                  else "incomplete_or_error" if not full else "complete"),
    }

def quality_label(windows, tests=None):
    """Conservative; low traffic alone never proves tunnel failure."""
    if tests and tests.get("state")=="failed":
        return {"state":"confirmed_transfer_test_failure",
                "confidence":"high","reason":"explicit_download_failed"}
    valid=[w for w in windows if w and w.get("state")=="ok"]
    if len(valid)<8:
        return {"state":"not_measured","confidence":"none","reason":"insufficient_valid_counters"}
    # Baseline must be independent of the latest three windows.
    baseline=[w["bytes_out_per_s"] for w in valid[:-3]
              if w["new_connections"]>=20 and w["active_connections"]>=20
              and w["bytes_out_per_s"]>=65536]
    recent=valid[-3:]
    if (len(baseline)>=5 and len(recent)==3
        and all(w["new_connections"]>=20 and w["active_connections"]>=20 for w in recent)):
        median=statistics.median(baseline)
        if (median>=65536 and all(w["bytes_out_per_s"]<median*0.10
                                  for w in recent)):
            return {"state":"suspected_degradation",
                    "confidence":"medium","reason":"three_low_windows_vs_own_baseline"}
        if all(w["bytes_out_per_s"]>=median*0.4 for w in recent):
            return {"state":"normal_by_observed_counters","confidence":"limited",
                    "reason":"sufficient_recent_and_baseline_samples"}
    return {"state":"inconclusive","confidence":"low","reason":"counter_trends_not_decisive"}

def summarise(history, now):
    ordered=sorted(history,key=lambda row:row["at"])
    latest=ordered[-1]
    old=now-latest["at"]>STALE_AFTER
    output={"format":FORMAT,"generated_at":now,
            "source_at":latest["at"],"source_stale":old,
            "sampling_note":"Existing hourly/manual Dual V1 snapshots only",
            "servers":{},"alerts":[]}
    for sid in SERVERS:
        current=latest["servers"][sid]
        server={"state":current["state"],"paths":{}}
        for role in ROLES:
            value=current["paths"][role]
            prior=None; windows=[];trend=[]
            for row in ordered:
                item=row["servers"][sid]["paths"][role]
                if item["counters"] and prior and prior["counters"]:
                    w=deltas(prior["counters"],item["counters"],row["at"]-prior["at"])
                    if w and w.get("state")=="ok":
                        windows.append(w)
                        trend.append({"at":row["at"],"bytes_out_per_s":w["bytes_out_per_s"]})
                    elif w:
                        trend.append({"at":row["at"],"bytes_out_per_s":None})
                prior={"at":row["at"],"counters":item["counters"]}
            q=quality_label(windows)
            if old or server["state"]!="ok" or value["health"]=="stale":
                q={"state":"stale" if old or value["health"]=="stale" else "not_measured",
                   "confidence":"none","reason":"stale_or_no_source"}
            if value["health"]=="down" and not old and server["state"]=="ok":
                q={"state":"path_down","confidence":"connectivity",
                   "reason":"controller_connectivity_down_not_transfer_test"}
            rate=windows[-1] if windows else None
            server["paths"][role]={
                "ip":value["ip"],"health":value["health"] if not old else "stale",
                "https_passed":value["https_passed"],"https_total":value["https_total"],
                "https_avg_ms":value["https_avg_ms"],
                "quality":q,"latest_counters":rate,
                "counter_samples":len(windows),
                "trend":trend[-48:],
                "last_transfer_test":None,
                "last_quality_evaluated_at":now if not old else None,
            }
            if q["state"]=="suspected_degradation":
                output["alerts"].append({"server":sid,"role":role,
                   "kind":"suspected_degradation","confidence":"medium",
                   "reason":q["reason"]})
        output["servers"][sid]=server
    return output

def atomic(path,content):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o750)
    fd,temp=tempfile.mkstemp(prefix=".quality-",dir=str(path.parent))
    try:
        os.fchmod(fd,0o640)
        with os.fdopen(fd,"w",encoding="utf8") as stream:
            json.dump(content,stream,ensure_ascii=False,separators=(",",":"))
            stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def run():
    if os.geteuid()!=0:
        raise PermissionError("Root required for local snapshots")
    STORE.mkdir(mode=0o750,parents=True,exist_ok=True)
    with LOCK.open("a+") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if INPUT.is_symlink() or not INPUT.is_file() or INPUT.stat().st_size>MAX_SNAPSHOT_BYTES:
            raise ValueError("Missing or invalid local snapshot")
        payload=INPUT.read_bytes()
        doc=validate_snapshot(json.loads(payload),int(time.time()))
        history=[]
        if HISTORY.is_file():
            if HISTORY.is_symlink() or HISTORY.stat().st_size>3000000:
                raise ValueError("Unsafe or oversized history")
            data=json.loads(HISTORY.read_text(encoding="utf8"))
            if data.get("format")!=FORMAT or not isinstance(data.get("records"),list):
                raise ValueError("Invalid history format")
            history=data["records"]
        # 1-second timestamps can coincide; use content digest for identity.
        digest=hashlib.sha256(payload).hexdigest()
        doc["digest"]=digest
        if not history or history[-1].get("digest")!=digest:
            # Collector may run in same second; preserve distinct samples
            # without inventing a positive dt for counter calculations.
            history.append(doc)
        history=sorted(history,key=lambda row:row["at"])[-MAX_HISTORY:]
        atomic(HISTORY,{"format":FORMAT,"records":history})
        atomic(OUTPUT,summarise(history,int(time.time())))
        print("DUAL_QUALITY_PASSIVE_OK sample_count="+str(len(history))+
              " valid_traffic_counters="+str(sum(
                1 for sid in SERVERS for role in ROLES
                if any(w["servers"][sid]["paths"][role]["counters"] for w in history))))
if __name__=="__main__":
    try:run()
    except (OSError,ValueError,KeyError,TypeError,PermissionError) as exc:
        print("DUAL_QUALITY_PASSIVE_STOP",type(exc).__name__)
        sys.exit(1)
