#!/usr/bin/env bash
# PORTAL_LOGIN_REPORT_INSTALL_V1
# Add login-event recording and read-only admin reporting with existing images.
# No portal template overwrite, no customer account, payment or SMS mutation.
set -Eeuo pipefail
umask 077
cd /opt/vpn-control-center
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
C=(docker compose -f docker-compose.yml -f docker-compose.sms.yml)
COMPOSE=docker-compose.sms.yml
PORTAL_FILE=customer_portal/login_activity.py
ADMIN_FILE=patches/portal_login_report.py

test -s "$COMPOSE"
test -s "$REPO/$PORTAL_FILE"
test -s "$REPO/$ADMIN_FILE"
test -s customer_portal/server.py
test -s customer_portal/v2.py

echo "=== Verify current services BEFORE changing anything ==="
"${C[@]}" exec -T customer-portal python -c \
  'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8091/health",timeout=4).read()'
"${C[@]}" exec -T app python -c \
  'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=4).read()'

if grep -q 'PORTAL_LOGIN_REPORT_INSTALL_V1' "$COMPOSE"; then
    echo "ALREADY INSTALLED: Login activity report"
    exit 0
fi

echo "=== Preflight Python syntax and Jinja report template ==="
python3 - "$REPO" <<'PY'
from pathlib import Path
import ast,sys
root=Path(sys.argv[1])
portal=(root/"customer_portal/login_activity.py").read_text(encoding="utf8")
admin=(root/"patches/portal_login_report.py").read_text(encoding="utf8")
compile(portal,"customer_portal/login_activity.py","exec")
mod=ast.parse(admin)
compile(admin,"patches/portal_login_report.py","exec")
assert "PORTAL_LOGIN_ACTIVITY_V1" in portal
assert "PORTAL_LOGIN_REPORT_ADMIN_V1" in admin
assert "customer_portal_login_events" in portal and "customer_portal_login_events" in admin
assert "v2_login" in portal and '_pla_original_login(phone=phone)' in portal
assert "INSERT INTO customer_portal_login_events" in portal
assert "UPDATE subscriptions" not in portal and "sms_jobs" not in portal
assert "UPDATE subscriptions" not in admin and "DELETE FROM" not in admin
assert any(isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="_PLA_ADMIN_TEMPLATE" for t in n.targets) for n in mod.body)
print("Python syntax / read-only admin checks passed")
PY

"${C[@]}" exec -T app python -c '
import ast,sys
from jinja2 import Environment
t=ast.parse(sys.stdin.read())
found=[n.value.value for n in t.body if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=="_PLA_ADMIN_TEMPLATE" for x in n.targets)]
assert len(found)==1
Environment(autoescape=True).parse(found[0])
print("Jinja template parse PASSED")
' < "$REPO/$ADMIN_FILE"

echo "=== Back up configuration and verify database backup ==="
BACKUP="/opt/hesab-backups/portal-login-report-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
cp -p "$COMPOSE" "$BACKUP/docker-compose.sms.yml"
for p in "$PORTAL_FILE" "$ADMIN_FILE"; do
    if test -e "$p"; then
        mkdir -p "$BACKUP/$(dirname "$p")"
        cp -p "$p" "$BACKUP/$p"
    fi
done
"${C[@]}" exec -T db sh -lc \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  > "$BACKUP/pre-install.dump"
test -s "$BACKUP/pre-install.dump"
"${C[@]}" exec -T db pg_restore -l < "$BACKUP/pre-install.dump" >/dev/null
echo "BACKUP=$BACKUP"

rollback(){
    trap - ERR
    echo "ERROR: restoring previous compose and activity files"
    cp -p "$BACKUP/docker-compose.sms.yml" "$COMPOSE"
    for p in "$PORTAL_FILE" "$ADMIN_FILE"; do
        if test -f "$BACKUP/$p"; then
            cp -p "$BACKUP/$p" "$p"
        else
            rm -f "$p"
        fi
    done
    "${C[@]}" up -d --no-deps --no-build --force-recreate customer-portal app || true
    echo "Rollback attempted. Additive audit table (if created) was not deleted."
    exit 1
}
trap rollback ERR

