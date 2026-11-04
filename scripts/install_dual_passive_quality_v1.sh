#!/usr/bin/env bash
# HESAB_DUAL_PASSIVE_QUALITY_V1_INSTALLER
# ACCOUNT SERVER ONLY. No Iran-host login, SOCKS/HTTPS tests, tunnel/control changes.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP=ROOT_REQUIRED"; exit 2; }
SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT=/opt/vpn-control-center
UI=patches/maya1_control.py
QUALITY="$SOURCE/scripts/maya_dual_passive_quality_v1.py"
PATCH="$SOURCE/patches/control_room_passive_quality_v1.py"
OLD_V2="$SOURCE/patches/control_room_dual_manual_refresh_v2.py"
TARGET=scripts/maya_dual_passive_quality_v1.py
SERVICE=/etc/systemd/system/hesab-dual-quality-passive-v1.service
TIMER=/etc/systemd/system/hesab-dual-quality-passive-v1.timer

cd "$ROOT"
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for f in "$UI" "$QUALITY" "$PATCH" "$OLD_V2" docker-compose.yml \
         docker-compose.sms.yml maya_extra_sync/dual_hourly_v1.json;do
  [[ -s "$f" ]] || { echo "STOP=MISSING_FILE $f";exit 3; }
done
if grep -Fq '# HESAB_DUAL_PASSIVE_QUALITY_V1' "$UI";then
 echo "ALREADY_INSTALLED=YES"
 systemctl is-active --quiet hesab-dual-quality-passive-v1.timer &&
   echo "PASSIVE_QUALITY_TIMER=ACTIVE"
 exit 0
fi

grep -Fq '# HESAB_CONTROL_ROOM_COMPACT_V10' "$UI" ||
 { echo "STOP=V10_ADMIN_UI_MISSING";exit 3; }
grep -Fq '# HESAB_CONTROL_ROOM_DUAL_HOURLY_SIMPLE_V1' "$UI" ||
 { echo "STOP=DUAL_V1_UI_MISSING";exit 3; }
grep -Fq '# HESAB_DUAL_HOURLY_MANUAL_REFRESH_V2' "$UI" ||
 { echo "STOP=MANUAL_V2_UI_MISSING";exit 3; }

echo "=== VERIFY INSTALLED DUAL V2 PATCH MATCHES GITHUB REFERENCE ==="
python3 - "$UI" "$OLD_V2" <<'PY'
import sys
from pathlib import Path
live=Path(sys.argv[1]).read_text(encoding="utf8")
reference=Path(sys.argv[2]).read_text(encoding="utf8").strip()
if reference not in live:
    raise SystemExit("STOP=LIVE_V2_PATCH_DIFFERS_FROM_REVIEWED_REFERENCE")
print("CURRENT_DUAL_V2_SOURCE_PARITY=PASS")
PY

python3 -m py_compile "$UI" "$PATCH" "$QUALITY"
compose config -q
OLD="$(compose ps -q app)"
[[ -n "$OLD" && "$(docker inspect -f '{{.State.Running}}' "$OLD")" == true ]] ||
 { echo "STOP=ADMIN_APP_NOT_RUNNING"; exit 3; }
systemctl is-active --quiet hesab-dual-hourly-v1.timer ||
 { echo "STOP=DUAL_V1_TIMER_NOT_ACTIVE";exit 3; }
systemctl is-active --quiet hesab-dual-refresh-v2.service ||
 { echo "STOP=DUAL_MANUAL_REFRESH_NOT_ACTIVE";exit 3; }

echo "=== PREFLIGHT PATCH AGAINST CURRENT LIVE ADMIN APP ==="
cat "$PATCH" | compose exec -T app python -c '
import sys
from app import main as m
from starlette.requests import Request
from jinja2 import Environment
before=[r.path for r in m.app.routes]
for route in ("/control-room","/control-room/dual-hourly/status",
              "/control-room/dual-hourly/refresh",
              "/control-room/v9/topup"):
 assert before.count(route)==1,route
