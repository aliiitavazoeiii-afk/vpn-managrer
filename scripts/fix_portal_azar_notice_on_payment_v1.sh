#!/usr/bin/env bash
# HESAB_AZAR_NOTICE_ON_PAYMENT_V1
# Fix only the existing customer-portal modal condition. Financial and payment
# logic, Maya XUI, admin dashboard and other services are never edited.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == "0" ]] || { echo "STOP=ROOT_REQUIRED"; exit 2; }
ROOT=/opt/vpn-control-center
cd "$ROOT"
PAY=customer_portal/v2.py
HTML=customer_portal/dashboard_v2.html
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }

for f in "$PAY" "$HTML" customer_portal/Dockerfile \
         docker-compose.yml docker-compose.sms.yml; do
  [[ -s "$f" ]] || { echo "STOP=MISSING_REQUIRED_SOURCE $f"; exit 3; }
done
compose config -q
OLD_CONTAINER="$(compose ps -q customer-portal)"
[[ -n "$OLD_CONTAINER" && "$(docker inspect -f '{{.State.Running}}' "$OLD_CONTAINER")" == true ]] ||
 { echo "STOP=CUSTOMER_PORTAL_NOT_RUNNING"; exit 3; }
grep -Fq 'HESAB_CUSTOMER_V9' customer_portal/Dockerfile ||
 { echo "STOP=UNREVIEWED_CUSTOMER_PORTAL_DOCKERFILE"; exit 3; }

echo "=== VERIFY AZAR MODAL AND EXISTING V2 PAYMENT ROUTE ==="
python3 - "$PAY" "$HTML" <<'PY'
import ast
from pathlib import Path
import sys
code=Path(sys.argv[1]).read_text(encoding="utf8")
page=Path(sys.argv[2]).read_text(encoding="utf8")
old='show_welcome=request.query_params.get("welcome") == "1",'
new='show_welcome=(request.query_params.get("welcome") == "1" or request.query_params.get("view") == "payments"),'
if (code.count(old),code.count(new)) not in ((1,0),(0,1)):
    raise RuntimeError("Current payment welcome condition customized; no automatic edit")
ast.parse(code)
if (page.count("تمامی اکانت‌ها تا تاریخ یکم آذر محاسبه می‌شوند.")!=1
    or page.count('id="entryModal"')!=1
    or page.count("{% if show_welcome %}")!=1):
    raise RuntimeError("Azar modal is missing or duplicated; stop")
if '@app.get("/", response_class=HTMLResponse)' not in code:
    raise RuntimeError("Original payment dashboard route unavailable")
print("SOURCE_PREFLIGHT=PASS")
print("CHANGE_SCOPE=NOTICE_VISIBILITY_ONLY")
PY

compose exec -T customer-portal python - <<'PY'
from pathlib import Path
import server
import urllib.request
source=Path("/srv/v2.py").read_text(encoding="utf8")
old='show_welcome=request.query_params.get("welcome") == "1",'
new='show_welcome=(request.query_params.get("welcome") == "1" or request.query_params.get("view") == "payments"),'
assert (source.count(old),source.count(new)) in ((1,0),(0,1))
assert callable(server.v2_home)
assert server._V2_DASH.count("تمامی اکانت‌ها تا تاریخ یکم آذر محاسبه می‌شوند.")==1
assert "entryModal" in server._V2_DASH
urllib.request.urlopen("http://127.0.0.1:8091/health",timeout=5).read()
print("RUNNING_PORTAL_PREFLIGHT=PASS")
PY

if grep -Fq 'show_welcome=(request.query_params.get("welcome") == "1" or request.query_params.get("view") == "payments"),' "$PAY"; then
  echo "SOURCE_ALREADY_PATCHED=YES"
else
  echo "SOURCE_NEEDS_SINGLE_LINE_PATCH=YES"
fi

