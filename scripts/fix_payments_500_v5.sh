#!/usr/bin/env bash
# HESAB_PAYMENTS_500_SAFE_FIX_V5_1
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo 'STOP: run with sudo'; exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
test -s patches/sms_native_v2.py
test -s "$SRC/patches/payment_history_fix_v5.py"
c config -q
python3 -m py_compile "$SRC/patches/payment_history_fix_v5.py"
if grep -Fq '# HESAB_PAYMENTS_500_SAFE_FIX_V5_1' patches/sms_native_v2.py; then
 echo 'ALREADY_INSTALLED: payments fix present'; exit 0;
fi
grep -Fq '# HESAB_OPERATOR_WORKSPACE_V5' patches/sms_native_v2.py || {
 echo 'STOP: V5 source not found; this fix is specific to V5'; exit 3;
}
grep -Fq 'sms_native_v2.py' docker-compose.sms.yml || {
 echo 'STOP: SMS patch mount missing';exit 3;
}
BACKUP="/opt/hesab-backups/fix-payments-v5-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACKUP"
cp -a patches/sms_native_v2.py "$BACKUP/sms_native_v2.py"
# This change contains no SQL write, but preserve an administrative DB snapshot.
c exec -T db sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$BACKUP/db.dump"
test -s "$BACKUP/db.dump"
c exec -T db pg_restore -l < "$BACKUP/db.dump" >/dev/null
CHANGED=0
rollback(){
 trap - ERR
 if [[ "$CHANGED" == "1" ]]; then
    cp -a "$BACKUP/sms_native_v2.py" patches/sms_native_v2.py
    c up -d --no-deps --no-build --force-recreate app || true
 fi
 echo "BACKUP=$BACKUP";exit 1
}
trap rollback ERR
CHANGED=1
printf '\n\n' >> patches/sms_native_v2.py
cat "$SRC/patches/payment_history_fix_v5.py" >> patches/sms_native_v2.py
python3 -m py_compile patches/sms_native_v2.py
c up -d --no-deps --no-build --force-recreate app
READY=0
for i in $(seq 1 30); do
 if c exec -T app python - <<'PY' >/dev/null 2>&1
from app.main import app,TEMPLATES
from jinja2 import Environment
assert 'id="pf-days"' in TEMPLATES["payments.html"]
assert sum(r.path=="/payments" and "GET" in r.methods for r in app.routes)==1
assert any(r.path=="/payments/{pid}/undo" and "POST" in r.methods for r in app.routes)
Environment().parse(TEMPLATES["payments.html"])
PY
 then READY=1;break;fi
 sleep 2
done
test "$READY" == 1
trap - ERR
echo 'SUCCESS: payments V5 page repaired using original undo-safe records.'
echo 'No payments, billing rows, or subscriptions changed.'
echo "BACKUP=$BACKUP"
