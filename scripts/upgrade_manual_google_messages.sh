#!/usr/bin/env bash
# HESAB_GOOGLE_MESSAGES_MANUAL_UPGRADE
# Safe upgrade for machines that already run native V2.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo 'Run as root'; exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
c() { docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
test -s "$SRC/sms_gateway/server.py"
test -s "$SRC/patches/sms_native_v2.py"
test -s sms_gateway/server.py
test -s patches/sms_native_v2.py
c config -q
grep -Fq '# NATIVE_SMS_V2_SEPARATE_QUEUE' sms_gateway/server.py
grep -Fq '# HESAB_NATIVE_SMS_V2_ADMIN' patches/sms_native_v2.py
if grep -Fq '# GOOGLE_MESSAGES_MANUAL_HANDOFF_V1' sms_gateway/server.py; then
  echo 'STOP: manual handoff already present'; exit 3
fi
c exec -T app grep -q HESAB_NATIVE_SMS_V2_ADMIN /app/app/main.py
python3 -m py_compile "$SRC/sms_gateway/server.py" "$SRC/patches/sms_native_v2.py"
BACKUP="/opt/hesab-backups/manual-handoff-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACKUP"
cp -a docker-compose.sms.yml "$BACKUP/"
cp -a sms_gateway/server.py "$BACKUP/"
cp -a patches/sms_native_v2.py "$BACKUP/"
c exec -T db sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$BACKUP/db.dump"
test -s "$BACKUP/db.dump"
c exec -T db pg_restore -l < "$BACKUP/db.dump" >/dev/null
changed=0
rollback(){
  trap - ERR
  if [[ "$changed" == 1 ]];then
    cp -a "$BACKUP/server.py" sms_gateway/server.py
    cp -a "$BACKUP/sms_native_v2.py" patches/sms_native_v2.py
    c build sms-gateway || true
    c up -d --no-deps --no-build sms-gateway || true
    c up -d --no-deps --no-build --force-recreate app || true
  fi
  echo "Backup retained at $BACKUP"; exit 1
}
trap rollback ERR
changed=1
python3 - "$SRC" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1])
current=Path("sms_gateway/server.py")
live=current.read_text()
latest=(src/"sms_gateway/server.py").read_text()
assert latest.count("# GOOGLE_MESSAGES_MANUAL_HANDOFF_V1")==1
assert "# GOOGLE_MESSAGES_MANUAL_HANDOFF_V1" not in live
addon=latest.split("# GOOGLE_MESSAGES_MANUAL_HANDOFF_V1",1)[1]
out=live.rstrip()+"\n\n# GOOGLE_MESSAGES_MANUAL_HANDOFF_V1"+addon
compile(out,str(current),"exec")
current.write_text(out)
current_patch=Path("patches/sms_native_v2.py")
new_patch=(src/"patches/sms_native_v2.py").read_text()
assert "# HESAB_NATIVE_SMS_V2_ADMIN" in new_patch
compile(new_patch,str(current_patch),"exec")
current_patch.write_text(new_patch)
PY
c build sms-gateway
c up -d --no-deps --no-build sms-gateway
c up -d --no-deps --no-build --force-recreate app
c exec -T sms-gateway python - <<'PY'
from server import app
paths={r.path for r in app.routes}
assert "/v3/drafts/next" in paths
print("Manual drafts API OK")
PY
c exec -T app python - <<'PY'
from app.main import app
paths={r.path for r in app.routes}
assert "/sms/debt-send" in paths
print("Debt form API OK")
PY
echo "SUCCESS: manual Google Messages handoff backend prepared; no SMS sent"
echo "BACKUP=$BACKUP"
