#!/usr/bin/env bash
# HESAB_PRIVATE_NPVS_FILES_V1_INSTALLER
# Offline, additive account and customer UI. Only a dedicated DB table is added.
# No Docker build, PyPI, changes to payments, XUI, VPN or tunnels.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == "0" ]] || { echo "STOP=ROOT_REQUIRED"; exit 2; }

SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT=/opt/vpn-control-center
cd "$ROOT"
ADMIN_LIVE=patches/portal_login_report.py
PORTAL_LIVE=customer_portal/login_activity.py
ADMIN_ADDON="$SOURCE/patches/customer_private_npvs_admin_v1.py"
PORTAL_ADDON="$SOURCE/customer_portal/customer_private_npvs_v1.py"
COMPOSE=docker-compose.sms.yml
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }

for f in "$ADMIN_LIVE" "$PORTAL_LIVE" "$ADMIN_ADDON" "$PORTAL_ADDON" \
         "$COMPOSE" docker-compose.yml;do
  [[ -s "$f" ]] || { echo "STOP=MISSING_FILE $f";exit 3; }
done
grep -Fq 'PORTAL_LOGIN_REPORT_ADMIN_V1' "$ADMIN_LIVE" ||
 { echo "STOP=EXISTING_ADMIN_LOGIN_REPORT_UNAVAILABLE";exit 3; }
grep -Fq 'HESAB_CUSTOMER_SERVICES_AFTER_LOGIN_ACTIVITY_V4' "$PORTAL_LIVE" ||
 { echo "STOP=EXISTING_CUSTOMER_V4_ROUTE_UNAVAILABLE";exit 3; }

ADMIN_INSTALLED=0;PORTAL_INSTALLED=0
grep -Fq 'HESAB_PRIVATE_NPVS_ADMIN_V1' "$ADMIN_LIVE" && ADMIN_INSTALLED=1
grep -Fq 'HESAB_PRIVATE_NPVS_CUSTOMER_V1' "$PORTAL_LIVE" && PORTAL_INSTALLED=1
if [[ "$ADMIN_INSTALLED" == 1 && "$PORTAL_INSTALLED" == 1 ]];then
  echo "NPVS_FILES=ALREADY_INSTALLED"
  exit 0
fi
[[ "$ADMIN_INSTALLED" == 0 && "$PORTAL_INSTALLED" == 0 ]] ||
 { echo "STOP=PARTIAL_PRIOR_INSTALL_NEEDS_MANUAL_REVIEW";exit 3; }

compose config -q
APP="$(compose ps -q app)"
PORTAL="$(compose ps -q customer-portal)"
for cid in "$APP" "$PORTAL"; do
  [[ -n "$cid" && "$(docker inspect -f '{{.State.Running}}' "$cid")" == "true" ]] ||
   { echo "STOP=REQUIRED_APP_NOT_RUNNING";exit 3; }
done

# Must modify only two reviewed, already-mounted additive modules.
EXPECTED_ADMIN="$ROOT/$ADMIN_LIVE"
EXPECTED_PORTAL="$ROOT/$PORTAL_LIVE"
ACTUAL_ADMIN="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/sms-patch/portal_login_report.py"}}{{.Source}}{{end}}{{end}}' "$APP")"
ACTUAL_PORTAL="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/srv/login_activity.py"}}{{.Source}}{{end}}{{end}}' "$PORTAL")"
[[ "$ACTUAL_ADMIN" == "$EXPECTED_ADMIN" && "$ACTUAL_PORTAL" == "$EXPECTED_PORTAL" ]] ||
 { echo "STOP=RUNNING_CONTAINER_MOUNT_MISMATCH";exit 3; }

echo "=== SOURCE VALIDATION AND READ-ONLY APP PREFLIGHT ==="
python3 - "$ADMIN_LIVE" "$ADMIN_ADDON" "$PORTAL_LIVE" "$PORTAL_ADDON" <<'PY'
import ast,sys
from pathlib import Path
admin,admin_addon,portal,portal_addon=[Path(s) for s in sys.argv[1:]]
for p in (admin,admin_addon,portal,portal_addon):
    ast.parse(p.read_text(encoding="utf8"),filename=str(p))
