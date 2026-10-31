#!/usr/bin/env bash
# HESAB_MAYA_TOPUP_V9_INSTALL
# Adds admin-only 100/200/500 GB topup journal + provisional low-traffic alerts.
# User's 2026-10-31 Maya1 +500GB purchase is inserted ONCE after verifying
# their BEFORE-purchase provider reference baseline (82/140/137.66GB).
# No XUI/tunnel/financial ledger writes. Only admin app recreated.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP: run as root";exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
ROOT=/opt/vpn-control-center
LIVE=patches/maya1_control.py
PATCH="$SRC/patches/control_room_traffic_topup_v9.py"
cd "$ROOT"
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
[[ -s "$PATCH" && -s "$LIVE" ]] || { echo "STOP: source missing";exit 3; }
grep -Fq 'HESAB_MAYA_PROVISIONAL_REMAINING_V7' "$LIVE" || {
 echo "STOP: V7 meter baseline is not installed";exit 3;
}
if grep -Fq '# HESAB_CONTROL_ROOM_TRAFFIC_TOPUP_V9' "$LIVE";then
 echo "ALREADY_INSTALLED: traffic journal UI V9, skip purchase seed";exit 0;
fi
systemctl is-active --quiet hesab-maya-net-meter-v2.timer || {
 echo "STOP: minute-level meter timer inactive";exit 3;
}
python3 - <<'PY'
import json,time
from pathlib import Path
root=Path("/opt/vpn-control-center/maya_extra_sync/phase1")
base=json.loads((root/"provisional_meter_baseline_v7.json").read_text())
ref=json.loads((root/"provider_balance_reference_v1.json").read_text())
live=json.loads((root/"status.json").read_text())
assert base["format"]=="HESAB_MAYA_PROVISIONAL_BASELINE_V7"
assert ref["format"]=="HESAB_PROVIDER_BALANCE_REFERENCE_V1"
assert base["direction_assumption"]=="rx" and base["alert_eligible"] is False
assert 0<=time.time()-live["collected_at"]<180,"Meter stale"
expected={"maya1":82.0,"maya-s3":140.0,"maya4":137.66}
for name,value in expected.items():
 assert base["servers"][name]["starting_reported_remaining_gb"]==value,(name,"V8 before-purchase baseline differs")
 assert ref["servers"][name]["remaining_gb"]==value,(name,"current provider reference differs")
 assert live["servers"][name]["state"]=="ok",(name,"sensor offline")
 assert live["servers"][name]["counter_uncertain"] is False,(name,"reset uncertainty")
print("BASELINE_82_140_137_66_CONFIRMED_BEFORE_MAYA1_500GB_PURCHASE")
PY
python3 -m py_compile "$PATCH"
compose config -q
OLD="$(compose ps -q app)"
[[ -n "$OLD" ]] && [[ "$(docker inspect -f '{{.State.Running}}' "$OLD")" == true ]] || {
 echo "STOP: admin app not running";exit 3;
}
echo "=== V9 ISOLATED CONTROL ROOM TEMPLATE PREFLIGHT ==="
cat "$PATCH" | compose exec -T app python -c '
import sys
from app import main as m
from jinja2 import Environment
before=[(r.path,sorted(r.methods)) for r in m.app.routes
        if getattr(r,"path","").startswith("/control-room")]
assert "/control-room/v9/topup" not in [r[0] for r in before]
exec(compile(sys.stdin.read(),"<topup-v9-preflight>","exec"),vars(m))
after=[(r.path,sorted(r.methods)) for r in m.app.routes
       if getattr(r,"path","").startswith("/control-room")]
assert after==before+[("/control-room/v9/traffic",["GET"]),("/control-room/v9/topup",["POST"])]
t=m.TEMPLATES["control_room.html"]
for key in ("id=\"t9-topup-panel\"","name=\"t9-amount\"",
             "id=\"t9-notify-enable\"","id=\"c3-mode\"","id=\"c2-users\""):
 assert key in t,key
