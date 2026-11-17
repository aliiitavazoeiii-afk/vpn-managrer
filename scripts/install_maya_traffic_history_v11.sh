#!/usr/bin/env bash
# MAYA_NIC_TRAFFIC_HISTORY_V11_INSTALLER
# Management host only, read-only NIC charts. Never changes meter config,
# provider quota/remaining, XUI, foreign tunnels, Caddy, SMS, finance or DB.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP=ROOT_REQUIRED";exit 2; }
SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
UI=patches/maya1_control.py
PATCH="$SOURCE/patches/control_room_traffic_analytics_v11.py"
SAMPLER="$SOURCE/scripts/maya_traffic_history_v11.py"
LOCAL=scripts/maya_traffic_history_v11.py
SERVICE=/etc/systemd/system/hesab-maya-traffic-history-v11.service
TIMER=/etc/systemd/system/hesab-maya-traffic-history-v11.timer
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }

for f in "$UI" "$PATCH" "$SAMPLER" \
 docker-compose.yml docker-compose.sms.yml \
 /var/lib/hesab-maya-net-meter-v2/state.json \
 /opt/vpn-control-center/maya_extra_sync/phase1/status.json; do
 [[ -s "$f" ]] || { echo "STOP=MISSING_REQUIRED_FILE $f";exit 3; }
done
grep -Fq "# HESAB_CONTROL_ROOM_COMPACT_V10" "$UI" ||
 { echo "STOP=REQUIRES_LIVE_V10";exit 3; }
if grep -Fq "# HESAB_CONTROL_ROOM_TRAFFIC_ANALYTICS_V11" "$UI";then
 echo "ALREADY_INSTALLED=YES"
 systemctl is-active --quiet hesab-maya-traffic-history-v11.timer &&
  echo "TRAFFIC_HISTORY_TIMER=ACTIVE"
 exit 0
fi
grep -Fq './maya_extra_sync:/srv/maya-live:ro' docker-compose.sms.yml ||
 { echo "STOP=READ_ONLY_ADMIN_MOUNT_MISSING";exit 3; }
systemctl is-active --quiet hesab-maya-net-meter-v2.timer ||
 { echo "STOP=EXISTING_NIC_METER_TIMER_INACTIVE";exit 3; }
python3 -m py_compile "$PATCH" "$SAMPLER" "$UI"
bash -n "$0"
compose config -q
OLD="$(compose ps -q app)"
[[ -n "$OLD" && "$(docker inspect -f '{{.State.Running}}' "$OLD")" == true ]] ||
 { echo "STOP=ADMIN_APP_NOT_RUNNING";exit 3; }
for target in "$SERVICE" "$TIMER";do
 if [[ -e "$target" ]] && ! grep -Fq 'MAYA_NIC_TRAFFIC_HISTORY_V11' "$target";then
  echo "STOP=UNEXPECTED_SYSTEMD_UNIT $target";exit 3
 fi
done

echo "=== READ ONLY PRECHECK: ALL THREE NIC STATES ==="
python3 - <<'PY'
import json,time
from pathlib import Path
names=("maya1","maya-s3","maya4")
status=json.loads(Path("/opt/vpn-control-center/maya_extra_sync/phase1/status.json").read_text())
raw=json.loads(Path("/var/lib/hesab-maya-net-meter-v2/state.json").read_text())
print("NIC_SNAPSHOT_AGE_SEC",round(time.time()-status.get("collected_at",0)))
for name in names:
 s=status.get("servers",{}).get(name,{})
 p=raw.get(name,{})
 print("NIC_SENSOR",name,s.get("state","unknown"),
       "traffic_state",s.get("traffic_state","unknown"),
       "has_raw_counter",all(k in p for k in ("last_rx","last_tx","sample_at","boot_id")),
       "sample_age_sec",int(time.time()-p["sample_at"]) if isinstance(p.get("sample_at"),int) else "—")
print("NOTE=OFFLINE_OR_RESET_HOSTS_ARE_NOT_GUESSED")
PY

