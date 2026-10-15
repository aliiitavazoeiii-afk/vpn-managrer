#!/usr/bin/env bash
# HESAB_BROWSER_SMS_HISTORY_BLOCK_FIX_V1
# Update only the existing backend bridge patch. No browser changes, no SMS sending.
set -Eeuo pipefail
umask 077
[[ $(id -u) == 0 ]] || { echo 'STOP: run as root'; exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)/patches/sms_browser_bridge.py"
cd /opt/vpn-control-center
TARGET=patches/sms_browser_bridge.py
COMPOSE=docker-compose.sms.yml
c() { docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
test -s "$SRC" && test -s "$TARGET" && test -s "$COMPOSE"
grep -Fq 'EXISTING_IDENTICAL_CONFIRMED_SMS' "$SRC" || { echo 'STOP: updated patch missing'; exit 3; }
grep -Fq 'EXISTING_LEGACY_SMS_CHECK_HISTORY' "$TARGET" || { echo 'STOP: live patch is different; do not overwrite'; exit 3; }
grep -Fq 'HESAB_BROWSER_SMS_BRIDGE_V1' "$TARGET"
grep -Fq 'sms_browser_bridge.py:/sms-patch/sms_browser_bridge.py:ro' "$COMPOSE"
python3 -m py_compile "$SRC"
c config -q
if ! c exec -T app sh -lc 'grep -q HESAB_BROWSER_SMS_BRIDGE_V1 /app/app/main.py && curl -fsS http://127.0.0.1:8000/health >/dev/null'; then
  echo 'STOP: live browser bridge or health missing'; exit 4
fi
BACKUP="/opt/hesab-backups/browser-sms-history-fix-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACKUP"
cp -a "$TARGET" "$BACKUP/sms_browser_bridge.py"
cp -a "$COMPOSE" "$BACKUP/docker-compose.sms.yml"
rollback() {
  trap - ERR
  echo 'ERROR: restoring prior browser SMS backend patch'
  cp -a "$BACKUP/sms_browser_bridge.py" "$TARGET"
  c up -d --no-deps --no-build --force-recreate app || true
  echo "BACKUP: $BACKUP"
  exit 1
}
trap rollback ERR
cp "$SRC" "$TARGET"
c up -d --no-deps --no-build --force-recreate app
READY=0
for i in $(seq 1 35); do
  if c exec -T app sh -lc 'grep -q EXISTING_IDENTICAL_CONFIRMED_SMS /app/app/main.py && curl -fsS http://127.0.0.1:8000/health >/dev/null' >/dev/null 2>&1; then
    READY=1; break
  fi
  sleep 2
done
test "$READY" -eq 1
trap - ERR
echo 'SUCCESS: LEGACY HISTORY BLANKET BLOCK REMOVED'
echo 'Only identical confirmed old reminders are blocked; old queued jobs were not touched.'
echo 'No SMS sent and no waiting/financial data changed by installer.'
echo "BACKUP: $BACKUP"
