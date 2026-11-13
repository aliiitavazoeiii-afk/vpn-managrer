#!/usr/bin/env bash
# HESAB_CUSTOMER_SERVER_STATUS_INSTALL_V1
# Default --check is read-only; --install is explicit only.
# No cron/timer, active probe, SSH, tunnel or financial writes.
set -Eeuo pipefail
umask 077
MODE=--check
if (( $# > 0 ));then MODE="$1";fi
[[ "$MODE" == "--check" || "$MODE" == "--install" ]] || { echo "USAGE: $0 [--check|--install]";exit 2; }
[[ "$(id -u)" == 0 ]] || { echo "STOP=ROOT_REQUIRED";exit 2; }
ROOT=/opt/vpn-control-center
SRC="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ADMIN=patches/maya1_control.py
PORTAL=customer_portal/login_activity.py
COMPOSE=docker-compose.sms.yml
ADD_ADMIN="$SRC/patches/customer_server_status_bridge_v1.py"
ADD_PORTAL="$SRC/customer_portal/customer_server_status_portal_v1.py"
KEY=customer_status_v1/bridge.key
compose(){ docker compose -f docker-compose.yml -f "$COMPOSE" "$@"; }
for f in "$ADMIN" "$PORTAL" "$ADD_ADMIN" "$ADD_PORTAL" docker-compose.yml "$COMPOSE";do
 [[ -s "$f" && ! -L "$f" ]] || { echo "STOP=REQUIRED_FILE_MISSING $f";exit 3; }
done
for marker in HESAB_MAYA_MANUAL_LINKS_V1 HESAB_CONTROL_ROOM_DUAL_HOURLY_SIMPLE_V1 HESAB_CONTROL_ROOM_MANUAL_PATH_TEST_V1;do
 grep -Fq "$marker" "$ADMIN" || { echo "STOP=ADMIN_MARKER_MISSING $marker";exit 3; }
done
for marker in PORTAL_LOGIN_ACTIVITY_V1 HESAB_CUSTOMER_SERVICES_AFTER_LOGIN_ACTIVITY_V4;do
 grep -Fq "$marker" "$PORTAL" || { echo "STOP=PORTAL_MARKER_MISSING $marker";exit 3; }
done
if grep -Fq HESAB_CUSTOMER_SERVER_STATUS_BRIDGE_V1 "$ADMIN" ||
   grep -Fq HESAB_CUSTOMER_SERVER_STATUS_PORTAL_V1 "$PORTAL";then
 echo "STOP=ALREADY_INSTALLED_OR_PARTIAL";exit 3
fi
python3 -m py_compile "$ADMIN" "$PORTAL" "$ADD_ADMIN" "$ADD_PORTAL"
compose config -q
APP="$(compose ps -q app)"
CUSTOMER="$(compose ps -q customer-portal)"
for cid in "$APP" "$CUSTOMER";do
 [[ -n "$cid" && "$(docker inspect -f '{{.State.Running}}' "$cid")" == true ]] ||
 { echo "STOP=WEB_SERVICE_NOT_RUNNING";exit 3; }
done
ADMIN_MOUNT="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/sms-patch/maya1_control.py"}}{{.Source}}{{end}}{{end}}' "$APP")"
PORTAL_MOUNT="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/srv/login_activity.py"}}{{.Source}}{{end}}{{end}}' "$CUSTOMER")"
[[ "$ADMIN_MOUNT" == "$ROOT/$ADMIN" && "$PORTAL_MOUNT" == "$ROOT/$PORTAL" ]] ||
 { echo "STOP=LIVE_BIND_MOUNT_MISMATCH";exit 3; }
python3 - "$COMPOSE" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text()
anchors=[
 "      - ./patches/maya1_control.py:/sms-patch/maya1_control.py:ro\n",
 "      - ./customer_portal/login_activity.py:/srv/login_activity.py:ro\n"]
