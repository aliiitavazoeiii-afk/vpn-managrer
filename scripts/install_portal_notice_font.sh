#!/usr/bin/env bash
# UI-only rollout: exact Azar announcement text + Estedad renewal heading.
# Preserve production billing files and existing performance optimizations.
set -Eeuo pipefail
umask 077
cd /opt/vpn-control-center
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
C=(docker compose -f docker-compose.yml -f docker-compose.sms.yml)
HTML=customer_portal/dashboard_v2.html
CSS=customer_portal/v2_polish.css
for p in "$HTML" "$CSS"; do test -s "$p" || { echo "STOP missing $p"; exit 2; }; done
test -s "$REPO/customer_portal/dashboard_v2.html"
test -s "$REPO/customer_portal/v2_polish.css"
if grep -q 'PORTAL_NOTICE_RENEW_TYPOGRAPHY_V2' "$CSS" && grep -q '<h2>اطلاعیه مهم</h2>' "$HTML"; then
 echo "ALREADY INSTALLED: notice and heading font"; exit 0
fi

BACKUP="/opt/hesab-backups/portal-notice-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP/customer_portal"
cp -a "$HTML" "$BACKUP/$HTML"
cp -a "$CSS" "$BACKUP/$CSS"
echo "BACKUP=$BACKUP"

restore(){
 trap - ERR
 echo "RESTORING previous portal UI..."
 cp -a "$BACKUP/$HTML" "$HTML"
 cp -a "$BACKUP/$CSS" "$CSS"
 "${C[@]}" build customer-portal || true
 "${C[@]}" up -d --no-deps --no-build --force-recreate customer-portal || true
 echo "Rollback attempted; inspect portal health."
 exit 1
}
trap restore ERR

python3 - "$REPO" <<'PY'
from pathlib import Path
import re
import sys
repo=Path(sys.argv[1])
p=Path("customer_portal/dashboard_v2.html")
css=Path("customer_portal/v2_polish.css")
h=p.read_text(encoding="utf8")
s=css.read_text(encoding="utf8")
block=re.compile(r'<div class="entry-modal-icon">!</div>\s*<div class="entry-modal-kicker">اطلاعیه مهم</div>\s*<h2>.*?</h2>\s*<p>.*?</p>',re.S)
replacement=('<h2>اطلاعیه مهم</h2>\n    '
'<p>تمامی اکانت‌ها تا تاریخ یکم آذر محاسبه می‌شوند.</p>\n    '
'<p>از این پس سررسید اکانت شما یکم هر ماه خواهد بود.</p>')
if '<h2>اطلاعیه مهم</h2>' not in h:
    h,n=block.subn(replacement,h,count=1)
    if n != 1:
        raise RuntimeError("Announcement block changed; refusing to touch template")
else:
    expected = (
      '<h2>اطلاعیه مهم</h2>\n    '
      '<p>تمامی اکانت‌ها تا تاریخ یکم آذر محاسبه می‌شوند.</p>\n    '
      '<p>از این پس سررسید اکانت شما یکم هر ماه خواهد بود.</p>'
    )
    if expected not in h:
        raise RuntimeError("Existing notice differs; refusing to overwrite custom text")

fontlink='<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Estedad:wght@500;600;700;800&display=swap">'
if fontlink not in h:
    anchor='<link rel="stylesheet" href="/assets/v2.css">'
    if h.count(anchor)!=1: raise RuntimeError("CSS anchor changed")
    h=h.replace(anchor,fontlink+'\n'+anchor,1)
h,count=re.subn(r'/assets/v2_polish\.css(?:\?v=[^"]*)?', '/assets/v2_polish.css?v=notice-renew-2', h)
if count != 1: raise RuntimeError("CSS link not found exactly once")

marker='/* PORTAL_NOTICE_RENEW_TYPOGRAPHY_V2 */'
if marker not in s:
    source=(repo/"customer_portal/v2_polish.css").read_text(encoding="utf8")
    pos=source.find(marker)
    if pos<0: raise RuntimeError("Typography CSS missing in source")
    s+='\n'+source[pos:]+'\n'
p.write_text(h,encoding="utf8")
css.write_text(s,encoding="utf8")
print("Announcement + headline typography patched. Existing CSS preserved.")
PY

"${C[@]}" build customer-portal
"${C[@]}" up -d --no-deps --no-build --force-recreate customer-portal
for n in $(seq 1 30); do
 if "${C[@]}" exec -T customer-portal python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8091/health",timeout=3).read()' >/dev/null 2>&1; then
   "${C[@]}" exec -T customer-portal python -c 'from pathlib import Path; p=Path("/srv/dashboard_v2.html").read_text(); c=Path("/srv/v2_polish.css").read_text(); assert "<h2>اطلاعیه مهم</h2>" in p; assert "تمامی اکانت‌ها تا تاریخ یکم آذر محاسبه می‌شوند." in p; assert "از این پس سررسید اکانت شما یکم هر ماه خواهد بود." in p; assert "PORTAL_NOTICE_RENEW_TYPOGRAPHY_V2" in c; print("NOTICE & FONT VERIFIED")'
   trap - ERR
   echo "SUCCESS: PORTAL NOTICE AND RENEWAL FONT UPDATED"
   echo "Backup: $BACKUP"
   exit 0
 fi
 sleep 2
done
echo "Portal health check timed out"
restore
