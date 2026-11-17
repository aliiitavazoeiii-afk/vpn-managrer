#!/usr/bin/env python3
"""MAYA_NIC_TRAFFIC_HISTORY_V11
Independent, read-only physical NIC time series for Maya 1/3/4.
Reads the existing restricted-SSH NIC meter ledger; never polls or touches XUI,
tunnel, provider quota, billing records, SMS or customer traffic.
Tehran hourly buckets, 45-day bounded history; gaps and reboots are NOT guessed.
"""
import fcntl
import json
import math
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SOURCE = Path("/var/lib/hesab-maya-net-meter-v2/state.json")
HEALTH = Path("/opt/vpn-control-center/maya_extra_sync/phase1/status.json")
V10 = Path("/opt/vpn-control-center/maya_extra_sync/phase1/daily_nic_v10.json")
STATE = Path("/var/lib/hesab-maya-traffic-history-v11/state.json")
LOCK = Path("/var/lib/hesab-maya-traffic-history-v11/lock")
OUT = Path("/opt/vpn-control-center/maya_extra_sync/phase1/traffic_history_v11.json")
NAMES = ("maya1", "maya-s3", "maya4")
ZONE = ZoneInfo("Asia/Tehran")
GB = 1_000_000_000
MAX_GAP = 300
HISTORY_DAYS = 45
DISPLAY_DAYS = 30


def document(path, limit=3_000_000, private=False):
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise ValueError("invalid source file: " + path.name)
    if private and path.stat().st_mode & 0o077:
        raise PermissionError("private source permissions: " + path.name)
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("source object expected")
    return result


def save(path, value, mode):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix=".traffic-v11-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def valid_sample(value):
    required = ("last_rx", "last_tx", "sample_at", "ifindex", "boot_id", "identity")
    if not isinstance(value, dict) or any(k not in value for k in required):
        return False
    if any(type(value[k]) is not int or value[k] < 0
           for k in ("last_rx", "last_tx", "sample_at", "ifindex")):
        return False
    return (isinstance(value["boot_id"], str) and
            isinstance(value["identity"], str) and len(value["boot_id"]) == 36 and
            bool(value["identity"]))


def bucket_key(ts):
    return datetime.fromtimestamp(ts, ZONE).strftime("%Y-%m-%dT%H")


def split_interval(buckets, first_at, last_at, rx, tx):
    """Distribute only an observed short interval across its actual local hours."""
    duration = last_at - first_at
    if not 0 < duration <= MAX_GAP:
        raise ValueError("interval too long for accurate hourly series")
    point = first_at
    prior_rx = prior_tx = 0
    while point < last_at:
        current = datetime.fromtimestamp(point, ZONE)
        next_hour = (current.replace(minute=0, second=0, microsecond=0) +
                     timedelta(hours=1)).timestamp()
        end = min(last_at, max(point + 1, int(next_hour)))
        end_rx = rx * (end - first_at) // duration
        end_tx = tx * (end - first_at) // duration
        key = bucket_key(point)
        b = buckets.setdefault(key, {"rx": 0, "tx": 0, "seconds": 0})
        b["rx"] += end_rx - prior_rx
        b["tx"] += end_tx - prior_tx
        b["seconds"] += end - point
        prior_rx, prior_tx = end_rx, end_tx
        point = end


def import_daily_carry(store, name, v10, captured, sample_at):
    """Preserve an already valid V10 daily RX total once, without fabricating hours."""
    if store.get("first_at") or not v10 or abs(captured - sample_at) > 120:
        return
    day = datetime.fromtimestamp(sample_at, ZONE).date().isoformat()
    if (v10.get("day") != day or
            abs(int(v10.get("collected_at", -999999)) - sample_at) > 120):
        return
    old = v10.get("servers", {}).get(name, {})
    value = old.get("rx_today_gb")
    if old.get("state") != "ok" or type(value) not in (int, float):
        return
    if not math.isfinite(value) or not 0 <= value <= 100000:
        return
    store["carry_day"] = day
    store["carry_rx"] = int(value * GB)
    store["carry_from_v10"] = True


