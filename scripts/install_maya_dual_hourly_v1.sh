#!/usr/bin/env bash
# HESAB_DUAL_HOURLY_SIMPLE_V1_INSTALLER
# Management host only. Additive Control Room UI and hourly cached dual status.
# Does not modify Caddy, tunnels, remote hosts, XUI or payment/traffic ledgers.
set -Eeuo pipefail
umask 077

SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT=/opt/vpn-control-center
UI=patches/maya1_control.py
CFG=/root/.config/hesab-dual-hourly-v1.json
COLLECTOR="$SOURCE/scripts/maya_dual_hourly_collect_v1.py"
PATCH="$SOURCE/patches/control_room_dual_hourly_v1.py"
LOCAL_COLLECTOR=scripts/maya_dual_hourly_collect_v1.py
SERVICE=/etc/systemd/system/hesab-dual-hourly-v1.service
TIMER=/etc/systemd/system/hesab-dual-hourly-v1.timer

[[ "$(id -u)" == 0 ]] || { echo "STOP=ROOT_REQUIRED"; exit 2; }
cd "$ROOT"
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }

for f in "$UI" "$CFG" "$COLLECTOR" "$PATCH" docker-compose.yml docker-compose.sms.yml; do
  [[ -s "$f" ]] || { echo "STOP=MISSING_REQUIRED_FILE $f"; exit 2; }
done
[[ -s /root/.ssh/hesab_dual_hourly_v1 ]] || { echo "STOP=MONITOR_KEY_MISSING"; exit 2; }
grep -Fq '# HESAB_CONTROL_ROOM_COMPACT_V10' "$UI" ||
  { echo "STOP=REQUIRES_LIVE_V10"; exit 2; }
if grep -Fq '# HESAB_CONTROL_ROOM_DUAL_HOURLY_SIMPLE_V1' "$UI"; then
  echo "ALREADY_INSTALLED=YES"
  systemctl is-active --quiet hesab-dual-hourly-v1.timer &&
    echo "HOURLY_TIMER=ACTIVE"
  exit 0
fi
python3 -m py_compile "$UI" "$COLLECTOR" "$PATCH"
compose config -q
OLD="$(compose ps -q app)"
[[ -n "$OLD" && "$(docker inspect -f '{{.State.Running}}' "$OLD")" == true ]] ||
  { echo "STOP=APP_NOT_RUNNING"; exit 2; }

echo "=== VERIFY THREE CORRECT MAYA IPs (READ ONLY) ==="
python3 -u - "$SOURCE/scripts" <<'PY'
import ipaddress,sys
sys.path.insert(0,sys.argv[1])
import maya_dual_hourly_collect_v1 as m
correct={"maya1":"94.184.4.38","maya-s3":"185.215.230.221","maya4":"5.10.249.206"}
current=m.validate_config()
assert set(correct).issubset(current),"Missing required Maya config"
for name,ip in correct.items():
    item=dict(current[name]);item["host"]=ip
    report=m.fetch(name,item)
    assert set(report["paths"])=={"backhaul","mieru"}
    assert all(report["paths"][r]["ip"] for r in ("backhaul","mieru"))
    print("VERIFIED",name,ip,"BACKHAUL",report["paths"]["backhaul"]["state"],
          "MIERU",report["paths"]["mieru"]["state"],flush=True)
print("THREE_CORRECT_REMOTE_IDENTITIES=VERIFIED",flush=True)
PY

