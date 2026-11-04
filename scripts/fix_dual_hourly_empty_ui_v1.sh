#!/usr/bin/env bash
# Repair a previously deployed V1 Control Room UI where its inline script was
# injected before the grid node. No monitoring/tunnel/Caddy/DB changes.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP=ROOT_REQUIRED"; exit 2; }
cd /opt/vpn-control-center
UI=patches/maya1_control.py
[[ -s "$UI" ]] || { echo "STOP=ADMIN_OVERLAY_NOT_FOUND"; exit 2; }
grep -Fq '# HESAB_CONTROL_ROOM_DUAL_HOURLY_SIMPLE_V1' "$UI" ||
 { echo "STOP=V1_NOT_INSTALLED"; exit 2; }
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
compose config -q
OLD="$(compose ps -q app)"
[[ -n "$OLD" && "$(docker inspect -f '{{.State.Running}}' "$OLD")" == true ]] ||
 { echo "STOP=ADMIN_APP_NOT_RUNNING"; exit 2; }

echo "=== CONFIRM EMPTY-CARDS CAUSE IN LIVE ADMIN APP ==="
compose exec -T app python - <<'PY'
from app import main as m
t=m.TEMPLATES["control_room.html"]
assert t.count('id="dh1-grid"')==1
assert t.count('id="dh1-script"')==1
assert t.index('id="dh1-script"') < t.index('id="dh1-grid"'),"Script already after grid; stop and diagnose"
assert "/control-room/dual-hourly/status" in [r.path for r in m.app.routes]
print("ROOT_CAUSE_CONFIRMED=SCRIPT_RAN_BEFORE_GRID")
PY

echo "=== BACKUP AND APPLY SCOPED UI FIX ==="
BACKUP="/root/hesab-dual-cards-hotfix-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BACKUP"
cp -a "$UI" "$BACKUP/maya1_control.py"
echo "BACKUP=$BACKUP"

CHANGED=0
rollback(){
 code=$?
 trap - EXIT
 if ((code!=0&&CHANGED));then
  echo "HOTFIX_FAILED_ROLLING_BACK"
  cp -a "$BACKUP/maya1_control.py" "$UI"
  compose up -d --no-deps --no-build --force-recreate app ||
    echo "WARNING=APP_ROLLBACK_RECREATE_FAILED"
 fi
 exit "$code"
}
trap rollback EXIT

CHANGED=1
python3 - "$UI" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
source=p.read_text(encoding="utf8")
old='''_DH1_TEMPLATE = _DH1_TEMPLATE.replace(_ANCHOR, _ANCHOR + _DH1_HTML, 1)
_DH1_TEMPLATE = _DH1_TEMPLATE.replace("{% endblock %}",
                                      _DH1_JS + "\\n{% endblock %}", 1)'''
new='''_DH1_TEMPLATE = _DH1_TEMPLATE.replace(_ANCHOR, _ANCHOR + _DH1_HTML + _DH1_JS, 1)
# Script now follows its grid node; never use the first Jinja endblock.'''
if source.count(old)!=1:
    raise RuntimeError("Exact old UI code not found; no replacement made")
tail=source.split("# HESAB_CONTROL_ROOM_DUAL_HOURLY_SIMPLE_V1",1)[1]
if tail.count(old)!=1:
    raise RuntimeError("Expected only in Dual V1 addon")
p.write_text(source.replace(old,new,1),encoding="utf8")
print("UI_JS_POSITION=PATCHED")
PY
python3 -m py_compile "$UI"
echo "=== RECREATE ONLY ADMIN APP ==="
compose up -d --no-deps --no-build --force-recreate app

READY=0
for i in $(seq 1 30); do
 if compose exec -T app python - <<'PY' >/dev/null 2>&1
import json
from app import main as m
from starlette.requests import Request
t=m.TEMPLATES["control_room.html"]
assert t.count('id="dh1-grid"')==1
assert t.count('id="dh1-script"')==1
assert t.index('id="dh1-grid"') < t.index('id="dh1-script"')
assert t.count('id="c2-cards"')==1
assert "t10-compact-css" in t
paths=[r.path for r in m.app.routes]
for x in ("/control-room","/control-room/v10/daily","/control-room/v9/topup",
          "/control-room/dual-hourly/status"):
    assert paths.count(x)==1
token="c"*40
scope={"type":"http","asgi":{"version":"3.0"},"http_version":"1.1",
"method":"GET","scheme":"https","path":"/control-room/dual-hourly/status",
"root_path":"","query_string":b"",
"headers":[(b"host",b"hesab.filmjadiid.ir"),(b"x-control-csrf",token.encode())],
"server":("hesab.filmjadiid.ir",443),"client":("127.0.0.1",1234),
"session":{"maya1_control_csrf":token},"app":m.app}
data=json.loads(m._dh1_status(Request(scope)).body)
assert all(data["servers"][sid]["state"]=="ok" for sid in ("maya1","maya-s3","maya4"))
scope["headers"]=[(b"host",b"hesab.filmjadiid.ir")]
assert m._dh1_status(Request(scope)).status_code==403
assert m._cr2_page(Request(scope)).status_code==200
PY
 then READY=1; break; fi
 sleep 2
done
[[ "$READY" == 1 ]] || { echo "STOP=RUNTIME_VALIDATION_FAILED"; false; }
trap - EXIT
echo "SUCCESS=DUAL_HOURLY_CARDS_FIXED"
echo "THREE_MAYA_SNAPSHOTS=HEALTHY"
echo "HOURLY_TIMER_CHANGED=NO"
echo "VPN_CADDY_XUI_DATABASE_CHANGED=NO"
echo "BACKUP=$BACKUP"
