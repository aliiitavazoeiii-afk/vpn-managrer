#!/usr/bin/env python3
"""Hesab simple hourly Dual HA status: read 'dual status' from Iran hosts via SSH.

Management-host-only; no probes, tunnel changes, XUI writes, or web receiver.
Each SSH connection is batch-mode, host-key verified and uses a configured key.
Never logs raw remote stdout/stderr or any credentials.
"""
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path("/opt/vpn-control-center")
CFG = Path("/root/.config/hesab-dual-hourly-v1.json")
OUT = ROOT / "maya_extra_sync/dual_hourly_v1.json"
SERVERS = ("maya1", "maya-s3", "maya4")
FORMAT = "HESAB_DUAL_HOURLY_V1"
MAX_STDOUT = 10000

def validate_config():
    if not CFG.is_file() or CFG.is_symlink() or CFG.stat().st_uid != 0 or CFG.stat().st_mode & 0o077:
        raise ValueError("Protected config missing or insecure")
    data = json.loads(CFG.read_text(encoding="utf8"))
    servers = data.get("servers")
    if not isinstance(servers, dict) or not servers or set(servers) - set(SERVERS):
        raise ValueError("Expected configured Maya names")
    for name, item in servers.items():
        if not isinstance(item, dict):
            raise ValueError("Invalid server config")
        if item.get("enabled") is False:
            continue
        host = str(item["host"])
        ipaddress.ip_address(host)
        key = Path(str(item["ssh_identity"]))
        if key.parent != Path("/root/.ssh") or not key.is_file() or key.is_symlink():
            raise ValueError("Dedicated SSH identity missing")
        if key.stat().st_mode & 0o077:
            raise ValueError("SSH identity permission unsafe")
        if item.get("ssh_user", "root") != "root":
            raise ValueError("Restricted to root for dual status")
        port = int(item.get("ssh_port", 22))
        if not 1 <= port <= 65535:
            raise ValueError("Invalid SSH port")
    return servers

def parse_dual_status(text, sampled_at=None):
    """Parse the exact text produced by upstream dual-backhaul-mieru-ha/v2/dual.py status."""
    if not isinstance(text, str) or len(text) > MAX_STDOUT:
        raise ValueError("Remote output size")
    if "\x1b" in text:
        raise ValueError("Unexpected terminal escape")
    lines = text.splitlines()
    controller_age = None
    for line in lines:
        m = re.search(r"health\.json age:\s*(\d+)s", line)
        if m:
            controller_age = int(m.group(1))
            break
    paths = {}
    for i, line in enumerate(lines[:-1]):
        m = re.match(r"^\s*(BACKHAUL|MIERU)\s+(\S+)\s+local SOCKS 127\.0\.0\.1:(21001|21002)\s*$", line)
        if not m:
            continue
        name = m.group(1).lower()
        if name in paths or m.group(3) != ("21001" if name == "backhaul" else "21002"):
            raise ValueError("Duplicate/invalid role")
        raw_ip = m.group(2)
        try:
            foreign_ip = str(ipaddress.IPv4Address(raw_ip))
            if not ipaddress.ip_address(foreign_ip).is_global:
                foreign_ip = None
        except ipaddress.AddressValueError:
            foreign_ip = None
        detail = lines[i+1]
        health = re.search(r"(?:HEALTHY\b|DOWN / health checks failed\b|UNKNOWN \(stale/missing controller data\))", detail)
        https = re.search(r"https=(\d+)/(\d+)\s+avg=([0-9.]+|\?|None)s?", detail)
        if not https or not health:
            raise ValueError("Unrecognized dual status line")
        passed, total = int(https.group(1)), int(https.group(2))
        if total != 3 or passed > total:
            raise ValueError("Unexpected probe totals")
        latency = None
        try:
            value = float(https.group(3))
            if 0 <= value <= 120 and value != float("inf"):
                latency = round(value * 1000)
        except ValueError:
            pass
        line_state = health.group(0)
        state = ("healthy" if line_state == "HEALTHY" and passed >= 2
                 else "down" if line_state.startswith("DOWN") else "unknown")
        if controller_age is None or controller_age > 30:
            state = "stale"
            latency = None
        paths[name] = {
            "ip": foreign_ip, "state": state,
            "https_passed": passed, "https_total": total,
            "https_avg_ms": latency,
        }
    if set(paths) != {"backhaul", "mieru"}:
        raise ValueError("Dual roles absent")
    return {
        "state": "ok" if controller_age is not None and controller_age <= 30 else "stale",
        "sampled_at": int(time.time()) if sampled_at is None else int(sampled_at),
        "controller_age_s": controller_age,
        "paths": paths,
    }

def fetch(name, item):
    host = str(item["host"])
    port = str(int(item.get("ssh_port", 22)))
    key = str(item["ssh_identity"])
    command = [
        "ssh", "-F", "/dev/null", "-n", "-T",
        "-i", key, "-p", port,
        "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=6", "-o", "ConnectionAttempts=1",
        "-o", "ControlMaster=no", "-o", "ForwardAgent=no",
        "-o", "ClearAllForwardings=yes", "-o", "LogLevel=ERROR",
        "root@" + host,
        "/usr/bin/env NO_COLOR=1 /usr/local/bin/dual status",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
    if result.returncode != 0 or len(result.stdout) > MAX_STDOUT:
        raise RuntimeError("SSH unavailable or unexpected response")
    return parse_dual_status(result.stdout)

def atomic(obj):
    OUT.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    fd, name = tempfile.mkstemp(prefix=".dual-hourly-", dir=str(OUT.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf8") as stream:
            json.dump(obj, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, 0o640)
        os.replace(name, OUT)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def main():
    if os.geteuid() != 0:
        raise PermissionError("Root is required for protected SSH identity")
    servers = validate_config()
    results = {}
    for sid in SERVERS:
        item = servers.get(sid)
        if not item or item.get("enabled") is False:
            results[sid] = {"state": "not_configured"}
            continue
        try:
            results[sid] = fetch(sid, item)
            print("DUAL_HOURLY_OK", sid, results[sid]["state"])
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as err:
            results[sid] = {"state": "unavailable"}
            print("DUAL_HOURLY_UNAVAILABLE", sid, type(err).__name__)
    atomic({"format": FORMAT, "collected_at": int(time.time()), "servers": results})
    print("DUAL_HOURLY_SNAPSHOT_SAVED")

if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, PermissionError) as err:
        print("DUAL_HOURLY_FATAL", type(err).__name__)
        sys.exit(1)