echo "=== PREFLIGHT READ-ONLY ADMIN ADDON ==="
cat "$PATCH" | compose exec -T app python -c '
import sys,json
from app import main as m
from starlette.requests import Request
before=[r.path for r in m.app.routes]
assert before.count("/control-room")==1
assert "/control-room/v10/daily" in before
assert "t10-compact-css" in m.TEMPLATES["control_room.html"]
code=sys.stdin.read()
exec(compile(code,"<dual-hourly-ui-preflight>","exec"),vars(m))
after=[r.path for r in m.app.routes]
assert len(after)==len(before)+1
assert after.count("/control-room/dual-hourly/status")==1
assert "dh1-root" in m.TEMPLATES["control_room.html"]
assert "مایا ۳" in m.TEMPLATES["control_room.html"]
token="v"*40
scope={"type":"http","asgi":{"version":"3.0"},"http_version":"1.1",
"method":"GET","scheme":"https","path":"/control-room/dual-hourly/status",
"root_path":"","query_string":b"",
"headers":[(b"host",b"hesab.filmjadiid.ir"),(b"x-control-csrf",token.encode())],
"server":("hesab.filmjadiid.ir",443),"client":("127.0.0.1",1234),
"session":{"maya1_control_csrf":token},"app":m.app}
assert m._dh1_status(Request(scope)).status_code==200
scope["headers"]=[(b"host",b"hesab.filmjadiid.ir")]
assert m._dh1_status(Request(scope)).status_code==403
print("PREFLIGHT_ADMIN_UI_AND_AUTH=PASS")
'

BACKUP="/root/hesab-dual-hourly-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BACKUP"
cp -a "$CFG" "$BACKUP/config.json"
cp -a "$UI" "$BACKUP/maya1_control.py"
for entry in "$LOCAL_COLLECTOR" "$SERVICE" "$TIMER"; do
  key="$(echo "$entry" | tr '/.' '__')"
  if [[ -e "$entry" ]]; then cp -a "$entry" "$BACKUP/$key"; fi
done
docker inspect -f '{{.Image}}' "$OLD" >"$BACKUP/app-image-id"
echo "BACKUP=$BACKUP"

CHANGED=0
rollback(){
  code=$?
  trap - EXIT
  if (( code != 0 && CHANGED )); then
    echo "INSTALL_FAILED_ROLLING_BACK"
    systemctl disable --now hesab-dual-hourly-v1.timer >/dev/null 2>&1 || true
    cp -a "$BACKUP/config.json" "$CFG"
    cp -a "$BACKUP/maya1_control.py" "$UI"
    for entry in "$LOCAL_COLLECTOR" "$SERVICE" "$TIMER"; do
      key="$(echo "$entry" | tr '/.' '__')"
      if [[ -e "$BACKUP/$key" ]]; then cp -a "$BACKUP/$key" "$entry"
      else rm -f "$entry"; fi
    done
    systemctl daemon-reload || true
    if ! compose up -d --no-deps --no-build --force-recreate app; then
       echo "WARNING=APP_ROLLBACK_RECREATE_FAILED"
    fi
    echo "ROLLBACK_BACKUP=$BACKUP"
  fi
  exit "$code"
}
trap rollback EXIT

CHANGED=1
echo "=== CORRECT ONLY DUAL MONITOR IP MAP ==="
python3 - <<'PY'
import json,os,tempfile
from pathlib import Path
p=Path("/root/.config/hesab-dual-hourly-v1.json")
doc=json.loads(p.read_text(encoding="utf8"))
correct={"maya1":"94.184.4.38","maya-s3":"185.215.230.221","maya4":"5.10.249.206"}
for name,ip in correct.items():
    assert name in doc["servers"]
    doc["servers"][name]["host"]=ip
fd,temp=tempfile.mkstemp(prefix=".hesab-dual-config-",dir=str(p.parent))
try:
    os.fchmod(fd,0o600)
    with os.fdopen(fd,"w",encoding="utf8") as out:
        json.dump(doc,out,ensure_ascii=False,indent=2)
        out.flush();os.fsync(out.fileno())
    os.replace(temp,p)
finally:
    if os.path.exists(temp):os.unlink(temp)
print("DUAL_MONITOR_IP_MAPPING=CORRECTED")
print("NET_METER_CONFIG_CHANGED=NO")
PY

install -o root -g root -m 0700 "$COLLECTOR" "$LOCAL_COLLECTOR"
python3 "$LOCAL_COLLECTOR"