echo "=== PREFLIGHT CHART UI INSIDE ISOLATED APP PYTHON ==="
cat "$PATCH" | compose exec -T app python -c '
import sys,json
from app import main as m
from jinja2 import Environment
from starlette.requests import Request
before=[r.path for r in m.app.router.routes]
assert before.count("/control-room")==1 and before.count("/control-room/v10/daily")==1
code=sys.stdin.read()
exec(compile(code,"<traffic-chart-preflight>","exec"),vars(m))
paths=[r.path for r in m.app.router.routes]
for p in ("/control-room/traffic/summary","/control-room/traffic/data/{server}",
          "/control-room/traffic/{server}"):
 assert paths.count(p)==1,p
assert len(paths)==len(before)+3
assert "th11-traffic-link" in m.TEMPLATES["control_room.html"]
assert "t10-compact-css" in m.TEMPLATES["control_room.html"]
assert "th11-hourly" in m.TEMPLATES["control_room_traffic_v11.html"]
Environment().parse(m.TEMPLATES["control_room.html"])
Environment().parse(m.TEMPLATES["control_room_traffic_v11.html"])
token="t"*40
scope={"type":"http","asgi":{"version":"3.0"},"http_version":"1.1",
"method":"GET","scheme":"https","path":"/control-room/traffic/summary",
"root_path":"","query_string":b"",
"headers":[(b"host",b"hesab.filmjadiid.ir"),(b"x-control-csrf",token.encode())],
"server":("hesab.filmjadiid.ir",443),"client":("127.0.0.1",1234),
"session":{"maya1_control_csrf":token},"app":m.app}
assert m._th11_summary(Request(scope)).status_code==200
scope["headers"]=[(b"host",b"hesab.filmjadiid.ir")]
assert m._th11_summary(Request(scope)).status_code==403
assert m._cr2_page(Request(scope)).status_code==200
print("CHART_PREFLIGHT_ROUTES_CSRF_TEMPLATE=PASS")
'

BACKUP="/root/hesab-traffic-v11-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BACKUP"
cp -a "$UI" "$BACKUP/maya1_control.py"
for f in "$LOCAL" "$SERVICE" "$TIMER";do
 key="$(echo "$f" | tr '/.' '__')"
 if [[ -e "$f" ]];then cp -a "$f" "$BACKUP/$key";fi
done
docker inspect -f '{{.Image}}' "$OLD" >"$BACKUP/app-image-id"
echo "BACKUP=$BACKUP"

CHANGED=0
rollback(){
 code=$?
 trap - EXIT
 if (( code != 0 && CHANGED ));then
  echo "INSTALL_FAILED_RESTORING_PREVIOUS_ADMIN_UI"
  systemctl disable --now hesab-maya-traffic-history-v11.timer >/dev/null 2>&1 || true
  cp -a "$BACKUP/maya1_control.py" "$UI"
  for f in "$LOCAL" "$SERVICE" "$TIMER";do
   key="$(echo "$f" | tr '/.' '__')"
   if [[ -e "$BACKUP/$key" ]];then cp -a "$BACKUP/$key" "$f"
   else rm -f "$f";fi
  done
  systemctl daemon-reload || true
  compose up -d --no-deps --no-build --force-recreate app ||
   echo "WARNING=ADMIN_APP_ROLLBACK_RECREATE_FAILED"
  echo "BACKUP=$BACKUP"
 fi
 exit "$code"
}
trap rollback EXIT
CHANGED=1
install -o root -g root -m 0700 "$SAMPLER" "$LOCAL"
mkdir -p /var/lib/hesab-maya-traffic-history-v11
chmod 0700 /var/lib/hesab-maya-traffic-history-v11

cat >"$SERVICE" <<'UNIT'
# MAYA_NIC_TRAFFIC_HISTORY_V11
[Unit]
Description=Aggregate already collected Maya physical NIC counters by Tehran hour
After=hesab-maya-net-meter-v2.service