exec(compile(sys.stdin.read(),"<passive-quality-preflight>","exec"),vars(m))
after=[r.path for r in m.app.routes]
assert after==before+["/control-room/dual-quality/status"]
page=m.TEMPLATES["control_room.html"]
for node in ("pq-root","pq-cards","pq-alerts","pq-js","dm2-refresh","dh1-grid"):
 assert node in page,node
assert page.index("id=\"pq-cards\"")<page.index("id=\"pq-js\"")
Environment().parse(page)
scope={"type":"http","asgi":{"version":"3.0"},"http_version":"1.1",
"method":"GET","scheme":"https","path":"/control-room/dual-quality/status",
"root_path":"","query_string":b"",
"headers":[(b"host",b"hesab.filmjadiid.ir")],
"server":("hesab.filmjadiid.ir",443),"client":("127.0.0.1",1234),
"session":{},"app":m.app}
assert m._pq_endpoint(Request(scope)).status_code==403
assert m._cr2_page(Request(scope)).status_code==200
print("ADMIN_UI_READ_ONLY_PREFLIGHT=PASS")
'

echo "=== SAFE BACKUP BEFORE ANY CHANGES ==="
BACKUP="/root/hesab-dual-quality-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BACKUP"
cp -a "$UI" "$BACKUP/maya1_control.py"
cp -a docker-compose.yml docker-compose.sms.yml "$BACKUP/"
docker inspect -f '{{.Image}}' "$OLD" >"$BACKUP/app-image-id"
for f in "$TARGET" "$SERVICE" "$TIMER";do
 key="$(echo "$f"|tr '/.' '__')"
 if [[ -e "$f" ]];then cp -a "$f" "$BACKUP/$key";fi
done
echo "BACKUP=$BACKUP"

# Database backup: exactly one read-only dump; no migration or table mutation.
compose exec -T db sh -c \
 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
 >"$BACKUP/database-before.dual-quality.dump"
[[ -s "$BACKUP/database-before.dual-quality.dump" ]] ||
 { echo "STOP=DATABASE_BACKUP_FAILED";exit 3; }
echo "DATABASE_BACKUP=CREATED"

CHANGED=0
rollback(){
 code=$?
 trap - EXIT
 if ((code!=0&&CHANGED));then
  echo "PASSIVE_QUALITY_INSTALL_FAILED_ROLLING_BACK"
  systemctl disable --now hesab-dual-quality-passive-v1.timer >/dev/null 2>&1 || true
  cp -a "$BACKUP/maya1_control.py" "$UI"
  for f in "$TARGET" "$SERVICE" "$TIMER";do
   key="$(echo "$f"|tr '/.' '__')"
   if [[ -e "$BACKUP/$key" ]];then cp -a "$BACKUP/$key" "$f"
   else rm -f "$f";fi
  done
  systemctl daemon-reload || true
  compose up -d --no-deps --no-build --force-recreate app ||
    echo "WARNING=APP_ROLLBACK_RECREATE_FAILED"
  echo "ROLLBACK_BACKUP=$BACKUP"
 fi
 exit "$code"
}
trap rollback EXIT
CHANGED=1

install -o root -g root -m 0700 "$QUALITY" "$TARGET"
echo "=== LOCAL SNAPSHOT ONLY: FIRST PASSIVE ANALYSIS ==="
python3 "$TARGET"
python3 - <<'PY'
import json
from pathlib import Path
d=json.loads(Path("maya_extra_sync/dual_quality_v1/status.json").read_text())
assert d["format"]=="HESAB_DUAL_PASSIVE_QUALITY_V1"
for sid in ("maya1","maya-s3","maya4"):
 for role in ("backhaul","mieru"):
  p=d["servers"][sid]["paths"][role]
  assert p["quality"]["state"] in ("not_measured","stale","path_down",
         "suspected_degradation","inconclusive","normal_by_observed_counters")
  assert p["last_transfer_test"] is None
  assert p["latest_counters"] is None, "Unexpected metrics in V1 schema; stop for review"