python3 - <<'PY'
import json,time
from pathlib import Path
p=Path("/opt/vpn-control-center/maya_extra_sync/dual_hourly_v1.json")
doc=json.loads(p.read_text(encoding="utf8"))
assert doc["format"]=="HESAB_DUAL_HOURLY_V1"
assert 0<=time.time()-doc["collected_at"]<150
for name in ("maya1","maya-s3","maya4"):
    row=doc["servers"][name]
    assert row["state"]=="ok",(name,row.get("state"))
    assert all(row["paths"][role]["ip"] for role in ("backhaul","mieru"))
print("THREE_MAYA_HOURLY_SNAPSHOT=PASS")
PY

# This is already mounted read-only for V10's own traffic data.
compose exec -T app python - <<'PY'
import json
from pathlib import Path
p=Path("/srv/maya-live/dual_hourly_v1.json")
d=json.loads(p.read_text())
assert d["format"]=="HESAB_DUAL_HOURLY_V1"
assert all(d["servers"][n]["state"]=="ok" for n in ("maya1","maya-s3","maya4"))
print("APP_SHARED_SNAPSHOT=READABLE")
PY

cat >"$SERVICE" <<'UNIT'
[Unit]
Description=Hesab read-only hourly Dual Backhaul and Mieru cached status
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=root
ExecStart=/usr/bin/python3 /opt/vpn-control-center/scripts/maya_dual_hourly_collect_v1.py
TimeoutStartSec=100
UNIT

cat >"$TIMER" <<'UNIT'
[Unit]
Description=Hesab Dual HA cached status every hour

[Timer]
OnCalendar=hourly
Persistent=true
AccuracySec=1min
Unit=hesab-dual-hourly-v1.service

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
printf '\n\n' >>"$UI"
cat "$PATCH" >>"$UI"
python3 -m py_compile "$UI"

echo "=== RECREATE ADMIN APP ONLY ==="
compose up -d --no-deps --no-build --force-recreate app

READY=0
for attempt in $(seq 1 30); do
  if compose exec -T app python - <<'PY' >/dev/null 2>&1
import json
from app import main as m
from starlette.requests import Request
paths=[r.path for r in m.app.routes]
for expected in ("/control-room","/control-room/v10/daily",
                 "/control-room/v9/topup","/control-room/dual-hourly/status"):
    assert paths.count(expected)==1,expected
assert "dh1-root" in m.TEMPLATES["control_room.html"]
assert "t10-compact-css" in m.TEMPLATES["control_room.html"]
token="s"*40
scope={"type":"http","asgi":{"version":"3.0"},"http_version":"1.1",
"method":"GET","scheme":"https","path":"/control-room/dual-hourly/status",
"root_path":"","query_string":b"",
"headers":[(b"host",b"hesab.filmjadiid.ir"),(b"x-control-csrf",token.encode())],
"server":("hesab.filmjadiid.ir",443),"client":("127.0.0.1",1234),
"session":{"maya1_control_csrf":token},"app":m.app}
response=m._dh1_status(Request(scope))
assert response.status_code==200
data=json.loads(response.body)
assert all(data["servers"][s]["state"]=="ok" for s in ("maya1","maya-s3","maya4"))
scope["headers"]=[(b"host",b"hesab.filmjadiid.ir")]
assert m._dh1_status(Request(scope)).status_code==403
assert m._cr2_page(Request(scope)).status_code==200
PY
  then READY=1; break; fi
  sleep 2
done
[[ "$READY" == 1 ]] || { echo "STOP=ADMIN_APP_RUNTIME_VALIDATION_FAILED"; false; }

systemctl enable --now hesab-dual-hourly-v1.timer
systemctl is-active --quiet hesab-dual-hourly-v1.timer
trap - EXIT
echo "SUCCESS=DUAL_HOURLY_CONTROL_ROOM_LIVE"
echo "MAYA1_MAYA3_MAYA4=CONNECTED"
echo "HOURLY_TIMER=ACTIVE"
echo "NO_TUNNEL_CADDY_XUI_FINANCE_CHANGES=TRUE"
echo "NET_METER_IP_MAPPING_STILL_REQUIRES_SEPARATE_CORRECTION=TRUE"
echo "BACKUP=$BACKUP"
