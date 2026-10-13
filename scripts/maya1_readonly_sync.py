#!/usr/bin/env python3
"""MAYA1_READONLY_SYNC_V1. Pull x-ui data over forced-command SSH; never modify x-ui or finance."""
import collections
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

BASE = Path("/opt/vpn-control-center")
OUT = BASE / "maya1_sync"
KEY = Path("/root/.ssh/hesab_maya1_readonly")
HOST = "94.184.4.38"
EXPECTED_CLIENTS = 145
EXPECTED_SHA = "8e1509674cf0c06d1e8015064c8c3b69b76931311bce4489b1bbda49d50f37fb"
EXCLUDED = {
    "m0z2wrul": "default",
    "khodamm": "personal",
    "pedram tofigh": "free",
    "pedram tofigh hamsar": "free",
}
MANUAL = {
    "reza hadi": 30,
    "soniya reza samaneh": 39,
    "tina milad samaneh": 45,
    "faraji samaneh": 33,
    "sharareh madar": 49,
    "bashiri faraji samaneh": 67,
    "freydoni soheila": 50,
    "taherpoor": 269,
    "abri nazanin soheila": 27,
    "afrogh hooman": 24,
    "taherian": 266,
    "khademi ayda": 180,
    "torabi ardeshir": 109,
    "ebi ashkan davari": 267,
    "elham ashkan davari": 28,
    "golpari mahsa sara": 149,
    "hori milad samaneh": 44,
    "javaherian parisa hashemi": 41,
    "ravesh amirmohamad": 71,
    "monji2": 196,
    "ahmad amani 2": 291,
    "parnian": 303,
    "khabarfit amirmohamd": 330,
    "pejman pone": 281,
    "asal mehrdad": 311,
    "atashin maleklo": 121,
}

def norm(v):
    return "".join(str(v or "").casefold().split())

def fail(message):
    raise RuntimeError(message)

def pull_remote():
    cmd = [
        "ssh", "-T", "-i", str(KEY),
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=8",
        "-o", "ServerAliveInterval=5",
        "-o", "ServerAliveCountMax=2",
        "root@" + HOST, "maya1-readonly-export",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode:
        fail("SSH export failed: " + proc.stderr[-500:].strip())
    if len(proc.stdout) > 3000000:
        fail("SSH response too large")
    data = json.loads(proc.stdout)
    if data.get("format") != "MAYA1_XUI_EXPORT_V1" or data.get("server") != "maya1":
        fail("Unexpected exporter format/server")
    clients = data.get("clients")
    if not isinstance(clients, list) or len(clients) != EXPECTED_CLIENTS:
        fail("Maya1 roster changed: expected 145, got " + str(len(clients) if isinstance(clients, list) else "?"))
    keys = [str(c.get("email") or "").strip().casefold() for c in clients]
    if not all(keys) or len(set(keys)) != len(keys):
        fail("Duplicate/empty remote emails")
    if any(not isinstance(c.get("enabled"), bool) for c in clients):
        fail("Invalid remote status")
    return data, keys

def read_dashboard():
    query = """COPY (
      SELECT id, display_name,
        COALESCE((SELECT CASE a.kind
          WHEN 'followup_cut' THEN 'removed'
          WHEN 'followup_waiting' THEN 'waiting'
          ELSE 'normal' END
          FROM audit_events a
          WHERE a.kind IN ('followup_cut','followup_waiting','followup_clear')
          AND a.message LIKE 'sid=' || s.id::text || ';%'
          ORDER BY a.id DESC LIMIT 1),'normal') AS account_state
      FROM subscriptions s ORDER BY id
    ) TO STDOUT WITH CSV HEADER;"""
    cmd = [
        "docker", "compose", "-f", "docker-compose.yml",
        "-f", "docker-compose.sms.yml",
        "exec", "-T", "db", "sh", "-c",
        'PGOPTIONS="-c default_transaction_read_only=on" PGPASSWORD="$POSTGRES_PASSWORD" psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
    ]
    proc = subprocess.run(cmd, input=query, capture_output=True, text=True, cwd=BASE, timeout=45)
    if proc.returncode:
        fail("Dashboard read failed: " + proc.stderr[-350:].strip())
    rows = list(csv.DictReader(io.StringIO(proc.stdout)))
    if not rows or set(rows[0]) != {"id", "display_name", "account_state"}:
        fail("Unexpected dashboard schema")
    return {int(row["id"]): row for row in rows}

def build_mapping(keys, db):
    index = collections.defaultdict(list)
    for row in db.values():
        index[norm(row["display_name"])].append(row)
    mapping = {}
    ids = set()
    for email in keys:
        if email in EXCLUDED:
            mapping[email] = {"id": None, "reason": EXCLUDED[email]}
            continue
        if email in MANUAL:
            sid = MANUAL[email]
            kind = "confirmed"
        else:
            matches = index.get(norm(email), [])
            if len(matches) != 1:
                fail("No unique exact match for: " + email)
            sid = int(matches[0]["id"])
            kind = "exact_approved"
        if sid in ids or sid not in db:
            fail("Duplicate/missing dashboard ID " + str(sid))
        if db[sid]["account_state"] == "removed":
            fail("Archived dashboard account " + str(sid) + " for " + email)
        ids.add(sid)
        mapping[email] = {"id": sid, "name": db[sid]["display_name"], "reason": kind}
    if len(ids) != 141 or len([v for v in mapping.values() if v["reason"] == "confirmed"]) != 26:
        fail("Unexpected linked/confirmed count")
    canonical = "\n".join(sorted(k + ":" + str(mapping[k]["id"] or "") for k in mapping))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    if digest != EXPECTED_SHA:
        fail("MAPPING MISMATCH: expected approved 145-account map SHA; got " + digest)
    return mapping

def atomic_json(path, obj):
    OUT.mkdir(mode=0o750, parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".maya1-", dir=OUT)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, 0o640)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    if mode not in ("--check", "--sync"):
        fail("Usage: maya1_readonly_sync.py [--check|--sync]")
    if not KEY.is_file():
        fail("SSH key missing: " + str(KEY))
    remote, keys = pull_remote()
    mapping = build_mapping(keys, read_dashboard())
    linked = sum(v["id"] is not None for v in mapping.values())
    print("MAYA1 VERIFIED: remote=" + str(len(keys)) +
          ", linked=" + str(linked) + ", exclusions=4, fingerprint=OK")
    if mode == "--sync":
        snapshot = {
            "format": "MAYA1_CONTROL_SNAPSHOT_V1",
            "synced_at": datetime.now(timezone.utc).isoformat(),
            "source_generated_at": remote["generated_at"],
            "clients": remote["clients"],
        }
        atomic_json(OUT / "snapshot.json", snapshot)
        atomic_json(OUT / "mapping.json", {
            "format": "MAYA1_CONTROL_MAPPING_V1",
            "mapping": mapping,
            "expected_sha": EXPECTED_SHA,
        })
        from maya1_usage_daily import record as _usage_record
        print("MAYA1 DAILY USAGE:", _usage_record(snapshot, OUT / "daily_usage.json"))
        print("MAYA1 SYNC COMPLETE: read-only snapshot refreshed.")
    else:
        print("DRY RUN PASSED: no files, Docker services or accounts modified.")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("MAYA1 STOP: " + str(exc), file=sys.stderr)
        sys.exit(1)