echo "=== Install mount-only modules, preserving current UI and all billing patches ==="
python3 - "$REPO" <<'PY'
from pathlib import Path
import sys,re
repo=Path(sys.argv[1])
compose=Path("docker-compose.sms.yml")
source=compose.read_text(encoding="utf8")
assert "PORTAL_LOGIN_REPORT_INSTALL_V1" not in source
admin_mount="      - ./patches/sms_admin.py:/sms-patch/sms_admin.py:ro\n"
portal_mount="      - ./customer_portal/logo.png:/srv/logo.png:ro\n"
app_compile="        python -m py_compile /app/app/main.py\n"
assert source.count(admin_mount)==1, "Unexpected admin patch mounts"
assert source.count(portal_mount)==1, "Unexpected portal volumes"
assert source.count(app_compile)==1, "Unexpected admin runtime"
assert source.count("\n  customer-portal:\n")==1
portal_part=source.split("\n  customer-portal:\n",1)[1]
assert not re.search(r"\n  [a-z][a-z0-9_-]*:\s*\n",portal_part), "Portal is not final service"
assert not re.search(r"^    (command|entrypoint):",portal_part,re.M), "Portal command customized; refuse overwrite"
assert "/srv/login_activity.py" not in source
source=source.replace(admin_mount, admin_mount+
  "      - ./patches/portal_login_report.py:/sms-patch/portal_login_report.py:ro\n",1)
source=source.replace(app_compile,
  "        if ! grep -q 'PORTAL_LOGIN_REPORT_ADMIN_V1' /app/app/main.py; then\n"
  "          cat /sms-patch/portal_login_report.py >> /app/app/main.py\n"
  "        fi\n"+app_compile,1)
source=source.replace(portal_mount,portal_mount+
  "      - ./customer_portal/login_activity.py:/srv/login_activity.py:ro\n",1)
source=source.rstrip()+"\n"+"""    # PORTAL_LOGIN_REPORT_INSTALL_V1
    command:
      - /bin/sh
      - -lc
      - |
        if ! grep -q 'PORTAL_LOGIN_ACTIVITY_V1' /srv/server.py; then
          cat /srv/login_activity.py >> /srv/server.py
        fi
        python -m py_compile /srv/server.py
        exec uvicorn server:app --host 0.0.0.0 --port 8091 --proxy-headers --forwarded-allow-ips=*
"""
Path("patches/portal_login_report.py").write_text((repo/"patches/portal_login_report.py").read_text(encoding="utf8"),encoding="utf8")
Path("customer_portal/login_activity.py").write_text((repo/"customer_portal/login_activity.py").read_text(encoding="utf8"),encoding="utf8")
compose.write_text(source,encoding="utf8")
print("Preserved existing compose options and services.")
PY

"${C[@]}" config -q

echo "=== Start portal logger first, then reporting dashboard ==="
"${C[@]}" up -d --no-deps --no-build --force-recreate customer-portal
ok=0
for i in $(seq 1 35); do
    if "${C[@]}" exec -T customer-portal python -c \
      'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8091/health",timeout=3).read()' \
      >/dev/null 2>&1; then ok=1;break;fi
    sleep 2
done
test "$ok" -eq 1
"${C[@]}" exec -T customer-portal grep -q PORTAL_LOGIN_ACTIVITY_V1 /srv/server.py

# The portal startup creates the table without touching any existing row.
"${C[@]}" exec -T db sh -lc \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='''public''' AND table_name='''customer_portal_login_events'''"' \
  | grep -qx 1

"${C[@]}" up -d --no-deps --no-build --force-recreate app
ok=0
for i in $(seq 1 35); do
    if "${C[@]}" exec -T app python -c \
      'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=3).read()' \
      >/dev/null 2>&1; then ok=1;break;fi
    sleep 2
done
test "$ok" -eq 1
"${C[@]}" exec -T app grep -q PORTAL_LOGIN_REPORT_ADMIN_V1 /app/app/main.py

echo "=== Verify report is NOT visible without admin login ==="
"${C[@]}" exec -T app python - <<'PY'
import http.client
conn=http.client.HTTPConnection("127.0.0.1",8000,timeout=5)
conn.request("GET","/portal-logins")
response=conn.getresponse()
body=response.read()
conn.close()
# Refuse to expose account/phone report without a valid admin session.
assert not (response.status==200 and b'class="pla-table"' in body), (
    "SECURITY: unauthenticated customer login table visible!"
)
print("Unauthenticated report check passed, HTTP",response.status)
PY

trap - ERR
echo "SUCCESS: CUSTOMER PORTAL LOGIN REPORT ACTIVE"
echo "Admin: /portal-logins | Recording starts NOW; no historic logins fabricated"
echo "No SMS sent; no subscription, billing or payment changes."
echo "BACKUP=$BACKUP"