assert t.count("id=\"c2-cards\"")==1
assert t.count("id=\"c2-search\"")==1
Environment().parse(t)
assert m._t9_epochs()["maya1"]
print("MAYA_TOPUP_V9_PREFLIGHT_OK")
'
BACKUP="/root/hesab-topup-v9-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$BACKUP"
cp -a "$LIVE" "$BACKUP/maya1_control.py"
docker inspect -f '{{.Image}}' "$OLD" >"$BACKUP/app-image-id-before.txt"
echo "BACKUP=$BACKUP"
CHANGED=0
rollback(){
 local rc=$?
 trap - EXIT
 if ((rc!=0&&CHANGED));then
  echo "ROLLBACK: restore previous admin template; existing topup journal retained for audit"
  cp -a "$BACKUP/maya1_control.py" "$LIVE"
  compose up -d --no-deps --no-build --force-recreate app || \
    echo "ROLLBACK_RECREATE_FAILED: source backup $BACKUP"
 fi
 exit "$rc"
}
trap rollback EXIT
CHANGED=1
printf '\n\n' >>"$LIVE"
cat "$PATCH" >>"$LIVE"
python3 -m py_compile "$LIVE"
compose up -d --no-deps --no-build --force-recreate app
echo "=== CREATE ISOLATED TOPUP JOURNAL AND SEED THE USER'S SINGLE MAYA1 PURCHASE ==="
compose exec -T app python - <<'PY'
from app import main as m
from sqlalchemy import text
sgen=m.get_db()
db=next(sgen)
try:
    # Explicit write during installation only, never during GET.
    db.execute(text(m._T9_DDL))
    db.commit()
    ep=m._t9_epochs()
    assert all(ep.values()),"V7 baseline not readable in app"
    key="INITIAL_MAYA1_500GB_20261031_OPERATOR_ONCE"
    db.execute(text("""
INSERT INTO hesab_maya_traffic_topups_v9(server_id,gb,request_key,meter_epoch,origin)
VALUES('maya1',500,:key,:epoch,'initial_operator_purchase')
ON CONFLICT(request_key) DO NOTHING
"""),{"key":key,"epoch":ep["maya1"]})
    db.commit()
    row=db.execute(text("""
SELECT server_id,gb,meter_epoch FROM hesab_maya_traffic_topups_v9
WHERE request_key=:key
"""),{"key":key}).one()
    assert row.server_id=="maya1" and row.gb==500 and row.meter_epoch==ep["maya1"]
    sums,recent=m._t9_get_data(db)
    assert sums["maya1"]>=500
    assert any(x["server"]=="maya1" and x["gb"]==500 and
               x["origin"]=="initial_operator_purchase" for x in recent)
    print("MAYA1_500GB_PURCHASE_REGISTERED_EXACTLY_ONCE")
    print("MAYA_TOPUPS_NOW_GB",sums)
finally:
    sgen.close()
PY
echo "=== VERIFY NEW ADMIN API AND PRESERVE ORIGINAL CONTROLS ==="
compose exec -T app python - <<'PY'
from app import main as m
from jinja2 import Environment
from sqlalchemy import text
import json
routes=[r.path for r in m.app.routes]
for path in ("/control-room","/control-room/v9/traffic","/control-room/v9/topup",
             "/control-room/v7/provisional-remaining","/control-room/maya-live/toggle"):
    assert routes.count(path)==1,path
html=m.TEMPLATES["control_room.html"]
assert html.count('id="t9-topup-panel"')==1
Environment().parse(html)
source=m.get_db()
db=next(source)
try:
    doc=json.loads(m._t9_status(None,db).body)
    assert doc["servers"]["maya1"]["topup_gb"]>=500
    assert doc["servers"]["maya1"]["state"]=="provisional"
    assert doc["servers"]["maya1"]["alert_is_estimate_only"] is True
    print("MAYA_TOPUP_V9_ADMIN_RUNTIME_OK")
finally:source.close()
PY
trap - EXIT
echo "SUCCESS: MAYA THREE-SERVER TOPUP SELECTOR 100/200/500 + WEB ALERTS INSTALLED"
echo "CURRENT_MAYA1_PLUS_500_ALREADY_RECORDED_ONCE=TRUE"
echo "NOTIFICATION_BROWSER_TAB_MUST_BE_OPEN=TRUE"
echo "ALERTS_ARE_PROVISIONAL_UNTIL_RX_CONFIRMED_BY_PROVIDER=TRUE"
echo "BACKUP=$BACKUP"
