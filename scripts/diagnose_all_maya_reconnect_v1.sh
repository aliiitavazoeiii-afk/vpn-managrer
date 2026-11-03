#!/usr/bin/env bash
# HESAB_MAYA_RECONNECT_READONLY_V1
# Inspect current production config and test only targets verified to be at
# the operator-supplied new IPs. DOES NOT modify files, SSH, X-UI or finance.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo "STOP: run on accounting host as root"; exit 2; }
cd /opt/vpn-control-center || exit 2
[[ -s scripts/maya_multi_panel_sync.py ]] || {
  echo "STOP: existing Maya connector script missing"; exit 3;
}
echo "=== MAYA RECONNECTION CHECK (READ ONLY) ==="
echo "EXPECTED: maya1=94.184.4.38; maya-s3=185.215.230.221; maya4=5.10.249.206"
python3 - <<'PY'
import datetime as dt
import ipaddress
import json
import os
import re
import socket
import stat
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path("/opt/vpn-control-center")
CONFIG = Path("/root/.config/hesab-maya-extra.json")
EXPECTED = (
  ("maya1", "94.184.4.38"),
  ("maya-s3", "185.215.230.221"),
  ("maya4", "5.10.249.206"),
)
if not CONFIG.is_file():
    print("CONFIG=ABSENT (no server credentials were read)")
    sys.exit(0)
if CONFIG.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
    print("STOP: configuration permissions not private; do not read credentials")
    sys.exit(3)
try:
    config=json.loads(CONFIG.read_text())
    if not isinstance(config,dict):raise TypeError("config not object")
except (ValueError,OSError,TypeError):
    print("CONFIG=UNREADABLE (no contents displayed)")
    sys.exit(3)

def host_match(entry,expected):
    transport=entry.get("transport","https")
    if transport=="ssh":
        host=str(entry.get("ssh_host",""))
        return host==expected,host,"ssh"
    if transport=="https":
        try:
            host=urlsplit(str(entry.get("url",""))).hostname or ""
        except ValueError:
            return False,"[invalid]","https"
        if host==expected:
            return True,host,"https"
        try:
            ips={v[4][0] for v in socket.getaddrinfo(host,None,type=socket.SOCK_STREAM)}
        except (socket.gaierror,OSError):
            ips=set()
        return expected in ips,host,"https"
    return False,"[unsupported]","unknown"

def category(output):
    msg=(output or "").casefold()
    for label,patterns in (
        ("SSH_HOST_KEY_CHANGED",("host identification has changed","remote host identification","host key verification failed")),
        ("SSH_PAIRING_MISSING",("ssh key missing","permission denied","tunnel failed")),
        ("PANEL_PROTOCOL_MISMATCH",("wrong_version_number","wrong version number","ssl error")),
        ("PANEL_AUTH_FAILED",("rejected login","panel rejected login","http 401","http 403","unauthorized")),
        ("PANEL_PATH_OR_PORT",("http 404","returned a non-json","non-json response","connection refused")),
        ("PANEL_TIMEOUT",("timed out","timeout")),
        ("DATABASE_READ_FAILED",("dashboard read-only query failed",)),
    ):
        if any(p in msg for p in patterns):return label
    return "UNCLASSIFIED_ERROR"

def bridge(name):
    sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    try:
        sock.settimeout(38)
        sock.connect(str(ROOT/"maya_extra_sync/live.sock"))
        sock.sendall(json.dumps({"op":"snapshot","server":name}).encode()+b"\n")
        sock.shutdown(socket.SHUT_WR)
        out=b""
        while not out.endswith(b"\n") and len(out)<3000000:
            chunk=sock.recv(65536)
            if not chunk:break
            out+=chunk
        if not out.endswith(b"\n"):
            print("BROKER=INCOMPLETE_RESPONSE")
            return
        obj=json.loads(out)
        if obj.get("ok") is True:
            snap=obj.get("snapshot") or {}
            print("BROKER=CONNECTED clients="+str(len(snap.get("clients") or [])))
        else:
            print("BROKER=FAILED category="+category(str(obj.get("error") or "")))
    except (OSError,ValueError) as e:
        print("BROKER=FAILED kind="+type(e).__name__)
    finally:sock.close()

try:
    r=subprocess.run(["systemctl","is-active","hesab-maya-live.service"],
        capture_output=True,text=True,timeout=5)
    print("BROKER_SERVICE="+("ACTIVE" if r.returncode==0 else "INACTIVE"))
except (OSError,subprocess.TimeoutExpired):
    print("BROKER_SERVICE=UNKNOWN")

for name,expected in EXPECTED:
    print("\n--- "+name+" ---")
    entry=config.get(name)
    if not isinstance(entry,dict):
        print("CONFIG=NOT_CONFIGURED")
        continue
    matches,host,transport=host_match(entry,expected)
    print("TRANSPORT="+transport)
    print("CONFIGURED_HOST="+host)
    print("EXPECTED_IP="+expected)
    print("TARGET_VERIFIED="+("YES" if matches else "NO"))
    if transport=="ssh":
        port=entry.get("remote_port")
        print("XUI_PORT="+str(port if isinstance(port,int) or str(port).isdigit() else "UNKNOWN"))
        key=Path("/root/.ssh/hesab_"+name.replace("-","_")+"_tunnel")
        print("RESTRICTED_SSH_KEY="+("PRESENT" if key.is_file() else "MISSING"))
    if not matches:
        print("CHECK=SKIPPED_TO_PROTECT_CREDENTIALS (old target or unverifiable DNS)")
        continue
    # Existing 'check' uses exact 3x-ui API read and finance read-only SQL;
    # it does not toggle a client or save snapshots.
    try:
        p=subprocess.run([sys.executable,str(ROOT/"scripts/maya_multi_panel_sync.py"),"check",name],
            capture_output=True,text=True,timeout=88,cwd=str(ROOT))
        if p.returncode==0:
            output=p.stdout.strip()
            count=re.search(r"\btotal=\s*(\d+).*?\blinked=\s*(\d+).*?\bunmatched=\s*(\d+)",output)
            print("PANEL_CHECK=PASS")
            if count:
                print("XUI_CLIENT_COUNT="+count.group(1))
                print("NAME_MATCH_COUNT="+count.group(2))
                print("NEEDS_MATCH_REVIEW="+count.group(3))
            else:
                print("PANEL_RESULT=UNPARSED")
        else:
            print("PANEL_CHECK=FAILED category="+category(p.stderr+" "+p.stdout))
    except subprocess.TimeoutExpired:
        print("PANEL_CHECK=TIMEOUT")
    except OSError:
        print("PANEL_CHECK=EXECUTION_ERROR")
    bridge(name)

print("\n=== SNAPSHOT FRESHNESS (NOT A HEALTH CERTIFICATE) ===")
for name,_ in EXPECTED:
    p=ROOT/"maya_extra_sync/public"/(name+".json")
    if not p.is_file():
        print(name,"snapshot=MISSING")
    else:
        seconds=max(0,dt.datetime.now(dt.timezone.utc).timestamp()-p.stat().st_mtime)
        print(name,"snapshot_age_minutes="+str(round(seconds/60,1)))
print("=== END: NO CREDENTIALS PRINTED; NO CHANGES MADE ===")
PY
