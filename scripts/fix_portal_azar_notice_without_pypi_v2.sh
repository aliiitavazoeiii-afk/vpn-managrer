#!/usr/bin/env bash
# HESAB_PORTAL_AZAR_NOTICE_LOCAL_MOUNT_V2
# Offline repair of only one UI condition, with a persistent read-only mount.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP=ROOT_REQUIRED"; exit 2; }
cd /opt/vpn-control-center
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
SOURCE=customer_portal/v2.py
COMPOSE=docker-compose.sms.yml
[[ -s "$SOURCE" && -s "$COMPOSE" ]] || { echo "STOP=MISSING_SOURCE"; exit 3; }
compose config -q
CID="$(compose ps -q customer-portal)"
[[ -n "$CID" && "$(docker inspect -f '{{.State.Running}}' "$CID")" == true ]] ||
 { echo "STOP=PORTAL_NOT_RUNNING"; exit 3; }
echo "=== READONLY PRODUCTION PREFLIGHT ==="
python3 - "$SOURCE" "$COMPOSE" <<'PY'
from pathlib import Path
import ast,sys
source=Path(sys.argv[1]).read_text()
conf=Path(sys.argv[2]).read_text()
old='show_welcome=request.query_params.get("welcome") == "1",'
new='show_welcome=(request.query_params.get("welcome") == "1" or request.query_params.get("view") == "payments"),'
assert (source.count(old),source.count(new)) in ((1,0),(0,1))
assert conf.count('      - ./customer_portal/logo.png:/srv/logo.png:ro')==1
assert conf.count('      - ./customer_portal/v2.py:/srv/v2.py:ro') in (0,1)
ast.parse(source)
print("HOST_PREFLIGHT=PASS")
PY
compose exec -T customer-portal python - <<'PY'
import server
from pathlib import Path
text=Path("/srv/v2.py").read_text()
old='show_welcome=request.query_params.get("welcome") == "1",'
new='show_welcome=(request.query_params.get("welcome") == "1" or request.query_params.get("view") == "payments"),'
assert (text.count(old),text.count(new)) in ((1,0),(0,1))
assert server._V2_DASH.count('تمامی اکانت‌ها تا تاریخ یکم آذر محاسبه می‌شوند.')==1
print("RUNNING_PORTAL_PREFLIGHT=PASS")
PY
BACKUP="/root/hesab-azar-offline-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 700 "$BACKUP"
cp -a "$SOURCE" "$BACKUP/v2.py"
cp -a "$COMPOSE" "$BACKUP/docker-compose.sms.yml"
docker cp "$CID:/srv/v2.py" "$BACKUP/container-v2.py"
python3 - "$SOURCE" "$BACKUP/container-v2.py" <<'PY'
from pathlib import Path
import sys
old='show_welcome=request.query_params.get("welcome") == "1",'
new='show_welcome=(request.query_params.get("welcome") == "1" or request.query_params.get("view") == "payments"),'
host=Path(sys.argv[1]).read_text(encoding="utf8").replace(new,old)
image=Path(sys.argv[2]).read_text(encoding="utf8").replace(new,old)
assert host==image,"STOP=HOST_V2_DIFFERS_FROM_RUNNING_IMAGE"
print("HOST_AND_RUNNING_PORTAL_CODE_PARITY=PASS")
PY
echo "BACKUP=$BACKUP"
CHANGED=0
rollback(){
 code=$?
 trap - EXIT
 if ((code!=0 && CHANGED));then
  echo "ROLLBACK=RESTORING_PORTAL_FILES"
  cp -a "$BACKUP/v2.py" "$SOURCE"
  cp -a "$BACKUP/docker-compose.sms.yml" "$COMPOSE"
  compose up -d --no-deps --no-build --force-recreate customer-portal ||
     echo "WARNING=ROLLBACK_PORTAL_RECREATE_FAILED"
 fi
 exit "$code"
}
trap rollback EXIT
CHANGED=1
python3 - "$SOURCE" "$COMPOSE" <<'PY'
from pathlib import Path
import ast,sys
source=Path(sys.argv[1]);conf=Path(sys.argv[2])
text=source.read_text()
old='show_welcome=request.query_params.get("welcome") == "1",'
new='show_welcome=(request.query_params.get("welcome") == "1" or request.query_params.get("view") == "payments"),'
if text.count(old)==1:
    text=text.replace(old,new,1)
assert text.count(new)==1 and old not in text
ast.parse(text)
source.write_text(text)
cfg=conf.read_text()
anchor='      - ./customer_portal/logo.png:/srv/logo.png:ro'
volume='      - ./customer_portal/v2.py:/srv/v2.py:ro'
if volume not in cfg:
    assert cfg.count(anchor)==1
    cfg=cfg.replace(anchor,anchor+'\n'+volume,1)
    conf.write_text(cfg)
print("ONE_BOOLEAN_AND_READONLY_MOUNT=PATCHED")
PY
python3 -m py_compile "$SOURCE"
compose config -q
echo "=== RECREATE CUSTOMER PORTAL ONLY, NO BUILD / NO PYPI ==="
compose up -d --no-deps --no-build --force-recreate customer-portal
READY=0
for i in $(seq 1 30);do
 if compose exec -T customer-portal python - <<'PY' >/dev/null 2>&1
from pathlib import Path
import urllib.request
import server
source=Path("/srv/v2.py").read_text()
new='show_welcome=(request.query_params.get("welcome") == "1" or request.query_params.get("view") == "payments"),'
assert source.count(new)==1
assert server._V2_DASH.count('تمامی اکانت‌ها تا تاریخ یکم آذر محاسبه می‌شوند.')==1
urllib.request.urlopen("http://127.0.0.1:8091/health",timeout=4).read()
PY
 then READY=1;break;fi
 sleep 2
done
[[ "$READY" == 1 ]] || { echo "STOP=PORTAL_VERIFY_FAILED"; false; }
trap - EXIT
echo "SUCCESS=AZAR_NOTICE_ON_PAYMENT_RESTORED_WITHOUT_BUILD"
echo "IMAGE_BUILD_OR_PIP=NOT_RUN"
echo "DATABASE_XUI_TUNNELS_ADMIN_APP=UNCHANGED"
echo "BACKUP=$BACKUP"