print("PASSIVE_SNAPSHOT_VALID=NO_TRAFFIC_METRICS_IN_CURRENT_V1")
print("ACTIVE_TESTS=DISABLED")
PY

compose exec -T app python - <<'PY'
import json
from pathlib import Path
data=json.loads(Path("/srv/maya-live/dual_quality_v1/status.json").read_text())
assert data["format"]=="HESAB_DUAL_PASSIVE_QUALITY_V1"
print("ADMIN_SNAPSHOT_VOLUME=READABLE")
PY

cat >"$SERVICE" <<'UNIT'
[Unit]
Description=Hesab Dual passive quality rollup (local snapshot only)
After=local-fs.target

[Service]
Type=oneshot
User=root
WorkingDirectory=/opt/vpn-control-center
ExecStart=/usr/bin/python3 /opt/vpn-control-center/scripts/maya_dual_passive_quality_v1.py
TimeoutStartSec=15
UNIT
cat >"$TIMER" <<'UNIT'
[Unit]
Description=Read Hesab local Dual snapshot for passive quality every 30 seconds

[Timer]
OnBootSec=40s
OnUnitActiveSec=30s
AccuracySec=5s
Unit=hesab-dual-quality-passive-v1.service

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
printf '\n\n' >>"$UI"
cat "$PATCH" >>"$UI"
python3 -m py_compile "$UI"

echo "=== RECREATE ONLY ADMIN APP; NO DATA-PLANE RESTART ==="
compose up -d --no-deps --no-build --force-recreate app
READY=0
for i in $(seq 1 30);do
 if compose exec -T app python - <<'PY' >/dev/null 2>&1
import json
from app import main as m
from starlette.requests import Request
paths=[r.path for r in m.app.routes]
for key in ("/control-room","/control-room/v9/topup",
 "/control-room/dual-hourly/status","/control-room/dual-hourly/refresh",
 "/control-room/dual-quality/status"):
 assert paths.count(key)==1,key
page=m.TEMPLATES["control_room.html"]
assert "id=\"pq-root\"" in page and "id=\"pq-js\"" in page
assert page.index("id=\"pq-cards\"")<page.index("id=\"pq-js\"")
token="q"*40
scope={"type":"http","asgi":{"version":"3.0"},"http_version":"1.1",
 "method":"GET","scheme":"https","path":"/control-room/dual-quality/status",
 "root_path":"","query_string":b"",
 "headers":[(b"host",b"hesab.filmjadiid.ir"),(b"x-control-csrf",token.encode())],
 "server":("hesab.filmjadiid.ir",443),"client":("127.0.0.1",1234),
 "session":{"maya1_control_csrf":token},"app":m.app}
response=m._pq_endpoint(Request(scope))
assert response.status_code==200
obj=json.loads(response.body)
assert obj["ok"] and obj["report"]["format"]=="HESAB_DUAL_PASSIVE_QUALITY_V1"
scope["headers"]=[(b"host",b"hesab.filmjadiid.ir")]
assert m._pq_endpoint(Request(scope)).status_code==403
assert m._cr2_page(Request(scope)).status_code==200
PY
 then READY=1;break;fi
 sleep 2
done
[[ "$READY" == 1 ]] || { echo "STOP=ADMIN_APP_VALIDATION_FAILED";false; }
systemctl enable --now hesab-dual-quality-passive-v1.timer
systemctl is-active --quiet hesab-dual-quality-passive-v1.timer
systemctl is-active --quiet hesab-dual-hourly-v1.timer
systemctl is-active --quiet hesab-dual-refresh-v2.service
trap - EXIT

echo "SUCCESS=DUAL_PASSIVE_QUALITY_UI_DEPLOYED"
echo "QUALITY_MODE=PASSIVE_ONLY"
echo "TRANSFER_DOWNLOAD_TESTS=NOT_IMPLEMENTED_ON_PRODUCTION"
echo "NO_TUNNEL_OR_HEALTH_CONTROLLER_CHANGES=TRUE"
echo "DUAL_V1_AND_MANUAL_REFRESH=UNCHANGED"
echo "BACKUP=$BACKUP"
