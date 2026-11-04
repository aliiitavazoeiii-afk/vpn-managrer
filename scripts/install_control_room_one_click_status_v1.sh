#!/usr/bin/env bash
# HESAB_CONTROL_ROOM_ONE_CLICK_STATUS_V1_INSTALLER
# Only visual simplification for the existing account admin dashboard.
# Does not change collectors, V1 snapshot, tunnels, Caddy, XUI or timers.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP=ROOT_REQUIRED";exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
ROOT=/opt/vpn-control-center
UI=patches/maya1_control.py
PATCH="$SRC/patches/control_room_one_click_status_v1.py"
cd "$ROOT"
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }

for f in "$UI" "$PATCH" docker-compose.yml docker-compose.sms.yml;do
 [[ -s "$f" ]] || { echo "STOP=MISSING_FILE $f"; exit 2; }
done
for marker in '# HESAB_CONTROL_ROOM_COMPACT_V10' \
              '# HESAB_CONTROL_ROOM_DUAL_HOURLY_SIMPLE_V1' \
              '# HESAB_DUAL_HOURLY_MANUAL_REFRESH_V2' \
              '# HESAB_DUAL_PASSIVE_QUALITY_V1';do
 grep -Fq "$marker" "$UI" || { echo "STOP=EXPECTED_ADDON_MISSING";exit 2; }
done
if grep -Fq '# HESAB_CONTROL_ROOM_ONE_CLICK_STATUS_V1' "$UI";then
 echo "ALREADY_INSTALLED=YES";exit 0
fi
python3 -m py_compile "$UI" "$PATCH"
compose config -q
APP="$(compose ps -q app)"
[[ -n "$APP" && "$(docker inspect -f '{{.State.Running}}' "$APP")" == true ]] ||
 { echo "STOP=ADMIN_APP_NOT_RUNNING";exit 2; }
systemctl is-active --quiet hesab-dual-hourly-v1.timer ||
 { echo "STOP=DUAL_HOURLY_TIMER_NOT_ACTIVE";exit 2; }
systemctl is-active --quiet hesab-dual-refresh-v2.service ||
 { echo "STOP=DUAL_REFRESH_WORKER_NOT_ACTIVE";exit 2; }

echo "=== PREFLIGHT PRODUCTION DASHBOARD - NO WRITES ==="
cat "$PATCH" | compose exec -T app python -c '
import sys
from app import main as m
from jinja2 import Environment
before=[r.path for r in m.app.routes]
assert before.count("/control-room/dual-hourly/refresh")==1
assert before.count("/control-room/dual-hourly/refresh-meta")==1
assert before.count("/control-room/dual-hourly/status")==1
assert before.count("/control-room/dual-quality/status")==1
assert "id=\"pq-root\"" in m.TEMPLATES["control_room.html"]
exec(compile(sys.stdin.read(),"<one-click-preflight>","exec"),vars(m))
assert [r.path for r in m.app.routes]==before
t=m.TEMPLATES["control_room.html"]
for node in ("ocs-root","ocs-check","ocs-grid","ocs-status","ocs-js"):
 assert t.count("id=\""+node+"\"")==1,node
assert t.index("id=\"ocs-grid\"")<t.index("id=\"ocs-js\"")
assert "#c2-root #dh1-root, #c2-root #pq-root {display:none!important}" in t
Environment().parse(t)
print("ONE_CLICK_UI_PREFLIGHT=PASS")
'

echo "=== BACKUP ADMIN OVERLAY AND DATABASE ==="
BACKUP="/root/hesab-one-click-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BACKUP"
cp -a "$UI" "$BACKUP/maya1_control.py"
cp -a docker-compose.yml docker-compose.sms.yml "$BACKUP/"
docker inspect -f '{{.Image}}' "$APP" >"$BACKUP/app-image-id"
compose exec -T db sh -c \
 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
 > "$BACKUP/database-before-one-click.dump"
[[ -s "$BACKUP/database-before-one-click.dump" ]] ||
 { echo "STOP=DATABASE_BACKUP_MISSING";exit 2; }
echo "BACKUP=$BACKUP"
echo "DATABASE_BACKUP=CREATED"

CHANGED=0
rollback(){
 code=$?
 trap - EXIT
 if ((code!=0&&CHANGED));then
  echo "INSTALL_FAILED_RESTORING_ADMIN_OVERLAY"
  cp -a "$BACKUP/maya1_control.py" "$UI"
  if ! compose up -d --no-deps --no-build --force-recreate app;then
   echo "WARNING=ADMIN_APP_RECREATE_AFTER_ROLLBACK_FAILED"
  fi
  echo "BACKUP=$BACKUP"
 fi
 exit "$code"
}
trap rollback EXIT
CHANGED=1
printf '\n\n' >>"$UI"
cat "$PATCH" >>"$UI"
python3 -m py_compile "$UI"
echo "=== RECREATE ADMIN APP ONLY ==="
compose up -d --no-deps --no-build --force-recreate app

READY=0
for n in $(seq 1 30);do
 if compose exec -T app python - <<'PY' >/dev/null 2>&1
from app import main as m
from starlette.requests import Request
from jinja2 import Environment
paths=[r.path for r in m.app.routes]
for endpoint in ("/control-room","/control-room/v9/topup",
 "/control-room/dual-hourly/refresh","/control-room/dual-hourly/refresh-meta",
 "/control-room/dual-hourly/status","/control-room/dual-quality/status"):
 assert paths.count(endpoint)==1,endpoint
t=m.TEMPLATES["control_room.html"]
assert t.count('id="ocs-root"')==1
assert t.count('id="ocs-check"')==1
assert t.count('id="ocs-js"')==1
assert t.index('id="ocs-grid"')<t.index('id="ocs-js"')
Environment().parse(t)
token="x"*40
scope={"type":"http","asgi":{"version":"3.0"},"http_version":"1.1",
"method":"GET","scheme":"https","path":"/control-room/dual-hourly/status",
"root_path":"","query_string":b"",
"headers":[(b"host",b"hesab.filmjadiid.ir"),(b"x-control-csrf",token.encode())],
"server":("hesab.filmjadiid.ir",443),"client":("127.0.0.1",1234),
"session":{"maya1_control_csrf":token},"app":m.app}
assert m._dh1_status(Request(scope)).status_code==200
scope["headers"]=[(b"host",b"hesab.filmjadiid.ir")]
assert m._dh1_status(Request(scope)).status_code==403
assert m._cr2_page(Request(scope)).status_code==200
PY
 then READY=1;break;fi
 sleep 2
done
[[ "$READY" == 1 ]] || { echo "STOP=ADMIN_APP_RUNTIME_VALIDATION_FAILED";false; }
systemctl is-active --quiet hesab-dual-hourly-v1.timer
systemctl is-active --quiet hesab-dual-refresh-v2.service
trap - EXIT
echo "SUCCESS=ONE_CLICK_STATUS_UI_LIVE"
echo "SIX_PATHS_SHOWN_AS_COMPACT_RESULTS=YES"
echo "NETWORK_TRANSFER_QUALITY_STILL_UNMEASURED=YES"
echo "EXISTING_COLLECTORS_AND_MANUAL_REFRESH_UNCHANGED=YES"
echo "VPN_XUI_CADDY_FINANCIAL_STATE_CHANGED=NO"
echo "BACKUP=$BACKUP"
