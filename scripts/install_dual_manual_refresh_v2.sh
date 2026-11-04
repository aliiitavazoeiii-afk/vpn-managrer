#!/usr/bin/env bash
# HESAB_DUAL_MANUAL_REFRESH_AND_MAYA3_XUI_V2_INSTALLER
# Installs one local Unix-socket read-only refresh worker and protected admin UI.
# Existing hourly collector, XUI tunnel paths, Caddy, DB, and traffic ledgers untouched.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP=ROOT_REQUIRED"; exit 2; }
SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT=/opt/vpn-control-center
cd "$ROOT"
UI=patches/maya1_control.py
PATCH="$SOURCE/patches/control_room_dual_manual_refresh_v2.py"
BROKER="$SOURCE/scripts/maya_dual_refresh_broker_v2.py"
REPAIR="$SOURCE/scripts/repair_maya3_xui_sync_v2.py"
BROKER_DEST=scripts/maya_dual_refresh_broker_v2.py
REPAIR_DEST=scripts/repair_maya3_xui_sync_v2.py
SERVICE=/etc/systemd/system/hesab-dual-refresh-v2.service
SOCKET=maya_extra_sync/dual_refresh_v2.sock
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }

for path in "$UI" "$PATCH" "$BROKER" "$REPAIR" \
            scripts/maya_dual_hourly_collect_v1.py \
            scripts/maya_multi_panel_sync.py \
            docker-compose.yml docker-compose.sms.yml; do
  [[ -s "$path" ]] || { echo "STOP=MISSING_FILE $path"; exit 3; }
done
grep -Fq '# HESAB_CONTROL_ROOM_DUAL_HOURLY_SIMPLE_V1' "$UI" ||
 { echo "STOP=HOURLY_DUAL_UI_NOT_INSTALLED"; exit 3; }
if grep -Fq '# HESAB_DUAL_HOURLY_MANUAL_REFRESH_V2' "$UI";then
 echo "ALREADY_INSTALLED=YES"
 systemctl is-active --quiet hesab-dual-refresh-v2.service &&
   echo "MANUAL_REFRESH_WORKER=ACTIVE"
 python3 "$REPAIR" || true
 exit 0
fi

python3 -m py_compile "$PATCH" "$BROKER" "$REPAIR" "$UI"
compose config -q
OLD="$(compose ps -q app)"
[[ -n "$OLD" && "$(docker inspect -f '{{.State.Running}}' "$OLD")" == true ]] ||
 { echo "STOP=ADMIN_APP_NOT_RUNNING"; exit 3; }

echo "=== PREFLIGHT CURRENT V1 UI + NEW BUTTON ==="
cat "$PATCH" | compose exec -T app python -c '
import sys
from app import main as m
from starlette.requests import Request
from jinja2 import Environment
routes_before=[r.path for r in m.app.routes]
assert routes_before.count("/control-room/dual-hourly/status")==1
assert "id=\"dh1-script\"" in m.TEMPLATES["control_room.html"]
assert "id=\"dh1-grid\"" in m.TEMPLATES["control_room.html"]
assert m.TEMPLATES["control_room.html"].index("id=\"dh1-grid\"") < m.TEMPLATES["control_room.html"].index("id=\"dh1-script\"")
exec(compile(sys.stdin.read(),"<dual-manual-v2-preflight>","exec"),vars(m))
assert [r.path for r in m.app.routes]==routes_before+[
 "/control-room/dual-hourly/refresh","/control-room/dual-hourly/refresh-meta"]
t=m.TEMPLATES["control_room.html"]
assert t.count("id=\"dm2-refresh\"")==1 and t.count("id=\"dm2-script\"")==1
assert t.index("id=\"dh1-grid\"") < t.index("id=\"dh1-script\"") < t.index("id=\"dm2-script\"")
assert "window.__HESAB_DUAL_REFRESH_NOW=refresh" in t
Environment().parse(t)
token="t"*40
scope={"type":"http","asgi":{"version":"3.0"},"http_version":"1.1",
"method":"GET","scheme":"https","path":"/control-room/dual-hourly/refresh-meta",
"root_path":"","query_string":b"",
"headers":[(b"host",b"hesab.filmjadiid.ir"),(b"x-control-csrf",token.encode())],
"server":("hesab.filmjadiid.ir",443),"client":("127.0.0.1",1234),
"session":{"maya1_control_csrf":token},"app":m.app}
assert m._dm2_meta(Request(scope)).status_code==200
scope["headers"]=[(b"host",b"hesab.filmjadiid.ir")]
assert m._dm2_meta(Request(scope)).status_code==403
scope["method"]="POST"
assert m._dm2_trigger(Request(scope)).status_code==403
print("ADMIN_AUTH_AND_BUTTON_PREFLIGHT=PASS")
'

BACKUP="/root/hesab-dual-manual-v2-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BACKUP"
cp -a "$UI" "$BACKUP/maya1_control.py"
for f in "$BROKER_DEST" "$REPAIR_DEST" "$SERVICE";do
 key="$(echo "$f" | tr '/.' '__')"
 if [[ -e "$f" ]];then cp -a "$f" "$BACKUP/$key";fi
done
echo "BACKUP=$BACKUP"

CHANGED=0
rollback(){
 code=$?
 trap - EXIT
 if ((code!=0&&CHANGED));then
  echo "MANUAL_REFRESH_INSTALL_FAILED_ROLLING_BACK"
  systemctl stop hesab-dual-refresh-v2.service >/dev/null 2>&1 || true
  systemctl disable hesab-dual-refresh-v2.service >/dev/null 2>&1 || true
  cp -a "$BACKUP/maya1_control.py" "$UI"
  for f in "$BROKER_DEST" "$REPAIR_DEST" "$SERVICE";do
   key="$(echo "$f" | tr '/.' '__')"
   if [[ -e "$BACKUP/$key" ]];then cp -a "$BACKUP/$key" "$f"
   else rm -f "$f";fi
  done
  systemctl daemon-reload || true
  compose up -d --no-deps --no-build --force-recreate app ||
   echo "WARNING=ADMIN_APP_ROLLBACK_RECREATE_FAILED"
  echo "ROLLBACK_BACKUP=$BACKUP"
 fi
 exit "$code"
}
trap rollback EXIT

