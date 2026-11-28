#!/usr/bin/env bash
# HESAB_PROFILE_HARD_DELETE_GUARDED_V1_INSTALL
# Enables a NEW admin-profile permanent-delete page. This installer deletes
# NO USERS, NO PAYMENTS and makes NO changes to XUI/Shahan/VPN infrastructure.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP=ROOT_REQUIRED";exit 2; }
SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT=/opt/vpn-control-center
cd "$ROOT"
COMPOSE=docker-compose.sms.yml
PATCH=patches/profile_hard_delete_v1.py
MARKER=HESAB_PROFILE_HARD_DELETE_GUARDED_V1
compose(){ docker compose -f docker-compose.yml -f "$COMPOSE" "$@"; }
for f in .env docker-compose.yml "$COMPOSE" "$SOURCE/$PATCH";do
  [[ -s "$f" ]] || { echo "STOP=MISSING $f";exit 3; }
done
python3 -m py_compile "$SOURCE/$PATCH"
compose config -q
compose exec -T app python3 -c 'from app.main import app,TEMPLATES;assert TEMPLATES.get("user_detail.html");assert TEMPLATES.get("user_status.html");assert any(r.path=="/users/{sid}" for r in app.routes)'
compose exec -T app python3 - <<'PY'
from app.main import app
assert any(r.path=="/manage/users/{sid}/delete" for r in app.routes)
assert any(r.path=="/user-status" for r in app.routes)
print("PROFILE_AND_ARCHIVE_ROUTES_PRESENT=YES")
PY
python3 - "$COMPOSE" <<'PY'
import sys
from pathlib import Path
src=Path(sys.argv[1]).read_text()
if src.count("        python -m py_compile /app/app/main.py")!=1:
    raise SystemExit("STOP=UNEXPECTED_APP_STARTUP_LAYOUT")
if src.count("      - ./patches/sms_admin.py:/sms-patch/sms_admin.py:ro")!=1:
    raise SystemExit("STOP=UNEXPECTED_APP_MOUNT_LAYOUT")
print("COMPOSE_PRECHECK=PASS")
PY
if grep -Fq "$MARKER" "$COMPOSE";then
  compose exec -T app python3 - <<'PY'
from app.main import TEMPLATES,app
assert "hd-erase-user" in TEMPLATES["user_detail.html"]
assert any(r.path=="/users/{sid}/permanent-delete" and "POST" in r.methods for r in app.routes)
print("ALREADY_INSTALLED=YES")
PY
  exit 0
fi
if [[ -e "$PATCH" ]];then
  echo "STOP=TARGET_PATCH_ALREADY_EXISTS_BUT_NOT_CONFIGURED";exit 3
fi

BACKUP="/root/hesab-hard-delete-ui-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BACKUP"
cp -a "$COMPOSE" "$BACKUP/docker-compose.sms.yml"
echo "BACKUP_DIR=$BACKUP"

# Full verified DB backup before enabling a destructive admin control.
compose exec -T db sh -lc \
'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "$BACKUP/pre-enable-postgres.dump"
test "$(wc -c < "$BACKUP/pre-enable-postgres.dump")" -gt 1024
test "$(head -c 5 "$BACKUP/pre-enable-postgres.dump")" = PGDMP
compose cp "$BACKUP/pre-enable-postgres.dump" db:/tmp/hesab-hd-v1-check-$$.dump
compose exec -T -u 0 db pg_restore --list /tmp/hesab-hd-v1-check-$$.dump > "$BACKUP/backup-list.txt"
compose exec -T -u 0 db rm -f /tmp/hesab-hd-v1-check-$$.dump
grep -Fq 'TABLE' "$BACKUP/backup-list.txt"
chmod 0600 "$BACKUP/pre-enable-postgres.dump"
echo "FULL_DB_BACKUP_VERIFIED=YES"

STAGED="$(mktemp /root/hesab-hd-compose.XXXXXX)"
trap 'rm -f "$STAGED"' EXIT
python3 - "$COMPOSE" "$STAGED" <<'PY'
import sys
from pathlib import Path
s=Path(sys.argv[1]).read_text(encoding="utf-8")
mount="      - ./patches/sms_admin.py:/sms-patch/sms_admin.py:ro\n"
startup="        python -m py_compile /app/app/main.py\n"
if s.count(mount)!=1 or s.count(startup)!=1:
    raise RuntimeError("Unexpected app compose anchors")
s=s.replace(mount,mount+"      - ./patches/profile_hard_delete_v1.py:/sms-patch/profile_hard_delete_v1.py:ro\n",1)
s=s.replace(startup,
    "        if ! grep -q 'HESAB_PROFILE_HARD_DELETE_GUARDED_V1' /app/app/main.py; then\n"
    "          cat /sms-patch/profile_hard_delete_v1.py >> /app/app/main.py\n"
    "        fi\n"+startup,1)
Path(sys.argv[2]).write_text(s,encoding="utf-8")
print("COMPOSE_ISOLATED_PATCH_STAGED=YES")
PY

CHANGED=0
rollback(){
  code=$?
  trap - EXIT
  if ((code!=0 && CHANGED));then
    echo "ROLLBACK=RESTORE_COMPOSE_AND_DISABLE_PROFILE_ACTION"
    cp -a "$BACKUP/docker-compose.sms.yml" "$COMPOSE"
    rm -f "$PATCH"
    compose up -d --no-deps --no-build --force-recreate app ||
       echo "WARNING=CHECK_APP_AFTER_ROLLBACK"
  fi
  exit "$code"
}
trap rollback EXIT
install -m 0644 "$SOURCE/$PATCH" "$PATCH"
install -m 0644 "$STAGED" "$COMPOSE"
CHANGED=1
compose config -q
echo "RESTART_ONLY_ADMIN_APP=YES"
compose up -d --no-deps --no-build --force-recreate app
READY=0
for i in $(seq 1 36);do
  if compose exec -T app python3 - <<'PY' >/dev/null 2>&1
from app.main import app,TEMPLATES
import urllib.request
assert "hd-erase-user" in TEMPLATES["user_detail.html"]
get=[r for r in app.routes if r.path=="/users/{sid}/permanent-delete"
     and "GET" in (r.methods or set())]
post=[r for r in app.routes if r.path=="/users/{sid}/permanent-delete"
      and "POST" in (r.methods or set())]
assert len(get)==1 and len(post)==1
assert any(r.path=="/manage/users/{sid}/delete" for r in app.routes)
urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=5).read()
PY
  then READY=1;break;fi
  sleep 2
done
[[ "$READY" == 1 ]] || { echo "STOP=PROFILE_RUNTIME_VERIFY_FAILED";false; }
# Unauthorized requests must NOT be served a deletion confirmation form.
compose exec -T app python3 - <<'PY'
import urllib.request,urllib.error
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None
opener=urllib.request.build_opener(NoRedirect())
try:
    response=opener.open(
        "http://127.0.0.1:8000/users/1/permanent-delete",timeout=8)
    code=response.getcode()
except urllib.error.HTTPError as error:
    code=error.code
assert code in (301,302,303,307,308,401,403), (
    "UNAUTHENTICATED_PROFILE_DELETE_ROUTE_EXPOSED",code)
print("UNAUTHENTICATED_DELETE_PROBE=BLOCKED",code)
PY
trap - EXIT
echo "SUCCESS=PROFILE_GUARDED_PERMANENT_DELETE_UI_INSTALLED"
echo "DB_USER_OR_PAYMENT_ROWS_CHANGED=NO"
echo "XUI_SHAHAN_SMS_VPN_CHANGED=NO"
echo "BACKUP_DIR=$BACKUP"
