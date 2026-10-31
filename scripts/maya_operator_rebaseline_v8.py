#!/usr/bin/env python3
"""HESAB_MAYA_OPERATOR_REBASELINE_V8
Explicitly replace historical operator balance and provisional RX starting
counters with a NEW operator-provided snapshot (three Maya servers).

NO XUI writes, finance writes, NIC ledger changes, quota reset, service restart.
Provider observation time is NOT claimed to be meter sample time.
Both old files are backed up and can be restored.
"""
import fcntl
import json
import math
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path("/opt/vpn-control-center")
STATUS=ROOT/"maya_extra_sync/phase1/status.json"
REFERENCE=ROOT/"maya_extra_sync/phase1/provider_balance_reference_v1.json"
BASELINE=ROOT/"maya_extra_sync/phase1/provisional_meter_baseline_v7.json"
LOCK=Path("/var/lib/hesab-maya-net-meter-v2/operator-rebaseline.lock")
BACKUP_ROOT=Path("/root")
NAMES=("maya1","maya-s3","maya4")

def read(path, fmt):
    if not path.is_file() or path.is_symlink() or not 0<path.stat().st_size<=65536:
        raise ValueError("unavailable/unsafe file: "+path.name)
    data=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data,dict) or data.get("format")!=fmt:
        raise ValueError("invalid file format: "+path.name)
    return data

def number(txt):
    try:
        value=float(txt)
    except (TypeError,ValueError) as ex:
        raise ValueError("balance must be a decimal number") from ex
    if not math.isfinite(value) or not 0<=value<=1_000_000_000:
        raise ValueError("invalid balance")
    if round(value,3)!=value:
        raise ValueError("max 3 decimal places supported")
    return value

def atomic(path, data):
    fd,name=tempfile.mkstemp(prefix=".operator-rebase-",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(data,stream,ensure_ascii=False,separators=(",",":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name,0o640)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def execute(raw):
    if os.geteuid()!=0:raise PermissionError("root required")
    if len(raw)!=3:raise ValueError("expected Maya1, Maya3 and Maya4 remaining GB")
    amounts={name:number(txt) for name,txt in zip(NAMES,raw)}
    LOCK.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(LOCK,"a+") as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        snapshot=read(STATUS,"HESAB_PHASE1_V1")
        old_reference=read(REFERENCE,"HESAB_PROVIDER_BALANCE_REFERENCE_V1")
        old_baseline=read(BASELINE,"HESAB_MAYA_PROVISIONAL_BASELINE_V7")
        if old_baseline.get("direction_assumption")!="rx" or old_baseline.get("alert_eligible") is not False:
            raise ValueError("existing baseline is not RX-only provisional")
        if old_reference.get("provider_observed_at_known") is not False:
            raise ValueError("unexpected provider observation metadata")
        now=time.time()
        captured=snapshot.get("collected_at")
        if type(captured) not in (int,float) or not 0<=now-captured<=120:
            raise ValueError("stale meter snapshot; run systemctl start hesab-maya-net-meter-v2.service")
        rows={}
        for name in NAMES:
            server=(snapshot.get("servers") or {}).get(name,{})
            if (server.get("state")!="ok" or
                server.get("traffic_state")!="direction_unconfirmed" or
                server.get("counter_uncertain") is not False):
                raise ValueError(name+": meter not healthy, has reset uncertainty or already calibrated")
            rx=server.get("rx_period_gb")
            tx=server.get("tx_period_gb")
            if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1e9
                   for v in (rx,tx)):
                raise ValueError(name+": missing/invalid NIC counters")
            rows[name]={
                "starting_reported_remaining_gb":amounts[name],
                "rx_baseline_gb":rx,"tx_baseline_gb":tx,
                "baseline_meter_time":captured
            }
        stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup=BACKUP_ROOT/("hesab-maya-v8-rebaseline-"+stamp+"-"+str(os.getpid()))
        backup.mkdir(mode=0o700)
        # Preserve BOTH earlier input and baseline so operator can audit changes.
        oldrefbytes=REFERENCE.read_bytes()
        oldbasebytes=BASELINE.read_bytes()
        for filename,content in (("provider-reference-before.json",oldrefbytes),
                                 ("provisional-baseline-before.json",oldbasebytes)):
            file=backup/filename
            with open(file,"xb") as stream:
                stream.write(content)
                stream.flush();os.fsync(stream.fileno())
            file.chmod(0o600)
        new_ref={
            "format":"HESAB_PROVIDER_BALANCE_REFERENCE_V1",
            "recorded_at":int(now),
            "provider_observed_at_known":False,
            "source":"operator_report",
            "servers":{name:{"remaining_gb":value} for name,value in amounts.items()}
        }
        new_base={
            "format":"HESAB_MAYA_PROVISIONAL_BASELINE_V7",
            "created_at":int(now),
            "direction_assumption":"rx",
            "provider_observation_time_known":False,
            "alert_eligible":False,
            "rebaseline_reason":"fresh_operator_report_2026-10-31",
            "servers":rows
        }
        try:
            atomic(REFERENCE,new_ref)
            atomic(BASELINE,new_base)
        except Exception:
            # Restore old coherent pair if either write fails.
            try:
                fd,tmp=tempfile.mkstemp(dir=REFERENCE.parent,prefix=".restore-ref-")
                with os.fdopen(fd,"wb") as f:f.write(oldrefbytes)
                os.chmod(tmp,0o640);os.replace(tmp,REFERENCE)
                fd,tmp=tempfile.mkstemp(dir=BASELINE.parent,prefix=".restore-base-")
                with os.fdopen(fd,"wb") as f:f.write(oldbasebytes)
                os.chmod(tmp,0o640);os.replace(tmp,BASELINE)
            except OSError:
                print("ROLLBACK_FAILED: restore from "+str(backup),file=sys.stderr)
            raise
        # Verify persisted amounts, no changes to NIC usage state.
        checked=read(REFERENCE,"HESAB_PROVIDER_BALANCE_REFERENCE_V1")
        baseline=read(BASELINE,"HESAB_MAYA_PROVISIONAL_BASELINE_V7")
        for name in NAMES:
            assert checked["servers"][name]["remaining_gb"]==amounts[name]
            assert baseline["servers"][name]["starting_reported_remaining_gb"]==amounts[name]
        print("OPERATOR_REBASELINE_V8_OK")
        for name in NAMES:
            print("MAYA",name,"REPORTED_REMAINING_GB",amounts[name],
                  "RX_BASELINE_GB",rows[name]["rx_baseline_gb"],
                  "METER_SAMPLE_AT_UNIX",int(captured))
        print("TOTAL_REPORTED_GB",round(sum(amounts.values()),3))
        print("BILLING_DIRECTION_ASSUMED=RX_UNVERIFIED")
        print("PROVIDER_SNAPSHOT_TIMESTAMP_UNKNOWN=TRUE")
        print("AUTOMATED_10GB_ALERTS_FROM_THIS_ESTIMATE=DISABLED")
        print("HISTORICAL_REFERENCE_AND_BASELINE_BACKUP="+str(backup))

def main():
    if len(sys.argv)!=5 or sys.argv[1]!="--apply":
        raise ValueError("Usage: script --apply MAYA1_REMAINING_GB MAYA3_REMAINING_GB MAYA4_REMAINING_GB")
    execute(sys.argv[2:])

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("OPERATOR_REBASELINE_V8_STOP",type(exc).__name__,str(exc)[:150],file=sys.stderr)
        raise SystemExit(1)
