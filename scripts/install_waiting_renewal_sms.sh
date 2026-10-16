#!/usr/bin/env bash
# HESAB_WAITING_RENEWAL_SMS_V1_INSTALL
# Add a fixed reminder next to waiting "تسویه کامل" and "برگرداندن همه".
# No payment/status mutation during install, no automatic SMS.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == "0" ]] || { echo 'STOP: run with sudo'; exit 2; }
SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
c() { docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
[[ -s patches/sms_native_v2.py && -s sms_gateway/server.py ]] || {
  echo 'STOP: existing native SMS V2 installation not found'; exit 3;
}
[[ -s "$SOURCE/patches/sms_native_v2.py" ]] || {
  echo 'STOP: source waiting reminder patch not found'; exit 3;
}
c config -q

# Upgrade V4 queue first, only when absent. Its installer has its own backup
# and compatibility guards; a failure stops here without touching this patch.
if ! grep -Fq '# GOOGLE_MESSAGES_BATCH_OPEN_V4' sms_gateway/server.py; then
  echo 'V4 batch inbox not detected; using its safe prerequisite installer...'
  bash "$SOURCE/scripts/install_batch_operator_open.sh"
fi
grep -Fq '# GOOGLE_MESSAGES_BATCH_OPEN_V4' sms_gateway/server.py || {
  echo 'STOP: V4 queue not available'; exit 3;
}
grep -Fq '# HESAB_NATIVE_SMS_V2_ADMIN' patches/sms_native_v2.py || {
  echo 'STOP: native SMS admin patch not installed'; exit 3;
}
grep -Fq 'sms_native_v2.py' docker-compose.sms.yml || {
  echo 'STOP: native patch mount is missing'; exit 3;
}
if grep -Fq '# HESAB_WAITING_RENEWAL_SMS_V1' patches/sms_native_v2.py; then
  echo 'STOP: reminder patch already present; inspect current installation'; exit 3;
fi
python3 - "$SOURCE" <<'PY'
from pathlib import Path
import re,sys
source=(Path(sys.argv[1])/"patches/sms_native_v2.py").read_text()
live=Path("patches/sms_native_v2.py").read_text()
marker="# HESAB_WAITING_RENEWAL_SMS_V1"
assert source.count(marker)==1
assert live.count(marker)==0
assert "# HESAB_NATIVE_SMS_V2_ADMIN" in live
assert '_NS_SCRIPT = r"""<script>' in live
assert "TEMPLATES" in live
assert '/sms/waiting-renewal' in source
assert 'سلام وقت بخیر، اکانتتون تمدید بشه؟' in source
sample='''<div class="waiting-head-pay waiting-pay-tools">
<form><button>تسویه کامل</button></form>
<details><div class="waiting-amount-input">تاریخ و مبلغ</div></details>
<form><button>برگرداندن همه</button></form>
</div>
<span class="waiting-chevron">⌄</span>'''
pattern=re.compile(r'(<div class="waiting-head-pay waiting-pay-tools">[\s\S]*?)(</div>\s*(?=<span class="waiting-chevron">))',re.S)
assert pattern.search(sample), "Cannot place SMS next to waiting group controls"
compile(live+"\n"+marker+source.split(marker,1)[1],
        "sms_native_v2.py","exec")
print("PASS: reminder patch targets the waiting group header")
PY
BACKUP="/opt/hesab-backups/waiting-renewal-sms-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACKUP"
cp -a patches/sms_native_v2.py "$BACKUP/sms_native_v2.py"
cp -a docker-compose.sms.yml "$BACKUP/docker-compose.sms.yml"
echo 'Saving pre-install PostgreSQL snapshot...'
c exec -T db sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$BACKUP/db.dump"
test -s "$BACKUP/db.dump"
c exec -T db pg_restore -l < "$BACKUP/db.dump" >/dev/null
CHANGED=0
rollback(){
  trap - ERR
  if [[ "$CHANGED" == 1 ]]; then
    echo 'ERROR: reverting only the waiting renewal code. Database remains untouched.'
    cp -a "$BACKUP/sms_native_v2.py" patches/sms_native_v2.py
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
path=Path("patches/sms_native_v2.py")
existing=path.read_text()
latest=(Path(sys.argv[1])/"patches/sms_native_v2.py").read_text()
marker="# HESAB_WAITING_RENEWAL_SMS_V1"
assert marker not in existing
updated=existing.rstrip()+"\n\n"+marker+latest.split(marker,1)[1]
compile(updated,str(path),"exec")
path.write_text(updated)
PY
c up -d --no-deps --no-build --force-recreate app
healthy=0
for i in $(seq 1 30); do
  if c exec -T app sh -lc \
    'grep -Fq HESAB_WAITING_RENEWAL_SMS_V1 /app/app/main.py && curl -fsS http://127.0.0.1:8000/health >/dev/null' >/dev/null 2>&1; then
      healthy=1;break
  fi
  sleep 2
done
[[ "$healthy" == 1 ]] || { echo 'ERROR: app not healthy with waiting reminder'; false; }
trap - ERR
echo 'SUCCESS: waiting-payment renewal SMS button installed beside group actions'
echo 'Text: سلام وقت بخیر، اکانتتون تمدید بشه؟'
echo 'No SMS was sent, no account status or payment record changed.'
echo "Backup: $BACKUP"
