#!/usr/bin/env bash
# HESAB_WAITING_SMS_REMINDER_V1
# Adds only the waiting-payment SMS box. Never submits SMS, modifies payments,
# or changes subscription/followup status. Uses existing V4 manual draft queue.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo "STOP: run as root"; exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
c() { docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }

for p in .env docker-compose.yml docker-compose.sms.yml patches/sms_native_v2.py sms_gateway/server.py; do
  [[ -s "$p" ]] || { echo "STOP: missing production $p"; exit 3; }
done
test -s "$SRC/patches/waiting_sms_reminder.py"
python3 -m py_compile "$SRC/patches/waiting_sms_reminder.py"
grep -Fq 'سلام وقت بخیر، اکانتتون تمدید بشه؟' "$SRC/patches/waiting_sms_reminder.py"
c config -q

if ! grep -Fq '# GOOGLE_MESSAGES_BATCH_OPEN_V4' sms_gateway/server.py; then
  echo "V4 manual queue not present. Installing existing guarded V4 first..."
  bash "$SRC/scripts/install_batch_operator_open.sh"
fi
grep -Fq '# GOOGLE_MESSAGES_BATCH_OPEN_V4' sms_gateway/server.py || {
  echo "STOP: V4 queue missing after installer"; exit 3;
}
grep -Fq 'sms_native_v2.py' docker-compose.sms.yml || {
  echo "STOP: no native V2 patch mount; no changes"; exit 3;
}
grep -Fq '# HESAB_NATIVE_SMS_V2_ADMIN' patches/sms_native_v2.py || {
  echo "STOP: native V2 patch missing; no changes"; exit 3;
}
if grep -Fq '# WAITING_SMS_REMINDER_V1' patches/sms_native_v2.py; then
  echo "ALREADY_INSTALLED: waiting SMS box exists in production patch"; exit 0
fi

echo "Checking the REAL running waiting page layout, without changing anything..."
c exec -T app python - <<'PY'
from app.main import app, TEMPLATES
page=TEMPLATES.get("followups.html","")
anchor='<div class="waiting-services" data-waiting-panel="{{ loop.index0 }}" hidden>'
assert page.count(anchor)==1, "STOP: production waiting page differs from expected template"
assert "data-waiting-sms-reminder-box" not in page, "STOP: reminder box already running"
assert sum(1 for r in app.routes if r.path=="/followups/sms-reminder")==0, "STOP: route already exists"
print("PASS: waiting-payment page allows isolated SMS box")
PY
c exec -T app grep -Fq '# HESAB_NATIVE_SMS_V2_ADMIN' /app/app/main.py || {
  echo "STOP: current admin container is not using native V2 patch"; exit 3;
}

BACKUP="/opt/hesab-backups/waiting-sms-box-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACKUP"
cp -a patches/sms_native_v2.py "$BACKUP/sms_native_v2.py"
cp -a docker-compose.sms.yml "$BACKUP/docker-compose.sms.yml"
echo "Making database backup before updating the admin app..."
c exec -T db sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$BACKUP/db.dump"
test -s "$BACKUP/db.dump"
c exec -T db pg_restore -l < "$BACKUP/db.dump" >/dev/null
CHANGED=0
rollback(){
  trap - ERR
  if [[ "$CHANGED" -eq 1 ]]; then
    echo "Restoring old admin SMS patch. Database backup retained."
    cp -a "$BACKUP/sms_native_v2.py" patches/sms_native_v2.py
    c up -d --no-deps --no-build --force-recreate app || true
  fi
  echo "BACKUP=$BACKUP"
  exit 1
}
trap rollback ERR

CHANGED=1
printf '\n\n' >> patches/sms_native_v2.py
cat "$SRC/patches/waiting_sms_reminder.py" >> patches/sms_native_v2.py
python3 -m py_compile patches/sms_native_v2.py
echo "Recreating only Hesab admin application; database, gateway, portal untouched..."
c up -d --no-deps --no-build --force-recreate app
READY=0
for i in $(seq 1 40); do
  if c exec -T app python - <<'PY' >/dev/null 2>&1
from app.main import app,TEMPLATES
assert any(r.path=="/followups/sms-reminder" and "POST" in r.methods for r in app.routes)
page=TEMPLATES.get("followups.html","")
assert "data-waiting-sms-reminder-box" in page
assert "سلام وقت بخیر، اکانتتون تمدید بشه؟" in page
PY
  then READY=1;break;fi
  sleep 2
done
test "$READY" -eq 1
trap - ERR
echo "SUCCESS: waiting-payment SMS box installed and connected to V4 manual queue."
echo "No SMS was sent; no finance or waiting-status rows were changed."
echo "BACKUP=$BACKUP"
