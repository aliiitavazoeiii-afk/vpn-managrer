#!/usr/bin/env bash
# HESAB_BROWSER_SMS_BRIDGE_INSTALL_V1
# App-only deployment, backup-first, NEVER resets Docker volumes or sends SMS.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo "Run as root"; exit 2; }
SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
c() { docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
test -s "$SOURCE/patches/sms_browser_bridge.py"
python3 -m py_compile "$SOURCE/patches/sms_browser_bridge.py"
c config -q

for mark in SMS_GATEWAY_PATCH_V1 SMS_DEBT_DEFAULT_ABAN_V1 DEBT_SMS_LIVE_NOJUMP_V1; do
  if ! c exec -T app grep -q "$mark" /app/app/main.py; then
    echo "STOP: production lacks $mark"; exit 3
  fi
done
if grep -q HESAB_BROWSER_SMS_BRIDGE_V1 docker-compose.sms.yml; then
  echo "Already configured; nothing changed"; exit 0
fi
backup="/opt/hesab-backups/browser-sms-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$backup"
cp -a docker-compose.sms.yml "$backup/"
if test -e patches/sms_browser_bridge.py; then
  cp -a patches/sms_browser_bridge.py "$backup/"
fi

echo "Backing up PostgreSQL before any app changes..."
c exec -T db sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup/database.dump"
test -s "$backup/database.dump"
c exec -T db pg_restore -l < "$backup/database.dump" > /dev/null

modified=0
rollback() {
  trap - ERR
  echo "ERROR: reverting only admin server change"
  if [[ "$modified" == 1 ]]; then
    cp -a "$backup/docker-compose.sms.yml" docker-compose.sms.yml
    if test -f "$backup/sms_browser_bridge.py"; then
      cp -a "$backup/sms_browser_bridge.py" patches/sms_browser_bridge.py
    else
      rm -f patches/sms_browser_bridge.py
    fi
    c up -d --no-deps --no-build --force-recreate app || true
  fi
  echo "Backup retained: $backup"
  exit 1
}
trap rollback ERR
python3 - "$SOURCE" <<'PY'
from pathlib import Path
import sys
repo = Path(sys.argv[1])
compose = Path("docker-compose.sms.yml")
target = Path("patches/sms_browser_bridge.py")
text = compose.read_text(encoding="utf-8")
anchor = "      - ./patches/sms_admin.py:/sms-patch/sms_admin.py:ro\n"
runtime = "        python -m py_compile /app/app/main.py\n"
assert text.count(anchor) == 1 and text.count(runtime) == 1, "Unexpected Compose structure"
assert "SMS_DEBT_DEFAULT_ABAN_V1" in text
assert "DEBT_SMS_LIVE_NOJUMP_V1" in text
assert "HESAB_BROWSER_SMS_BRIDGE_V1" not in text
mount = "      - ./patches/sms_browser_bridge.py:/sms-patch/sms_browser_bridge.py:ro\n"
startup = ("        if ! grep -q 'HESAB_BROWSER_SMS_BRIDGE_V1' /app/app/main.py; then\n"
           "          cat /sms-patch/sms_browser_bridge.py >> /app/app/main.py\n"
           "        fi\n")
assert mount not in text
text = text.replace(anchor, anchor + mount, 1)
text = text.replace(runtime, startup + runtime, 1)
source = (repo/"patches/sms_browser_bridge.py").read_text(encoding="utf-8")
compile(source, str(target), "exec")
target.write_text(source, encoding="utf-8")
compose.write_text(text, encoding="utf-8")
PY
modified=1
c config -q
echo "Recreating only the app service; no database or gateway restarts..."
c up -d --no-deps --no-build --force-recreate app
ready=0
for i in $(seq 1 35); do
  if c exec -T app sh -lc 'grep -q HESAB_BROWSER_SMS_BRIDGE_V1 /app/app/main.py && curl -fsS http://127.0.0.1:8000/health >/dev/null' >/dev/null 2>&1; then
    ready=1; break
  fi
  sleep 2
done
test "$ready" -eq 1
c exec -T app python - <<'PY'
from app.main import app
paths = {getattr(r,"path","") for r in app.router.routes}
assert "/sms/browser/begin" in paths
assert "/sms/browser/finish" in paths
print("Browser SMS API ready; old gateway form POSTs disabled")
PY
trap - ERR
echo "SUCCESS: HESAB BROWSER SMS RECONCILIATION DEPLOYED"
echo "No SMS sent, no gateway queue replayed, no accounting records edited"
echo "Backup: $backup"
