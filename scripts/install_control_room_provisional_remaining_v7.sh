#!/usr/bin/env bash
# HESAB_MAYA_PROVISIONAL_REMAINING_V7_INSTALL
# Reversible admin UI and non-financial RX progress. Preserves historical ref.
# Does not alter NIC state ledger, XUI clients, billing, tunnel or provider quotas.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP: root required"; exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
ROOT=/opt/vpn-control-center
LIVE=patches/maya1_control.py
COLLECTOR=scripts/maya_net_meter_collect_v2.py
PATCH="$SRC/patches/control_room_provisional_remaining_v7.py"
NEW_METER="$SRC/scripts/maya_net_meter_collect_v2.py"
NEW_INIT="$SRC/scripts/maya_provider_provisional_baseline_v7.py"
LOCAL_INIT=scripts/maya_provider_provisional_baseline_v7.py
BASELINE=maya_extra_sync/phase1/provisional_meter_baseline_v7.json
cd "$ROOT"
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for f in .env docker-compose.yml docker-compose.sms.yml "$LIVE" "$PATCH" "$COLLECTOR" "$NEW_METER" "$NEW_INIT";do
 [[ -s "$f" ]] || { echo "STOP: missing $f";exit 3; }
done
for marker in HESAB_CONTROL_ROOM_PROVIDER_REFERENCE_V6 HESAB_CONTROL_ROOM_LIVE_VISUAL_V4;do
 grep -Fq "$marker" "$LIVE" || { echo "STOP: requires installed $marker";exit 3; }
done
grep -Fq './maya_extra_sync:/srv/maya-live:ro' docker-compose.sms.yml || {
 echo "STOP: readonly meter mount missing";exit 3;
}
if grep -Fq '# HESAB_MAYA_PROVISIONAL_REMAINING_V7' "$LIVE";then
 echo "ALREADY_INSTALLED: V7, no rebaseline or reset";exit 0
fi
if [[ -e "$BASELINE" ]];then
 echo "STOP: provisional V7 baseline exists already; will not overwrite";exit 3
fi
# Ensure the exact live collector can be amended in-place safely.
python3 - "$COLLECTOR" "$NEW_METER" <<'PY'
import sys
old=open(sys.argv[1],encoding="utf8").read()
new=open(sys.argv[2],encoding="utf8").read()
a='          "sample_age_s":0,\n          "traffic_state":"direction_unconfirmed"}'
b='          "sample_age_s":0,\n          "counter_uncertain":uncertain,\n          "traffic_state":"direction_unconfirmed"}'
if old.replace(a,b)!=new or old.count(a)!=1:
 raise SystemExit("STOP: collector changed from expected V2; manual review required")
print("CURRENT_NIC_LEDGER_COLLECTOR_SAFE_TO_PATCH")
PY
python3 -m py_compile "$PATCH" "$NEW_METER" "$NEW_INIT"
c config -q
OLD="$(c ps -q app)"
[[ -n "$OLD" ]] && [[ "$(docker inspect -f '{{.State.Running}}' "$OLD")" == true ]] || {
 echo "STOP: admin app not running";exit 3;
}
echo "=== V7 READONLY UI API PREFLIGHT ==="
cat "$PATCH" | c exec -T app python -c '
import sys
from app import main as m
from jinja2 import Environment
before=[(r.path,sorted(r.methods)) for r in m.app.routes
    if getattr(r,"path","").startswith("/control-room")]
assert "/control-room/v7/provisional-remaining" not in [r[0] for r in before]
exec(compile(sys.stdin.read(),"<v7_preflight>","exec"),vars(m))
after=[(r.path,sorted(r.methods)) for r in m.app.routes
    if getattr(r,"path","").startswith("/control-room")]
