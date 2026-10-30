#!/usr/bin/env bash
# HESAB_CONTROL_ROOM_PROVIDER_REFERENCE_V6_INSTALL
# Install clearly non-live operator-reported balance for 3 Maya cards.
# Only app recreated; no meter ledger, XUI, payments, or systemd timer changes.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo "STOP: root required";exit 2; }
[[ "$#" -eq 3 ]] || { echo "Usage: $0 MAYA1_GB MAYA3_GB MAYA4_GB";exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
ROOT=/opt/vpn-control-center
PATCH="$SRC/patches/control_room_provider_reference_v6.py"
MANAGER="$SRC/scripts/maya_provider_balance_reference_v1.py"
LIVE=patches/maya1_control.py
MANAGER_LIVE=scripts/maya_provider_balance_reference_v1.py
BALANCE=maya_extra_sync/phase1/provider_balance_reference_v1.json
cd "$ROOT"
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for f in .env docker-compose.yml docker-compose.sms.yml "$LIVE" "$PATCH" "$MANAGER";do
 [[ -s "$f" ]] || { echo "STOP: required file missing: $f";exit 3; }
done
python3 -m py_compile "$PATCH" "$MANAGER"
# Check balance amounts before touching any prod files.
python3 - "$@" <<'PY'
import sys,math
for n in sys.argv[1:]:
 x=float(n)
 assert math.isfinite(x) and 0<=x<=1e9
print("THREE_OPERATOR_REFERENCES_VALID")
PY
for key in HESAB_CONTROL_ROOM_LIVE_VISUAL_V4 HESAB_CONTROL_ROOM_NET_METER_V2_UI;do
 grep -Fq "$key" "$LIVE" || { echo "STOP: missing $key";exit 3; }
done
grep -Fq './maya_extra_sync:/srv/maya-live:ro' docker-compose.sms.yml || {
 echo "STOP: app cannot see live read-only meter volume";exit 3;
}
c config -q
OLD="$(c ps -q app)"
[[ -n "$OLD" ]] && [[ "$(docker inspect -f '{{.State.Running}}' "$OLD")" == true ]] || {
 echo "STOP: admin app is not running";exit 3;
}
# If the route already exists, only refresh the local human-entered reference
# without touching the container and without resetting NIC usage.
if grep -Fq '# HESAB_CONTROL_ROOM_PROVIDER_REFERENCE_V6' "$LIVE";then
 [[ -s "$MANAGER_LIVE" ]] || { echo "STOP: V6 UI present but manager missing";exit 3; }
 python3 "$MANAGER_LIVE" set "$@"
 echo "REFERENCE_UPDATED_NO_RESTART"
 exit 0
fi
echo "=== VALIDATE V4/M2/V5 COMPATIBILITY IN ISOLATED APP PROCESS ==="
cat "$PATCH" | c exec -T app python -c '
import sys
from app import main as m
from jinja2 import Environment
src=sys.stdin.read()
before=[(r.path,sorted(r.methods)) for r in m.app.routes
        if getattr(r,"path","").startswith("/control-room")]
assert before and "/control-room/v6/provider-reference" not in [r[0] for r in before]
exec(compile(src,"<provider_reference_v6_preflight>","exec"),vars(m))
after=[(r.path,sorted(r.methods)) for r in m.app.routes
       if getattr(r,"path","").startswith("/control-room")]
assert after==before+[("/control-room/v6/provider-reference",["GET"])]
html=m.TEMPLATES["control_room.html"]
for marker in ("آخرین مانده اعلامی دیتاسنتر","b6FetchReference()",
               "id=\"b6-reference-style\"","id=\"c2-users\"","id=\"c3-mode\"",
               "mdl2-toolbar"):
 assert marker in html,marker
assert html.count("id=\"c2-cards\"")==1
assert html.count("id=\"c2-search\"")==1
Environment().parse(html)
print("PROVIDER_REFERENCE_V6_JINJA_PREFLIGHT_OK")
'
BACKUP="/root/hesab-reference-v6-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$BACKUP"
cp -a "$LIVE" "$BACKUP/maya1_control.py"
docker inspect -f '{{.Image}}' "$OLD" >"$BACKUP/previous-app-image-id.txt"
if [[ -e "$BALANCE" ]];then cp -a "$BALANCE" "$BACKUP/reference.json";fi
if [[ -e "$MANAGER_LIVE" ]];then cp -a "$MANAGER_LIVE" "$BACKUP/manager.py";fi
echo "BACKUP=$BACKUP"
CHANGED=0
rollback(){
 local rc=$?
 trap - EXIT
 if ((rc!=0 && CHANGED));then
  echo "ROLLBACK: restore pre-V6 admin UI and local reference"
  cp -a "$BACKUP/maya1_control.py" "$LIVE"
  if [[ -e "$BACKUP/reference.json" ]];then cp -a "$BACKUP/reference.json" "$BALANCE";
  else rm -f "$BALANCE";fi
  if [[ -e "$BACKUP/manager.py" ]];then cp -a "$BACKUP/manager.py" "$MANAGER_LIVE";
  else rm -f "$MANAGER_LIVE";fi
  c up -d --no-deps --no-build --force-recreate app || \
    echo "ROLLBACK RECREATE FAILED: inspect $BACKUP"
 fi
 exit "$rc"
}
trap rollback EXIT
CHANGED=1
install -o root -g root -m 0700 "$MANAGER" "$MANAGER_LIVE"
python3 "$MANAGER_LIVE" set "$@"
printf '\n\n' >>"$LIVE"
cat "$PATCH" >>"$LIVE"
python3 -m py_compile "$LIVE"
echo "RECREATE: only admin app, finance/XUI/meter unchanged"
c up -d --no-deps --no-build --force-recreate app
READY=0
for i in $(seq 1 35);do
 if c exec -T app python - <<'PY' >/dev/null 2>&1
from app import main as m
from jinja2 import Environment
import json
routes=[r.path for r in m.app.routes]
assert routes.count("/control-room")==1
assert routes.count("/control-room/v6/provider-reference")==1
assert routes.count("/control-room/maya-live/toggle")==1
html=m.TEMPLATES["control_room.html"]
assert html.count('id="b6-reference-style"')==1
assert "آخرین مانده اعلامی دیتاسنتر" in html
Environment().parse(html)
response=json.loads(m._b6_status(None).body)
for key,value in (("maya1",144),("maya-s3",189),("maya4",144)):
 assert response["servers"][key]["state"]=="reported_not_live"
 assert response["servers"][key]["remaining_gb"]==value
PY
 then READY=1;break;fi
 sleep 2
done
[[ "$READY" -eq 1 ]] || { echo "STOP: V6 runtime checks failed";false; }
trap - EXIT
echo "SUCCESS: PROVIDER REPORTED BALANCE V6 INSTALLED"
echo "BALANCES_ARE_OPERATOR_REPORTS_NOT_REALTIME=TRUE"
echo "BACKUP=$BACKUP"
