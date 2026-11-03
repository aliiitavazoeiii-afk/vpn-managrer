#!/usr/bin/env python3
"""Hesab telemetry V11: HMAC-authenticated receiver, local or isolated Docker.

Independent SQLite tables inside the pre-existing read-only Maya telemetry mount.
Does not load or write the finance PostgreSQL database, X-UI or local tunnel.
Never sends SMS. The alert outbox is review-only until provider delivery is approved.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import threading
import time

CONFIG = Path("/etc/hesab-telemetry-v11/receiver.json")
PATH = "/api/control-room/v11/heartbeat"
MAX_BODY = 65536
SKEW_S = 120
STALE_S = 120
MIN_INTERVAL_S = 10
ALERT_COOLDOWN_S = 600
ALLOWED = {"maya1", "maya-s3", "maya4"}
LANES = ("backhaul", "mieru")

SCHEMA = """
CREATE TABLE IF NOT EXISTS replays (
 server_id TEXT NOT NULL, nonce TEXT NOT NULL, received_ts INTEGER NOT NULL,
 PRIMARY KEY(server_id,nonce)
);
CREATE TABLE IF NOT EXISTS server_state (
 server_id TEXT PRIMARY KEY, received_ts INTEGER NOT NULL, sent_ts INTEGER NOT NULL,
 payload TEXT NOT NULL, effective_state TEXT NOT NULL DEFAULT 'unknown',
 pending_state TEXT NOT NULL DEFAULT '', pending_streak INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS samples (
 id INTEGER PRIMARY KEY AUTOINCREMENT, server_id TEXT NOT NULL,
 received_ts INTEGER NOT NULL, cpu_pct REAL, ram_pct REAL, disk_pct REAL,
 rx_bytes INTEGER, tx_bytes INTEGER, tunnel_state TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_v11_samples_server_ts ON samples(server_id,received_ts DESC);
CREATE TABLE IF NOT EXISTS counters (
 server_id TEXT NOT NULL, lane TEXT NOT NULL, epoch INTEGER NOT NULL DEFAULT 0,
 total_connections INTEGER, bytes_in INTEGER, bytes_out INTEGER, updated_ts INTEGER NOT NULL,
 PRIMARY KEY(server_id,lane)
);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, server_id TEXT NOT NULL,
 event_ts INTEGER NOT NULL, kind TEXT NOT NULL, lane TEXT NOT NULL DEFAULT '',
 detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_v11_events_server_ts ON events(server_id,event_ts DESC);
CREATE TABLE IF NOT EXISTS alerts (
 id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL UNIQUE,
 server_id TEXT NOT NULL, kind TEXT NOT NULL, created_ts INTEGER NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending_review', sent_at INTEGER,
 CHECK(state IN ('pending_review','cancelled','sent'))
);
"""


def read_config(path=CONFIG):
    if (not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077
            or path.stat().st_uid != 0):
        raise RuntimeError("Receiver config must be root-owned, regular, non-symlink, 0600")
    cfg = json.loads(path.read_text(encoding="utf8"))
    entries = cfg.get("servers", {})
    if not isinstance(entries, dict) or not entries or set(entries) - ALLOWED:
        raise RuntimeError("Invalid receiver server roster")
    keys = {}
    for sid, entry in entries.items():
        try:
            secret = bytes.fromhex(entry["key_hex"])
        except (ValueError, KeyError, TypeError):
            raise RuntimeError("Invalid HMAC key metadata") from None
        if len(secret) != 32 or type(entry.get("enabled")) is not bool:
            raise RuntimeError("Invalid per-server HMAC key/enable flag")
        if entry["enabled"]:
            keys[sid] = secret
    output = cfg.get("database_path", "/opt/vpn-control-center/maya_extra_sync/telemetry_v11/telemetry.sqlite3")
    if not isinstance(output, str) or not output.startswith("/opt/vpn-control-center/maya_extra_sync/telemetry_v11/"):
        raise RuntimeError("Unexpected database path")
    return keys, Path(output)


def db_connect(path):
    db = sqlite3.connect(str(path), timeout=5, isolation_level=None)
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def initialize(path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    db = db_connect(path)
    try:
        db.executescript(SCHEMA)
        os.chmod(path, 0o600)
    finally:
        db.close()


def validate_payload(data, sid, nonce, timestamp):
    if type(data) is not dict or set(data) != {
        "schema", "server_id", "sent_at", "nonce", "tunnel_type",
        "system", "services", "controller", "haproxy", "foreign_ips",
        "quota", "xui_online", "vpn_end_to_end"
    }:
        raise ValueError("unrecognized telemetry shape")
    if (data["schema"] != "hesab-tunnel-v11" or data["server_id"] != sid
            or data["nonce"] != nonce or type(data["sent_at"]) is not int
            or data["sent_at"] != timestamp):
        raise ValueError("signed metadata mismatch")
    if data["tunnel_type"] not in ("dual-backhaul-mieru-ha", "unidentified"):
        raise ValueError("unknown tunnel type")
    for field in ("system", "services", "controller", "haproxy", "foreign_ips", "quota"):
        if not isinstance(data[field], dict):
            raise ValueError("invalid nested telemetry")
    if data["xui_online"] is not None or data["vpn_end_to_end"] != "not_tested":
        raise ValueError("unsupported fabricated online/probe data")
    if data["quota"] != {"state": "unknown", "remaining_gb": None}:
        raise ValueError("quota must remain unknown without verified provider source")
    if set(data["controller"]) != {"state", "age_s", "paths"}:
        raise ValueError("controller fields changed")
    if data["controller"]["state"] not in ("ok", "stale", "invalid", "unavailable"):
        raise ValueError("invalid controller state")
    if not isinstance(data["controller"]["paths"], dict) or set(data["controller"]["paths"]) - set(LANES):
        raise ValueError("unknown tunnel paths")
    if set(data["haproxy"]) - {*LANES, "BACKEND"}:
        raise ValueError("unexpected HAProxy backend")
    if set(data["foreign_ips"]) - set(LANES):
        raise ValueError("unexpected egress IP metadata")
    if set(data["system"]) != {
        "cpu_pct","ram_pct","disk_pct","uptime_s","interface",
        "rx_bytes","tx_bytes","tcp443_listen"
    }:
        raise ValueError("unknown host system metric")
    for k in ("cpu_pct", "ram_pct", "disk_pct"):
        v = data["system"][k]
        if v is not None and (type(v) not in (int, float) or not 0 <= v <= 100):
            raise ValueError("invalid host percentage")
    if data["system"]["tcp443_listen"] not in ("listening", "not_listening", "unknown"):
        raise ValueError("unexpected passive socket state")
    for k in ("rx_bytes", "tx_bytes", "uptime_s"):
        v = data["system"][k]
        if v is not None and (type(v) is not int or not 0 <= v <= 2**63 - 1):
            raise ValueError("invalid host counter")
    if len(data["services"]) > 12 or any(
        type(k) is not str or type(v) is not str or len(k) > 60 or
        v not in ("active", "inactive", "failed", "activating", "unknown")
        for k, v in data["services"].items()
    ):
        raise ValueError("invalid service names/states")
    for name, lane in data["controller"]["paths"].items():
        if not isinstance(lane,dict) or set(lane) != {
            "available", "passed_probes", "total_probes", "latency_ms",
            "consecutive_success", "consecutive_fail", "haproxy_before_action",
            "tcp_https", "udp"
        }:
            raise ValueError("invalid controller path fields")
        if lane["available"] is not None and type(lane["available"]) is not bool:
            raise ValueError("invalid available flag")
        if lane["udp"] != "unknown" or lane["tcp_https"] not in ("ok","degraded","unknown"):
            raise ValueError("unsupported protocol state")
    for name, val in data["haproxy"].items():
        if not isinstance(val,dict) or set(val) != {
            "status", "active_connections", "total_connections",
            "bytes_in", "bytes_out", "check_failures"
        }:
            raise ValueError("invalid backend counter fields")
        if val["status"] not in ("UP","DOWN","MAINT","STOPPED","unknown"):
            raise ValueError("invalid backend status")
        for key in ("active_connections", "total_connections","bytes_in","bytes_out","check_failures"):
            v = val[key]
            if v is not None and (type(v) is not int or v < 0 or v > 2**63-1):
                raise ValueError("invalid backend counter")
    return data


def telemetry_state(payload):
    controller = payload["controller"]
    if controller.get("state") != "ok":
        return "unknown"
    paths = controller["paths"]
    availability = [paths.get(name, {}).get("available") for name in LANES]
    if availability == [True, True]:
        return "healthy"
    if availability == [False, False]:
        return "both_unavailable"
    if any(x is False for x in availability):
        return "degraded"
    return "unknown"


def make_event(db, sid, kind, ts, lane="", detail=""):
    # Event content is generated from fixed internal enums, never raw system output.
    row = db.execute(
        "INSERT INTO events(server_id,event_ts,kind,lane,detail) VALUES (?,?,?,?,?)",
        (sid, ts, kind, lane, detail)).lastrowid
    if kind not in ("both_unavailable","degraded","healthy","stale"):
        return
    prior = db.execute(
        "SELECT created_ts FROM alerts WHERE server_id=? AND kind=? ORDER BY id DESC LIMIT 1",
        (sid, kind)).fetchone()
    if prior and ts - prior[0] < ALERT_COOLDOWN_S:
        return
    db.execute(
        "INSERT OR IGNORE INTO alerts(event_id,server_id,kind,created_ts,state) VALUES (?,?,?,?,?)",
        (row, sid, kind, ts, "pending_review"))


def update_counter_epochs(db, sid, timestamp, payload):
    counters = payload.get("haproxy", {})
    for lane in LANES:
        item = counters.get(lane, {})
        fields = ("total_connections","bytes_in","bytes_out")
        new = tuple(item.get(k) for k in fields)
        if any(type(n) is not int for n in new):
            continue
        old = db.execute(
            "SELECT epoch,total_connections,bytes_in,bytes_out FROM counters WHERE server_id=? AND lane=?",
            (sid, lane)).fetchone()
        epoch = old[0] if old else 0
        if old and any(o is not None and n < o for n,o in zip(new,old[1:])):
            epoch += 1
            make_event(db, sid, "counter_reset", timestamp, lane, "HAProxy cumulative counter reset; sample epoch changed")
        db.execute(
            "INSERT INTO counters(server_id,lane,epoch,total_connections,bytes_in,bytes_out,updated_ts)"
            " VALUES (?,?,?,?,?,?,?) ON CONFLICT(server_id,lane) DO UPDATE SET"
            " epoch=excluded.epoch,total_connections=excluded.total_connections,"
            " bytes_in=excluded.bytes_in,bytes_out=excluded.bytes_out,updated_ts=excluded.updated_ts",
            (sid, lane, epoch, *new, timestamp))


def ingest(db, sid, nonce, timestamp, payload, now=None):
    """Atomic INSERT of replay receipt + snapshot + trends + deduped incidents."""
    now = int(time.time()) if now is None else int(now)
    db.execute("BEGIN IMMEDIATE")
    try:
        last = db.execute(
            "SELECT received_ts,effective_state,pending_state,pending_streak FROM server_state WHERE server_id=?",
            (sid,)).fetchone()
        if last and now - last[0] < MIN_INTERVAL_S:
            db.execute("ROLLBACK")
            return 429, "rate_limit"
        if db.execute("SELECT 1 FROM replays WHERE server_id=? AND nonce=?",(sid,nonce)).fetchone():
            db.execute("ROLLBACK")
            return 409, "replay"
        db.execute("INSERT INTO replays(server_id,nonce,received_ts) VALUES (?,?,?)",
                   (sid, nonce, now))
        raw = json.dumps(payload,ensure_ascii=False,separators=(",",":"))
        state = telemetry_state(payload)
        oldstate = last[1] if last else "unknown"
        pending = last[2] if last else ""
        streak = last[3] if last else 0
        if state == pending:
            streak += 1
        else:
            pending, streak = state, 1
        effective = oldstate
        if streak >= 2 and state != oldstate:
            effective = state
            if state != "unknown":
                make_event(db, sid, state, now)
        db.execute(
            "INSERT INTO server_state(server_id,received_ts,sent_ts,payload,effective_state,pending_state,pending_streak)"
            " VALUES (?,?,?,?,?,?,?) ON CONFLICT(server_id) DO UPDATE SET"
            " received_ts=excluded.received_ts,sent_ts=excluded.sent_ts,payload=excluded.payload,"
            " effective_state=excluded.effective_state,pending_state=excluded.pending_state,"
            " pending_streak=excluded.pending_streak",
            (sid, now, timestamp, raw, effective, pending, streak))
        host = payload["system"]
        db.execute(
            "INSERT INTO samples(server_id,received_ts,cpu_pct,ram_pct,disk_pct,rx_bytes,tx_bytes,tunnel_state)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (sid,now,host.get("cpu_pct"),host.get("ram_pct"),host.get("disk_pct"),
             host.get("rx_bytes"),host.get("tx_bytes"),state))
        update_counter_epochs(db,sid,now,payload)
        db.execute("DELETE FROM replays WHERE received_ts < ?", (now - 7200,))
        db.execute("COMMIT")
        return 202, "accepted"
    except Exception:
        db.execute("ROLLBACK")
        raise


def mark_stale(db, now=None):
    now = int(time.time()) if now is None else int(now)
    db.execute("BEGIN IMMEDIATE")
    try:
        rows = db.execute(
            "SELECT server_id,received_ts,effective_state FROM server_state").fetchall()
        for sid, seen, state in rows:
            if now - seen > STALE_S and state != "stale":
                make_event(db, sid, "stale", now, detail="No signed heartbeat within 120 seconds")
                db.execute("UPDATE server_state SET effective_state='stale',pending_state='',pending_streak=0 WHERE server_id=?",(sid,))
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise


def process_heartbeat(headers, body, config_keys, db_path, now=None):
    """Return HTTP code and non-sensitive explanation. Testable without network."""
    now = int(time.time()) if now is None else int(now)
    sid = headers.get("X-Hesab-Server","")
    nonce = headers.get("X-Hesab-Nonce","")
    timestamp = headers.get("X-Hesab-Time","")
    signature = headers.get("X-Hesab-Signature","")
    if sid not in config_keys or not re.fullmatch(r"[a-f0-9]{32}",nonce):
        return 401,"unauthorized"
    if not re.fullmatch(r"[0-9]{10,11}",timestamp) or abs(now-int(timestamp)) > SKEW_S:
        return 401,"unauthorized"
    if not re.fullmatch(r"sha256=[a-f0-9]{64}",signature):
        return 401,"unauthorized"
    actual = hmac.new(config_keys[sid], timestamp.encode()+b"."+body,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature[7:],actual):
        return 401,"unauthorized"
    try:
        payload=validate_payload(json.loads(body),sid,nonce,int(timestamp))
    except (ValueError,TypeError,UnicodeDecodeError):
        return 422,"invalid_payload"
    db=db_connect(db_path)
    try:
        return ingest(db,sid,nonce,int(timestamp),payload,now)
    finally:
        db.close()


def allowed_proxy_peer(address, mode):
    """No public source IPs; Docker mode still REQUIRES HMAC and no ports mapping."""
    if mode == "loopback":
        return address in ("127.0.0.1", "::1")
    if mode == "docker-internal":
        try:
            peer = ipaddress.ip_address(address)
        except ValueError:
            return False
        return (peer.version == 4 and peer.is_private and not peer.is_loopback
                and not peer.is_link_local and not peer.is_multicast)
    return False

class Handler(BaseHTTPRequestHandler):
    keys = {}
    storage = None
    peer_mode = "loopback"
    def log_message(self, fmt, *args):
        # Do not log signed payload, token, URL query, remote addresses or headers.
        return

    def respond(self, code, value):
        raw=json.dumps({"ok":code==202,"status":value}).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/healthz":
            return self.respond(202,"receiver_alive")
        self.respond(404,"not_found")

    def do_POST(self):
        if self.path != PATH:
            return self.respond(404,"not_found")
        if not allowed_proxy_peer(self.client_address[0], self.peer_mode):
            return self.respond(403,"untrusted_proxy_peer")
        if self.headers.get("X-Forwarded-Proto") != "https":
            return self.respond(403,"https_required")
        if self.headers.get("Content-Type","").split(";")[0].strip().lower()!="application/json":
            return self.respond(415,"json_required")
        size=self.headers.get("Content-Length","")
        if not size.isdigit() or not 0<int(size)<=MAX_BODY:
            return self.respond(413,"invalid_body_size")
        body=self.rfile.read(int(size))
        try:
            code,reason=process_heartbeat(self.headers,body,self.keys,self.storage)
            self.respond(code,reason)
        except (sqlite3.Error,OSError):
            self.respond(503,"storage_unavailable")


def sweep_loop(db_path):
    while True:
        try:
            db=db_connect(db_path)
            try:
                mark_stale(db)
            finally:
                db.close()
        except (OSError,sqlite3.Error):
            pass
        time.sleep(30)


def main():
    if os.geteuid()!=0:
        raise RuntimeError("root service expected for protected config")
    keys,storage=read_config()
    initialize(storage)
    Handler.keys=keys
    Handler.storage=storage
    mode = os.environ.get("HESAB_RECEIVER_DEPLOYMENT", "loopback")
    if mode not in ("loopback", "docker-internal"):
        raise RuntimeError("Invalid receiver deployment mode")
    Handler.peer_mode = mode
    threading.Thread(target=sweep_loop,args=(storage,),daemon=True).start()
    # Docker mode binds container interfaces but MUST have no host-published ports.
    # Signed HMAC remains mandatory regardless of the peer address.
    bind_host = "0.0.0.0" if mode == "docker-internal" else "127.0.0.1"
    server=ThreadingHTTPServer((bind_host,8199),Handler)
    print("HESAB_TELEMETRY_V11_DEPLOYMENT",mode,flush=True)
    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("RECEIVER_FAILED",type(exc).__name__,file=sys.stderr)
        raise SystemExit(1)
