#!/usr/bin/env python3
"""Safely reuse existing verified Maya SSH tunnel metadata if executable.

No SSH key creation, host-key acceptance, tunnel change, app change or Caddy.
Writes only a NEW protected local config; never overwrites it. A restricted
XUI port-forward-only identity may legitimately deny dual status execution.
"""
import ipaddress
import json
import os
from pathlib import Path
import sys

ROOT = Path("/opt/vpn-control-center")
SOURCE = Path("/root/.config/hesab-maya-extra.json")
OUTPUT = Path("/root/.config/hesab-dual-hourly-v1.json")
sys.path.insert(0, str(ROOT / "scripts"))
import maya_dual_hourly_collect_v1 as collector

def prepare():
    if os.geteuid() != 0:
        raise PermissionError("Requires root")
    if OUTPUT.exists():
        print("EXISTING_DUAL_CONFIG=UNCHANGED")
        cfg = json.loads(OUTPUT.read_text(encoding="utf8"))
        servers = cfg["servers"]
    else:
        if not SOURCE.is_file() or SOURCE.is_symlink() or SOURCE.stat().st_mode & 0o077:
            raise ValueError("Maya config not secure/available")
        original = json.loads(SOURCE.read_text(encoding="utf8"))
        servers = {}
        for sid in ("maya1", "maya-s3"):
            item = original.get(sid) or {}
            if item.get("transport") != "ssh":
                print("SSH_METADATA_UNAVAILABLE", sid)
                continue
            host = str(item.get("ssh_host", ""))
            try:
                ipaddress.ip_address(host)
            except ValueError:
                print("SSH_HOST_INVALID", sid)
                continue
            key = Path("/root/.ssh/hesab_" + sid.replace("-", "_") + "_tunnel")
            if not key.is_file() or key.is_symlink() or key.stat().st_mode & 0o077:
                print("SSH_IDENTITY_UNAVAILABLE", sid)
                continue
            if str(item.get("ssh_user") or "root") != "root":
                print("SSH_USER_UNSUPPORTED", sid)
                continue
            port = int(item.get("ssh_port", 22))
            if not 1 <= port <= 65535:
                print("SSH_PORT_INVALID", sid)
                continue
            servers[sid] = {"host": host, "ssh_port": port,
                            "ssh_identity": str(key), "ssh_user": "root"}
        if not servers:
            print("NO_EXISTING_SSH_IDENTITY_CAN_BE_REUSED")
            return 3
        fd = os.open(str(OUTPUT), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf8") as f:
            json.dump({"servers": servers}, f, ensure_ascii=False)
        print("DUAL_CONFIG=CREATED_PRIVATE")
    passes = 0
    for sid in ("maya1", "maya-s3"):
        if sid not in servers:
            print("DUAL_SSH_NOT_CONFIGURED", sid)
            continue
        try:
            item = collector.fetch(sid, servers[sid])
            print("DUAL_SSH_ACCESS=PASS", sid,
                  "backhaul", item["paths"]["backhaul"]["state"],
                  "mieru", item["paths"]["mieru"]["state"])
            passes += 1
        except Exception as ex:
            print("DUAL_SSH_ACCESS=NOT_YET_AVAILABLE", sid, type(ex).__name__)
    print("READONLY_CHECK_FINISHED; PASSED_HOSTS", passes)
    return 0 if passes == len(servers) else 4

if __name__ == "__main__":
    try:
        raise SystemExit(prepare())
    except (OSError, ValueError, PermissionError, KeyError, TypeError) as ex:
        print("PREPARE_STOP", type(ex).__name__)
        raise SystemExit(2)
