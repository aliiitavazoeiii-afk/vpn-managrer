#!/usr/bin/env bash
# HESAB_CONTROL_ROOM_USER_ROWS_V13_INSTALL
# Read-only --check by default; explicit --install for admin UI only.
# No XUI, VPN, traffic collectors, finance, database or customer restarts.
set -Eeuo pipefail
umask 077
MODE=--check
if (( $# > 0 ));then MODE="$1";fi
[[ "$MODE" == "--check" || "$MODE" == "--install" ]] ||
 { echo "USAGE: $0 [--check|--install]";exit 2; }
[[ "$(id -u)" == "0" ]] || { echo "STOP=ROOT_REQUIRED";exit 2; }
ROOT=/opt/vpn-control-center
SRC="$(cd "$(dirname "$0")/.." && pwd)"
PATCH="$SRC/patches/control_room_user_rows_v13.py"
LIVE=patches/maya1_control.py
cd "$ROOT"
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for f in "$PATCH" "$LIVE" docker-compose.yml docker-compose.sms.yml;do
 [[ -s "$f" && ! -L "$f" ]] ||
 { echo "STOP=MISSING_OR_LINKED_FILE:$f";exit 3; }
done
for marker in HESAB_CONTROL_ROOM_TABLE_V3 HESAB_CONTROL_ROOM_COMPACT_V10;do
 grep -Fq "$marker" "$LIVE" ||
 { echo "STOP=CONTROL_ROOM_DEPENDENCY_MISSING:$marker";exit 3; }
done
if grep -Fq HESAB_CONTROL_ROOM_USER_ROWS_V13 "$LIVE";then
 echo "STOP=V13_ALREADY_INSTALLED";exit 3
fi
python3 -m py_compile "$LIVE" "$PATCH"
compose config -q
APP="$(compose ps -q app)"
[[ -n "$APP" && "$(docker inspect -f '{{.State.Running}}' "$APP")" == true ]] ||
 { echo "STOP=ADMIN_NOT_RUNNING";exit 3; }
MOUNT="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/sms-patch/maya1_control.py"}}{{.Source}}{{end}}{{end}}' "$APP")"
[[ "$MOUNT" == "$ROOT/$LIVE" ]] ||
 { echo "STOP=ADMIN_BIND_MOUNT_MISMATCH";exit 3; }
echo "=== READ-ONLY LIVE ADMIN PREFLIGHT ==="
cat "$PATCH" | compose exec -T app python -c '
import sys
from app import main as m
from jinja2 import Environment
old=dict(m.TEMPLATES)
routes=[(r.path,tuple(sorted(getattr(r,"methods",[]) or ())))
        for r in m.app.router.routes]
original=m._cr2_one
assert old["control_room.html"].count("id=\"c3-mode\"")==1
assert old["control_room.html"].count("id=\"c2-users\"")==1
source=sys.stdin.read()
assert source.startswith("# HESAB_CONTROL_ROOM_USER_ROWS_V13")
exec(compile(source,"<v13-preflight>","exec"),vars(m))
new=m.TEMPLATES["control_room.html"]
assert new.count("id=\"r13-compact-list-style\"")==1
assert new.count("<option value=\"unmatched\">")==1
assert "c3LastMs(a.last_online)-c3LastMs(b.last_online)" in new
assert "detailsButton.onclick=()=>c3Details(server,item)" in new
assert "btn.onclick=()=>toggle(server,item,btn)" in new
assert m._cr2_one is original
assert old.keys()==m.TEMPLATES.keys()
assert all(old[k]==m.TEMPLATES[k] for k in old if k!="control_room.html")
assert routes==[(r.path,tuple(sorted(getattr(r,"methods",[]) or ())))
               for r in m.app.router.routes]
Environment().parse(new)
print("V13_PREFLIGHT_PASS")
'
if [[ "$MODE" == "--check" ]];then
 echo "SUCCESS=V13_READ_ONLY_CHECK_NO_CHANGES"
 exit 0
fi
BACKUP="/root/hesab-control-room-rows-v13-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BACKUP"
cp -a "$LIVE" "$BACKUP/maya1_control.py"
docker inspect -f '{{.Image}}' "$APP" > "$BACKUP/admin-image-before.txt"
echo "BACKUP=$BACKUP"
CHANGED=0
rollback(){
 code=$?
 trap - EXIT
 if ((code!=0 && CHANGED));then
   echo "ROLLBACK=RESTORING_ADMIN_UI"
   cp -a "$BACKUP/maya1_control.py" "$LIVE"
   compose up -d --no-deps --no-build --force-recreate app ||
    echo "WARNING=ADMIN_RECREATE_AFTER_ROLLBACK_FAILED"
 fi
 exit "$code"
}
trap rollback EXIT
CHANGED=1
printf '\n\n' >>"$LIVE"
cat "$PATCH" >>"$LIVE"
python3 -m py_compile "$LIVE"
sha256sum "$LIVE" > "$BACKUP/installed-sha256.txt"
chmod 0600 "$BACKUP/installed-sha256.txt"
echo "=== RECREATE ADMIN WEB APP ONLY ==="
compose up -d --no-deps --no-build --force-recreate app

echo "=== VERIFY LOADED CONTROL ROOM UI ==="
READY=0
for i in $(seq 1 30);do
 if compose exec -T app python - <<'PY' >/dev/null 2>&1
from app import main as m
from jinja2 import Environment
page=m.TEMPLATES["control_room.html"]
assert page.count('id="r13-compact-list-style"')==1
assert page.count('<option value="unmatched">')==1
assert page.count('id="c2-users"')==1
assert "c3LastMs(a.last_online)-c3LastMs(b.last_online)" in page
assert "detailsButton.onclick=()=>c3Details(server,item)" in page
assert "fetch(\"/control-room/v2/data\"" in page
assert "fetch(\"/control-room/maya-live/toggle\"" in page
Environment().parse(page)
paths=[r.path for r in m.app.router.routes]
for p in ("/control-room","/control-room/v2/data",
          "/control-room/maya-live/toggle"):
 assert paths.count(p)==1
PY
 then READY=1;break;fi
 sleep 2
done
[[ "$READY" == "1" ]] ||
 { echo "STOP=V13_RUNTIME_CHECK_FAILED";false; }
trap - EXIT
echo "SUCCESS=CONTROL_ROOM_USER_ROWS_V13_INSTALLED"
echo "MAYA_1_3_4=ROW_LAYOUT"
echo "UNMATCHED_FILTER=YES"
echo "OFFLINE_48H=OLDEST_FIRST"
echo "MAYA3_MAYA4_DAILY_USAGE_CALCULATION_CHANGED=NO"
echo "CUSTOMER_PORTAL_XUI_TUNNELS_FINANCE_CHANGED=NO"
echo "BACKUP=$BACKUP"
