#!/usr/bin/env bash
# DEBT_SMS_FAILED_MANUAL_RESEND_V1
# Explicit one-time operator retry of failed debt SMS only. No automatic SMS.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo "STOP: must run as root"; exit 2; }
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd /opt/vpn-control-center
TARGET=patches/sms_aban_default.py
SOURCE="$REPO/$TARGET"
C=(docker compose -f docker-compose.yml -f docker-compose.sms.yml)
MARK=manual-resend-20261013
echo "=== PREFLIGHT ==="
test -s "$TARGET" && test -s "$SOURCE"
grep -q 'SMS_DEBT_DEFAULT_ABAN_V1' "$TARGET"
grep -q 'SMS_DEBT_DEFAULT_ABAN_V1' docker-compose.sms.yml
if grep -q "$MARK" "$TARGET"; then
    echo "ALREADY INSTALLED: one-time failed debt SMS manual retry"
    exit 0
fi
python3 - "$SOURCE" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text(encoding="utf-8")
compile(s,sys.argv[1],"exec")
assert "manual-resend-20261013" in s
assert 'previous["status"] == "failed"' in s
assert 'if used:' in s and "previous = None" in s
assert "pg_advisory_xact_lock" in s
assert "delivered" in s and "operator_confirmed" in s
print("Patch validation PASSED")
PY
"${C[@]}" config -q
"${C[@]}" exec -T app python - <<'PY'
import urllib.request
urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=5).read()
print("Admin health PASSED")
PY
"${C[@]}" exec -T db sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM sms_jobs WHERE status=\x27failed\x27"' >/dev/null 2>&1 || true
BACKUP="/opt/hesab-backups/sms-failed-manual-resend-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
cp -a "$TARGET" "$BACKUP/sms_aban_default.py"
echo "BACKUP=$BACKUP"
rollback() {
  trap - ERR
  echo "ERROR: restoring previous SMS patch"
  cp -a "$BACKUP/sms_aban_default.py" "$TARGET"
  "${C[@]}" up -d --no-deps --no-build --force-recreate app || true
  echo "Rollback attempted. No SMS automatically queued."
  exit 1
}
trap rollback ERR
install -m 0644 "$SOURCE" "$TARGET"
echo "=== RECREATE ADMIN ONLY ==="
"${C[@]}" up -d --no-deps --no-build --force-recreate app
ready=0
for i in $(seq 1 35); do
  if "${C[@]}" exec -T app sh -lc \
    "grep -q $MARK /app/app/main.py && curl -fsS http://127.0.0.1:8000/health >/dev/null" \
    >/dev/null 2>&1; then ready=1;break; fi
  sleep 2
done
test "$ready" = 1
echo "=== CHECK CUSTOMER PORTAL STILL HEALTHY ==="
"${C[@]}" exec -T customer-portal python - <<'PY'
import urllib.request
urllib.request.urlopen("http://127.0.0.1:8091/health",timeout=6).read()
print("Portal health PASSED")
PY
trap - ERR
echo "SUCCESS: FAILED DEBT SMS ONE-TIME MANUAL RESEND ENABLED"
echo "No SMS sent by installer; no payment/billing/followup rows changed."
echo "Backup: $BACKUP"
