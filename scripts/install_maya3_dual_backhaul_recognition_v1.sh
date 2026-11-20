#!/usr/bin/env bash
# Management server only: Maya3 Backhaul1+Backhaul2 collector and admin UI.
# Keep Maya1+Maya4 legacy Mieru schema unchanged. NO tunnel or provider edits.
set -Eeuo pipefail
umask 077
[[ $EUID == 0 && $# == 1 && "$1" =~ ^[0-9a-f]{40}$ ]] || {
 echo "Usage: sudo bash install_maya3_dual_backhaul_recognition_v1.sh PINNED_COMMIT"; exit 2;
}
REF="$1"
ROOT=/opt/vpn-control-center
cd "$ROOT"
UI=patches/maya1_control.py
COLLECTOR=scripts/maya_dual_hourly_collect_v1.py
CFG=/root/.config/hesab-dual-hourly-v1.json
SCRIPTROOT="https://raw.githubusercontent.com/aliiitavazoeiii-afk/vpn-managrer/$REF/scripts"
[[ -f "$UI" && -f "$COLLECTOR" && -f "$CFG" && -f docker-compose.yml &&
   -f docker-compose.sms.yml ]] || {
 echo "STOP: management host files missing";exit 3;
}
grep -Fq '# HESAB_CONTROL_ROOM_DUAL_HOURLY_SIMPLE_V1' "$UI" || {
 echo "STOP: currently deployed dual-hourly overlay not detected"; exit 3;
}
[[ -f /root/.ssh/hesab_dual_hourly_v1 ]] || {
 echo "STOP: restricted dual SSH key missing";exit 3;
}
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
compose config -q
OLD="$(compose ps -q app)"
[[ -n "$OLD" && "$(docker inspect -f '{{.State.Running}}' "$OLD")" == true ]] || {
 echo "STOP: admin app is not running";exit 3;
}
T="$(mktemp -d /root/.maya3-dual-recognition.XXXXXXXX)"
trap 'rm -rf "$T"' EXIT
curl --proto '=https' --tlsv1.2 --connect-timeout 10 --max-time 60 -fsSLo \
 "$T/maya_dual_hourly_collect_v1.py" "$SCRIPTROOT/maya_dual_hourly_collect_v1.py"
curl --proto '=https' --tlsv1.2 --connect-timeout 10 --max-time 60 -fsSLo \
 "$T/patch_maya3_dual_backhaul_ui_v1.py" "$SCRIPTROOT/patch_maya3_dual_backhaul_ui_v1.py"
python3 -m py_compile "$T/"*.py
cp -a "$UI" "$T/admin_overlay.py"
python3 "$T/patch_maya3_dual_backhaul_ui_v1.py" "$T/admin_overlay.py"
python3 -m py_compile "$T/admin_overlay.py"
echo "=== PREFLIGHT RESTRICTED MAYA3 STATUS (READ ONLY) ==="
python3 - "$T" <<'PY'
import importlib.util,sys
spec=importlib.util.spec_from_file_location("monitor",sys.argv[1]+"/maya_dual_hourly_collect_v1.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
cfg=m.validate_config()
assert cfg.get("maya-s3") and cfg["maya-s3"].get("host")=="185.215.230.221","Wrong Maya3 SSH target"
row=m.fetch("maya-s3",cfg["maya-s3"])
assert row["state"]=="ok" and row["mode"]=="dual_backhaul",row.get("state")
assert row["paths"]["backhaul"]["ip"]=="152.237.230.140","Maya3 Backhaul1 changed"
assert row["paths"]["mieru"]["ip"]=="82.152.132.112","Maya3 Backhaul2 changed"
print("MAYA3_DUAL_BACKHAUL_1_2_SSH_PREFLIGHT=PASS")
PY
BACKUP="/root/hesab-maya3-dual-backhaul-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BACKUP"
cp -a "$UI" "$BACKUP/maya1_control.py"
cp -a "$COLLECTOR" "$BACKUP/maya_dual_hourly_collect_v1.py"
if [[ -f maya_extra_sync/dual_hourly_v1.json ]];then
 cp -a maya_extra_sync/dual_hourly_v1.json "$BACKUP/dual_hourly_v1.json"
fi
echo "BACKUP=$BACKUP"
changed=0
rollback(){
 code=$?
 trap - EXIT
 if (( code!=0 && changed==1 ));then
  echo "ROLLBACK: restoring management collector and admin overlay"
  cp -a "$BACKUP/maya1_control.py" "$UI"
  cp -a "$BACKUP/maya_dual_hourly_collect_v1.py" "$COLLECTOR"
  [[ -f "$BACKUP/dual_hourly_v1.json" ]] &&
    cp -a "$BACKUP/dual_hourly_v1.json" maya_extra_sync/dual_hourly_v1.json || true
  compose up -d --no-deps --no-build --force-recreate app ||
   echo "WARNING: manual admin-app rollback may be required"
  echo "BACKUP=$BACKUP"
 fi
 rm -rf "$T"
 exit "$code"
}
trap rollback EXIT
changed=1
install -o root -g root -m 0700 "$T/maya_dual_hourly_collect_v1.py" "$COLLECTOR"
cp -a "$T/admin_overlay.py" "$UI"
python3 -m py_compile "$COLLECTOR" "$UI"
echo "=== REFRESH CACHED DUAL STATUS WITH NEW PARSER ==="
python3 "$COLLECTOR"
python3 - <<'PY'
import json,time
p="maya_extra_sync/dual_hourly_v1.json"
doc=json.load(open(p))
assert doc["format"]=="HESAB_DUAL_HOURLY_V1"
assert 0 <= time.time()-doc["collected_at"] < 120
r=doc["servers"]["maya-s3"]
assert r["state"]=="ok" and r["mode"]=="dual_backhaul"
assert r["paths"]["backhaul"]["state"]=="healthy"
assert r["paths"]["mieru"]["state"]=="healthy"
print("MAYA3_NEW_SNAPSHOT=VERIFIED",r["paths"]["backhaul"]["ip"],r["paths"]["mieru"]["ip"])
PY
echo "=== RECREATE MANAGEMENT APP ONLY ==="
compose up -d --no-deps --no-build --force-recreate app
READY=0
for attempt in $(seq 1 30); do
 if compose exec -T app python - <<'PY' >/dev/null 2>&1
import json
from app import main as m
from starlette.requests import Request
routes=[r.path for r in m.app.routes]
for path in ("/control-room","/control-room/v10/daily",
             "/control-room/dual-hourly/status",
             "/control-room/dual-hourly/refresh",
             "/control-room/dual-hourly/refresh-meta"):
    assert routes.count(path)==1,path
page=m.TEMPLATES["control_room.html"]
assert 'item.mode==="dual_backhaul"' in page
assert 'Backhaul 2' in page and 'Mieru' in page
assert page.count('id="dh1-grid"')==1
token="v"*40
scope={"type":"http","asgi":{"version":"3.0"},"http_version":"1.1",
"method":"GET","scheme":"https","path":"/control-room/dual-hourly/status",
"root_path":"","query_string":b"",
"headers":[(b"host",b"hesab.filmjadiid.ir"),(b"x-control-csrf",token.encode())],
"server":("hesab.filmjadiid.ir",443),"client":("127.0.0.1",1234),
"session":{"maya1_control_csrf":token},"app":m.app}
response=m._dh1_status(Request(scope))
assert response.status_code==200
payload=json.loads(response.body)
assert payload["servers"]["maya-s3"]["mode"]=="dual_backhaul"
assert payload["servers"]["maya-s3"]["paths"]["mieru"]["state"]=="healthy"
scope["headers"]=[(b"host",b"hesab.filmjadiid.ir")]
assert m._dh1_status(Request(scope)).status_code==403
print("MANAGEMENT_APP_ROUTES_AND_ROLE_LABELS=PASS")
PY
 then READY=1;break;fi
 sleep 2
done
[[ $READY == 1 ]] || { echo "STOP: management runtime validation failed";false; }
trap - EXIT
rm -rf "$T"
echo "SUCCESS=MAYA3_DUAL_BACKHAUL_RECOGNIZED"
echo "MAYA1_MAYA4_LEGACY_MIERU_COMPATIBILITY=PRESERVED"
echo "HOURLY_TIMER_AND_MANUAL_REFRESH=PRESERVED"
echo "VPN_TUNNELS_XRAY_CADDY_DATABASE_UNCHANGED"
echo "BACKUP=$BACKUP"
