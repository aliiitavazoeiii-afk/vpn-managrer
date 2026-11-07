#!/usr/bin/env bash
# HESAB_MAYA_XUI_USER_DAILY_V11_INSTALL
# Management host ONLY. No change to Iran hosts, XUI, Reality, Backhaul,
# Mieru, HAProxy, billing data, provider NIC collector, or previous timers.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP=ROOT_REQUIRED";exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
ROOT=/opt/vpn-control-center
cd "$ROOT"
LIVE=patches/maya1_control.py
PATCH="$SRC/patches/control_room_xui_daily_usage_v11.py"
COLLECTOR="$SRC/scripts/maya_xui_user_daily_v11.py"
TARGET=scripts/maya_xui_user_daily_v11.py
SERVICE=/etc/systemd/system/hesab-maya-xui-user-daily-v11.service
TIMER=/etc/systemd/system/hesab-maya-xui-user-daily-v11.timer
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }

for f in "$LIVE" "$PATCH" "$COLLECTOR" \
         docker-compose.yml docker-compose.sms.yml \
         maya_extra_sync/live.sock;do
 [[ -e "$f" ]] || { echo "STOP=MISSING_PREREQUISITE $f";exit 3; }
done
grep -Fq '# HESAB_CONTROL_ROOM_COMPACT_V10' "$LIVE" ||
 { echo "STOP=EXISTING_V10_LAYOUT_NOT_FOUND";exit 3; }
grep -Fq '# HESAB_CONTROL_ROOM_DUAL_HOURLY_SIMPLE_V1' "$LIVE" ||
 { echo "STOP=CSRF_AUTH_MODULE_NOT_FOUND";exit 3; }
if grep -Fq '# HESAB_MAYA_XUI_USER_DAILY_UI_V11' "$LIVE";then
 echo "ALREADY_INSTALLED=YES";exit 0
fi
if [[ -e "$SERVICE" || -e "$TIMER" || -e "$TARGET" ]];then
 echo "STOP=UNEXPECTED_PRIOR_DAILY_V11_FILES";exit 3
fi
compose config -q
python3 -m py_compile "$LIVE" "$PATCH" "$COLLECTOR"
APP="$(compose ps -q app)"
[[ -n "$APP" && "$(docker inspect -f '{{.State.Running}}' "$APP")" == true ]] ||
 { echo "STOP=ADMIN_APP_NOT_RUNNING";exit 3; }
systemctl is-active --quiet hesab-maya-live.service ||
 { echo "STOP=READ_ONLY_XUI_LIVE_BRIDGE_NOT_RUNNING";exit 3; }

echo "=== CHECK ALL THREE XUI SOURCES: READ-ONLY, NO TRAFFIC/LEDGER WRITES ==="
python3 "$COLLECTOR" --check
echo "MAYA1_MAYA3_MAYA4_XUI_READ=PASS"

echo "=== DRY-RUN ADDITIVE ADMIN UI AGAINST CURRENT LIVE TEMPLATE ==="
cat "$PATCH" | compose exec -T app python -c '
import sys
from app import main as m
from jinja2 import Environment
before=[(r.path,sorted(r.methods)) for r in m.app.router.routes]
old=m.TEMPLATES["control_room.html"]
assert "t10-compact-css" in old
assert "/control-room/v10/daily" in old
exec(compile(sys.stdin.read(),"<xui-user-daily-v11-preflight>","exec"),vars(m))
after=[(r.path,sorted(r.methods)) for r in m.app.router.routes]
assert after==before+[("/control-room/v11/users-daily",["GET"])]
page=m.TEMPLATES["control_room.html"]
assert "fetch(\"/control-room/v11/users-daily\"" in page
assert "X-Control-CSRF" in page
assert "مصرف کاربران امروز" in page
assert "rx_today_gb" not in page
assert "fetch(\"/control-room/v10/daily\"" not in page
Environment().parse(page)
print("XUI_USER_DAILY_V11_UI_PREFLIGHT=PASS")
'

echo "=== BACKUP ADMIN AND MONITORING FILES ==="
BACKUP="/root/hesab-maya-xui-user-daily-v11-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BACKUP"
cp -a "$LIVE" "$BACKUP/maya1_control.py"
cp -a docker-compose.yml docker-compose.sms.yml "$BACKUP/"
docker inspect -f '{{.Image}}' "$APP" >"$BACKUP/admin-image-id"
if [[ -f maya_extra_sync/usage_v1.sqlite3 ]];then
 cp -a maya_extra_sync/usage_v1.sqlite3 "$BACKUP/legacy-usage-v1.sqlite3"
fi
echo "BACKUP=$BACKUP"
# No finances/DB migrations; do not depend on a PostgreSQL dump to refresh telemetry.
CHANGED=0
rollback(){
 code=$?
 trap - EXIT
 if ((code!=0&&CHANGED));then
   echo "ROLLBACK=RESTORING_ADMIN_AND_NEW_LOCAL_TIMER"
   systemctl disable --now hesab-maya-xui-user-daily-v11.timer >/dev/null 2>&1 || true
   cp -a "$BACKUP/maya1_control.py" "$LIVE"
   rm -f "$SERVICE" "$TIMER" "$TARGET"
   systemctl daemon-reload || true
   compose up -d --no-deps --no-build --force-recreate app ||
      echo "WARNING=ADMIN_RECREATE_ON_ROLLBACK_FAILED"
   echo "ROLLBACK_NOTE=NEW_SQLITE_BASELINES_RETAINED_FOR_REVIEW"
   echo "BACKUP=$BACKUP"
 fi
 exit "$code"
}
trap rollback EXIT
CHANGED=1
install -o root -g root -m 0700 "$COLLECTOR" "$TARGET"
cat >"$SERVICE" <<'UNIT'
[Unit]
Description=Hesab read-only XUI per-client Tehran-day user usage
After=hesab-maya-live.service
Wants=hesab-maya-live.service