ast.parse(admin.read_text()+"\n"+admin_addon.read_text())
ast.parse(portal.read_text()+"\n"+portal_addon.read_text())
for p in (admin,portal):
    assert not p.is_symlink(),"Refusing symlink"
print("ADDITIVE_SOURCES_AND_PYTHON_SYNTAX=PASS")
PY
cat "$ADMIN_ADDON" | compose exec -T app python -c '
import sys
from app import main as m
from jinja2 import Environment
before={r.path for r in m.app.router.routes}
assert "/portal-logins" in before
assert "/customer-files" not in before
assert "base.html" in m.TEMPLATES
exec(compile(sys.stdin.read(),"<npvs-admin-preflight>","exec"),vars(m))
after={r.path for r in m.app.router.routes}
assert after-before=={
 "/customer-files","/customer-files/upload","/customer-files/delete"}
assert "private_npvs_admin.html" in m.TEMPLATES
Environment().parse(m.TEMPLATES["private_npvs_admin.html"])
print("ADMIN_PREFLIGHT=PASS")
'
cat "$PORTAL_ADDON" | compose exec -T customer-portal python -c '
import sys
import server as m
assert callable(m._v2_session_phone)
assert callable(m._sv2_landing)
before={r.path for r in m.app.router.routes}
assert "/my-file/download" not in before
exec(compile(sys.stdin.read(),"<npvs-portal-preflight>","exec"),vars(m))
assert {r.path for r in m.app.router.routes}-before=={"/my-file/download"}
assert m._SV2_HTML.count("id=\"sv-private-file\"")==1
assert m._SV2_HTML.index("id=\"sv-private-file\"")<m._SV2_HTML.index("sv-box sv-support")
print("CUSTOMER_PORTAL_PREFLIGHT=PASS")
'

echo "=== BACKUP CUSTOMER PORTAL, ADMIN AND DATABASE ==="
BACKUP="/root/hesab-npvs-files-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BACKUP"
cp -a "$ADMIN_LIVE" "$BACKUP/portal_login_report.py"
cp -a "$PORTAL_LIVE" "$BACKUP/login_activity.py"
cp -a docker-compose.yml "$COMPOSE" "$BACKUP/"
docker inspect -f '{{.Image}}' "$APP" >"$BACKUP/admin-image-id"
docker inspect -f '{{.Image}}' "$PORTAL" >"$BACKUP/customer-portal-image-id"
compose exec -T db sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  >"$BACKUP/database-before-private-files.dump"
[[ -s "$BACKUP/database-before-private-files.dump" ]] ||
 { echo "STOP=DATABASE_BACKUP_FAILED";exit 3; }
echo "BACKUP=$BACKUP"
echo "DATABASE_BACKUP=CREATED"

# Refuse reusing or overwriting any pre-existing unknown table.
EXISTING="$(compose exec -T db sh -c \
 'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT COALESCE(to_regclass('\''public.customer_private_npvs'\'')::text, '\''none'\'')"' | tr -d '\r')"
[[ "$EXISTING" == "none" ]] ||
 { echo "STOP=TABLE_ALREADY_EXISTS_REVIEW_REQUIRED";exit 3; }

CHANGED=0
rollback(){
  code=$?
  trap - EXIT
  if ((code!=0 && CHANGED));then
    echo "INSTALL_FAILED_RESTORING_ADMIN_AND_PORTAL_SOURCES"
    cp -a "$BACKUP/portal_login_report.py" "$ADMIN_LIVE"
    cp -a "$BACKUP/login_activity.py" "$PORTAL_LIVE"
    compose up -d --no-deps --no-build --force-recreate app customer-portal ||
      echo "WARNING=RECREATE_AFTER_ROLLBACK_FAILED"
    echo "BACKUP=$BACKUP"
    echo "NOTE=EMPTY_ADDITIVE_NPVS_TABLE_MAY_REMAIN"
  fi
  exit "$code"
}
trap rollback EXIT

echo "=== CREATE ONLY PRIVATE FILE STORAGE TABLE ==="
compose exec -T db sh -c \
 'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
