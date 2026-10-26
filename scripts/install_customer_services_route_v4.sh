#!/usr/bin/env bash
# HESAB_CUSTOMER_SERVICES_V4_ROUTE_REPAIR
set -Eeuo pipefail
umask 077
[ "$#" -eq 1 ] || { echo "Usage: bash install_customer_services_route_v4.sh REPO";exit 2; }
[ "$(id -u)" = 0 ] || { echo "STOP: root only";exit 2; }
SRC="$1"
cd /opt/vpn-control-center
LIVE=/opt/vpn-control-center/customer_portal/login_activity.py
PATCH="$SRC/customer_portal/services_after_login_activity_v4.py"
compose() { docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
[ -s "$LIVE" ] && [ -s "$PATCH" ] || { echo "STOP: source missing";exit 3; }
compose config -q
CID="$(compose ps -q customer-portal)"
[ -n "$CID" ] && [ "$(docker inspect -f '{{.State.Running}}' "$CID")" = true ] || { echo "STOP: container not running";exit 3; }
MOUNT="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/srv/login_activity.py"}}{{.Source}}{{end}}{{end}}' "$CID")"
[ "$MOUNT" = "$LIVE" ] || { echo "STOP: source mount differs";exit 3; }
docker exec "$CID" grep -q HESAB_CUSTOMER_SERVICES_V2 /srv/server.py || { echo "STOP: dashboard V2 missing";exit 3; }
docker exec "$CID" grep -q PORTAL_LOGIN_ACTIVITY_V1 /srv/server.py || { echo "STOP: login audit missing";exit 3; }
grep -q '_pla_previous_home = v2_home' "$LIVE"
grep -q 'def _pla_home_with_activity(' "$LIVE"
if grep -q HESAB_CUSTOMER_SERVICES_AFTER_LOGIN_ACTIVITY_V4 "$LIVE";then echo "ALREADY INSTALLED";exit 0;fi
python3 - "$LIVE" "$PATCH" <<'PY'
from pathlib import Path
import ast,sys
a=Path(sys.argv[1]).read_text();b=Path(sys.argv[2]).read_text()
assert a.count("def _pla_home_with_activity(")==1
assert "HESAB_CUSTOMER_SERVICES_AFTER_LOGIN_ACTIVITY_V4" in b
ast.parse(a+"\n"+b)
print("PREFLIGHT_OK")
PY
BACKUP="/root/hesab-services-v4-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
cp -a "$LIVE" "$BACKUP/login_activity.py"
echo "BACKUP=$BACKUP"
MODIFIED=0
rollback() {
 code=$?
 trap - EXIT
 if [ "$code" -ne 0 ] && [ "$MODIFIED" = 1 ];then
   echo "ERROR: rolling back login patch"
   cp -a "$BACKUP/login_activity.py" "$LIVE"
   compose up -d --no-deps --no-build --force-recreate customer-portal || echo "ROLLBACK RECREATE FAILED"
 fi
 exit "$code"
}
trap rollback EXIT
TMP="$(mktemp /opt/vpn-control-center/customer_portal/.activity-v4.XXXXXX)"
cp -a "$LIVE" "$TMP"
printf '\n' >> "$TMP"
cat "$PATCH" >> "$TMP"
python3 -m py_compile "$TMP"
MODIFIED=1
mv -f "$TMP" "$LIVE"
compose up -d --no-deps --no-build --force-recreate customer-portal
NEW="$(compose ps -q customer-portal)"
[ -n "$NEW" ]
READY=0
for i in $(seq 1 30);do
 state="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$NEW")"
 if [ "$state" = healthy ];then READY=1;break;fi
 sleep 2
done
[ "$READY" = 1 ] || { echo "PORTAL NOT HEALTHY";false; }
docker exec "$NEW" python -c '
import server
routes=[r for r in server.app.router.routes if getattr(r,"path",None)=="/" and "GET" in (getattr(r,"methods",set()) or set())]
assert len(routes)==1 and routes[0].endpoint is server._pla_home_with_activity
assert server._pla_previous_home is server._sv2_landing
assert any(r.path=="/payments/history" for r in server.app.router.routes)
print("DASHBOARD_V2_AND_LOGIN_AUDIT_OK")
'
trap - EXIT
echo "SUCCESS: CUSTOMER SERVICES V4 ROUTE FIX INSTALLED"
echo "BACKUP=$BACKUP"