assert all(s.count(x)==1 for x in anchors), "COMPOSE_MOUNT_PATTERN_MISMATCH"
assert "/run/hesab-customer-status-v1.key" not in s
print("COMPOSE_PRECHECK=PASS")
PY
echo "=== READ-ONLY LIVE ADMIN PREFLIGHT ==="
cat "$ADD_ADMIN" | compose exec -T app python -c '
import sys
from app import main as m
old=[r.path for r in m.app.router.routes]
assert callable(getattr(m,"_ma_approved",None))
exec(compile(sys.stdin.read(),"<admin-status-preflight>","exec"),vars(m))
assert [r.path for r in m.app.router.routes]==old+["/internal/customer-server-status/v1"]
assert m._cssb_report("maya1")["method"]=="central_cached_only"
print("ADMIN_BRIDGE_PREFLIGHT=PASS")
'
echo "=== READ-ONLY LIVE CUSTOMER PREFLIGHT ==="
cat "$ADD_PORTAL" | compose exec -T customer-portal python -c '
import sys
import server as m
from jinja2 import Environment
before=m._SV2_HTML
old=[r.path for r in m.app.router.routes]
exec(compile(sys.stdin.read(),"<portal-status-preflight>","exec"),vars(m))
assert [r.path for r in m.app.router.routes]==old+[
 "/api/my-server-status/accounts","/api/my-server-status/check"]
assert "sv-cstatus-check" in m._SV2_HTML
assert "customer_status_verified_phone_v1" not in m._cssp_session_phone.__code__.co_names
assert m._SV2_HTML.count("id=\"sv-cstatus\"")==1
assert m._SV2_HTML.replace(m._CSSP_CARD,"",1).replace(
       m._CSSP_STYLE+m._CSSP_JS,"",1)==before
Environment().parse(m._SV2_HTML)
print("CUSTOMER_STATUS_PREFLIGHT=PASS")
'
echo "AUTHENTICATION_NOTICE=USES_EXISTING_SIGNED_PHONE_LOGIN_NO_OTP"
echo "STATUS_ACCESS=SIGNED_SESSION_AND_DATABASE_OWNERSHIP_ONLY"
if [[ "$MODE" == "--check" ]];then
 echo "SUCCESS=CUSTOMER_STATUS_V1_PREFLIGHT_ONLY_NO_CHANGES"
 exit 0
fi
if [[ -e "$KEY" || -L "$KEY" ]];then echo "STOP=SECRET_ALREADY_EXISTS";exit 4;fi
BACKUP="/root/hesab-customer-status-v1-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BACKUP"
cp -a "$ADMIN" "$BACKUP/maya1_control.py"
cp -a "$PORTAL" "$BACKUP/login_activity.py"
cp -a "$COMPOSE" "$BACKUP/docker-compose.sms.yml"
echo "BACKUP=$BACKUP"
CHANGED=0
rollback(){
 code=$?
 trap - EXIT
 if ((code!=0 && CHANGED));then
   echo "STATUS_V1_INSTALL_FAILED=RESTORING"
   cp -a "$BACKUP/maya1_control.py" "$ADMIN"
   cp -a "$BACKUP/login_activity.py" "$PORTAL"
   cp -a "$BACKUP/docker-compose.sms.yml" "$COMPOSE"
   compose up -d --no-deps --no-build --force-recreate app customer-portal ||
    echo "WARNING=SERVICE_RESTORE_FAILED"
 fi
 exit "$code"
}
trap rollback EXIT
CHANGED=1
mkdir -p -m 0700 customer_status_v1
[[ ! -L customer_status_v1 ]] || { echo "STOP=SECRET_FOLDER_SYMLINK";exit 4; }
python3 - "$KEY" <<'PY'
from pathlib import Path
import os,sys,secrets
path=Path(sys.argv[1])
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o400)
with os.fdopen(fd,"wb") as f:
 f.write(secrets.token_urlsafe(48).encode("ascii")+b"\n")
