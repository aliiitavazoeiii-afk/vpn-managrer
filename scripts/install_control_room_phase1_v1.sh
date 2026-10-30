#!/usr/bin/env bash
# HESAB_CONTROL_ROOM_PHASE1_V1_INSTALL — scoped reversible ADMIN UI
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo "STOP: root required";exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
PATCH="$SRC/patches/control_room_phase1_v1.py"
ROOT=/opt/vpn-control-center
cd "$ROOT"
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
LIVE=patches/maya1_control.py
for path in .env docker-compose.yml docker-compose.sms.yml "$LIVE" "$PATCH";do
 [[ -s "$path" ]] || { echo "STOP: missing $path";exit 3; }
done
grep -Fq 'maya1_control.py' docker-compose.sms.yml || { echo "STOP: Maya control runtime mount missing";exit 3; }
grep -Fq 'HESAB_MAYA_CONTROL_ROOM_V2' "$LIVE" || { echo "STOP: existing Control Room V2 required";exit 3; }
if grep -Fq 'HESAB_CONTROL_ROOM_PHASE1_V1' "$LIVE";then
 echo "ALREADY_PRESENT: Phase1 UI loaded in source. Inspect current runtime before repeating."
 exit 0
fi
python3 -m py_compile "$PATCH"
c config -q
OLD="$(c ps -q app)"
[[ -n "$OLD" ]] && [[ "$(docker inspect -f '{{.State.Running}}' "$OLD")" == true ]] || {
 echo "STOP: admin app not currently running";exit 3;
}
echo "=== TEST EXACT PHASE1 OVERLAY IN SEPARATE READONLY PYTHON PROCESS ==="
cat "$PATCH" | c exec -T app python -c '
import sys
from app import main as m
from jinja2 import Environment
src=sys.stdin.read()
assert "HESAB_CONTROL_ROOM_PHASE1_V1" in src
before=[r for r in m.app.routes if getattr(r,"path",None)=="/control-room"]
assert len(before)==1
exec(compile(src,"<p1-preflight>","exec"),vars(m))
assert len([r for r in m.app.routes if getattr(r,"path",None)=="/control-room"])==1
assert len([r for r in m.app.routes if getattr(r,"path",None)=="/control-room/phase1/status"])==1
t=m.TEMPLATES["control_room.html"]
for marker in ("p1-ops-root","p1-monitor","id=\"c2-users\"","mdl2-toolbar"):
 assert marker in t,marker
Environment().parse(t)
print("PHASE1_OVERLAY_AND_JINJA_PREFLIGHT_OK")
'
BACKUP="/root/hesab-phase1-ui-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$BACKUP"
cp -a "$LIVE" "$BACKUP/maya1_control.py"
docker inspect -f '{{.Image}}' "$OLD" > "$BACKUP/previous-image-id.txt"
echo "BACKUP=$BACKUP"
CHANGED=0
rollback(){
 local rc=$?
 trap - EXIT
 if ((rc!=0)) && ((CHANGED));then
  echo "ROLLBACK: restoring previous admin UI code"
  cp -a "$BACKUP/maya1_control.py" "$LIVE"
  c up -d --no-deps --no-build --force-recreate app || echo "ROLLBACK RECREATE FAILED; inspect $BACKUP"
 fi
 exit "$rc"
}
trap rollback EXIT
CHANGED=1
printf '\n\n' >> "$LIVE"
cat "$PATCH" >> "$LIVE"
python3 -m py_compile "$LIVE"
echo "RESTART: ONLY admin app; financial tables, customer-portal, SMS and XUI configs unchanged"
c up -d --no-deps --no-build --force-recreate app
ready=0
for i in $(seq 1 35);do
 if c exec -T app python - <<'PY' >/dev/null 2>&1
from app import main as m
from jinja2 import Environment
paths=[r.path for r in m.app.routes]
assert paths.count("/control-room")==1
assert paths.count("/control-room/v2/data")==1
assert paths.count("/control-room/phase1/status")==1
assert paths.count("/control-room/maya-live/toggle")==1
t=m.TEMPLATES["control_room.html"]
assert "p1-monitor" in t and "p1-ops-root" in t
assert "c2-users" in t and "mdl2-toolbar" in t
Environment().parse(t)
result=m._p1_status(None)
assert result.status_code==200
PY
 then ready=1;break;fi
 sleep 2
done
[[ "$ready" -eq 1 ]] || { echo "STOP: phase1 runtime verification unsuccessful";false; }
trap - EXIT
echo "SUCCESS: HESAB CONTROL ROOM PHASE1 UI ACTIVE"
echo "BACKUP=$BACKUP"
echo "NOTE: Host metrics and VPN-path probes require separate verified sensor/configuration."
