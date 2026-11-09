#!/usr/bin/env bash
# HESAB_MOBILE_SIDEBAR_V12_1_INSTALL -- app presentation ONLY
# Preflight/read-only validation, backup, exact-source hash, and rollback.
# NEVER rebuild or restart portal, DB, VPN, tunnels, or web proxy.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP=ROOT_REQUIRED";exit 2; }
ROOT=/opt/vpn-control-center
ADDON="$(cd "$(dirname "$0")/.." && pwd)/patches/mobile_dashboard_nav_fix_v12_1.py"
cd "$ROOT"
ADMIN=patches/maya1_control.py
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for f in "$ADMIN" "$ADDON" docker-compose.yml docker-compose.sms.yml;do
 [[ -s "$f" && ! -L "$f" ]] || { echo "STOP=MISSING_OR_UNSAFE_FILE $f";exit 3; }
done
grep -Fq '# HESAB_MOBILE_DASHBOARD_V12' "$ADMIN" ||
 { echo "STOP=MOBILE_V12_NOT_INSTALLED";exit 3; }
if grep -Fq '# HESAB_MOBILE_SIDEBAR_LAYER_FIX_V12_1' "$ADMIN";then
 echo "ALREADY_INSTALLED=MOBILE_NAV_V12_1";exit 0
fi
python3 -m py_compile "$ADMIN" "$ADDON"
compose config -q
APP="$(compose ps -q app)"
[[ -n "$APP" && "$(docker inspect -f '{{.State.Running}}' "$APP")" == true ]] ||
 { echo "STOP=ADMIN_NOT_RUNNING";exit 3; }
ADMIN_MOUNT="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/sms-patch/maya1_control.py"}}{{.Source}}{{end}}{{end}}' "$APP")"
[[ "$ADMIN_MOUNT" == "$ROOT/$ADMIN" ]] ||
 { echo "STOP=ADMIN_MOUNT_MISMATCH";exit 3; }

echo "=== REAL ADMIN NAV PREFLIGHT: READ-ONLY ==="
cat "$ADDON" | compose exec -T app python -c '
import sys
from app import main as m
from jinja2 import Environment
old=dict(m.TEMPLATES)
paths=[(r.path,tuple(sorted(getattr(r,"methods",[]) or []))) for r in m.app.routes]
assert old["base.html"].count("hm12-admin-menu")==1
exec(compile(sys.stdin.read(),"<mobile-sidebar-v12-1-preflight>","exec"),vars(m))
new=m.TEMPLATES["base.html"]
assert new.count("hm121-sidebar-layer-style")==1
assert new.count("hm121-sidebar-layer-script")==1
assert "appendChild(sidebar)" in new
assert "marker.parentNode.insertBefore(sidebar,marker.nextSibling)" in new
assert old.keys()==m.TEMPLATES.keys()
assert all(old[k]==m.TEMPLATES[k] for k in old if k!="base.html")
assert [(r.path,tuple(sorted(getattr(r,"methods",[]) or [])))
        for r in m.app.routes]==paths
Environment().parse(new)
print("MOBILE_SIDEBAR_V12_1_PREFLIGHT_PASS")
'

echo "=== BACKUP EXACT ADMIN UI SOURCE ==="
BACKUP="/root/hesab-mobile-nav-v12-1-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BACKUP"
cp -a "$ADMIN" "$BACKUP/maya1_control.py"
cp -a docker-compose.yml docker-compose.sms.yml "$BACKUP/"
docker inspect -f '{{.Image}}' "$APP" > "$BACKUP/admin-image-id"
echo "BACKUP=$BACKUP"

CHANGED=0
rollback(){
 code=$?
 trap - EXIT
 if ((code!=0 && CHANGED));then
   echo "ROLLBACK=MOBILE_SIDEBAR_V12_1_RESTORE"
   cp -a "$BACKUP/maya1_control.py" "$ADMIN"
   compose up -d --no-deps --no-build --force-recreate app ||
     echo "WARNING=ADMIN_RECREATE_AFTER_ROLLBACK_FAILED"
   echo "BACKUP=$BACKUP"
 fi
 exit "$code"
}
trap rollback EXIT
CHANGED=1
printf '\n\n' >>"$ADMIN"
cat "$ADDON" >>"$ADMIN"
python3 -m py_compile "$ADMIN"
sha256sum "$ADMIN" > "$BACKUP/installed-sha256.txt"
chmod 0600 "$BACKUP/installed-sha256.txt"
echo "=== RECREATE ONLY ADMIN WEB CONTAINER, NO BUILD ==="
compose up -d --no-deps --no-build --force-recreate app

echo "=== VERIFY RUNNING NAVIGATION AND EXISTING CONTROL ROOM ==="
READY=0
for i in $(seq 1 30);do
 if compose exec -T app python - <<'PY' >/dev/null 2>&1
from app import main as m
from jinja2 import Environment
import urllib.request
base=m.TEMPLATES["base.html"]
assert 'id="hm121-sidebar-layer-script"' in base
assert 'id="hm121-sidebar-layer-style"' in base
assert 'id="hm12-admin-menu"' in base
assert 'appendChild(sidebar)' in base
assert all(x in base for x in ('href="/debts"','href="/followups"',
             'href="/payments"','href="/control-room"'))
assert "t10-compact-css" in m.TEMPLATES["control_room.html"]
Environment().parse(base)
assert any(r.path=="/control-room" for r in m.app.routes)
with urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=4) as r:
 assert r.status==200
PY
 then READY=1;break;fi
 sleep 2
done
[[ "$READY" == 1 ]] || { echo "STOP=ADMIN_NAV_RUNTIME_VERIFY_FAILED";false; }
trap - EXIT
echo "SUCCESS=MOBILE_SIDEBAR_V12_1_ACTIVE"
echo "MOBILE_DRAWER=ABOVE_BACKDROP_WITH_FULL_NAV"
echo "DESKTOP_SIDEBAR=ORIGINAL_POSITION_RESTORED_ON_RESIZE"
echo "CUSTOMER_PORTAL_RESTARTED=NO"
echo "VPN_TUNNELS_XUI_DB_PAYMENTS_CHANGED=NO"
echo "BACKUP=$BACKUP"
