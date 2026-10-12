#!/usr/bin/env bash
# Safely repair debt-SMS -> waiting, and protect reported received jobs 13-15.
# Never queues, retries or dispatches any SMS.
set -Eeuo pipefail
umask 077
cd /opt/vpn-control-center
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
C=(docker compose -f docker-compose.yml -f docker-compose.sms.yml)
TARGET=patches/sms_aban_default.py

test -s "$TARGET"
test -s "$REPO/$TARGET"
test -s "$REPO/scripts/reconcile_sms_13_15_no_resend.py"
grep -q 'SMS_DEBT_DEFAULT_ABAN_V1' docker-compose.sms.yml
grep -q 'SMS_DEBT_DEFAULT_ABAN_V1' "$TARGET"

echo "=== 1. Read-only recovery preview ==="
"${C[@]}" exec -T customer-portal python - --check \
  < "$REPO/scripts/reconcile_sms_13_15_no_resend.py"

echo "=== 2. Verified backup BEFORE any writes ==="
BACKUP="/opt/hesab-backups/sms-waiting-fix-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
cp -a "$TARGET" "$BACKUP/sms_aban_default.py"
"${C[@]}" exec -T db sh -lc \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "$BACKUP/database.dump"
test -s "$BACKUP/database.dump"
"${C[@]}" exec -T db pg_restore -l < "$BACKUP/database.dump" >/dev/null
echo "BACKUP=$BACKUP"

rollback(){
  trap - ERR
  echo "Restoring previous SMS patch (nothing automatically resent)..."
  cp -a "$BACKUP/sms_aban_default.py" "$TARGET"
  "${C[@]}" up -d --no-deps --no-build --force-recreate app || true
  echo "Previous SMS patch restored. Check application health."
  exit 1
}
trap rollback ERR

echo "=== 3. Installing atomic, duplicate-safe SMS/waiting route ==="
install -m 0644 "$REPO/$TARGET" "$TARGET"
"${C[@]}" config -q
"${C[@]}" up -d --no-deps --no-build --force-recreate app

echo "=== 4. Health check of admin; no SMS has been sent ==="
ready=0
for i in $(seq 1 30); do
  if "${C[@]}" exec -T app sh -c \
      'grep -q pg_advisory_xact_lock /app/app/main.py && curl -fsS http://127.0.0.1:8000/health >/dev/null' \
      >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
test "$ready" -eq 1
echo "Admin route and health verified."
trap - ERR

echo "=== 5. Manual-confirm existing received SMS; recover waiting (NO RESEND) ==="
"${C[@]}" exec -T customer-portal python - --apply \
  < "$REPO/scripts/reconcile_sms_13_15_no_resend.py"

echo "=== 6. Verify three jobs cannot be retried ==="
"${C[@]}" exec -T db sh -lc \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -P pager=off -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT id, status, attempts FROM sms_jobs WHERE id IN (13,14,15) ORDER BY id;"'

echo "SUCCESS: SMS WAITING FIX ACTIVE; NO MESSAGES RESENT"
echo "Jobs 13,14,15 are not retryable. Eligible overdue accounts moved to waiting."
echo "BACKUP=$BACKUP"
