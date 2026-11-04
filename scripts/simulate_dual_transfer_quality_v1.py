#!/usr/bin/env python3
"""Stage-2 MOCK ONLY: classify recorded download test fixtures.
No network or subprocess functionality. Not installed by the production installer.
"""
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
CORE=ROOT/"scripts/maya_dual_passive_quality_v1.py"
FIXTURE=ROOT/"fixtures/maya3_mieru_degraded_20261104.json"

def analyse():
    if not FIXTURE.is_file():
        raise ValueError("Missing offline fixture")
    spec=importlib.util.spec_from_file_location("dual_passive_quality_core",CORE)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    doc=json.loads(FIXTURE.read_text(encoding="utf8"))
    if doc.get("case")!="Maya3 Mieru HTTPS connectivity passed while transfer failed":
        raise ValueError("Fixture mismatch")
    results={}
    for record in doc["transfer_tests"]:
        path=record["path"]
        if path not in ("backhaul","mieru","haproxy","mieru_replacement"):
            raise ValueError("Unexpected mock path")
        result=mod.transfer_test(record)
        if not result:
            raise ValueError("Invalid mock transfer result")
        results[path]={"state":result["state"],"reason":result["reason"],
                       "http_status":result["http_status"],
                       "exit_code":result["exit_code"],
                       "requested":result["requested_bytes"],
                       "received":result["received_bytes"],
                       "duration_ms":result["duration_ms"],
                       "bytes_per_second":result["bytes_per_second"]}
    return {"mode":"offline_mock_only","server":"maya-s3","results":results,
            "network_requests":0,"production_changes":0}

if __name__=="__main__":
    print(json.dumps(analyse(),ensure_ascii=False,indent=2))
