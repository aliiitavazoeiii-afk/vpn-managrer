#!/usr/bin/env bash
# HESAB_SENT_SMS_CONFIRMATION_V1
# Safely install sent-SMS verification; never replay legacy queues.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo "STOP: root required"; exit 2; }
SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
c() { docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for p in .env docker-compose.yml docker-compose.sms.yml sms_gateway/server.py patches/sms_native_v2.py; do
  test -s "$p" || { echo "STOP: missing $p"; exit 3; }
done
c config -q
python3 -m py_compile "$SOURCE/sms_gateway/server.py" "$SOURCE/patches/sms_native_v2.py"
grep -Fq '# NATIVE_SMS_V2_SEPARATE_QUEUE' sms_gateway/server.py || { echo "STOP: V2 not installed"; exit 3; }
grep -Fq '# HESAB_NATIVE_SMS_V2_ADMIN' patches/sms_native_v2.py || { echo "STOP: V2 admin missing"; exit 3; }
grep -Fq 'sms_native_v2.py' docker-compose.sms.yml || { echo "STOP: V2 mount absent"; exit 3; }
c exec -T app grep -q HESAB_NATIVE_SMS_V2_ADMIN /app/app/main.py || { echo "STOP: running V2 admin absent"; exit 3; }
python3 - "$SOURCE" <<'PY'
from pathlib import Path
import sys
prod=Path("sms_gateway/server.py").read_text()
src=(Path(sys.argv[1])/"sms_gateway/server.py").read_text()
assert "# NATIVE_SMS_V2_SEPARATE_QUEUE" in prod
assert prod.count("# GOOGLE_MESSAGES_SENT_FOLDER_V1")==0,"Already installed"
assert src.count("# GOOGLE_MESSAGES_MANUAL_HANDOFF_V1")==1
assert src.count("# GOOGLE_MESSAGES_SENT_FOLDER_V1")==1
if "# GOOGLE_MESSAGES_MANUAL_HANDOFF_V1" in prod:
  assert "/v3/drafts/next" in prod and "/v3/drafts/{job_id}/opened" in prod
print("PASS: compatible backend")
PY
BACKUP="/opt/hesab-backups/sent-folder-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACKUP"
cp -a sms_gateway/server.py "$BACKUP/server.py"
cp -a patches/sms_native_v2.py "$BACKUP/sms_native_v2.py"
cp -a docker-compose.sms.yml "$BACKUP/docker-compose.sms.yml"
echo "Creating PostgreSQL backup..."
c exec -T db sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$BACKUP/db.dump"
test -s "$BACKUP/db.dump"
c exec -T db pg_restore -l < "$BACKUP/db.dump" >/dev/null
CHANGED=0
rollback() {
  trap - ERR
  if [[ "$CHANGED" == 1 ]]; then
    echo "ERROR: restoring SMS backend files, not DB rows"
    cp -a "$BACKUP/server.py" sms_gateway/server.py
    cp -a "$BACKUP/sms_native_v2.py" patches/sms_native_v2.py
    c build sms-gateway || true
    c up -d --no-deps --no-build sms-gateway || true
    c up -d --no-deps --no-build --force-recreate app || true
  fi
  echo "Backup: $BACKUP"
  exit 1
}
trap rollback ERR
CHANGED=1
python3 - "$SOURCE" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1])
backend=Path("sms_gateway/server.py")
old=backend.read_text()
new=(src/"sms_gateway/server.py").read_text()
v3="# GOOGLE_MESSAGES_MANUAL_HANDOFF_V1"
sent="# GOOGLE_MESSAGES_SENT_FOLDER_V1"
if v3 in old:
  combined=old.rstrip()+"\n\n"+sent+new.split(sent,1)[1]
else:
  combined=old.rstrip()+"\n\n"+v3+new.split(v3,1)[1]
assert combined.count(sent)==1 and combined.count(v3)==1
compile(combined,str(backend),"exec")
backend.write_text(combined)
patch=Path("patches/sms_native_v2.py")
source=(src/"patches/sms_native_v2.py").read_text()
compile(source,str(patch),"exec")
patch.write_text(source)
PY
echo "Updating SMS API + admin application only..."
c build sms-gateway
c up -d --no-deps --no-build sms-gateway
c up -d --no-deps --no-build --force-recreate app
ok=0
for i in $(seq 1 35); do
  if c exec -T sms-gateway python - <<'PY' >/dev/null 2>&1
from server import app
paths={r.path for r in app.routes}
assert "/v3/drafts/next" in paths
assert "/v3/drafts/{job_id}/verified-sent" in paths
assert "/v3/drafts/{job_id}/cancel" in paths
PY
  then ok=1; break; fi
  sleep 2
done
test "$ok" == 1
ok=0
for i in $(seq 1 35); do
  if c exec -T app sh -lc 'grep -q HESAB_NATIVE_SMS_V2_ADMIN /app/app/main.py' >/dev/null 2>&1; then
    ok=1; break
  fi
  sleep 2
done
test "$ok" == 1
trap - ERR
echo "SUCCESS: only new sent-folder confirmations can mark debt followup waiting"
echo "No SMS sent and no financial/customer rows modified during install"
echo "BACKUP=$BACKUP"
