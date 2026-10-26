#!/usr/bin/env bash
# HESAB_MAYA1_AFTER_REBUILD_DIAG_V1
# Read-only. Does not alter credentials, ssh trust, mappings, XUI or accounting.
set -u
cd /opt/vpn-control-center || exit 2
echo "=== MAYA1 AFTER-REBUILD SAFETY DIAG ==="
python3 - <<'PY'
import json,os,ast,re
from pathlib import Path
p=Path("/root/.config/hesab-maya-extra.json")
if not p.exists():
 print("LIVE_CFG=MISSING")
else:
 try:
  cfg=json.loads(p.read_text())
  e=cfg.get("maya1")
  if not isinstance(e,dict):
   print("LIVE_CFG=MAYA1_NOT_CONFIGURED")
  else:
   print("LIVE_CFG=present")
   for k in ("transport","server","ssh_host","ssh_port","ssh_user","remote_port","panel_path","mode"):
    if k in e:print("LIVE_"+k.upper()+"="+str(e[k]))
   if e.get("transport","https")=="https" and e.get("url"):
    from urllib.parse import urlsplit
    u=urlsplit(e["url"])
    print("LIVE_HTTPS_HOST="+str(u.hostname))
    print("LIVE_HTTPS_PORT="+str(u.port or 443))
    print("LIVE_HTTPS_PATH="+(u.path or "/"))
   # Never print token, username, password, API keys, cookie, full JSON.
 except Exception as exc:
  print("LIVE_CFG_ERROR="+type(exc).__name__+":"+str(exc)[:110])
for path in ["/opt/vpn-control-center/scripts/maya1_readonly_sync.py",
             "/opt/vpn-control-center/scripts/maya1_control_gateway.py"]:
 try:
  source=Path(path).read_text()
  tree=ast.parse(source)
  old=None
  for item in tree.body:
   if isinstance(item,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="HOST" for t in item.targets):
    old=ast.literal_eval(item.value)
  print("LEGACY_PINNED_HOST_"+Path(path).name+"="+str(old))
 except Exception as exc: print("LEGACY_HOST_CHECK_ERROR="+str(exc)[:90])
for path in ["/opt/vpn-control-center/maya1_sync/mapping.json",
             "/opt/vpn-control-center/maya1_sync/snapshot.json",
             "/opt/vpn-control-center/maya_extra_sync/public/maya1.json"]:
 p=Path(path)
 print("FILE_"+p.name+"="+("exists size="+str(p.stat().st_size) if p.is_file() else "missing"))
PY
echo "=== LIVE BROKER SERVICE / SOCKET ==="
systemctl is-active hesab-maya-live.service 2>&1 || true
test -S maya_extra_sync/live.sock && echo "LIVE_SOCKET=present" || echo "LIVE_SOCKET=missing"
echo "=== LIVE API SNAPSHOT AS SEEN BY DASHBOARD ==="
python3 - <<'PY'
import json,socket
msg=json.dumps({"op":"snapshot","server":"maya1"}).encode()+b"\n"
try:
 s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(45)
 s.connect("/opt/vpn-control-center/maya_extra_sync/live.sock")
 s.sendall(msg);s.shutdown(socket.SHUT_WR)
 buf=b""
 while not buf.endswith(b"\n") and len(buf)<3000000:
  x=s.recv(65536)
  if not x:break
  buf+=x
 d=json.loads(buf)
 if d.get("ok") is True:
  snap=d.get("snapshot") or {}
  print("LIVE_BROKER_OK=TRUE")
  print("LIVE_CLIENTS_COUNT="+str(len(snap.get("clients") or [])))
  print("LIVE_SERVER="+str(snap.get("server")))
 else:
  print("LIVE_BROKER_OK=FALSE")
  print("LIVE_BROKER_ERROR="+str(d.get("error") or "unknown")[:160])
except Exception as exc:
 print("LIVE_BROKER_FAILED="+type(exc).__name__+":"+str(exc)[:160])
finally:
 try:s.close()
 except Exception:pass
PY
echo "=== LIVE CONFIG DIRECT PROBE (no snapshots written) ==="
python3 /opt/vpn-control-center/scripts/maya_multi_panel_sync.py check maya1 2>&1 | tail -8 || true
echo "=== OLD MAYA1 CRON/SYNC (only inventory; NOT RUNNING OLD SYNC) ==="
test -s /etc/cron.d/hesab-maya1-sync && grep -Ec '^[^#].*maya1_readonly_sync.py' /etc/cron.d/hesab-maya1-sync || true
echo "=== MAYA BROKER RECENT ERRORS (SECRET-FREE CATEGORIES ONLY) ==="
journalctl -u hesab-maya-live.service --since '-20 min' --no-pager -o cat 2>/dev/null |
  grep -E 'error|Error|failed|Failed|SSH|Traceback' |
  sed -E 's/(password|token|api_key|secret)=([^[:space:]]+)/\1=[REDACTED]/g' | tail -10 || true
echo "=== DONE: READ ONLY; NO FINANCIAL OR XUI ACTIONS ==="
