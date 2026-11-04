#!/usr/bin/env bash
# HESAB_MANUAL_PATH_TRANSFER_V1_INSTALLER
# Account host only. NO ACTIVE DOWNLOAD ON INSTALL. Requires 3 verified forced
# SSH key deployments. No tunnel/HAProxy/XUI/Caddy/health-controller changes.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP=ROOT_REQUIRED";exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
ROOT=/opt/vpn-control-center
cd "$ROOT"
UI=patches/maya1_control.py
BROKER="$SRC/scripts/hesab_manual_path_test_broker_v1.py"
PATCH="$SRC/patches/control_room_manual_path_test_v1.py"
BROKER_DEST=scripts/hesab_manual_path_test_broker_v1.py
SERVICE=/etc/systemd/system/hesab-manual-path-transfer-v1.service
SOCKET=maya_extra_sync/path_transfer_v1.sock
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }

for f in "$UI" "$BROKER" "$PATCH" docker-compose.yml docker-compose.sms.yml \
         scripts/maya_dual_hourly_collect_v1.py;do
 [[ -s "$f" ]] || { echo "STOP=MISSING_FILE $f";exit 3; }
done
for marker in '# HESAB_CONTROL_ROOM_COMPACT_V10' \
              '# HESAB_CONTROL_ROOM_DUAL_HOURLY_SIMPLE_V1' \
              '# HESAB_DUAL_HOURLY_MANUAL_REFRESH_V2' \
              '# HESAB_DUAL_PASSIVE_QUALITY_V1' \
              '# HESAB_CONTROL_ROOM_ONE_CLICK_STATUS_V1';do
 grep -Fq "$marker" "$UI" || { echo "STOP=MISSING_EXPECTED_ADMIN_LAYER";exit 3; }
done
if grep -Fq '# HESAB_CONTROL_ROOM_MANUAL_PATH_TEST_V1' "$UI";then
 echo "MANUAL_TEST_UI=ALREADY_INSTALLED"
 systemctl is-active --quiet hesab-manual-path-transfer-v1.service &&
   echo "PATH_TEST_BROKER=ACTIVE"
 exit 0
fi

python3 -m py_compile "$UI" "$BROKER" "$PATCH"
compose config -q
APP="$(compose ps -q app)"
[[ -n "$APP" && "$(docker inspect -f '{{.State.Running}}' "$APP")" == true ]] ||
 { echo "STOP=ADMIN_APP_NOT_RUNNING";exit 3; }
systemctl is-active --quiet hesab-dual-refresh-v2.service ||
 { echo "STOP=DUAL_REFRESH_NOT_RUNNING";exit 3; }

echo "=== CONFIRM 3 STRICTLY RESTRICTED KEYS (PREFLIGHT; NO DOWNLOADS) ==="
python3 "$BROKER" --preflight
echo "TRANSFER_PREFLIGHT=ALL_MAYA_READY_NO_DOWNLOAD"

echo "=== APP UI PREFLIGHT NO MUTATION ==="
cat "$PATCH" | compose exec -T app python -c '
import sys
from app import main as m
from starlette.requests import Request
from jinja2 import Environment
before=[r.path for r in m.app.routes]
for route in ("/control-room","/control-room/dual-hourly/status",
              "/control-room/path-test/start","/control-room/path-test/status"):
 assert before.count(route)==(0 if "path-test" in route else 1)
exec(compile(sys.stdin.read(),"<path-test-addon-preflight>","exec"),vars(m))
assert [r.path for r in m.app.routes]==before+[
 "/control-room/path-test/start","/control-room/path-test/status"]
t=m.TEMPLATES["control_room.html"]
assert t.count("id=\"ocs-transfer-check\"")==1
assert t.count("id=\"pt-ui-script\"")==1
assert t.index("id=\"ocs-transfer-grid\"")<t.index("id=\"pt-ui-script\"")
Environment().parse(t)
token="x"*40
scope={"type":"http","asgi":{"version":"3.0"},"http_version":"1.1",
 "method":"POST","scheme":"https","path":"/control-room/path-test/start",
 "root_path":"","query_string":b"",
 "headers":[(b"host",b"hesab.filmjadiid.ir"),(b"x-control-csrf",token.encode())],
 "server":("hesab.filmjadiid.ir",443),"client":("127.0.0.1",1234),
 "session":{"maya1_control_csrf":token},"app":m.app}
# POST without explicitly verified browser Origin must be forbidden.
assert m._pt_start(Request(scope)).status_code==403
scope["method"]="GET"
scope["path"]="/control-room/path-test/status"
scope["headers"]=[(b"host",b"hesab.filmjadiid.ir")]
assert m._pt_status(Request(scope)).status_code==403
print("ADMIN_BUTTON_PREFLIGHT=PASS_NO_NETWORK_TEST")
'

echo "=== BACKUP CURRENT APP AND DATABASE ==="
BACKUP="/root/hesab-manual-path-transfer-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BACKUP"
cp -a "$UI" "$BACKUP/maya1_control.py"
cp -a docker-compose.yml docker-compose.sms.yml "$BACKUP/"
docker inspect -f '{{.Image}}' "$APP" >"$BACKUP/app-image-id"
for f in "$BROKER_DEST" "$SERVICE";do
 key="$(echo "$f" |tr '/.' '__')"
 if [[ -e "$f" ]];then cp -a "$f" "$BACKUP/$key";fi