def advance(store, sample, now):
    """Never count counter-reset jumps, duplicate samples or long unexplained gaps."""
    previous = store.get("last")
    new = {key: sample[key] for key in
           ("last_rx", "last_tx", "sample_at", "ifindex", "boot_id", "identity")}
    store.setdefault("buckets", {})
    store.setdefault("gaps", 0)
    if previous and new["sample_at"] <= previous["sample_at"]:
        return "duplicate"
    store["last"] = new
    if not previous:
        store["first_at"] = new["sample_at"]
        return "baseline"
    if (new["identity"] != previous["identity"] or
            new["boot_id"] != previous["boot_id"] or
            new["ifindex"] != previous["ifindex"] or
            new["last_rx"] < previous["last_rx"] or
            new["last_tx"] < previous["last_tx"]):
        store["gaps"] += 1
        store["last_gap_reason"] = "counter_reset"
        return "reset"
    gap = new["sample_at"] - previous["sample_at"]
    if gap > MAX_GAP:
        store["gaps"] += 1
        store["last_gap_reason"] = "long_unobserved_gap"
        return "gap"
    split_interval(store["buckets"], previous["sample_at"], new["sample_at"],
                   new["last_rx"] - previous["last_rx"],
                   new["last_tx"] - previous["last_tx"])
    return "observed"


def make_export(name, store, health, now, today):
    fresh = (health.get("state") == "ok" and
             store.get("last") and
             0 <= now - store["last"]["sample_at"] <= 190)
    last = store.get("last", {})
    observed_any = bool(store.get("buckets"))
    state = "ok" if fresh and observed_any else ("warming_up" if fresh else "unavailable")
    rows = []
    earliest = today - timedelta(days=DISPLAY_DAYS - 1)
    for d in range(DISPLAY_DAYS):
        date = earliest + timedelta(days=d)
        date_s = date.isoformat()
        rx = tx = covered = 0
        hour_rows = []
        for h in range(24):
            key = date_s + "T" + f"{h:02d}"
            b = store.get("buckets", {}).get(key)
            if b:
                x, y, seconds = (int(b.get(k, 0)) for k in ("rx", "tx", "seconds"))
                rx += x
                tx += y
                covered += seconds
                hour_rows.append({"hour": h, "rx_gb": round(x / GB, 4),
                                  "tx_gb": round(y / GB, 4),
                                  "minutes": round(seconds / 60, 1)})
            else:
                hour_rows.append({"hour": h, "rx_gb": None,
                                  "tx_gb": None, "minutes": 0})
        carry = (int(store.get("carry_rx", 0))
                 if store.get("carry_day") == date_s else 0)
        if covered or carry:
            elapsed = (min(now, int((datetime.combine(date + timedelta(days=1),
                      datetime.min.time(), tzinfo=ZONE)).timestamp())) -
                       int(datetime.combine(date, datetime.min.time(), tzinfo=ZONE).timestamp()))
            elapsed = max(1, elapsed)
            rows.append({"day": date_s, "rx_gb": round((rx + carry) / GB, 4),
                         "tx_gb": round(tx / GB, 4),
                         "coverage_pct": round(min(100, 100 * covered / elapsed), 1),
                         "unallocated_rx_gb": round(carry / GB, 4),
                         "hours": hour_rows})
        else:
            rows.append({"day": date_s, "rx_gb": None, "tx_gb": None,
                         "coverage_pct": 0, "unallocated_rx_gb": 0,
                         "hours": hour_rows})
    current = rows[-1]
    # Clock-hour peaks use substantially measured hour-buckets, not missing=zero.
    ranks = {}
    for day in rows[-7:]:
        for h in day["hours"]:
            if h["rx_gb"] is not None and h["minutes"] >= 45:
                ranks.setdefault(h["hour"], []).append(h["rx_gb"])
    averages = {h: sum(vals) / len(vals) for h, vals in ranks.items()}
    peak = max(averages, key=averages.get) if len(averages) >= 6 else None
    quiet = min(averages, key=averages.get) if len(averages) >= 6 else None
    last7 = rows[-7:]
    valid7 = [day["rx_gb"] for day in last7
              if day["rx_gb"] is not None and day["coverage_pct"] >= 75]
    summary = {
        "state": state,
        "rx_today_gb": current["rx_gb"] if state == "ok" else None,
        "tx_today_gb": current["tx_gb"] if state == "ok" else None,
        "partial_day": current["coverage_pct"] < 99 or
                       current["unallocated_rx_gb"] > 0,
        "coverage_today_pct": current["coverage_pct"],
        "sampled_at": last.get("sample_at"),
        "gaps": int(store.get("gaps", 0)),
        "last_gap_reason": store.get("last_gap_reason"),
    }
    return {"name": name, **summary,
            "last7_daily_average_rx_gb": (round(sum(valid7) / len(valid7), 3)
                                          if valid7 else None),
            "last30_observed_rx_gb": round(sum(d["rx_gb"] or 0 for d in rows), 3),
            "peak_hour": peak, "quiet_hour": quiet,
            "peak_avg_rx_gb": round(averages[peak], 3) if peak is not None else None,
            "quiet_avg_rx_gb": round(averages[quiet], 3) if quiet is not None else None,
            "days": rows}


