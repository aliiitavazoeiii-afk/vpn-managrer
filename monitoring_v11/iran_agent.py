#!/usr/bin/env python3
"""Hesab telemetry V11: read-only Iran agent. Python stdlib only.

Never imports, calls, restarts or reconfigures the tunnel's local controller.
No user identity, tunnel password, UUID or Reality private key is exported.
"""
import csv
import datetime as dt
import hashlib
import hmac
import io
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

HEALTH = Path("/run/dual-ha-v2/health.json")
HAPROXY = "/run/dual-ha-v2/haproxy.sock"
CONFIG = Path("/etc/hesab-telemetry-v11/agent.json")
ALLOWED = ("maya1", "maya-s3", "maya4")
LANES = ("backhaul", "mieru")
SERVICES = (
    "x-ui", "dual-ha-v2-health", "dual-ha-v2-gateway", "dual-ha-v2-router",
    "dual-ha-backhaul", "dual-ha-mieru", "dual-ha-router", "dual-ha-tls",
)
MAX_BYTES = 65536


def finite(value, lo, hi):
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    x = float(value)
    return round(x, 3) if lo <= x <= hi else None


def nonnegative(value):
    try:
        v = int(value)
        return v if 0 <= v <= 2**63 - 1 else None
    except (ValueError, TypeError):
        return None


def ipv4(value):
    try:
        parsed = ipaddress.ip_address(str(value))
        return str(parsed) if parsed.version == 4 and parsed.is_global else None
    except ValueError:
        return None


def read_json_small(path, limit=32768):
    try:
        if not path.is_file() or path.stat().st_size > limit:
            return {}
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def config():
    if not CONFIG.is_file() or CONFIG.stat().st_mode & 0o077:
        raise RuntimeError("Missing 0600 agent configuration")
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    if data.get("server_id") not in ALLOWED:
        raise RuntimeError("Invalid server_id")
    endpoint = str(data.get("endpoint", ""))
    if endpoint != "https://hesab.filmjadiid.ir/api/control-room/v11/heartbeat":
        raise RuntimeError("Unexpected remote endpoint")
    key = bytes.fromhex(str(data.get("key_hex", "")))
    if len(key) != 32:
        raise RuntimeError("HMAC key must be 32 random bytes")
    interface = str(data.get("interface", ""))
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,25}", interface) or interface == "lo":
        raise RuntimeError("Invalid network interface")
    return data["server_id"], endpoint, key, interface


def cpu():
    def ticks():
        a = Path("/proc/stat").read_text().splitlines()[0].split()
        values = [int(v) for v in a[1:]]
        return sum(values), values[3] + (values[4] if len(values) > 4 else 0)
    try:
        t0, i0 = ticks()
        time.sleep(0.2)
        t1, i1 = ticks()
        return finite(100 * (1 - (i1 - i0) / max(1, t1 - t0)), 0, 100)
    except (OSError, ValueError, IndexError):
        return None


def ram():
    try:
        mem = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            name, value = line.split(":", 1)
            if name in ("MemTotal", "MemAvailable"):
                mem[name] = int(value.split()[0])
        return finite(100 * (1 - mem["MemAvailable"] / mem["MemTotal"]), 0, 100)
    except (OSError, KeyError, ValueError, ZeroDivisionError):
        return None


def sysinfo(interface):
    net = Path("/sys/class/net") / interface / "statistics"
    result = {"cpu_pct": cpu(), "ram_pct": ram(), "disk_pct": None,
              "uptime_s": None, "interface": interface,
              "rx_bytes": None, "tx_bytes": None, "tcp443_loopback": "unknown"}
    try:
        usage = shutil.disk_usage("/")
        result["disk_pct"] = finite(100 * usage.used / usage.total, 0, 100)
        result["uptime_s"] = nonnegative(float(Path("/proc/uptime").read_text().split()[0]))
    except (OSError, ValueError, ZeroDivisionError):
        pass
    for field, name in (("rx_bytes", "rx_bytes"), ("tx_bytes", "tx_bytes")):
        try:
            result[field] = nonnegative((net / name).read_text().strip())
        except OSError:
            pass
    # No assertion about internet egress or port filtering from this loopback probe.
    try:
        with socket.create_connection(("127.0.0.1", 443), timeout=0.3):
            result["tcp443_loopback"] = "reachable"
    except OSError:
        pass
    return result


