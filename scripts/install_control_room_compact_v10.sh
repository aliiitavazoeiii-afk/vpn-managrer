#!/usr/bin/env bash
# HESAB_CONTROL_ROOM_COMPACT_V10_INSTALLER
# Scoped UI + daily RX sampling. Preserves V9 DB, XUI, finance and tunnels.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP: root only";exit 2; }
SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT=/opt/vpn-control-center
UI=patches/maya1_control.py
PATCH="$SOURCE/patches/control_room_compact_v10.py"
DAILY="$SOURCE/scripts/maya_daily_nic_v10.py"
DAILY_LOCAL=scripts/maya_daily_nic_v10.py
SERVICE=/etc/systemd/system/hesab-maya-daily-v10.service
TIMER=/etc/systemd/system/hesab-maya-daily-v10.timer
cd "$ROOT"
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for f in "$PATCH" "$DAILY" "$UI" .env docker-compose.yml docker-compose.sms.yml;do
 [[ -s "$f" ]] || { echo "STOP: missing $f";exit 3; }
done
grep -Fq '# HESAB_CONTROL_ROOM_TRAFFIC_TOPUP_V9' "$UI" ||
 { echo "STOP: V9 must be present";exit 3; }
if grep -Fq '# HESAB_CONTROL_ROOM_COMPACT_V10' "$UI";then
 echo "ALREADY_INSTALLED: compact V10, no second app recreation";exit 0;
fi
systemctl is-active --quiet hesab-maya-net-meter-v2.timer ||
 { echo "STOP: original NIC collector timer inactive";exit 3; }
python3 -m py_compile "$PATCH" "$DAILY"
compose config -q
OLD="$(compose ps -q app)"
[[ -n "$OLD" ]] && [[ "$(docker inspect -f '{{.State.Running}}' "$OLD")" == true ]] ||
 { echo "STOP: admin app not running";exit 3; }
echo "=== PREFLIGHT V10 REAL CONTROL ROOM RENDER ==="
cat "$PATCH" | compose exec -T app python -c '
import sys
from app import main as m
from jinja2 import Environment
from starlette.requests import Request
before=[r.path for r in m.app.routes]
assert "/control-room/v9/topup" in before
assert "/control-room/v10/daily" not in before
exec(compile(sys.stdin.read(),"<compact-v10-preflight>","exec"),vars(m))
assert [r.path for r in m.app.routes]==before+["/control-room/v10/daily"]
t=m.TEMPLATES["control_room.html"]
for name in ("t10-compact-css","t10-purchase","ترافیک روز","t10FetchDaily",
             "t10Topup","t10-notify",'id="c3-mode"','id="c2-users"'):
 assert name in t,name
assert 'id="t9-topup-panel"' not in t
assert "const t10CSRF=\"{{ ctrl_csrf }}\"" in t
assert "{{ mc.csrf_token }}" not in t
assert t.count('id="c2-cards"')==1
Environment().parse(t)
scope={"type":"http","asgi":{"version":"3.0"},"http_version":"1.1",
 "method":"GET","scheme":"https","path":"/control-room","root_path":"",
 "query_string":b"","headers":[(b"host",b"hesab.filmjadiid.ir")],
 "server":("hesab.filmjadiid.ir",443),"client":("127.0.0.1",1234),
 "session":{},"app":m.app}
page=m._cr2_page(Request(scope))
assert page.status_code==200
assert b"t10-purchase" in page.body and b\'id="t9-topup-panel"\' not in page.body
print("V10_ACTUAL_PAGE_RENDER_PREFLIGHT_OK")
'
echo "=== VERIFY EXISTING 500GB PURCHASE EXACTLY ONCE ==="
compose exec -T app python - <<'PY'
from app import main as m
from sqlalchemy import text
s=next(m.get_db())
try:
 rows=s.execute(text("""SELECT id,server_id,gb FROM hesab_maya_traffic_topups_v9
 WHERE request_key='INITIAL_MAYA1_500GB_20261031_OPERATOR_ONCE'""")).all()
 assert len(rows)==1 and rows[0].server_id=="maya1" and rows[0].gb==500
 sums,recent=m._t9_get_data(s)
 assert sums["maya1"]>=500
 print("MAYA1_500GB_EXISTING_TOPUP_PRESERVED",sums)
finally:
 s.rollback();s.close()
