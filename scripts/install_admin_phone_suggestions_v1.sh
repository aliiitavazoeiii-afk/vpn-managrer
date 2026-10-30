#!/usr/bin/env bash
# HESAB_ADMIN_PHONE_SUGGESTIONS_V1_INSTALL
# Scope: ONLY main admin app's mounted Python overlay. Existing add-user POST unchanged.
set -Eeuo pipefail
umask 077

[[ "$(id -u)" == 0 ]] || { echo "STOP: root required"; exit 2; }
SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="/opt/vpn-control-center"
PATCH="$SOURCE/patches/admin_phone_suggestions_v1.py"
[[ -s "$PATCH" ]] || { echo "STOP: source patch missing"; exit 3; }
cd "$ROOT"

compose() { docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
LIVE="patches/sms_native_v2.py"
[[ -s "$LIVE" && -s docker-compose.sms.yml && -s .env ]] || {
  echo "STOP: production admin overlay/compose not present"; exit 3;
}
grep -Fq 'sms_native_v2.py' docker-compose.sms.yml || {
  echo "STOP: mounted admin overlay is not configured"; exit 3;
}
grep -Fq '# HESAB_OPERATOR_WORKSPACE_V5' "$LIVE" || {
  echo "STOP: V5 admin workspace not present; refusing overlay"; exit 3;
}
if grep -Fq '# HESAB_ADMIN_PHONE_SUGGESTIONS_V1' "$LIVE"; then
  echo "ALREADY_INSTALLED: admin phone suggestions marker present"; exit 0;
fi
python3 -m py_compile "$PATCH"
compose config -q

OLD="$(compose ps -q app)"
[[ -n "$OLD" ]] && [[ "$(docker inspect -f '{{.State.Running}}' "$OLD")" == true ]] || {
  echo "STOP: production admin app is not running"; exit 3;
}

echo "=== PREFLIGHT EXISTING ADMIN FORMS (READ ONLY) ==="
compose exec -T app python - <<'PY'
from app.main import app,TEMPLATES
assert any(r.path=="/add-user" and "GET" in r.methods for r in app.routes)
assert any(r.path=="/debts" and "GET" in r.methods for r in app.routes)
assert any(r.path=="/manage/users/add" and "POST" in r.methods for r in app.routes)
assert "_op_add_user_page" in __import__("app.main",fromlist=["_op_add_user_page"]).__dict__
for name in ("add_user_page.html","debts.html"):
    html=TEMPLATES.get(name,"")
    assert 'name="display_name"' in html,(name,"name missing")
    assert 'name="phone"' in html,(name,"phone missing")
    assert "aps-directory" not in html,(name,"already patched")
print("ADMIN_REGISTRATION_FORMS_PRESENT_AND_UNMODIFIED")
PY

BACKUP="/root/hesab-admin-phone-suggest-v1-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$BACKUP"
cp -a "$LIVE" "$BACKUP/sms_native_v2.py"
docker inspect -f '{{.Image}}' "$OLD" > "$BACKUP/admin-image-before.txt"
echo "BACKUP=$BACKUP"

MODIFIED=0
revert_if_needed() {
  local rc=$?
  trap - EXIT
  if (( rc != 0 )) && (( MODIFIED == 1 )); then
    echo "ERROR: restoring original mounted admin overlay"
    cp -a "$BACKUP/sms_native_v2.py" "$LIVE"
    compose up -d --no-deps --no-build --force-recreate app || \
      echo "ROLLBACK RECREATE FAILED; inspect backup: $BACKUP"
  fi
  exit "$rc"
}
trap revert_if_needed EXIT

# The SMS native overlay is mounted read-only inside 'app' and appended LAST
# to /app/app/main.py at container start; append our read-only UI logic LAST.
printf '\n\n' >> "$LIVE"
cat "$PATCH" >> "$LIVE"
MODIFIED=1
python3 -m py_compile "$LIVE"

echo "RECREATE: main admin app ONLY, no image build and no DB changes"
compose up -d --no-deps --no-build --force-recreate app
NEW="$(compose ps -q app)"
[[ -n "$NEW" ]] || { echo "STOP: no new app container"; false; }

READY=0
for i in $(seq 1 35); do
  if compose exec -T app python - <<'PY' >/dev/null 2>&1
from app.main import app,env,TEMPLATES,admin_phone_suggestion_directory
assert callable(admin_phone_suggestion_directory)
for name in ("add_user_page.html","debts.html"):
    html=TEMPLATES[name]
    assert html.count("aps-directory")==1,(name,"widget missing or duplicated")
    assert 'name="display_name"' in html and 'name="phone"' in html
assert any(r.path=="/manage/users/add" and "POST" in r.methods for r in app.routes)
assert any(r.path=="/add-user" and "GET" in r.methods for r in app.routes)
assert any(r.path=="/debts" and "GET" in r.methods for r in app.routes)
assert "admin_phone_suggestion_directory" in env.globals
PY
  then READY=1;break;fi
  sleep 2
done
[[ "$READY" == 1 ]] || { echo "STOP: suggestions not live after admin restart"; false; }

echo "=== CHECK READ ONLY SUGGESTIONS ==="
compose exec -T app python - <<'PY'
from app.main import admin_phone_suggestion_directory
groups=admin_phone_suggestion_directory()
assert isinstance(groups,list)
for g in groups:
    assert len(g["phone"])==11 and g["phone"].startswith("09")
    assert isinstance(g["names"],list) and g["names"]
print("READ_ONLY_SUGGESTIONS_OK groups="+str(len(groups)))
PY

trap - EXIT
echo "SUCCESS: OPTIONAL ADMIN PHONE SUGGESTIONS V1 INSTALLED"
echo "BACKUP=$BACKUP"
echo "No subscriptions/payments/SMS/other Docker services modified."