def service_state(service):
    try:
        p = subprocess.run(["systemctl", "is-active", service],
                           capture_output=True, timeout=2, check=False)
        value = p.stdout.decode("ascii", "ignore").strip()
        return value if value in ("active", "inactive", "failed", "activating") else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def controller():
    doc = read_json_small(HEALTH)
    try:
        timestamp = dt.datetime.fromisoformat(doc["updated_utc"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            return {"state": "invalid", "age_s": None, "paths": {}}
        age = (dt.datetime.now(dt.timezone.utc) - timestamp).total_seconds()
        if not 0 <= age <= 90:
            return {"state": "stale", "age_s": finite(age, 0, 1e8), "paths": {}}
        raw = doc.get("paths")
        if not isinstance(raw, dict):
            raise ValueError("paths")
        lanes = {}
        for name in LANES:
            lane = raw.get(name, {})
            if not isinstance(lane, dict):
                continue
            available = lane.get("available")
            lanes[name] = {
                "available": available if type(available) is bool else None,
                "passed_probes": nonnegative(lane.get("passed_probes")),
                "total_probes": nonnegative(lane.get("total_probes")),
                "latency_ms": finite(1000 * lane["latency_average_s"], 0, 60000)
                    if type(lane.get("latency_average_s")) in (int, float) else None,
                "consecutive_success": nonnegative(lane.get("consecutive_success")),
                "consecutive_fail": nonnegative(lane.get("consecutive_fail")),
                "haproxy_before_action": str(lane.get("haproxy_before_action", ""))[:20]
                    if str(lane.get("haproxy_before_action", "")) in
                    ("UP", "DOWN", "MAINT", "STOPPED", "UNKNOWN") else "UNKNOWN",
                "tcp_https": "ok" if lane.get("available") is True
                    and (nonnegative(lane.get("passed_probes")) or 0) >= 2
                    else "degraded" if lane.get("available") is False else "unknown",
                "udp": "unknown",
            }
        return {"state": "ok", "age_s": round(age, 1), "paths": lanes}
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        return {"state": "unavailable", "age_s": None, "paths": {}}


def haproxy_stats():
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            sock.connect(HAPROXY)
            sock.sendall(b"show stat\n")
            sock.shutdown(socket.SHUT_WR)
            payload = bytearray()
            while len(payload) < 1024 * 1024:
                part = sock.recv(32768)
                if not part:
                    break
                payload += part
            else:
                return {}
        lines = payload.decode("utf-8", "replace").splitlines()
        if not lines:
            return {}
        names = lines[0].lstrip("# ").split(",")
        result = {}
        for row in csv.DictReader(io.StringIO("\n".join(lines[1:])), fieldnames=names):
            lane = row.get("svname")
            if row.get("pxname") != "dual_egress" or lane not in (*LANES, "BACKEND"):
                continue
            status = row.get("status", "unknown")
            result[lane] = {
                "status": status if status in ("UP", "DOWN", "MAINT", "STOPPED") else "unknown",
                "active_connections": nonnegative(row.get("scur")),
                "total_connections": nonnegative(row.get("stot")),
                "bytes_in": nonnegative(row.get("bin")),
                "bytes_out": nonnegative(row.get("bout")),
                "check_failures": nonnegative(row.get("chkfail")),
            }
        return result
    except (OSError, ValueError, csv.Error, UnicodeError):
        return {}


def foreign_ips():
    result = {name: None for name in LANES}
    try:
        for line in Path("/etc/dual-ha/backhaul-bundle.env").read_text().splitlines():
            m = re.fullmatch(r"BH_FOREIGN_IP='([^']+)'", line)
            if m:
                result["backhaul"] = ipv4(m.group(1))
    except OSError:
        pass
    mieru = read_json_small(Path("/etc/dual-ha/mieru.json"))
    try:
        result["mieru"] = ipv4(mieru["profiles"][0]["servers"][0]["ipAddress"])
    except (KeyError, IndexError, TypeError):
        pass
    return result


def build_snapshot(server_id, interface):
    health = controller()
    services = {name: service_state(name) for name in SERVICES}
    ha = haproxy_stats()
    if health["state"] == "ok" or ha:
        tunnel_type = "dual-backhaul-mieru-ha"
    else:
        tunnel_type = "unidentified"
    return {
        "schema": "hesab-tunnel-v11", "server_id": server_id,
        "sent_at": int(time.time()), "nonce": secrets.token_hex(16),
        "tunnel_type": tunnel_type, "system": sysinfo(interface),
        "services": services,
        "controller": health, "haproxy": ha,
        "foreign_ips": foreign_ips() if tunnel_type != "unidentified" else {},
        "quota": {"state": "unknown", "remaining_gb": None},
        "xui_online": None, "vpn_end_to_end": "not_tested",
    }


def send(endpoint, key, snapshot):
    raw = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise RuntimeError("Telemetry payload too large")
    timestamp = str(snapshot["sent_at"])
    signature = hmac.new(key, timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    req = urllib.request.Request(endpoint, data=raw, method="POST", headers={
        "Content-Type": "application/json",
        "X-Hesab-Server": snapshot["server_id"],
        "X-Hesab-Time": timestamp,
        "X-Hesab-Nonce": snapshot["nonce"],
        "X-Hesab-Signature": "sha256=" + signature,
    })
    with urllib.request.urlopen(req, timeout=9) as resp:
        if resp.status != 202:
            raise RuntimeError("Telemetry receiver did not accept payload")


def main():
    if os.geteuid() != 0:
        raise RuntimeError("Sensor requires root for local restricted HAProxy socket")
    sid, endpoint, key, iface = config()
    snapshot = build_snapshot(sid, iface)
    send(endpoint, key, snapshot)
    print("HEARTBEAT_ACCEPTED", sid, "controller", snapshot["controller"]["state"])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never log secrets, passwords, URLs or raw exception strings.
        print("TELEMETRY_FAILED", type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