def collect():
    if os.geteuid() != 0:
        raise PermissionError("root required for NIC meter ledger")
    STATE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(LOCK, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        now = int(time.time())
        ledger = document(SOURCE, private=True)
        sensor_status = document(HEALTH, 100_000)
        if sensor_status.get("format") != "HESAB_PHASE1_V1":
            raise ValueError("unexpected NIC sensor status format")
        captured = sensor_status.get("collected_at")
        if type(captured) is not int or not 0 <= now - captured <= 190:
            raise ValueError("NIC collector status stale; no data can be claimed")
        try:
            v10 = document(V10, 50_000)
        except (OSError, ValueError):
            v10 = None
        current = document(STATE, private=True) if STATE.is_file() else {
            "format": "MAYA_NIC_TRAFFIC_HISTORY_STATE_V11", "servers": {}}
        if current.get("format") != "MAYA_NIC_TRAFFIC_HISTORY_STATE_V11":
            raise ValueError("unexpected history state version")
        today = datetime.fromtimestamp(now, ZONE).date()
        cutoff = (today - timedelta(days=HISTORY_DAYS)).isoformat()
        output = {}
        for name in NAMES:
            entry = current.setdefault("servers", {}).setdefault(name, {})
            raw = ledger.get(name, {})
            status = sensor_status.get("servers", {}).get(name, {})
            if (status.get("state") == "ok" and valid_sample(raw) and
                    0 <= now - raw["sample_at"] <= 190):
                import_daily_carry(entry, name, v10, captured, raw["sample_at"])
                advance(entry, raw, now)
            # Old samples remain for graphs, but online health is never faked.
            entry["buckets"] = {k: v for k, v in
                                entry.get("buckets", {}).items()
                                if k[:10] >= cutoff}
            if entry.get("carry_day", "") < cutoff:
                entry.pop("carry_rx", None)
                entry.pop("carry_day", None)
            output[name] = make_export(name, entry, status, now, today)
        save(STATE, current, 0o600)
        save(OUT, {"format": "MAYA_NIC_TRAFFIC_HISTORY_V11",
                   "generated_at": now, "servers": output}, 0o640)
        for name, data in output.items():
            print("TRAFFIC_HISTORY", name, data["state"],
                  "rx_today_gb", data["rx_today_gb"],
                  "coverage_pct", data["coverage_today_pct"],
                  "last_sample_at", data["sampled_at"], flush=True)


if __name__ == "__main__":
    try:
        collect()
    except Exception as ex:
        print("TRAFFIC_HISTORY_FAILED", type(ex).__name__, str(ex)[:150])
        raise SystemExit(1)
