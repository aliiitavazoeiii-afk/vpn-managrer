#!/usr/bin/env bash
# HESAB_PROFILE_PURGE_BY_ID_V2_INSTALL
# Adds safe explicit ID-scoped purge flow to the already running V1 profile.
# Installs CODE ONLY. Does not delete a user, payment or send SMS during install.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP=ROOT_REQUIRED"; exit 2; }
SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT=/opt/vpn-control-center
FILE=patches/profile_hard_delete_v1.py
ADD=patches/profile_purge_by_id_v2.py
cd "$ROOT"
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for name in .env docker-compose.yml docker-compose.sms.yml "$FILE" "$SOURCE/$ADD";do
  [[ -s "$name" ]] || { echo "STOP=MISSING_FILE $name";exit 3; }
done
grep -Fq '# HESAB_PROFILE_HARD_DELETE_GUARDED_V1' "$FILE" || {
  echo "STOP=V1_PROFILE_DELETE_NOT_PRESENT";exit 3;
}
grep -Fq 'profile_hard_delete_v1.py:/sms-patch/profile_hard_delete_v1.py:ro' \
    docker-compose.sms.yml || {
  echo "STOP=V1_RUNTIME_MOUNT_NOT_FOUND";exit 3;
}
grep -Fq 'cat /sms-patch/profile_hard_delete_v1.py >> /app/app/main.py' \
    docker-compose.sms.yml || {
  echo "STOP=V1_RUNTIME_LOADER_NOT_FOUND";exit 3;
}
compose config -q
compose exec -T app python3 -c \
'from app.main import app,TEMPLATES; assert "hd-erase-user" in TEMPLATES["user_detail.html"]; assert any(r.path=="/users/{sid}/permanent-delete" for r in app.routes)'
python3 -m py_compile "$SOURCE/$ADD"
if grep -Fq '# HESAB_PROFILE_PURGE_BY_ID_V2' "$FILE";then
  compose exec -T app python3 -c \
'from app.main import _hp2_plan,app; assert len([r for r in app.routes if r.path=="/users/{sid}/permanent-delete" and "POST" in r.methods])==1'
  echo "ALREADY_INSTALLED=YES";exit 0
fi

STAGED="$(mktemp /root/hesab-profile-purge-v2-stage.XXXXXX)"
trap 'rm -f "$STAGED"' EXIT
cp "$FILE" "$STAGED"
printf '\n\n' >> "$STAGED"
cat "$SOURCE/$ADD" >> "$STAGED"
python3 -m py_compile "$STAGED"
grep -Fq 'HESAB_PROFILE_PURGE_BY_ID_V2' "$STAGED"
grep -Fq 'app.add_api_route("/users/{sid}/permanent-delete",_hp2_execute' "$STAGED"
echo "STAGED_EXPLICIT_ID_SCOPED_PROFILE_PURGE=YES"

BACKUP="/root/hesab-profile-purge-v2-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BACKUP"
cp -a "$FILE" "$BACKUP/profile_hard_delete_v1.py"
cp -a docker-compose.sms.yml "$BACKUP/docker-compose.sms.yml"
echo "BACKUP_DIR=$BACKUP"
# Verified, pre-deployment independent PostgreSQL dump.
compose exec -T db sh -lc \
'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "$BACKUP/postgres-before-v2.dump"
test "$(wc -c < "$BACKUP/postgres-before-v2.dump")" -gt 1024
test "$(head -c 5 "$BACKUP/postgres-before-v2.dump")" = PGDMP
inside="/tmp/hesab-profile-v2-$$.dump"
compose cp "$BACKUP/postgres-before-v2.dump" "db:$inside"
compose exec -T -u 0 db pg_restore --list "$inside" > "$BACKUP/backup-index.txt"
compose exec -T -u 0 db rm -f "$inside"
grep -Fq 'TABLE' "$BACKUP/backup-index.txt"
chmod 0600 "$BACKUP/postgres-before-v2.dump"
echo "FULL_DB_BACKUP_VERIFIED=YES"

CHANGED=0
rollback(){
  code=$?
  trap - EXIT
  if ((code!=0&&CHANGED));then
    echo "ROLLBACK=RESTORE_PROFILE_V1_PATCH"
    cp -a "$BACKUP/profile_hard_delete_v1.py" "$FILE"
    compose up -d --no-deps --no-build --force-recreate app ||
      echo "WARNING=ADMIN_APP_ROLLBACK_RESTART_FAILED"
  fi
  exit "$code"
}
trap rollback EXIT
install -m 0644 "$STAGED" "$FILE"
CHANGED=1
compose up -d --no-deps --no-build --force-recreate app

READY=0
for i in $(seq 1 36);do
  if compose exec -T app python3 - <<'PY' >/dev/null 2>&1
from app.main import _hp2_plan,app,TEMPLATES
import urllib.request
assert callable(_hp2_plan)
assert "حذف دائمی این شناسه" in TEMPLATES["user_detail.html"]
routes=[r for r in app.routes if r.path=="/users/{sid}/permanent-delete"]
assert sum(1 for r in routes if "GET" in r.methods)==1
assert sum(1 for r in routes if "POST" in r.methods)==1
assert any(r.path=="/manage/users/{sid}/delete" for r in app.routes)
urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=5).read()
PY
  then READY=1;break;fi
  sleep 2
done
[[ "$READY" == 1 ]] || { echo "STOP=PROFILE_V2_RUNTIME_FAILED";false; }

# A deleted user preview MUST require a valid admin session.
compose exec -T app python3 - <<'PY'
import urllib.request, urllib.error
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*a,**kw):return None
try:
    response=urllib.request.build_opener(NoRedirect()).open(
      "http://127.0.0.1:8000/users/346/permanent-delete",timeout=8)
    status=response.status
except urllib.error.HTTPError as ex:
    status=ex.code
assert status in (301,302,303,307,308,401,403),status
print("ANONYMOUS_PROFILE_PURGE=DENIED",status)
PY

trap - EXIT
echo "SUCCESS=PROFILE_ID_SCOPED_PURGE_V2_ENABLED"
echo "INSTALL_DELETED_ANY_ACCOUNTS=NO"
echo "INSTALL_CHANGED_ANY_PAYMENTS=NO"
echo "XUI_SHAHAN_SERVERS_UNCHANGED=YES"
echo "BACKUP_DIR=$BACKUP"
