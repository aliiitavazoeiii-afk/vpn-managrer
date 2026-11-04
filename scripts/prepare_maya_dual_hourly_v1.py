#!/usr/bin/env python3
"""Prepare simple hourly Dual reader from the EXISTING verified NIC-meter SSH map.

Management host only. Does not alter remote host, VPN, XUI, Caddy, SSH
known_hosts, meter settings or any preexisting key. Uses the new dedicated
root authorized_keys forced-command key already installed on Maya hosts.
Safe summary output never prints host addresses, secrets or raw SSH logs.
"""
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys

SOURCE = Path("/root/.config/hesab-maya-net-meter-v2.json")
OUTPUT = Path("/root/.config/hesab-dual-hourly-v1.json")
IDENTITY = Path("/root/.ssh/hesab_dual_hourly_v1")
KNOWN = Path("/root/.ssh/known_hosts")
SERVERS = ("maya1", "maya-s3", "maya4")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import maya_dual_hourly_collect_v1 as collector

def secured(path, owner=True):
    return (path.is_file() and not path.is_symlink()
            and (not owner or path.stat().st_uid == 0)
            and path.stat().st_mode & 0o077 == 0)

def known_host(ip, port):
    target = ip if port == 22 else f"[{ip}]:{port}"
    result = subprocess.run(
        ["ssh-keygen", "-F", target, "-f", str(KNOWN)],
        capture_output=True, text=True, timeout=4, check=False,
    )
    return result.returncode == 0

def generate():
    if not secured(SOURCE) or not secured(IDENTITY):
        raise ValueError("Missing protected meter config or dedicated SSH key")
    if not KNOWN.is_file() or KNOWN.is_symlink():
        raise ValueError("Existing verified SSH known_hosts required")
    original = json.loads(SOURCE.read_text(encoding="utf8"))
    entries = original.get("servers")
    if not isinstance(entries, dict):
        raise ValueError("Meter server map missing")
    servers = {}
    for sid in SERVERS:
        item = entries.get(sid)
        if not isinstance(item, dict):
            print("METER_SSH_SOURCE_MISSING", sid)
            continue
        host = str(item.get("host", ""))
        port = item.get("ssh_port", 22)
        try:
            ip = ipaddress.ip_address(host)
            if ip.version != 4 or not ip.is_global:
                raise ValueError("nonpublic")
            port = int(port)
            if not 1 <= port <= 65535:
                raise ValueError("port")
        except ValueError:
            print("METER_SSH_SOURCE_INVALID", sid)
            continue
        if not known_host(host, port):
            print("SSH_HOST_TRUST_MISSING", sid)
            continue
        servers[sid] = {
            "host": host, "ssh_port": port, "ssh_user": "root",
            "ssh_identity": str(IDENTITY),
        }
        print("REUSED_EXISTING_VERIFIED_SSH_IDENTITY", sid)
    if len(servers) != len(SERVERS):
        print("STOP=MISSING_VERIFIED_METER_HOST")
        return None
    return {"servers": servers}

def prepare():
    if os.geteuid() != 0:
        raise PermissionError("root required")
    if OUTPUT.exists():
        if not secured(OUTPUT):
            raise ValueError("Existing dual config is insecure")
        doc = json.loads(OUTPUT.read_text(encoding="utf8"))
        if not isinstance(doc, dict) or not isinstance(doc.get("servers"), dict):
            raise ValueError("Existing dual config malformed")
        servers = doc["servers"]
        print("EXISTING_DUAL_CONFIG=UNCHANGED")
    else:
        doc = generate()
        if doc is None:
            return 3
        OUTPUT.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(str(OUTPUT), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf8") as stream:
            json.dump(doc, stream, ensure_ascii=False)
        servers = doc["servers"]
        print("DUAL_CONFIG=CREATED_PRIVATE")

    # Verify and report each required Iran host. No active network probes
    # beyond the single restricted SSH execution of cached 'dual status'.
    verified = 0
    for sid in SERVERS:
        item = servers.get(sid)
        if not isinstance(item, dict):
            print("DUAL_SSH_ACCESS=NOT_CONFIGURED", sid)
            continue
        try:
            report = collector.fetch(sid, item)
            assert set(report["paths"]) == {"backhaul", "mieru"}
            for role in ("backhaul", "mieru"):
                assert report["paths"][role]["ip"] is not None
            print("DUAL_SSH_ACCESS=PASS", sid,
                  "backhaul", report["paths"]["backhaul"]["state"],
                  "mieru", report["paths"]["mieru"]["state"])
            verified += 1
        except Exception as exc:
            print("DUAL_SSH_ACCESS=FAILED", sid, type(exc).__name__)
    print("VERIFIED_HOSTS", verified, "/", len(SERVERS))
    print("PRODUCTION_APP_OR_TUNNEL_CHANGED=NO")
    return 0 if verified == len(SERVERS) else 4

if __name__ == "__main__":
    try:
        raise SystemExit(prepare())
    except (OSError, ValueError, PermissionError, KeyError, TypeError,
            subprocess.TimeoutExpired) as exc:
        print("PREPARE_STOP", type(exc).__name__)
        raise SystemExit(2)
