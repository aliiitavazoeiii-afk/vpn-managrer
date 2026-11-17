# HESAB_MAYA_LOW_TRAFFIC_ALERT_V12
# Dedicated read-only, gateway-token-protected telemetry endpoint for the owner's
# existing manual WhatsApp Android app. NO SMS jobs, customer data, XUI or VPN actions.
# Mounted via an existing private HTTPS /sms-gateway/ reverse proxy.
import json as _ma12_json
import math as _ma12_math
import time as _ma12_time
from pathlib import Path as _ma12_Path
from fastapi import Header as _ma12_Header, HTTPException as _ma12_HTTP
from fastapi.responses import JSONResponse as _ma12_JSON

_MA12_ROOT = _ma12_Path("/srv/maya-live/phase1")
_MA12_NAMES = ("maya1", "maya-s3", "maya4")
_MA12_THRESHOLD_GB = 10.0


def _ma12_document(name, expected_format):
    path = _MA12_ROOT / name
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size < 80000:
        raise ValueError("Maya telemetry missing")
    doc = _ma12_json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or doc.get("format") != expected_format:
        raise ValueError("Maya telemetry format mismatch")
    return doc


def _ma12_nonnegative(value):
    if type(value) not in (float, int) or not _ma12_math.isfinite(value) or not 0 <= value <= 1e9:
        raise ValueError("invalid Maya meter value")
    return float(value)


def _ma12_calculate(now, baseline, meter, purchases):
    if (type(now) is not int or type(meter.get("collected_at")) is not int or
            not 0 <= now - meter["collected_at"] <= 180 or
            type(baseline.get("created_at")) is not int or
            not 0 <= now - baseline["created_at"]):
        raise ValueError("meter stale or invalid")
    if (baseline.get("direction_assumption") != "rx" or
            baseline.get("alert_eligible") is not False or
            baseline.get("provider_observation_time_known") is not False):
        raise ValueError("unrecognized baseline policy")
    result = {}
    for sid in _MA12_NAMES:
        row = meter.get("servers", {}).get(sid, {})
        base = baseline.get("servers", {}).get(sid, {})
        output = {"state": "unavailable", "remaining_gb": None}
        try:
            if (row.get("state") != "ok" or
                    row.get("traffic_state") != "direction_unconfirmed" or
                    row.get("counter_uncertain") is not False):
                raise ValueError("sensor offline, reset or calibrated differently")
            if (type(base.get("baseline_meter_time")) is not int or
                    abs(base["baseline_meter_time"] - baseline["created_at"]) > 180 or
                    meter["collected_at"] < base["baseline_meter_time"]):
                raise ValueError("baseline time mismatch")
            current = _ma12_nonnegative(row.get("rx_period_gb"))
            initial = _ma12_nonnegative(base.get("rx_baseline_gb"))
            reported = _ma12_nonnegative(base.get("starting_reported_remaining_gb"))
            if current < initial - 0.002:
                raise ValueError("counter reset after baseline")
            # Rounded-up (0.002GB) counter jitter is not negative usage.
            measured = max(0, current - initial)
            # Purchases since the NEW current baseline only, all earlier credits
            # already included in the operator-provided starting remaining value.
            extra = int(purchases.get(sid, 0))
            if not 0 <= extra <= 1_000_000:
                raise ValueError("invalid purchase total")
            remaining = max(0, round(reported + extra - measured, 3))
            output = {
                "state": "provisional",
                "remaining_gb": remaining,
                "below_10gb": remaining < _MA12_THRESHOLD_GB,
                "direction": "rx_assumed",
                "is_provider_verified": False,
                "observed_at": meter["collected_at"],
                "epoch": str(baseline["created_at"]),
            }
        except (TypeError, ValueError, KeyError, OverflowError):
            pass
        result[sid] = output
    return result


@app.get("/v5/maya/low-traffic")
def _ma12_owner_low_traffic(x_sms_gateway_token: str = _ma12_Header(default="")):
    require_token(x_sms_gateway_token)
    try:
        baseline = _ma12_document(
            "provisional_meter_baseline_v7.json", "HESAB_MAYA_PROVISIONAL_BASELINE_V7")
        meter = _ma12_document("status.json", "HESAB_PHASE1_V1")
        # No database write. Existing V9 immutable journal remains authoritative.
        epochs = {}
        for sid in _MA12_NAMES:
            base = baseline["servers"][sid]
            epoch = f'{baseline["created_at"]}|{base["rx_baseline_gb"]}'
            if len(epoch) > 100:
                raise ValueError("invalid epoch")
            epochs[sid] = epoch
        purchases = {sid: 0 for sid in _MA12_NAMES}
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT server_id,meter_epoch,COALESCE(SUM(gb),0) AS gb
                    FROM hesab_maya_traffic_topups_v9
                    WHERE server_id IN ('maya1','maya-s3','maya4')
                    GROUP BY server_id,meter_epoch
                """)
                for rec in cur.fetchall():
                    sid = rec["server_id"]
                    if sid in purchases and rec["meter_epoch"] == epochs[sid]:
                        purchases[sid] += int(rec["gb"])
        result = _ma12_calculate(int(_ma12_time.time()), baseline, meter, purchases)
    except (OSError, ValueError, TypeError, KeyError, OverflowError, Exception):
        # Not safe to declare a server healthy when telemetry/journal is
        # unreadable. The Android client MUST NOT alert on this response.
        raise _ma12_HTTP(status_code=503, detail="Maya traffic telemetry unavailable")
    return _ma12_JSON({
        "ok": True,
        "threshold_gb": _MA12_THRESHOLD_GB,
        "estimate_only": True,
        "generated_at": int(_ma12_time.time()),
        "servers": result,
    }, headers={"Cache-Control": "private,no-store"})
