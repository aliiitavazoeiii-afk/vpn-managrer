#!/usr/bin/env bash
# Management host ONLY. Syncs Maya1/Maya3 v3 three-site health into existing
# Control Room, preserving Maya4, manual refresh, x-ui, finance and traffic.
# Changes only host read-only SSH collector, admin UI overlay, collector timer,
# and recreates the existing management APP container. NO VPN changes.
set -Eeuo pipefail
umask 077
[[ $EUID == 0 && $# == 1 && "$1" =~ ^[0-9a-f]{40}$ ]] || {
 echo "Usage: sudo bash install_control_room_three_site_v3.sh PINNED_COMMIT";exit 2;
}
REF="$1"
ROOT=/opt/vpn-control-center
UI="$ROOT/patches/maya1_control.py"
COLLECT="$ROOT/scripts/maya_dual_hourly_collect_v1.py"
SNAP="$ROOT/maya_extra_sync/dual_hourly_v1.json"
CFG=/root/.config/hesab-dual-hourly-v1.json
TIMER=/etc/systemd/system/hesab-dual-hourly-v1.timer
SERVICE=/etc/systemd/system/hesab-dual-hourly-v1.service
BASE="https://raw.githubusercontent.com/aliiitavazoeiii-afk/vpn-managrer/$REF/scripts"
TMP=""
BACKUP=""
CHANGED=0

for file in "$UI" "$COLLECT" "$SNAP" "$CFG" "$TIMER" "$SERVICE" \
            "$ROOT/docker-compose.yml" "$ROOT/docker-compose.sms.yml";do
  [[ -f "$file" && ! -L "$file" ]] || {
    echo "STOP: expected management file missing/symlink: $file";exit 3;
  }
done
[[ "$(stat -c '%u' "$CFG")" == 0 && ! "$(stat -c '%a' "$CFG")" =~ [1-7]$ ]] || {
  echo "STOP: protected SSH config ownership/permissions changed";exit 3;
}
grep -Fq '# HESAB_CONTROL_ROOM_DUAL_HOURLY_SIMPLE_V1' "$UI"
grep -Fq '# HESAB_MAYA3_DUAL_BACKHAUL_VISUAL_V1' "$UI"
grep -Fq '# HESAB_DUAL_HOURLY_MANUAL_REFRESH_V2' "$UI"
if grep -Fq '# HESAB_CONTROL_ROOM_THREE_SITE_V3' "$UI";then
  echo "STOP: V3 Control Room already installed; refusing duplicate";exit 3
fi
grep -Fq 'OnCalendar=hourly' "$TIMER" || {
  echo "STOP: unexpected hourly timer layout";exit 3;
}
grep -Fq '/opt/vpn-control-center/scripts/maya_dual_hourly_collect_v1.py' "$SERVICE"
systemctl is-active --quiet hesab-dual-hourly-v1.timer || {
  echo "STOP: existing hourly timer inactive";exit 3;
}
systemctl is-active --quiet hesab-dual-refresh-v2.service || {
  echo "STOP: existing manual refresh worker inactive";exit 3;
}
exec 9>/run/hesab-three-site-v3.lock
flock -n 9 || { echo "STOP: other dashboard deployment running";exit 3; }
cd "$ROOT"
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
compose config -q
CID="$(compose ps -q app)"
[[ -n "$CID" && "$(docker inspect -f '{{.State.Running}}' "$CID")" == true ]] || {
  echo "STOP: Control Room app container not running";exit 3;
}
TMP="$(mktemp -d /root/.hesab-3site.XXXXXXXX)"
rollback(){
 local code=$?
 trap - EXIT
 if ((code!=0 && CHANGED==1));then
   echo "ROLLBACK: Control Room V3 install failed, restoring originals"
   systemctl stop hesab-dual-hourly-v1.timer >/dev/null 2>&1 || true
   cp -a "$BACKUP/maya1_control.py" "$UI"
   cp -a "$BACKUP/collector.py" "$COLLECT"
   cp -a "$BACKUP/dual_hourly_v1.json" "$SNAP"
   cp -a "$BACKUP/dual_timer.old" "$TIMER"
   systemctl daemon-reload || true
   systemctl start hesab-dual-hourly-v1.timer || true
   compose up -d --no-deps --no-build --force-recreate app || {
     echo "WARNING: app container rollback needs operator review"
   }
   echo "BACKUP=$BACKUP"
 fi
 rm -rf "$TMP"
 exit "$code"
}
trap rollback EXIT

curl -fsSL --proto '=https' --tlsv1.2 --connect-timeout 8 --max-time 45 \
 "$BASE/maya_dual_hourly_collect_v1.py" -o "$TMP/collector.py"
curl -fsSL --proto '=https' --tlsv1.2 --connect-timeout 8 --max-time 45 \
 "$BASE/patch_control_room_three_site_v3.py" -o "$TMP/ui_patch.py"
python3 -m py_compile "$TMP/collector.py" "$TMP/ui_patch.py"
cp -a "$UI" "$TMP/overlay.py"
python3 "$TMP/ui_patch.py" "$TMP/overlay.py"
python3 -m py_compile "$TMP/overlay.py"
# Existing HTML/JS generated inside overlay: validate Jinja parsing on source.
python3 - "$TMP/overlay.py" <<'PY'
import ast,sys
from jinja2 import Environment
t=ast.parse(open(sys.argv[1],encoding="utf-8").read())
literals={}
for node in ast.walk(t):
 if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
  if node.targets[0].id in ("_DH1_HTML","_DH1_JS"):
   literals[node.targets[0].id]=ast.literal_eval(node.value)
assert set(literals)=={"_DH1_HTML","_DH1_JS"}
Environment().parse("{% block content %}"+literals["_DH1_HTML"]+literals["_DH1_JS"]+"{% endblock %}")
assert "Cloudflare" in literals["_DH1_JS"] and "Apple" in literals["_DH1_JS"]
print("CONTROL_ROOM_V3_TEMPLATE_AND_PARSER_PREFLIGHT_PASS")
PY

# Live restricted SSH preflight for both migrated Maya nodes BEFORE any write.
python3 - "$TMP/collector.py" <<'PY'
import importlib.util,sys
spec=importlib.util.spec_from_file_location("remote_monitor_candidate",sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
cfg=m.validate_config()
expected={
 "maya1":("94.184.4.38","82.152.132.159","152.237.230.77"),
 "maya-s3":("185.215.230.221","152.237.230.140","82.152.132.112")}
for name,(iran,a,b) in expected.items():
 item=cfg.get(name)
 assert item and item.get("enabled") is not False and item["host"]==iran, "Wrong configured host "+name
 data=m.fetch(name,item)
 assert data["state"]=="ok" and data["mode"]=="dual_backhaul",name+" not reporting healthy V3"
 assert data["health_interval_s"]==600, name+" is not running 10-minute V3"
 for role,ip in (("backhaul",a),("mieru",b)):
  path=data["paths"][role]
  assert path["ip"]==ip and path["state"]=="healthy",(name,role,"path unhealthy")
  assert isinstance(path.get("https_sites"),dict) and len(path["https_sites"])==3
  assert sum(path["https_sites"].values())==path["https_passed"]
 print("READ_ONLY_SSH_3SITE_PASS",name,
       data["paths"]["backhaul"]["https_passed"],
       data["paths"]["mieru"]["https_passed"],flush=True)
assert "maya4" in cfg,"Maya4 legacy config missing"
print("MAYA4_LEGACY_CONFIG_UNCHANGED")
PY
# Validate expected admin app baseline before modifying it.
compose exec -T app python - <<'PY'
from app import main as m
paths=[r.path for r in m.app.routes]
for path in ("/control-room","/control-room/dual-hourly/status",
             "/control-room/dual-hourly/refresh",
             "/control-room/dual-hourly/refresh-meta"):
 assert paths.count(path)==1,path
template=m.TEMPLATES["control_room.html"]
assert 'item.mode==="dual_backhaul"' in template
assert 'id="dh1-grid"' in template and 'id="dm2-refresh"' in template
print("LIVE_ADMIN_BASELINE=PASS")
PY

BACKUP="/root/hesab-control-room-three-site-v3-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p -m 0700 "$BACKUP"
cp -a "$UI" "$BACKUP/maya1_control.py"
cp -a "$COLLECT" "$BACKUP/collector.py"
cp -a "$SNAP" "$BACKUP/dual_hourly_v1.json"
cp -a "$TIMER" "$BACKUP/dual_timer.old"
echo "BACKUP=$BACKUP"
CHANGED=1
systemctl stop hesab-dual-hourly-v1.timer
install -o root -g root -m 0700 "$TMP/collector.py" "$COLLECT.v3-next"
cp -a "$TMP/overlay.py" "$UI.v3-next"
mv -Tf "$COLLECT.v3-next" "$COLLECT"
mv -Tf "$UI.v3-next" "$UI"
python3 -m py_compile "$COLLECT" "$UI"
# Host collector runs every 10 minutes, matching V3 server check interval.
# Only cached 'dual status' via existing restricted SSH; no remote probes.
python3 - "$TIMER" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
txt=p.read_text()
assert txt.count("OnCalendar=hourly")==1
p.write_text(txt.replace("OnCalendar=hourly",
                          "OnCalendar=*-*-* *:00/10:00",1))
PY
systemd-analyze verify "$TIMER"
systemctl daemon-reload
systemctl start hesab-dual-hourly-v1.timer
systemctl is-active --quiet hesab-dual-hourly-v1.timer
python3 "$COLLECT"
python3 - "$SNAP" <<'PY'
import json,sys,time
d=json.load(open(sys.argv[1],encoding="utf8"))
assert d["format"]=="HESAB_DUAL_HOURLY_V1" and time.time()-d["collected_at"]<120
for server in ("maya1","maya-s3"):
 x=d["servers"][server]
 assert x["state"]=="ok" and x["health_interval_s"]==600 and x["mode"]=="dual_backhaul"
 assert all(x["paths"][p]["state"]=="healthy" and
            len(x["paths"][p]["https_sites"])==3 for p in ("backhaul","mieru"))
print("V3_TWO_SERVERS_CACHED_REPORT_PASS")
assert "maya4" in d["servers"]
PY

# Recreate only management app (no VPN, DB, Caddy, HAProxy, Xray changes).
compose up -d --no-deps --no-build --force-recreate app
ready=0
for i in $(seq 1 30);do
 if compose exec -T app python - <<'PY' >/dev/null 2>&1
import json
from app import main as m
from starlette.requests import Request
paths=[r.path for r in m.app.routes]
for p in ("/control-room","/control-room/dual-hourly/status",
          "/control-room/dual-hourly/refresh",
          "/control-room/dual-hourly/refresh-meta"):
 assert paths.count(p)==1,p
page=m.TEMPLATES["control_room.html"]
assert page.count('id="dh1-grid"')==1
assert "Google" in page and "Cloudflare" in page and "Apple" in page
assert 'id="dm2-refresh"' in page
token="v"*40
scope={"type":"http","asgi":{"version":"3.0"},"http_version":"1.1",
"method":"GET","scheme":"https","path":"/control-room/dual-hourly/status",
"root_path":"","query_string":b"",
"headers":[(b"host",b"hesab.filmjadiid.ir"),(b"x-control-csrf",token.encode())],
"server":("hesab.filmjadiid.ir",443),"client":("127.0.0.1",1234),
"session":{"maya1_control_csrf":token},"app":m.app}
response=m._dh1_status(Request(scope))
assert response.status_code==200
data=json.loads(response.body)
for name in ("maya1","maya-s3"):
 item=data["servers"][name]
 assert item["state"]=="ok" and item["health_interval_s"]==600
 assert item["paths"]["backhaul"]["https_sites"]["google"] is True
 assert len(item["paths"]["mieru"]["https_sites"])==3
scope["headers"]=[(b"host",b"hesab.filmjadiid.ir")]
assert m._dh1_status(Request(scope)).status_code==403
PY
 then ready=1;break;fi
 sleep 2
done
[[ "$ready" == 1 ]] || { echo "STOP: management app post-deploy V3 validation failed";false; }
systemctl is-active --quiet hesab-dual-refresh-v2.service
CHANGED=0
trap - EXIT
rm -rf "$TMP"
echo "SUCCESS=CONTROL_ROOM_THREE_SITE_10MIN_V3_LIVE"
echo "MAYA1_MAYA3_GOOGLE_CLOUDFLARE_APPLE=CONNECTED"
echo "MAYA4_LEGACY_AND_MANUAL_REFRESH=PRESERVED"
echo "HOURLY_COLLECTOR_TIMER_NOW=TEN_MINUTES"
echo "NO_VPN_DB_CADDY_XUI_RESTARTS=TRUE"
echo "BACKUP=$BACKUP"