CREATE TABLE customer_private_npvs (
  phone VARCHAR(11) PRIMARY KEY,
  filename VARCHAR(120) NOT NULL,
  content BYTEA NOT NULL,
  sha256 VARCHAR(64) NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT customer_private_npvs_phone CHECK (phone ~ '^09[0-9]{9}$'),
  CONSTRAINT customer_private_npvs_size CHECK (octet_length(content) BETWEEN 1 AND 1048576),
  CONSTRAINT customer_private_npvs_filename CHECK (filename ~* '\.npvs$'),
  CONSTRAINT customer_private_npvs_sha CHECK (sha256 ~ '^[0-9a-f]{64}$')
);
SQL

echo "=== ADD ONLY TWO PROTECTED UI MODULES ==="
CHANGED=1
printf '\n\n' >>"$ADMIN_LIVE"
cat "$ADMIN_ADDON" >>"$ADMIN_LIVE"
printf '\n\n' >>"$PORTAL_LIVE"
cat "$PORTAL_ADDON" >>"$PORTAL_LIVE"
python3 -m py_compile "$ADMIN_LIVE" "$PORTAL_LIVE"

echo "=== RECREATE ADMIN AND CUSTOMER PORTAL ONLY; NO BUILD ==="
compose up -d --no-deps --no-build --force-recreate app customer-portal

READY=0
for i in $(seq 1 35);do
 if compose exec -T app python - <<'PY' >/dev/null 2>&1
from app import main as m
assert any(r.path=="/customer-files" and "GET" in r.methods for r in m.app.router.routes)
assert any(r.path=="/customer-files/upload" and "POST" in r.methods for r in m.app.router.routes)
assert "private_npvs_admin.html" in m.TEMPLATES
PY
 then READY=1;break;fi
 sleep 2
done
[[ "$READY" == 1 ]] || { echo "STOP=ADMIN_RUNTIME_VERIFY_FAILED";false; }

READY=0
for i in $(seq 1 35);do
 if compose exec -T customer-portal python - <<'PY' >/dev/null 2>&1
import server
import urllib.request
assert any(r.path=="/my-file/download" for r in server.app.router.routes)
assert server._SV2_HTML.count('id="sv-private-file"')==1
assert server._SV2_HTML.index('id="sv-private-file"')<server._SV2_HTML.index("sv-box sv-support")
urllib.request.urlopen("http://127.0.0.1:8091/health",timeout=4).read()
PY
 then READY=1;break;fi
 sleep 2
done
[[ "$READY" == 1 ]] || { echo "STOP=CUSTOMER_RUNTIME_VERIFY_FAILED";false; }

# Test unauthorized client requests, without uploading or downloading anything.
compose exec -T app python - <<'PY'
import http.client
c=http.client.HTTPConnection("127.0.0.1",8000,timeout=5)
c.request("GET","/customer-files")
r=c.getresponse()
body=r.read(80000);status=r.status;c.close()
assert b'name="upload"' not in body and b'customer_private_npvs' not in body, \
    "SECURITY: unauthenticated admin file manager exposed"
print("ADMIN_UNAUTHENTICATED_ACCESS=BLOCKED",status)
PY
compose exec -T customer-portal python - <<'PY'
import http.client
c=http.client.HTTPConnection("127.0.0.1",8091,timeout=5)
c.request("GET","/my-file/download")
r=c.getresponse()
body=r.read(80000);status=r.status;c.close()
assert status in (302,303,307,401,403) and b'npvs' not in body.lower()
print("CUSTOMER_DOWNLOAD_WITHOUT_LOGIN=BLOCKED",status)
PY

trap - EXIT
echo "SUCCESS=PRIVATE_NPVS_FILES_INSTALLED"
echo "ADMIN_FILE_MANAGER=/customer-files"
echo "CUSTOMER_DOWNLOAD_BOX=BEFORE_SUPPORT"
echo "DOWNLOAD_ACCESS=SIGNED_PHONE_SESSION_ONLY"
echo "STORAGE=DEDICATED_POSTGRES_TABLE_1MIB_LIMIT"
echo "DOCKER_BUILD_AND_PYPI=NOT_USED"
echo "PAYMENTS_XUI_VPN_TUNNELS_CHANGED=NO"
echo "BACKUP=$BACKUP"
