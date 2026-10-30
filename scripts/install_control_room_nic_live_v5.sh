#!/usr/bin/env bash
# HESAB_CONTROL_ROOM_NIC_LIVE_V5_INSTALL
# UI + read-only API ONLY. Does NOT modify counters, baselines, XUI or payments.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo "STOP: root required";exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
ROOT=/opt/vpn-control-center
PATCH="$SRC/patches/control_room_nic_live_v5.py"
LIVE="patches/maya1_control.py"
cd "$ROOT"
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for item in .env docker-compose.yml docker-compose.sms.yml "$LIVE" "$PATCH";do
 [[ -s "$item" ]] || { echo "STOP: missing $item";exit 3; }
done
for marker in HESAB_CONTROL_ROOM_LIVE_VISUAL_V4 HESAB_CONTROL_ROOM_NET_METER_V2_UI;do
 grep -Fq "$marker" "$LIVE" || { echo "STOP: missing installed $marker";exit 3; }
done
if grep -Fq '# HESAB_CONTROL_ROOM_NIC_LIVE_V5' "$LIVE";then
 echo "ALREADY_INSTALLED: V5 UI present";exit 0
fi
grep -Fq './maya_extra_sync:/srv/maya-live:ro' docker-compose.sms.yml || {
 echo "STOP: live telemetry RO mount unavailable";exit 3;
}
[[ -f maya_extra_sync/phase1/status.json ]] || {
 echo "STOP: no meter samples found";exit 3;
}
python3 - "$ROOT/maya_extra_sync/phase1/status.json" <<'PY'
import json,sys
p=sys.argv[1]
doc=json.load(open(p))
assert doc.get("format")=="HESAB_PHASE1_V1"
assert all(doc.get("servers",{}).get(x,{}).get("state")=="ok"
   for x in ("maya1","maya-s3","maya4"))
print("THREE_MAYA_NIC_SAMPLES_PRESENT")
PY
python3 -m py_compile "$PATCH"
c config -q
OLD="$(c ps -q app)"
[[ -n "$OLD" ]] && [[ "$(docker inspect -f '{{.State.Running}}' "$OLD")" == true ]] || {
 echo "STOP: admin app not running";exit 3;
}
echo "=== ISOLATED APP PREFLIGHT (NO PRODUCTION CHANGES) ==="
cat "$PATCH" | c exec -T app python -c '
import sys
from app import main as m
from jinja2 import Environment
src=sys.stdin.read()
assert "HESAB_CONTROL_ROOM_NIC_LIVE_V5" in src
before=[(r.path,sorted(r.methods)) for r in m.app.routes
        if getattr(r,"path","").startswith("/control-room")]
assert "/control-room/v5/nic-traffic" not in [x[0] for x in before]
exec(compile(src,"<nic-live-v5-preflight>","exec"),vars(m))
after=[(r.path,sorted(r.methods)) for r in m.app.routes
       if getattr(r,"path","").startswith("/control-room")]
assert after==before+[("/control-room/v5/nic-traffic",["GET"])]
t=m.TEMPLATES["control_room.html"]
for marker in ("id=\"n5-net-traffic\"","n5FetchTraffic()","RX اندازه‌گیری‌شده",
               "TX اندازه‌گیری‌شده","id=\"c3-mode\"","id=\"c2-users\"",
               "mdl2-toolbar"):
 assert marker in t,marker
assert t.count("id=\"c2-search\"")==1
Environment().parse(t)
sample=m._n5_read(None)
assert sample.status_code==200
import json
data=json.loads(sample.body)
for name in ("maya1","maya-s3","maya4"):
 item=data["servers"][name]
 assert item["state"]=="ok", (name,item["state"])
 assert "rx_period_gb" in item and "tx_period_gb" in item,name
print("NIC_V5_LIVE_SAMPLE_READABLE_IN_APP")
print("NIC_V5_JINJA_API_PREFLIGHT_PASS")
'
B="/root/hesab-nic-live-v5-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$B"
cp -a "$LIVE" "$B/maya1_control.py"
docker inspect -f '{{.Image}}' "$OLD" >"$B/previous-app-image-id.txt"
echo "BACKUP=$B"
CHANGED=0
rollback(){
 local rc=$?
 trap - EXIT
 if ((rc!=0 && CHANGED));then
  echo "ROLLBACK: restore previous admin UI"
  cp -a "$B/maya1_control.py" "$LIVE"
  c up -d --no-deps --no-build --force-recreate app || \
   echo "ROLLBACK RECREATE FAILED; use $B"
 fi
 exit "$rc"
}
trap rollback EXIT
CHANGED=1
printf '\n\n' >>"$LIVE"
cat "$PATCH" >>"$LIVE"
python3 -m py_compile "$LIVE"
echo "RECREATING ONLY ADMIN APP (no billing, DB, XUI or NIC counter modifications)"
c up -d --no-deps --no-build --force-recreate app
READY=0
for i in $(seq 1 35);do
 if c exec -T app python - <<'PY' >/dev/null 2>&1
from app import main as m
from jinja2 import Environment
paths=[r.path for r in m.app.routes]
for name in ("/control-room","/control-room/v2/data",
             "/control-room/v4/host-metrics",
             "/control-room/phase1/status",
             "/control-room/v5/nic-traffic",
             "/control-room/maya-live/toggle"):
 assert paths.count(name)==1,name
template=m.TEMPLATES["control_room.html"]
assert template.count('id="n5-net-traffic"')==1
assert 'RX اندازه‌گیری‌شده' in template
assert 'TX اندازه‌گیری‌شده' in template
Environment().parse(template)
import json
data=json.loads(m._n5_read(None).body)
assert all(data["servers"][name]["state"]=="ok" and
 "rx_period_gb" in data["servers"][name] and
 "tx_period_gb" in data["servers"][name]
 for name in ("maya1","maya-s3","maya4"))
PY
 then READY=1;break;fi
 sleep 2
done
[[ "$READY" -eq 1 ]] || { echo "STOP: V5 runtime verification failed";false; }
trap - EXIT
echo "SUCCESS: THREE MAYA NIC RX TX V5 NOW AVAILABLE IN CONTROL ROOM"
echo "BACKUP=$B"
echo "NOTE: provider remaining GB stays unconfirmed until calibrated."
