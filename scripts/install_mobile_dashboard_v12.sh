#!/usr/bin/env bash
# HESAB_MOBILE_DASHBOARD_V12_OFFLINE_INSTALL
# Additive UI only. No Docker build, PyPI, financial DB, XUI or tunnel changes.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP=ROOT_REQUIRED";exit 2; }
ROOT=/opt/vpn-control-center
SRC="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ADMIN=patches/maya1_control.py
CUSTOMER=customer_portal/login_activity.py
ADD_ADMIN="$SRC/patches/mobile_dashboard_admin_v12.py"
ADD_CUSTOMER="$SRC/customer_portal/mobile_dashboard_customer_v12.py"
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for f in "$ADMIN" "$CUSTOMER" "$ADD_ADMIN" "$ADD_CUSTOMER" docker-compose.yml docker-compose.sms.yml;do
 [[ -s "$f" && ! -L "$f" ]] || { echo "STOP=MISSING_OR_SYMLINK $f";exit 3; }
done
grep -Fq 'MAYA1_CONTROL_VIEW_V1' "$ADMIN" || { echo "STOP=ADMIN_PATCH_MARKER_MISSING";exit 3; }
grep -Fq 'HESAB_CONTROL_ROOM_COMPACT_V10' "$ADMIN" || { echo "STOP=EXPECTED_MAYA_CARDS_MISSING";exit 3; }
grep -Fq 'PORTAL_LOGIN_ACTIVITY_V1' "$CUSTOMER" || { echo "STOP=CUSTOMER_SESSION_WRAPPER_MISSING";exit 3; }
grep -Fq 'HESAB_CUSTOMER_SERVICES_AFTER_LOGIN_ACTIVITY_V4' "$CUSTOMER" || { echo "STOP=CUSTOMER_LANDING_V4_MISSING";exit 3; }
if grep -Fq '# HESAB_MOBILE_DASHBOARD_V12' "$ADMIN" ||
   grep -Fq '# HESAB_MOBILE_CUSTOMER_V12' "$CUSTOMER";then
 if grep -Fq '# HESAB_MOBILE_DASHBOARD_V12' "$ADMIN" &&
    grep -Fq '# HESAB_MOBILE_CUSTOMER_V12' "$CUSTOMER";then
   echo "ALREADY_INSTALLED=MOBILE_V12";exit 0
 fi
 echo "STOP=PARTIAL_EXISTING_MOBILE_INSTALL";exit 3
fi
python3 -m py_compile "$ADMIN" "$CUSTOMER" "$ADD_ADMIN" "$ADD_CUSTOMER"
compose config -q
APP="$(compose ps -q app)"
PORTAL="$(compose ps -q customer-portal)"
for cid in "$APP" "$PORTAL";do
 [[ -n "$cid" && "$(docker inspect -f '{{.State.Running}}' "$cid")" == true ]] ||
 { echo "STOP=APP_OR_PORTAL_NOT_RUNNING";exit 3; }
done
ADMIN_MOUNT="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/sms-patch/maya1_control.py"}}{{.Source}}{{end}}{{end}}' "$APP")"
PORTAL_MOUNT="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/srv/login_activity.py"}}{{.Source}}{{end}}{{end}}' "$PORTAL")"
[[ "$ADMIN_MOUNT" == "$ROOT/$ADMIN" && "$PORTAL_MOUNT" == "$ROOT/$CUSTOMER" ]] ||
 { echo "STOP=PATCH_BIND_MOUNT_MISMATCH";exit 3; }

echo "=== ADMIN UI PREFLIGHT (READ-ONLY) ==="
cat "$ADD_ADMIN" | compose exec -T app python -c '
import sys
from app import main as m
from jinja2 import Environment
before=dict(m.TEMPLATES)
routes=[(r.path,tuple(sorted(getattr(r,"methods",[]) or []))) for r in m.app.routes]
exec(compile(sys.stdin.read(),"<mobile-admin-v12>","exec"),vars(m))
assert before.keys()==m.TEMPLATES.keys()
assert all(before[k]==m.TEMPLATES[k] for k in before if k!="base.html")
assert m.TEMPLATES["base.html"].count("hm12-admin-mobile")==1
assert m.TEMPLATES["base.html"].count("hm12-admin-menu")==1
assert [(r.path,tuple(sorted(getattr(r,"methods",[]) or [])))
        for r in m.app.routes]==routes
Environment().parse(m.TEMPLATES["base.html"])
print("ADMIN_MOBILE_PREFLIGHT=PASS")
'

echo "=== CUSTOMER UI PREFLIGHT (READ-ONLY) ==="
cat "$ADD_CUSTOMER" | compose exec -T customer-portal python -c '
import sys
import server as m
from jinja2 import Environment
before={k:getattr(m,k) for k in ("_SV2_HTML","_V2_DASH","_V2_LOGIN")}
routes=[r.path for r in m.app.router.routes]
exec(compile(sys.stdin.read(),"<mobile-customer-v12>","exec"),vars(m))
for k,value in before.items():
    updated=getattr(m,k)
    assert updated.replace(m._HCM12_LINK,"",1)==value,k
    assert updated.count(m._HCM12_LINK)==1,k
    Environment().parse(updated)
