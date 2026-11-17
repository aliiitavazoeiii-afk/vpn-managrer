#!/usr/bin/env python3
"""No external services: verify Maya owner mobile alert math and strict fail-closed semantics."""
import ast
import math
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
source = (ROOT/"patches/sms_maya_low_traffic_v12.py").read_text(encoding="utf8")
tree = ast.parse(source)
functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and
             node.name in ("_ma12_nonnegative", "_ma12_calculate")]
namespace = {
    "_ma12_math": math,
    "_MA12_NAMES": ("maya1", "maya-s3", "maya4"),
    "_MA12_THRESHOLD_GB": 10.0,
}
exec(compile(ast.Module(body=functions, type_ignores=[]), "<offline-calculation>", "exec"), namespace)
calc = namespace["_ma12_calculate"]
now = int(time.time())
base = {
    "format": "HESAB_MAYA_PROVISIONAL_BASELINE_V7",
    "created_at": now-600,
    "direction_assumption": "rx",
    "alert_eligible": False,
    "provider_observation_time_known": False,
    "servers": {
        n: {"rx_baseline_gb": 100.0,
            "starting_reported_remaining_gb": 10.1,
            "baseline_meter_time": now-600} for n in namespace["_MA12_NAMES"]
    }
}
meter = {
    "format": "HESAB_PHASE1_V1",
    "collected_at": now-5,
    "servers": {
        n: {"state": "ok", "traffic_state": "direction_unconfirmed",
            "counter_uncertain": False, "rx_period_gb": 100.1}
        for n in namespace["_MA12_NAMES"]
    }
}
out = calc(now,base,meter,{n:0 for n in namespace["_MA12_NAMES"]})
assert all(row["state"]=="provisional" for row in out.values())
assert out["maya1"]["remaining_gb"]==10.0 and not out["maya1"]["below_10gb"]
meter["servers"]["maya-s3"]["rx_period_gb"]=100.2
out = calc(now,base,meter,{})
assert out["maya-s3"]["remaining_gb"]==9.9 and out["maya-s3"]["below_10gb"]
out = calc(now,base,meter,{"maya-s3":100})
assert out["maya-s3"]["remaining_gb"]==109.9 and not out["maya-s3"]["below_10gb"]
meter["servers"]["maya4"]["state"]="unavailable"
assert calc(now,base,meter,{})["maya4"]["remaining_gb"] is None
meter["servers"]["maya4"]["state"]="ok"
meter["servers"]["maya4"]["counter_uncertain"]=True
assert calc(now,base,meter,{})["maya4"]["state"]=="unavailable"
meter["servers"]["maya4"]["counter_uncertain"]=False
meter["servers"]["maya4"]["rx_period_gb"]=99.9
assert calc(now,base,meter,{})["maya4"]["state"]=="unavailable"
meter["servers"]["maya4"]["rx_period_gb"]=100.1
meter["collected_at"]=now-250
try:
    calc(now,base,meter,{})
except ValueError:
    pass
else:
    raise AssertionError("stale data must fail closed")
assert "_ma12_owner_low_traffic" in source
assert "require_token(x_sms_gateway_token)" in source
assert "hesab_maya_traffic_topups_v9" in source
print("MAYA_LOW_TRAFFIC_V12_OFFLINE_MATH_AND_SECURITY=PASS")
