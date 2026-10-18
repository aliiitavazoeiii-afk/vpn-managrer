#!/usr/bin/env bash
# HESAB_WAITING_EXPIRY_SMS_V2_INSTALL
# Upgrade waiting-payment SMS text ONLY. Existing V4 manual Android queue unchanged.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == "0" ]] || { echo 'STOP: run as root (sudo)'; exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
c() { docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for p in .env docker-compose.yml docker-compose.sms.yml sms_gateway/server.py patches/sms_native_v2.py; do
  [[ -s "$p" ]] || { echo "STOP: missing production $p"; exit 3; }
done
test -s "$SRC/patches/waiting_expiry_sms_v2.py"
c config -q
python3 -m py_compile "$SRC/patches/waiting_expiry_sms_v2.py"
if grep -Fq '# HESAB_WAITING_EXPIRY_SMS_V2' patches/sms_native_v2.py; then
  echo 'ALREADY_INSTALLED: waiting expiry message V2 is present'; exit 0
fi

# Respect previous deployments: if the waiting action has not yet been added,
# safely install its existing prerequisite (also installs V4 if necessary).
if ! grep -Fq '# HESAB_WAITING_RENEWAL_SMS_V1' patches/sms_native_v2.py; then
  echo 'Installing missing waiting-header SMS action first...'
  bash "$SRC/scripts/install_waiting_renewal_sms.sh"
fi
grep -Fq '# GOOGLE_MESSAGES_BATCH_OPEN_V4' sms_gateway/server.py || {
  echo 'STOP: V4 batch inbox is not installed'; exit 3;
}
grep -Fq '# HESAB_WAITING_RENEWAL_SMS_V1' patches/sms_native_v2.py || {
  echo 'STOP: waiting-header SMS action unavailable'; exit 3;
}
grep -Fq 'sms_native_v2.py' docker-compose.sms.yml || {
  echo 'STOP: patch is not mounted by admin service'; exit 3;
}
c exec -T app grep -Fq HESAB_WAITING_RENEWAL_SMS_V1 /app/app/main.py || {
  echo 'STOP: running admin service does not include waiting-header SMS'; exit 3;
}

python3 - "$SRC" <<'PY'
from pathlib import Path
import sys
prod=Path("patches/sms_native_v2.py").read_text()
source=(Path(sys.argv[1])/"patches/waiting_expiry_sms_v2.py").read_text()
assert source.count("# HESAB_WAITING_EXPIRY_SMS_V2")==1
assert '# HESAB_WAITING_EXPIRY_SMS_V2' not in prod
assert '# HESAB_WAITING_RENEWAL_SMS_V1' in prod
assert "data-waiting-renewal-form" in prod
assert "usersmanager.ir" in source
assert "سلام اکانت شما " in source
assert "followup_state_unchanged" in source
compile(prod.rstrip()+"\n\n"+source,"patched-main.py","exec")
# Standalone algorithm check without importing app/db.
scope={"__name__":"_test_"}
from datetime import date
start=source.index("_EWS_MONTHS = (")
end=source.index("def _ews_queue_impl(",start)
exec(source[start:end],scope)
assert scope["_ews_expiry_label"](date(2026,9,28))=="۶ مهر"
expected=("سلام اکانت شما ۶ مهر تمام شده.\n"
          "برای تمدید با شماره همراه خودتون وارد این سایت بشید و نسبت به پرداخت اقدام فرمایید.\n\n"
          "usersmanager.ir")
assert scope["_ews_message"](date(2026,9,28))==expected
print("PASS: exact sample date and SMS body")
PY

BACKUP="/opt/hesab-backups/waiting-expiry-sms-v2-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACKUP"
cp -a patches/sms_native_v2.py "$BACKUP/sms_native_v2.py"
cp -a docker-compose.sms.yml "$BACKUP/docker-compose.sms.yml"
echo 'Backing up database before admin-app restart...'
c exec -T db sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$BACKUP/db.dump"
test -s "$BACKUP/db.dump"
c exec -T db pg_restore -l < "$BACKUP/db.dump" >/dev/null

MODIFIED=0
rollback() {
  trap - ERR
  if [[ "$MODIFIED" == 1 ]]; then
    echo 'Restoring only SMS admin code; financial data unchanged.'
    cp -a "$BACKUP/sms_native_v2.py" patches/sms_native_v2.py
    c up -d --no-deps --no-build --force-recreate app || true
  fi
  echo "BACKUP=$BACKUP"
  exit 1
}
trap rollback ERR
MODIFIED=1
printf '\n\n' >> patches/sms_native_v2.py
cat "$SRC/patches/waiting_expiry_sms_v2.py" >> patches/sms_native_v2.py
python3 -m py_compile patches/sms_native_v2.py
c up -d --no-deps --no-build --force-recreate app

READY=0
for attempt in $(seq 1 35); do
  if c exec -T app python - <<'PY' >/dev/null 2>&1
from app.main import app,TEMPLATES,_ews_message
from datetime import date
paths={p:sum(p==r.path and "POST" in r.methods for r in app.routes)
       for p in ("/sms/waiting-renewal","/followups/sms-reminder")}
assert all(v==1 for v in paths.values()),paths
assert _ews_message(date(2026,9,28)).startswith("سلام اکانت شما ۶ مهر تمام شده.")
page=TEMPLATES.get("followups.html","")
assert "data-waiting-renewal-form" in page
assert "g.first_expiry|ews_message" in page
assert "تسویه کامل" in page and "برگردان همه" in page
PY
  then READY=1; break; fi
  sleep 2
done
test "$READY" -eq 1
trap - ERR
echo 'SUCCESS: waiting SMS uses customer expiry + usersmanager.ir'
echo 'No automatic SMS, payment edit, or followup-state change'
echo "BACKUP=$BACKUP"
