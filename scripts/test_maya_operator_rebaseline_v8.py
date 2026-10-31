#!/usr/bin/env python3
"""Offline validation for V8 operator-initiated balance refresh.
No VPS access, no provider calls, no production writes.
"""
import contextlib
import importlib.util
import io
import json
import tempfile
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location(
    "rebaseline_v8",HERE/"maya_operator_rebaseline_v8.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def put(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data),encoding="utf-8")

with tempfile.TemporaryDirectory() as root:
    dir=Path(root)
    m.STATUS=dir/"live_status.json"
    m.REFERENCE=dir/"provider_ref.json"
    m.BASELINE=dir/"baseline.json"
    m.LOCK=dir/"lock"/"write.lock"
    m.BACKUP_ROOT=dir/"backups"
    m.BACKUP_ROOT.mkdir()
    m.os.geteuid=lambda:0
    sample={"format":"HESAB_PHASE1_V1","collected_at":int(time.time()),
       "servers":{n:{"state":"ok","traffic_state":"direction_unconfirmed",
           "counter_uncertain":False,"rx_period_gb":rx,
           "tx_period_gb":tx}
           for n,rx,tx in (("maya1",100.5,99.2),
                           ("maya-s3",205.25,203.1),
                           ("maya4",26.9,25.5))}}
    previous={
      "format":"HESAB_PROVIDER_BALANCE_REFERENCE_V1",
      "recorded_at":int(time.time())-86400,
      "provider_observed_at_known":False,
      "source":"operator_report",
      "servers":{"maya1":{"remaining_gb":144},"maya-s3":{"remaining_gb":189},
                 "maya4":{"remaining_gb":144}}}
    oldbaseline={
       "format":"HESAB_MAYA_PROVISIONAL_BASELINE_V7",
       "created_at":int(time.time())-8000,
       "direction_assumption":"rx","provider_observation_time_known":False,
       "alert_eligible":False,
       "servers":{"maya1":{"rx_baseline_gb":10},
                  "maya-s3":{"rx_baseline_gb":20},
                  "maya4":{"rx_baseline_gb":2}}}
    put(m.STATUS,sample);put(m.REFERENCE,previous);put(m.BASELINE,oldbaseline)
    with contextlib.redirect_stdout(io.StringIO()):
        m.execute(["82","140","137.66"])
    newer=json.loads(m.REFERENCE.read_text())
    baseline=json.loads(m.BASELINE.read_text())
    assert [newer["servers"][n]["remaining_gb"] for n in m.NAMES]==[82,140,137.66]
    assert [baseline["servers"][n]["starting_reported_remaining_gb"]
            for n in m.NAMES]==[82,140,137.66]
    assert [baseline["servers"][n]["rx_baseline_gb"]
            for n in m.NAMES]==[100.5,205.25,26.9]
    assert baseline["alert_eligible"] is False
    assert baseline["provider_observation_time_known"] is False
    backups=list(m.BACKUP_ROOT.glob("hesab-maya-v8-rebaseline-*"))
    assert len(backups)==1
    assert json.loads((backups[0]/"provider-reference-before.json").read_text())==previous
    assert json.loads((backups[0]/"provisional-baseline-before.json").read_text())==oldbaseline
    unchanged=(m.REFERENCE.read_bytes(),m.BASELINE.read_bytes())
    # Refuse to reset or overwrite good data on a counter reboot/rollover.
    sample["servers"]["maya-s3"]["counter_uncertain"]=True
    put(m.STATUS,sample)
    try:
        m.execute(["75","120","130"])
    except ValueError as exc:
        assert "maya-s3" in str(exc)
    else:
        raise AssertionError("uncertain counter must fail closed")
    assert unchanged==(m.REFERENCE.read_bytes(),m.BASELINE.read_bytes())
    sample["servers"]["maya-s3"]["counter_uncertain"]=False
    sample["collected_at"]=int(time.time())-1000
    put(m.STATUS,sample)
    try:
        m.execute(["75","120","130"])
    except ValueError as exc:
        assert "stale" in str(exc)
    else:
        raise AssertionError("stale counter must fail closed")
    assert unchanged==(m.REFERENCE.read_bytes(),m.BASELINE.read_bytes())
    print("V8_NEW_PROVIDER_BALANCES_RX_COUNTER_BASELINE_BACKUP_AND_FAILCLOSED_TEST_PASS")