CHANGED=1
install -o root -g root -m 0700 "$BROKER" "$BROKER_DEST"
install -o root -g root -m 0700 "$REPAIR" "$REPAIR_DEST"
cat >"$SERVICE" <<'UNIT'
[Unit]
Description=Hesab manual cached Dual status refresh broker (local Unix socket)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/vpn-control-center
ExecStart=/usr/bin/python3 /opt/vpn-control-center/scripts/maya_dual_refresh_broker_v2.py
Restart=always
RestartSec=3
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now hesab-dual-refresh-v2.service
READY=0
for i in $(seq 1 20);do
 if systemctl is-active --quiet hesab-dual-refresh-v2.service && test -S "$SOCKET";then
  READY=1;break
 fi
 sleep 1
done
[[ "$READY" == 1 ]] || { echo "STOP=REFRESH_BROKER_NOT_RUNNING"; false; }

echo "=== CHECK ADMIN APP CAN REACH LOCAL BROKER SOCKET ==="
compose exec -T app python - <<'PY'
import socket
p="/srv/maya-live/dual_refresh_v2.sock"
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
    s.settimeout(3)
    s.connect(p)
print("ADMIN_TO_MANUAL_REFRESH_SOCKET=READY")
PY

printf '\n\n' >>"$UI"
cat "$PATCH" >>"$UI"
python3 -m py_compile "$UI"
echo "=== RECREATE ONLY ADMIN APP ==="
compose up -d --no-deps --no-build --force-recreate app

READY=0
for i in $(seq 1 30);do
 if compose exec -T app python - <<'PY' >/dev/null 2>&1
from app import main as m
from starlette.requests import Request
from jinja2 import Environment
routes=[r.path for r in m.app.routes]
for path in ("/control-room","/control-room/v10/daily","/control-room/v9/topup",
             "/control-room/dual-hourly/status",
             "/control-room/dual-hourly/refresh",
             "/control-room/dual-hourly/refresh-meta"):
 assert routes.count(path)==1,path
t=m.TEMPLATES["control_room.html"]
assert t.count("id=\"dm2-refresh\"")==1
assert t.count("id=\"dh1-grid\"")==1
assert "window.__HESAB_DUAL_REFRESH_NOW=refresh;" in t
Environment().parse(t)
token="t"*40
scope={"type":"http","asgi":{"version":"3.0"},"http_version":"1.1",
"method":"GET","scheme":"https","path":"/control-room/dual-hourly/refresh-meta",
"root_path":"","query_string":b"",
"headers":[(b"host",b"hesab.filmjadiid.ir"),(b"x-control-csrf",token.encode())],
"server":("hesab.filmjadiid.ir",443),"client":("127.0.0.1",1234),
"session":{"maya1_control_csrf":token},"app":m.app}
assert m._dm2_meta(Request(scope)).status_code==200
scope["headers"]=[(b"host",b"hesab.filmjadiid.ir")]
assert m._dm2_meta(Request(scope)).status_code==403
scope["method"]="POST"
assert m._dm2_trigger(Request(scope)).status_code==403
assert m._cr2_page(Request(scope)).status_code==200
PY
 then READY=1;break;fi
 sleep 2
done
[[ "$READY" == 1 ]] || { echo "STOP=MANUAL_REFRESH_APP_RUNTIME_CHECK_FAILED";false; }

echo "=== REAL LOCAL BUTTON WORKER TEST (READ ONLY) ==="
python3 - <<'PY'
import json,socket,time
from pathlib import Path
path=Path("/opt/vpn-control-center/maya_extra_sync/dual_hourly_v1.json")
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
 s.settimeout(5)
 s.connect("/opt/vpn-control-center/maya_extra_sync/dual_refresh_v2.sock")
 s.sendall(b'{"op":"refresh"}\n');s.shutdown(socket.SHUT_WR)
 raw=b""
 while not raw.endswith(b"\n") and len(raw)<1000:
  part=s.recv(1000-len(raw))
  if not part:break
  raw+=part
answer=json.loads(raw)
assert answer.get("ok") is True and answer.get("accepted") is True,answer.get("error")
before=answer["before"]
for n in range(80):
 if path.exists() and int(path.stat().st_mtime*1000)>before:
  doc=json.loads(path.read_text())
  assert doc["format"]=="HESAB_DUAL_HOURLY_V1"
  for name in ("maya1","maya-s3","maya4"):
   assert doc["servers"][name]["state"]=="ok",(name,doc["servers"][name]["state"])
  print("BUTTON_BROKER_ACTUAL_PULL=PASS_THREE_MAYA")
  break
 time.sleep(1)
else:raise RuntimeError("Fresh snapshot did not arrive")
PY

trap - EXIT
echo "SUCCESS=DUAL_MANUAL_REFRESH_BUTTON_LIVE"
echo "HOURLY_TIMER_PRESERVED=YES"
echo "=== MAYA3 XUI SOURCE CHECK / SAFE REPAIR ==="
python3 "$REPAIR_DEST" || echo "MAYA3_XUI_REPAIR_NEEDS_REVIEW"
echo "NO_CADDY_XUI_TUNNEL_PROVIDER_LEDGER_CHANGES=TRUE"
echo "BACKUP=$BACKUP"
