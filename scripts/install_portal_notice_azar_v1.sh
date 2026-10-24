#!/usr/bin/env bash
# HESAB_PORTAL_NOTICE_AZAR_V1
# Change ONLY customer portal welcome announcement text. No billing changes.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo "STOP: sudo/root required";exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
TEMPLATE=customer_portal/dashboard_v2.html
test -s "$TEMPLATE"
test -s "$SRC/$TEMPLATE"
c config -q

echo "=== PREFLIGHT: VERIFY EXACT ANNOUNCEMENT IN SOURCE AND PRODUCTION ==="
python3 - "$TEMPLATE" "$SRC/$TEMPLATE" <<'PY'
from pathlib import Path
import sys
old="تمامی اکانت‌ها تا تاریخ یکم آبان محاسبه می‌شوند."
new="تمامی اکانت‌ها تا تاریخ یکم آذر محاسبه می‌شوند."
prod=Path(sys.argv[1]).read_text(encoding="utf-8")
src=Path(sys.argv[2]).read_text(encoding="utf-8")
assert src.count(new)==1 and old not in src,"STOP: GitHub source notice is not updated"
assert (prod.count(old),prod.count(new)) in ((1,0),(0,1)),"STOP: Production notice was customized or duplicated"
assert "از این پس سررسید اکانت شما یکم هر ماه خواهد بود." in prod,"STOP: Unexpected notice template"
print("PREFLIGHT_SUCCESS: announcement can be safely updated without overwriting layout")
PY

if grep -Fq "تمامی اکانت‌ها تا تاریخ یکم آذر محاسبه می‌شوند." "$TEMPLATE";then
  echo "ALREADY_UPDATED: production template already shows Azar"
else
  BACKUP="/opt/hesab-backups/portal-notice-azar-$(date +%Y%m%d-%H%M%S)-$$"
  mkdir -p "$BACKUP/customer_portal"
  cp -a "$TEMPLATE" "$BACKUP/$TEMPLATE"
  echo "BACKUP=$BACKUP"
  changed=0
  rollback(){
    trap - ERR
    if [[ "$changed" == 1 ]];then
      echo "ROLLBACK: restoring prior customer-portal template"
      cp -a "$BACKUP/$TEMPLATE" "$TEMPLATE"
      c build customer-portal || true
      c up -d --no-deps --no-build --force-recreate customer-portal || true
    fi
    echo "Backup: $BACKUP"
    exit 1
  }
  trap rollback ERR
  changed=1
  python3 - "$TEMPLATE" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
a=p.read_text(encoding="utf-8")
old="تمامی اکانت‌ها تا تاریخ یکم آبان محاسبه می‌شوند."
new="تمامی اکانت‌ها تا تاریخ یکم آذر محاسبه می‌شوند."
assert a.count(old)==1 and new not in a
p.write_text(a.replace(old,new,1),encoding="utf-8")
print("PATCHED: one welcome announcement text")
PY
  echo "=== BUILD AND RECREATE CUSTOMER-PORTAL ONLY ==="
  c build customer-portal
  c up -d --no-deps --no-build --force-recreate customer-portal
fi
echo "=== VERIFY LIVE SERVICE, TEMPLATE AND LOADED CONTENT ==="
ready=0
for attempt in $(seq 1 30);do
  if c exec -T customer-portal python - <<'PY' >/dev/null 2>&1
from pathlib import Path
import urllib.request
old="تمامی اکانت‌ها تا تاریخ یکم آبان محاسبه می‌شوند."
new="تمامی اکانت‌ها تا تاریخ یکم آذر محاسبه می‌شوند."
page=Path("/srv/dashboard_v2.html").read_text(encoding="utf-8")
assert page.count(new)==1 and old not in page
import server
assert server._V2_DASH.count(new)==1 and old not in server._V2_DASH
urllib.request.urlopen("http://127.0.0.1:8091/health",timeout=3).read()
PY
  then ready=1;break;fi
  sleep 2
done
if [[ "$ready" != 1 ]];then
  echo "STOP: Live customer portal announcement not confirmed"
  false
fi
trap - ERR
echo "SUCCESS: customer welcome message now says first of Azar (یکم آذر)."
echo "Only customer-portal was recreated. Accounting, Maya XUI and Hesab app untouched."
