#!/usr/bin/env python3
"""MAYA1_XUI_EXPORT_V1: sanitized, read-only x-ui inventory over restricted SSH."""
import json
import sqlite3
import sys
from datetime import datetime, timezone

DB = "file:/etc/x-ui/x-ui.db?mode=ro"

def number(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0

def main():
    db = sqlite3.connect(DB, uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    inbound_rows = db.execute("SELECT enable, settings FROM inbounds").fetchall()
    traffic_rows = db.execute(
        "SELECT email, enable, up, down, total, expiry_time, last_online FROM client_traffics"
    ).fetchall()
    traffic = {}
    for row in traffic_rows:
        key = str(row["email"] or "").strip().casefold()
        if not key or key in traffic:
            raise ValueError("Missing or duplicate traffic email")
        traffic[key] = dict(row)
    clients = {}
    for inbound in inbound_rows:
        settings = json.loads(inbound["settings"] or "{}")
        for c in settings.get("clients", []):
            email = str(c.get("email") or "").strip()
            key = email.casefold()
            if not email or key in clients:
                raise ValueError("Missing or duplicate client email")
            t = traffic.get(key)
            if t is None:
                raise ValueError("Missing traffic record: " + email)
            clients[key] = {
                "email": email,
                "enabled": bool(c.get("enable", True)) and bool(inbound["enable"]) and bool(t["enable"]),
                "config_expiry_ms": number(c.get("expiryTime")),
                "traffic_expiry_ms": number(t["expiry_time"]),
                "up_bytes": number(t["up"]),
                "down_bytes": number(t["down"]),
                "quota_bytes": number(t["total"]),
                "last_online_ms": number(t["last_online"]),
            }
    db.close()
    if not clients or len(clients) > 5000:
        raise ValueError("Unexpected client count")
    print(json.dumps({
        "format": "MAYA1_XUI_EXPORT_V1",
        "server": "maya1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "clients": [clients[k] for k in sorted(clients)],
    }, ensure_ascii=False, separators=(",", ":")))

if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print("EXPORT_ERROR: " + str(ex), file=sys.stderr)
        sys.exit(1)
