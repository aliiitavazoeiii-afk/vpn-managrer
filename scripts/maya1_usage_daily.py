#!/usr/bin/env python3
"""MAYA1_USAGE_DAILY_V1

Accumulate estimated per-client traffic per Tehran calendar day from periodic
x-ui cumulative upload/download counters. Only writes a local JSON report on
the management host. Initial reading becomes a baseline; no fake past usage.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import tempfile

TZ = ZoneInfo("Asia/Tehran")
FORMAT = "MAYA1_USAGE_DAILY_V1"
KEEP_DAYS = 31
MAX_GAP_SECONDS = 60 * 60

def _save_atomic(path, doc):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".usage-", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf8") as stream:
            json.dump(doc, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, 0o640)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def _nonnegative(v):
    n = int(v or 0)
    if n < 0:
        raise ValueError("Negative x-ui traffic counter")
    return n

def _utc(value):
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Traffic sample without timezone")
    return dt.astimezone(timezone.utc)

def record(snapshot, path):
    if snapshot.get("format") != "MAYA1_CONTROL_SNAPSHOT_V1":
        raise ValueError("Unexpected maya1 snapshot")
    sampled = _utc(snapshot["source_generated_at"])
    now = datetime.now(timezone.utc)
    if abs((now - sampled).total_seconds()) > 180:
        raise ValueError("Remote x-ui snapshot is stale")
    day = sampled.astimezone(TZ).date().isoformat()
    target = Path(path)
    if target.exists():
        if target.stat().st_size > 3000000:
            raise ValueError("Daily usage report too large")
        doc = json.loads(target.read_text(encoding="utf8"))
        if doc.get("format") != FORMAT or not isinstance(doc.get("days"), dict):
            raise ValueError("Invalid existing usage report")
    else:
        doc = {"format": FORMAT, "days": {}, "last": {}}
    previous_time = _utc(doc["sampled_at"]) if doc.get("sampled_at") else None
    if previous_time is not None and sampled <= previous_time:
        # Idempotent: no double-counting repeated or delayed snapshots.
        return "ALREADY_RECORDED"

    clients = snapshot["clients"]
    if len(clients) != len({str(c["email"]).casefold() for c in clients}):
        raise ValueError("Duplicate x-ui email")
    days = doc["days"]
    daily = days.setdefault(day, {})
    previous = doc.get("last", {})
    current = {}
    gap = previous_time is None or (sampled - previous_time).total_seconds() > MAX_GAP_SECONDS
    for c in clients:
        email = str(c["email"]).strip().casefold()
        up = _nonnegative(c.get("up_bytes"))
        down = _nonnegative(c.get("down_bytes"))
        current[email] = {"up": up, "down": down}
        today = daily.setdefault(email, {
            "up": 0, "down": 0, "samples": 0,
            "resets": 0, "coverage_gaps": 0,
        })
        today["samples"] += 1
        if email not in previous or previous_time is None:
            # Baseline only, not inferred historical usage.
            continue
        if previous_time.astimezone(TZ).date().isoformat() != day:
            # Cannot assign a cross-midnight delta to one day correctly.
            today["coverage_gaps"] += 1
            continue
        if gap:
            # A long monitoring gap makes traffic timing unreliable.
            today["coverage_gaps"] += 1
            continue
        old = previous[email]
        for key in ("up", "down"):
            last = _nonnegative(old[key])
            value = current[email][key]
            if value < last:
                # Counter reset occurred. Account only post-reset bytes.
                today["resets"] += 1
                delta = value
            else:
                delta = value - last
            today[key] += delta
    cutoff = (sampled.astimezone(TZ).date() - timedelta(days=KEEP_DAYS)).isoformat()
    doc["days"] = {date: value for date, value in days.items() if date >= cutoff}
    doc["last"] = current
    doc["sampled_at"] = sampled.isoformat()
    doc["coverage_started_at"] = doc.get("coverage_started_at") or sampled.isoformat()
    _save_atomic(target, doc)
    return "UPDATED"

if __name__ == "__main__":
    raise SystemExit("Import record(snapshot, path) from the verified maya1 sync task")