done
compose exec -T db sh -c \
 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
 >"$BACKUP/database-before-manual-path-transfer.dump"
[[ -s "$BACKUP/database-before-manual-path-transfer.dump" ]] ||
 { echo "STOP=DB_BACKUP_FAILED";exit 3; }
echo "APP_AND_DATABASE_BACKUP=CREATED"
echo "BACKUP=$BACKUP"

CHANGED=0
rollback(){
 code=$?
 trap - EXIT
 if ((code!=0 && CHANGED));then
  echo "INSTALL_FAILED_ROLLING_BACK_ADMIN_APP"
  systemctl disable --now hesab-manual-path-transfer-v1.service >/dev/null 2>&1 || true
  cp -a "$BACKUP/maya1_control.py" "$UI"
  for f in "$BROKER_DEST" "$SERVICE";do
   key="$(echo "$f" |tr '/.' '__')"
   if [[ -e "$BACKUP/$key" ]];then cp -a "$BACKUP/$key" "$f"
   else rm -f "$f";fi
  done
  systemctl daemon-reload || true
  compose up -d --no-deps --no-build --force-recreate app ||
    echo "WARNING=ADMIN_ROLLBACK_RECREATE_FAILED"
 fi
 exit "$code"
}
trap rollback EXIT
CHANGED=1
install -m 0700 -o root -g root "$BROKER" "$BROKER_DEST"

cat >"$SERVICE" <<'UNIT'
[Unit]
Description=Hesab explicitly requested 512-KiB VPN path test (manual only)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/vpn-control-center
ExecStart=/usr/bin/python3 /opt/vpn-control-center/scripts/hesab_manual_path_test_broker_v1.py
Restart=always
RestartSec=3
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now hesab-manual-path-transfer-v1.service
READY=0
for i in $(seq 1 20);do
 if systemctl is-active --quiet hesab-manual-path-transfer-v1.service && test -S "$SOCKET";then
  READY=1;break
 fi
 sleep 1
done
[[ "$READY" == 1 ]] || { echo "STOP=LOCAL_BROKER_NOT_RUNNING";false; }
compose exec -T app python - <<'PY'
import socket
p="/srv/maya-live/path_transfer_v1.sock"
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
 sock.settimeout(4)
 sock.connect(p)
 sock.sendall(b'{"op":"not-a-test"}\n')
 sock.shutdown(socket.SHUT_WR)
 data=sock.recv(300)
 assert b'"ok":false' in data
print("ADMIN_TO_RESTRICTED_BROKER=PASS_NO_ACTIVE_TEST")
PY

printf '\n\n' >>"$UI"
cat "$PATCH" >>"$UI"
python3 -m py_compile "$UI"

echo "=== RECREATE ADMIN APP ONLY ==="
compose up -d --no-deps --no-build --force-recreate app

READY=0
for i in $(seq 1 30);do
 if compose exec -T app python - <<'PY' >/dev/null 2>&1
from app import main as m
from starlette.requests import Request
from jinja2 import Environment
routes=[r.path for r in m.app.routes]
for path in ("/control-room","/control-room/dual-hourly/refresh",
 "/control-room/path-test/start","/control-room/path-test/status"):
 assert routes.count(path)==1,path
t=m.TEMPLATES["control_room.html"]
assert t.count('id="ocs-transfer-check"')==1
assert t.index('id="ocs-transfer-box"')<t.index('id="pt-ui-script"')
Environment().parse(t)
token="p"*40
scope={"type":"http","asgi":{"version":"3.0"},"http_version":"1.1",
 "method":"POST","scheme":"https","path":"/control-room/path-test/start",
 "root_path":"","query_string":b"",
 "headers":[(b"host",b"hesab.filmjadiid.ir"),(b"x-control-csrf",token.encode())],
 "server":("hesab.filmjadiid.ir",443),"client":("127.0.0.1",1234),
 "session":{"maya1_control_csrf":token},"app":m.app}
# Never send a permitted POST during installation.
assert m._pt_start(Request(scope)).status_code==403
scope["method"]="GET"
scope["path"]="/control-room/path-test/status"
scope["headers"]=[(b"host",b"hesab.filmjadiid.ir")]
assert m._pt_status(Request(scope)).status_code==403
assert m._cr2_page(Request(scope)).status_code==200
PY
 then READY=1;break;fi
 sleep 2
done
[[ "$READY" == 1 ]] || { echo "STOP=ADMIN_APP_PATH_TEST_RUNTIME_FAILED";false; }
systemctl is-active --quiet hesab-dual-refresh-v2.service
systemctl is-active --quiet hesab-manual-path-transfer-v1.service
trap - EXIT

echo "SUCCESS=MANUAL_TRANSFER_TEST_BUTTON_INSTALLED"
echo "BUTTON=TEST_PATH_BACKHAUL_MIERU_HAPROXY"
echo "NO_ACTIVE_TEST_EXECUTED_DURING_INSTALL=TRUE"
echo "NO_SCHEDULED_DOWNLOAD_TEST=TRUE"
echo "CURRENT_DUAL_STATUS_REFRESH_UNCHANGED=TRUE"
echo "VPN_XUI_HAPROXY_CADDY_DATABASE_CHANGED=NO"
echo "BACKUP=$BACKUP"