[Service]
Type=oneshot
User=root
Group=root
WorkingDirectory=/opt/vpn-control-center
ExecStart=/usr/bin/python3 /opt/vpn-control-center/scripts/maya_xui_user_daily_v11.py
TimeoutStartSec=135
Nice=10
NoNewPrivileges=true
ProtectSystem=full
ReadWritePaths=/opt/vpn-control-center/maya_extra_sync
PrivateTmp=true
UNIT
cat >"$TIMER" <<'UNIT'
[Unit]
Description=Sample read-only user XUI counters each minute (Tehran calendar days)

[Timer]
OnCalendar=*-*-* *:*:00
AccuracySec=1s
Persistent=false
Unit=hesab-maya-xui-user-daily-v11.service

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload

echo "=== COLLECT FIRST LIVE BASELINE; NO HISTORICAL TRAFFIC INVENTED ==="
systemctl start hesab-maya-xui-user-daily-v11.service
test -s maya_extra_sync/phase1/maya_user_daily_v11.json
python3 - <<'PY'
import json
from pathlib import Path
p=Path("maya_extra_sync/phase1/maya_user_daily_v11.json")
d=json.loads(p.read_text(encoding="utf8"))
assert d["format"]=="HESAB_MAYA_XUI_USER_DAILY_V11"
assert set(d["servers"])=={"maya1","maya-s3","maya4"}
for name,row in d["servers"].items():
    assert row["state"] in ("partial","measured","not_measured","stale","unavailable"),(name,row)
    if row["state"] in ("partial","measured"):
        assert row["complete_day_exact"] is False
print("FIRST_BASELINE=VERIFIED_NO_HISTORICAL_BACKFILL")
PY

echo "=== SWITCH ONLY VISIBLE DAILY CARD; NO NIC OR PAYMENT CHANGE ==="
printf '\n\n' >>"$LIVE"
cat "$PATCH" >>"$LIVE"
python3 -m py_compile "$LIVE"
compose up -d --no-deps --no-build --force-recreate app

READY=0
for i in $(seq 1 30);do
 if compose exec -T app python - <<'PY' >/dev/null 2>&1
from app import main as m
from starlette.requests import Request
from jinja2 import Environment
import json
paths=[r.path for r in m.app.router.routes]
for p in ("/control-room","/control-room/v9/topup",
 "/control-room/v10/daily","/control-room/v11/users-daily",
 "/control-room/dual-hourly/refresh"):
 assert paths.count(p)==1,p
t=m.TEMPLATES["control_room.html"]
assert "مصرف کاربران امروز" in t
assert 'fetch("/control-room/v11/users-daily"' in t
assert "rx_today_gb" not in t
Environment().parse(t)
token="s"*40
scope={"type":"http","method":"GET","scheme":"https",
"path":"/control-room/v11/users-daily","root_path":"","query_string":b"",
"http_version":"1.1","headers":[(b"x-control-csrf",token.encode()),
(b"host",b"hesab.filmjadiid.ir")],
"server":("hesab.filmjadiid.ir",443),"client":("127.0.0.1",1000),
"session":{"maya1_control_csrf":token},"app":m.app}
res=m._ux11_daily(Request(scope))
assert res.status_code==200
response=json.loads(res.body)
assert response["ok"] is True and set(response["servers"])=={"maya1","maya-s3","maya4"}
scope["headers"]=[(b"host",b"hesab.filmjadiid.ir")]
assert m._ux11_daily(Request(scope)).status_code==403
print("READ_ONLY_ADMIN_XUI_DAILY_API_PASS")
PY
 then READY=1;break;fi
 sleep 2
done
[[ "$READY" == 1 ]] || { echo "STOP=XUI_DAILY_ADMIN_RUNTIME_FAILED";false; }

systemctl enable --now hesab-maya-xui-user-daily-v11.timer
systemctl is-active --quiet hesab-maya-xui-user-daily-v11.timer
systemctl is-active --quiet hesab-maya-live.service
trap - EXIT
echo "SUCCESS=MAYA_XUI_USER_TRAFFIC_DAILY_V11_ACTIVE"
echo "DAILY_SOURCE=XUI_SUM_CLIENTS_UP_PLUS_DOWN_NOT_IRAN_NIC"
echo "TIMEZONE=ASIA_TEHRAN"
echo "SAMPLE_INTERVAL=1_MINUTE"
echo "EXACT_UNOBSERVED_MIDNIGHT_USAGE=NOT_INVENTED"
echo "MAYA_PROVIDER_NIC_AND_TRAFFIC_QUOTA=UNCHANGED"
echo "XUI_TUNNELS_HAPROXY_PAYMENT_DB_CHANGED=NO"
echo "BACKUP=$BACKUP"