assert after==before+[("/control-room/v7/provisional-remaining",["GET"])]
t=m.TEMPLATES["control_room.html"]
assert t.count("id=\"e7-provisional-style\"")==1
assert "برآورد آزمایشی" in t and "id=\"c3-mode\"" in t
assert t.count("id=\"c2-search\"")==1
Environment().parse(t)
assert m._e7_read(None).status_code==200
print("V7_PROVISIONAL_JINJA_PREFLIGHT_OK")
'
BACKUP="/root/hesab-v7-provisional-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$BACKUP"
cp -a "$LIVE" "$BACKUP/maya1_control.py"
cp -a "$COLLECTOR" "$BACKUP/maya_net_meter_collect_v2.py"
if [[ -e "$LOCAL_INIT" ]];then cp -a "$LOCAL_INIT" "$BACKUP/provisional_init.py";fi
echo "BACKUP=$BACKUP"
CHANGED=0
rollback(){
 local rc=$?
 trap - EXIT
 if ((rc!=0&&CHANGED));then
  echo "ROLLBACK: V7 UI and collector; no NIC state reset"
  cp -a "$BACKUP/maya1_control.py" "$LIVE"
  cp -a "$BACKUP/maya_net_meter_collect_v2.py" "$COLLECTOR"
  if [[ -e "$BACKUP/provisional_init.py" ]];then
   cp -a "$BACKUP/provisional_init.py" "$LOCAL_INIT";
  else rm -f "$LOCAL_INIT";fi
  rm -f "$BASELINE"
  c up -d --no-deps --no-build --force-recreate app || \
    echo "ROLLBACK RECREATE FAILED: $BACKUP"
 fi
 exit "$rc"
}
trap rollback EXIT
CHANGED=1
install -o root -g root -m 0700 "$NEW_METER" "$COLLECTOR"
install -o root -g root -m 0700 "$NEW_INIT" "$LOCAL_INIT"
echo "=== READ LIVE NIC STATUS WITH RESET UNCERTAINTY FLAG ==="
systemctl start hesab-maya-net-meter-v2.service
python3 - <<'PY'
import json,time
from pathlib import Path
p=Path("/opt/vpn-control-center/maya_extra_sync/phase1/status.json")
doc=json.loads(p.read_text(encoding="utf8"))
assert doc["format"]=="HESAB_PHASE1_V1"
assert 0<=time.time()-doc["collected_at"]<=150
for name in ("maya1","maya-s3","maya4"):
 s=doc["servers"][name]
 assert s.get("state")=="ok",(name,s.get("state"))
 assert s.get("counter_uncertain") is False,(name,s.get("counter_uncertain"))
 assert s.get("traffic_state")=="direction_unconfirmed",(name,s.get("traffic_state"))
 assert isinstance(s.get("rx_period_gb"),(int,float)),name
print("THREE_FRESH_HEALTHY_RX_SENSORS_WITH_NO_RESET")
PY
python3 "$LOCAL_INIT"
printf '\n\n' >>"$LIVE"
cat "$PATCH" >>"$LIVE"
python3 -m py_compile "$LIVE"
c up -d --no-deps --no-build --force-recreate app
READY=0
for i in $(seq 1 35);do
 if c exec -T app python - <<'PY' >/dev/null 2>&1
from app import main as m
from jinja2 import Environment
import json
paths=[r.path for r in m.app.routes]
for p in ("/control-room","/control-room/v6/provider-reference",
          "/control-room/v7/provisional-remaining","/control-room/maya-live/toggle"):
 assert paths.count(p)==1,p
t=m.TEMPLATES["control_room.html"]
assert t.count('id="e7-provisional-style"')==1
Environment().parse(t)
data=json.loads(m._e7_read(None).body)
for k in ("maya1","maya-s3","maya4"):
 assert data["servers"][k]["state"]=="provisional",data["servers"][k]
 assert data["servers"][k]["alert_eligible"] is False
PY
 then READY=1;break;fi
 sleep 2
done
[[ "$READY" -eq 1 ]] || { echo "STOP: V7 app readback failed";false; }
trap - EXIT
echo "SUCCESS: V7 PROVISIONAL RX-DECREASING BALANCE ACTIVE"
echo "IMPORTANT: Historical provider balance may be outdated; calibrate against provider before trusting it."
echo "ALERTS_FROM_PROVISIONAL_BALANCE=DISABLED"
echo "BACKUP=$BACKUP"