echo "=== BACKUP CUSTOMER PORTAL AND DATABASE ==="
BACKUP="/root/hesab-azar-payment-notice-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BACKUP"
cp -a "$PAY" "$BACKUP/v2.py"
cp -a "$HTML" "$BACKUP/dashboard_v2.html"
cp -a customer_portal/Dockerfile "$BACKUP/Dockerfile"
docker inspect -f '{{.Image}}' "$OLD_CONTAINER" >"$BACKUP/portal-image-id"
compose exec -T db sh -c \
 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
 >"$BACKUP/database-before-azar-notice.dump"
[[ -s "$BACKUP/database-before-azar-notice.dump" ]] ||
 { echo "STOP=DATABASE_BACKUP_FAILED"; exit 3; }
echo "BACKUP=$BACKUP"

CHANGED=0
RECREATED=0
rollback(){
  rc=$?
  trap - ERR EXIT
  if ((rc!=0 && CHANGED));then
    echo "FAILURE=ROLLING_BACK_AZAR_NOTICE"
    cp -a "$BACKUP/v2.py" "$PAY"
    if ((RECREATED));then
      compose build customer-portal &&
        compose up -d --no-deps --no-build --force-recreate customer-portal ||
        echo "WARNING=PORTAL_ROLLBACK_RECREATE_FAILED"
    fi
    echo "BACKUP=$BACKUP"
  fi
  exit "$rc"
}
trap rollback ERR EXIT

echo "=== APPLY ONE-LINE NOTICE VISIBILITY CHANGE ==="
CHANGED=1
python3 - "$PAY" <<'PY'
import ast
import os
from pathlib import Path
import sys
import tempfile
p=Path(sys.argv[1])
code=p.read_text(encoding="utf8")
old='show_welcome=request.query_params.get("welcome") == "1",'
new='show_welcome=(request.query_params.get("welcome") == "1" or request.query_params.get("view") == "payments"),'
if code.count(old)==1 and new not in code:
    changed=code.replace(old,new,1)
elif code.count(new)==1 and old not in code:
    changed=code
else:
    raise RuntimeError("Unexpected payment notice condition")
ast.parse(changed)
fd,temp=tempfile.mkstemp(prefix=".v2-azar-",dir=str(p.parent))
try:
    os.fchmod(fd,p.stat().st_mode & 0o777)
    with os.fdopen(fd,"w",encoding="utf8") as f:
        f.write(changed)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp,p)
finally:
    if os.path.exists(temp):
        os.unlink(temp)
print("AZAR_NOTICE_ON_PAYMENT=PATCHED")
PY
python3 -m py_compile "$PAY"

echo "=== BUILD AND RECREATE ONLY CUSTOMER-PORTAL ==="
compose build customer-portal
RECREATED=1
compose up -d --no-deps --no-build --force-recreate customer-portal

echo "=== VERIFY RUNNING PORTAL ==="
READY=0
for i in $(seq 1 35);do
  if compose exec -T customer-portal python - <<'PY' >/dev/null 2>&1
import urllib.request
from pathlib import Path
import server
source=Path("/srv/v2.py").read_text(encoding="utf8")
new='show_welcome=(request.query_params.get("welcome") == "1" or request.query_params.get("view") == "payments"),'
assert source.count(new)==1
assert server._V2_DASH.count("تمامی اکانت‌ها تا تاریخ یکم آذر محاسبه می‌شوند.")==1
assert "entryModal" in server._V2_DASH
assert callable(server.v2_home)
urllib.request.urlopen("http://127.0.0.1:8091/health",timeout=4).read()
PY
  then READY=1;break;fi
  sleep 2
done
[[ "$READY" == 1 ]] || { echo "STOP=CUSTOMER_PORTAL_RUNTIME_VERIFICATION_FAILED";false; }
trap - ERR EXIT
echo "SUCCESS=AZAR_NOTICE_RESTORED_ON_PAYMENT_ENTRY"
echo "NOTICE=EXISTING_AZAR_1_TEXT_UNCHANGED"
echo "BILLING_PAYMENTS_DATABASE_LOGIC_CHANGED=NO"
echo "ADMIN_DASHBOARD_AND_MAYA_TUNNELS_CHANGED=NO"
echo "BACKUP=$BACKUP"