os.chmod(path,0o400)
print("INTERNAL_HMAC_SECRET=CREATED_ROOT_ONLY")
PY
printf '\n\n' >>"$ADMIN";cat "$ADD_ADMIN" >>"$ADMIN"
printf '\n\n' >>"$PORTAL";cat "$ADD_PORTAL" >>"$PORTAL"
python3 - "$COMPOSE" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]);s=p.read_text()
for anchor in (
 "      - ./patches/maya1_control.py:/sms-patch/maya1_control.py:ro\n",
 "      - ./customer_portal/login_activity.py:/srv/login_activity.py:ro\n"):
 assert s.count(anchor)==1
 s=s.replace(anchor,anchor+
    "      - ./customer_status_v1/bridge.key:/run/hesab-customer-status-v1.key:ro\n",1)
p.write_text(s)
PY
python3 -m py_compile "$ADMIN" "$PORTAL"
compose config -q
sha256sum "$ADMIN" "$PORTAL" "$COMPOSE" >"$BACKUP/installed-sha256.txt"
chmod 0600 "$BACKUP/installed-sha256.txt"
echo "=== RECREATE ONLY ADMIN AND CUSTOMER WEB SERVICES ==="
compose up -d --no-deps --no-build --force-recreate app customer-portal

echo "=== VERIFY ADMIN READ-ONLY BRIDGE ==="
ADMIN_READY=0
for i in $(seq 1 30);do
 if compose exec -T app python - <<'PY' >/dev/null 2>&1
from app import main as m
import urllib.request,urllib.error
assert len(m._cssb_secret())>=32
assert any(r.path=="/internal/customer-server-status/v1" for r in m.app.router.routes)
assert "t10-compact-css" in m.TEMPLATES["control_room.html"]
assert urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=4).status==200
try:
 urllib.request.urlopen("http://127.0.0.1:8000/internal/customer-server-status/v1?sid=1",timeout=4)
 raise AssertionError("Unsigned access allowed")
except urllib.error.HTTPError as e:assert e.code==403
PY
 then ADMIN_READY=1;break;fi
 sleep 2
done
[[ "$ADMIN_READY" == 1 ]] || { echo "STOP=ADMIN_VERIFY_FAILED";false; }

echo "=== VERIFY CUSTOMER ROUTES DENY VISITORS WITHOUT LOGIN ==="
CUSTOMER_READY=0
for i in $(seq 1 30);do
 if compose exec -T customer-portal python - <<'PY' >/dev/null 2>&1
import server,urllib.request,urllib.error
assert len(server._cssp_secret())>=32
assert "sv-cstatus-check" in server._SV2_HTML
assert urllib.request.urlopen("http://127.0.0.1:8091/health",timeout=4).status==200
try:
 urllib.request.urlopen("http://127.0.0.1:8091/api/my-server-status/accounts",timeout=4)
 raise AssertionError("Unverified read allowed")
except urllib.error.HTTPError as e:assert e.code==403
PY
 then CUSTOMER_READY=1;break;fi
 sleep 2
done
[[ "$CUSTOMER_READY" == 1 ]] || { echo "STOP=CUSTOMER_VERIFY_FAILED";false; }
trap - EXIT
echo "SUCCESS=CUSTOMER_STATUS_V1_INSTALLED_SESSION_SCOPED"
echo "MANAGEMENT_INTERNAL_ENDPOINT=HMAC_REQUIRED"
echo "NO_USER_TRIGGERED_DOWNLOADS_OR_SSH=YES"
echo "CURRENT_PHONE_ONLY_AUTH=SIGNED_SESSION_NO_EXTRA_OTP"
echo "VPN_XUI_HAPROXY_MIeru_BACKHAUL_FINANCE_CHANGED=NO"
echo "BACKUP=$BACKUP"