assert [r.path for r in m.app.router.routes]==routes+["/assets/mobile-dashboard-v12.css"]
assert ".entry-modal-card" in m._HCM12_STYLE
assert m._hcm12_asset().status_code==200
print("CUSTOMER_MOBILE_PREFLIGHT=PASS")
'

echo "=== BACKUP ==="
BACKUP="/root/hesab-mobile-dashboard-v12-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BACKUP"
cp -a "$ADMIN" "$BACKUP/maya1_control.py"
cp -a "$CUSTOMER" "$BACKUP/login_activity.py"
cp -a docker-compose.yml docker-compose.sms.yml "$BACKUP/"
docker inspect -f '{{.Image}}' "$APP" >"$BACKUP/admin-image-id"
docker inspect -f '{{.Image}}' "$PORTAL" >"$BACKUP/customer-image-id"
echo "BACKUP=$BACKUP"

CHANGED=0
rollback(){
 code=$?
 trap - EXIT
 if ((code!=0 && CHANGED));then
   echo "MOBILE_V12_INSTALL_FAILED=RESTORING_BOTH_SOURCES"
   cp -a "$BACKUP/maya1_control.py" "$ADMIN"
   cp -a "$BACKUP/login_activity.py" "$CUSTOMER"
   compose up -d --no-deps --no-build --force-recreate app customer-portal ||
     echo "WARNING=ROLLBACK_SERVICE_RECREATE_FAILED"
   echo "BACKUP=$BACKUP"
 fi
 exit "$code"
}
trap rollback EXIT
echo "=== INSTALL PRESENTATION MODULES ==="
CHANGED=1
printf '\n\n' >>"$ADMIN"
cat "$ADD_ADMIN" >>"$ADMIN"
printf '\n\n' >>"$CUSTOMER"
cat "$ADD_CUSTOMER" >>"$CUSTOMER"
python3 -m py_compile "$ADMIN" "$CUSTOMER"
sha256sum "$ADMIN" "$CUSTOMER" >"$BACKUP/installed-sha256.txt"
chmod 600 "$BACKUP/installed-sha256.txt"

echo "=== RECREATE ONLY UI SERVICES; NO BUILD ==="
compose up -d --no-deps --no-build --force-recreate app customer-portal
ADMIN_READY=0
for i in $(seq 1 35);do
 if compose exec -T app python - <<'PY' >/dev/null 2>&1
from app import main as m
from jinja2 import Environment
import urllib.request
assert "hm12-admin-mobile" in m.TEMPLATES["base.html"]
assert "hm12-admin-menu" in m.TEMPLATES["base.html"]
assert "c2-root" in m.TEMPLATES["control_room.html"]
assert "t10-compact-css" in m.TEMPLATES["control_room.html"]
assert any(r.path=="/control-room" for r in m.app.router.routes)
Environment().parse(m.TEMPLATES["base.html"])
urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=5).read()
PY
 then ADMIN_READY=1;break;fi
 sleep 2
done
[[ "$ADMIN_READY" == 1 ]] || { echo "STOP=ADMIN_MOBILE_VERIFY_FAILED";false; }
CUSTOMER_READY=0
for i in $(seq 1 35);do
 if compose exec -T customer-portal python - <<'PY' >/dev/null 2>&1
import server
import urllib.request
from jinja2 import Environment
for key in ("_SV2_HTML","_V2_DASH","_V2_LOGIN"):
    value=getattr(server,key)
    assert value.count("/assets/mobile-dashboard-v12.css")==1,key
    Environment().parse(value)
assert any(r.path=="/assets/mobile-dashboard-v12.css" for r in server.app.router.routes)
assert "sv-private-file" in server._HCM12_STYLE
urllib.request.urlopen("http://127.0.0.1:8091/health",timeout=5).read()
r=urllib.request.urlopen("http://127.0.0.1:8091/assets/mobile-dashboard-v12.css",timeout=5)
assert r.status==200 and b".sv-top-grid" in r.read()
PY
 then CUSTOMER_READY=1;break;fi
 sleep 2
done
[[ "$CUSTOMER_READY" == 1 ]] || { echo "STOP=CUSTOMER_MOBILE_VERIFY_FAILED";false; }
compose exec -T customer-portal python - <<'PY'
import server
paths=[r.path for r in server.app.router.routes]
assert paths.count("/")==1
assert paths.count("/payments/history")==1
assert paths.count("/assets/mobile-dashboard-v12.css")==1
print("CUSTOMER_EXISTING_ROUTES=UNCHANGED")
PY
trap - EXIT
echo "SUCCESS=MOBILE_DASHBOARD_V12_INSTALLED"
echo "ADMIN_MOBILE_DRAWER=ENABLED"
echo "MAYA_3_SERVER_CARDS=ONE_COLUMN_ON_MOBILE"
echo "ALL_ADMIN_TABLE_COLUMNS_AND_ACTIONS=PRESERVED"
echo "CUSTOMER_HOME_PAYMENT_LOGIN_AND_FILE_DOWNLOAD=RESPONSIVE"
echo "DESKTOP_UI=UNCHANGED_BY_MEDIA_QUERIES"
echo "NO_DOCKER_BUILD_OR_PYPI=YES"
echo "XUI_TUNNELS_HAPROXY_PAYMENT_DATABASE_CHANGED=NO"
echo "BACKUP=$BACKUP"