PY
BACKUP="/root/hesab-v10-compact-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$BACKUP"
cp -a "$UI" "$BACKUP/maya1_control.py"
docker inspect -f '{{.Image}}' "$OLD" >"$BACKUP/previous-app-image-id.txt"
if [[ -e "$DAILY_LOCAL" ]];then cp -a "$DAILY_LOCAL" "$BACKUP/daily.py";fi
if [[ -e "$SERVICE" ]];then cp -a "$SERVICE" "$BACKUP/service.unit";fi
if [[ -e "$TIMER" ]];then cp -a "$TIMER" "$BACKUP/timer.unit";fi
echo "BACKUP=$BACKUP"
CHANGED=0
rollback(){
 local code=$?
 trap - EXIT
 if ((code!=0&&CHANGED));then
  echo "ROLLBACK: restore V9 admin UI and daily files"
  systemctl disable --now hesab-maya-daily-v10.timer >/dev/null 2>&1 || true
  cp -a "$BACKUP/maya1_control.py" "$UI"
  if [[ -e "$BACKUP/daily.py" ]];then cp -a "$BACKUP/daily.py" "$DAILY_LOCAL";else rm -f "$DAILY_LOCAL";fi
  if [[ -e "$BACKUP/service.unit" ]];then cp -a "$BACKUP/service.unit" "$SERVICE";else rm -f "$SERVICE";fi
  if [[ -e "$BACKUP/timer.unit" ]];then cp -a "$BACKUP/timer.unit" "$TIMER";else rm -f "$TIMER";fi
  systemctl daemon-reload
  compose up -d --no-deps --no-build --force-recreate app ||
    echo "ROLLBACK_APP_RECREATE_FAILED: $BACKUP"
 fi
 exit "$code"
}
trap rollback EXIT
CHANGED=1
install -o root -g root -m 0700 "$DAILY" "$DAILY_LOCAL"
cat >"$SERVICE" <<'UNIT'
[Unit]
Description=Hesab physical Maya RX today (independent of XUI)
After=hesab-maya-net-meter-v2.service

[Service]
Type=oneshot
User=root
ExecStart=/usr/bin/python3 /opt/vpn-control-center/scripts/maya_daily_nic_v10.py
UNIT
cat >"$TIMER" <<'UNIT'
[Unit]
Description=Update physical Maya daily RX every minute

[Timer]
OnBootSec=40s
OnUnitActiveSec=60s
AccuracySec=10s
Unit=hesab-maya-daily-v10.service

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl start hesab-maya-net-meter-v2.service
systemctl start hesab-maya-daily-v10.service
test -s maya_extra_sync/phase1/daily_nic_v10.json
python3 - <<'PY'
from pathlib import Path
import json,time
d=json.loads(Path("maya_extra_sync/phase1/daily_nic_v10.json").read_text())
assert d["format"]=="HESAB_MAYA_DAILY_NIC_V10"
assert 0<=time.time()-d["collected_at"]<=180
assert all(d["servers"][name]["state"]=="ok"
 for name in ("maya1","maya-s3","maya4"))
print("V10_THREE_PHYSICAL_DAILY_METERS_OK")
PY
printf '\n\n' >>"$UI"
cat "$PATCH" >>"$UI"
python3 -m py_compile "$UI"
compose up -d --no-deps --no-build --force-recreate app
READY=0
for i in $(seq 1 30);do
 if compose exec -T app python - <<'PY' >/dev/null 2>&1
from app import main as m
from starlette.requests import Request
from sqlalchemy import text
import json
routes=[r.path for r in m.app.routes]
for path in ("/control-room","/control-room/v10/daily","/control-room/v9/topup",
             "/control-room/v9/traffic","/control-room/maya-live/toggle"):
 assert routes.count(path)==1,path
assert 'id="t10-compact-css"' in m.TEMPLATES["control_room.html"]
scope={"type":"http","asgi":{"version":"3.0"},"http_version":"1.1",
 "method":"GET","scheme":"https","path":"/control-room","root_path":"",
 "query_string":b"","headers":[(b"host",b"hesab.filmjadiid.ir")],
 "server":("hesab.filmjadiid.ir",443),"client":("127.0.0.1",1234),
 "session":{},"app":m.app}
page=m._cr2_page(Request(scope))
assert page.status_code==200
assert b"t10-purchase" in page.body and b\'id="t9-topup-panel"\' not in page.body
daily=json.loads(m._t10_daily(None).body)["servers"]
assert all(daily[k]["state"]=="ok" for k in ("maya1","maya-s3","maya4"))
s=next(m.get_db())
try:
 assert len(s.execute(text("""SELECT id FROM hesab_maya_traffic_topups_v9
 WHERE request_key='INITIAL_MAYA1_500GB_20261031_OPERATOR_ONCE'""")).all())==1
finally:
 s.rollback();s.close()
PY
 then READY=1;break;fi
 sleep 2
done
[[ "$READY" == 1 ]] || { echo "STOP: app page V10 runtime check failed";false; }
systemctl enable --now hesab-maya-daily-v10.timer
systemctl is-active --quiet hesab-maya-daily-v10.timer
trap - EXIT
echo "SUCCESS: COMPACT MAYA V10 DAILY RX + REMAINING RING + INLINE TOPUP"
echo "MAYA1_500GB_PURCHASE_PRESERVED_NO_NEW_PURCHASE=TRUE"
echo "IN_APP_BROWSER_LOW_ALERTS_PRESERVED=TRUE"
echo "BACKUP=$BACKUP"