[Service]
Type=oneshot
User=root
WorkingDirectory=/opt/vpn-control-center
ExecStart=/usr/bin/python3 /opt/vpn-control-center/scripts/maya_traffic_history_v11.py
TimeoutStartSec=20
NoNewPrivileges=true
PrivateTmp=true
UNIT
cat >"$TIMER" <<'UNIT'
# MAYA_NIC_TRAFFIC_HISTORY_V11
[Unit]
Description=Sample physical NIC traffic history from existing NIC meter

[Timer]
OnCalendar=*-*-* *:*:45
AccuracySec=5s
Persistent=false
Unit=hesab-maya-traffic-history-v11.service

[Install]
WantedBy=timers.target
UNIT
chmod 0644 "$SERVICE" "$TIMER"
systemctl daemon-reload
systemctl start hesab-maya-traffic-history-v11.service
python3 - <<'PY'
import json,time
from pathlib import Path
p=Path("/opt/vpn-control-center/maya_extra_sync/phase1/traffic_history_v11.json")
d=json.loads(p.read_text())
assert d["format"]=="MAYA_NIC_TRAFFIC_HISTORY_V11"
assert time.time()-d["generated_at"]<=190
assert set(d["servers"])=={"maya1","maya-s3","maya4"}
assert all(len(d["servers"][s]["days"])==30 for s in d["servers"])
print("TRAFFIC_HISTORY_INITIAL_OUTPUT=PASS")
for s,row in d["servers"].items():
 print("SERVER",s,"state",row["state"],"coverage_pct",row["coverage_today_pct"])
PY
printf '\n\n' >>"$UI"
cat "$PATCH" >>"$UI"
python3 -m py_compile "$UI"

echo "=== RECREATE ONLY ADMIN APP ==="
compose up -d --no-deps --no-build --force-recreate app
READY=0
for attempt in $(seq 1 30);do
 if compose exec -T app python - <<'PY' >/dev/null 2>&1
import json
from app import main as m
from starlette.requests import Request
routes=[r.path for r in m.app.router.routes]
for p in ("/control-room","/control-room/v10/daily",
          "/control-room/v9/topup","/control-room/traffic/summary",
          "/control-room/traffic/data/{server}","/control-room/traffic/{server}"):
 assert routes.count(p)==1,p
assert "th11-traffic-link" in m.TEMPLATES["control_room.html"]
token="v"*40
scope={"type":"http","asgi":{"version":"3.0"},"http_version":"1.1",
"method":"GET","scheme":"https","path":"/control-room/traffic/summary",
"root_path":"","query_string":b"",
"headers":[(b"host",b"hesab.filmjadiid.ir"),(b"x-control-csrf",token.encode())],
"server":("hesab.filmjadiid.ir",443),"client":("127.0.0.1",1234),
"session":{"maya1_control_csrf":token},"app":m.app}
assert m._th11_summary(Request(scope)).status_code==200
scope["headers"]=[(b"host",b"hesab.filmjadiid.ir")]
assert m._th11_summary(Request(scope)).status_code==403
page=m._th11_page(Request(scope),"maya1")
assert page.status_code==200
assert m._cr2_page(Request(scope)).status_code==200
PY
 then READY=1;break;fi
 sleep 2
done
[[ "$READY" == 1 ]] || { echo "STOP=ADMIN_APP_RUNTIME_VALIDATION_FAILED";false; }
systemctl enable --now hesab-maya-traffic-history-v11.timer
systemctl is-active --quiet hesab-maya-traffic-history-v11.timer
trap - EXIT
echo "SUCCESS=MAYA_NIC_TRAFFIC_HISTORY_V11_INSTALLED"
echo "CLICK_EXISTING_DAILY_TRAFFIC_TO_OPEN_CHART=YES"
echo "METER_QUOTA_XUI_TUNNELS_CADDY_FINANCE_SMS_CHANGED=NO"
echo "THREE_SENSOR_STATUS_REPORTED_ABOVE"
echo "BACKUP=$BACKUP"
