#!/usr/bin/env bash
# Jafari only: one account -> independent new mobile, NO OTP and NO SMS.
# Preserve existing live portal billing/UI overlays. Backups and rollback.
set -Eeuo pipefail
umask 077
cd /opt/vpn-control-center
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
C=(docker compose -f docker-compose.yml -f docker-compose.sms.yml)
SRC=customer_portal/v2.py
HTML=customer_portal/dashboard_v2.html
MARK=JAFARI_PHONE_CHANGE_V1
for p in "$SRC" "$HTML" customer_portal/Dockerfile "$REPO/customer_portal/jafari_phone_change.py" "$REPO/customer_portal/jafari_phone_ui.html"; do
  test -s "$p" || { echo "STOP: missing $p";exit 2; }
done
if grep -q "$MARK" "$SRC"; then
 echo "ALREADY INSTALLED: Jafari phone controls";exit 0
fi

BACKUP="/opt/hesab-backups/jafari-phone-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP/customer_portal"
cp -p "$SRC" "$BACKUP/$SRC"
cp -p "$HTML" "$BACKUP/$HTML"
echo "BACKUP=$BACKUP"
rollback(){
  trap - ERR
  echo "RESTORING former portal files"
  cp -p "$BACKUP/$SRC" "$SRC"
  cp -p "$BACKUP/$HTML" "$HTML"
  "${C[@]}" build customer-portal || true
  "${C[@]}" up -d --no-deps --no-build --force-recreate customer-portal || true
  exit 1
}
trap rollback ERR

python3 - "$REPO" <<'PY'
from pathlib import Path
import sys
repo=Path(sys.argv[1])
app=Path("customer_portal/v2.py")
page=Path("customer_portal/dashboard_v2.html")
addon=(repo/"customer_portal/jafari_phone_change.py").read_text(encoding="utf8")
widget=(repo/"customer_portal/jafari_phone_ui.html").read_text(encoding="utf8")
base=app.read_text(encoding="utf8")
html=page.read_text(encoding="utf8")
assert "JAFARI_PHONE_CHANGE_V1" in addon
assert "JAFARI_PHONE_CHANGE_V1" not in base
assert "/jafari/change-phone" not in html
assert base.count('@app.post("/disable/{sid}")')==1
assert html.count('        <form method="post" action="/disable/{{ a.id }}"')==1
assert "{{ csrf }}" in widget and "09357001107" in widget
assert "queue_sms" not in addon and "sms_jobs" not in addon
app.write_text(base+"\n\n"+addon+"\n",encoding="utf8")

anchor='        <form method="post" action="/disable/{{ a.id }}"'
html=html.replace(anchor,widget+"\n"+anchor,1)
css="""
<style>
.jafari-phone-panel{width:100%;border:1px solid #d5d9df;border-radius:15px;
 background:#f8f9fb;padding:12px 15px;margin-top:10px}
.jafari-phone-panel summary{font-size:13px;font-weight:850;color:#1d2229;cursor:pointer}
.jafari-phone-panel p{font-size:11px;line-height:1.9;color:#656f7e;margin:9px 0}
.jafari-phone-panel form{display:flex;flex-wrap:wrap;gap:9px;align-items:center}
.jafari-phone-panel input{flex:1;min-width:175px;height:43px;border-radius:11px;
 border:1px solid #d8dde5;background:#fff;color:#15171a;padding:8px;
 direction:ltr;text-align:left;font:inherit}
.jafari-phone-panel button{border:0;border-radius:11px;padding:11px 16px;
 background:#16181d;color:#fff;font:800 12px/1.6 inherit;cursor:pointer}
</style>
"""
assert html.count("</head>")==1
html=html.replace("</head>",css+"</head>",1)
flash="""
{% if request.query_params.get('jafari_phone') == 'changed' %}
<div class="flash ok">شماره این اکانت با موفقیت تغییر کرد. تمدید بعدی از شماره جدید انجام می‌شود.</div>
{% elif request.query_params.get('jafari_phone') %}
<div class="flash bad">
{% if request.query_params.get('jafari_phone') == 'pending_payment' %}برای جلوگیری از تداخل پرداخت، ابتدا درخواست پرداخت باز این شماره تعیین تکلیف شود.
{% elif request.query_params.get('jafari_phone') == 'already_used' %}این شماره به اکانت دیگری متصل است؛ شماره مستقل دیگری وارد کنید.
{% elif request.query_params.get('jafari_phone') == 'invalid' %}شماره جدید معتبر نیست.
{% else %}این اکانت قابل انتقال نیست یا دسترسی ندارید.{% endif %}
</div>
{% endif %}
"""
marker='  <section class="stats">'
assert html.count(marker)==1
html=html.replace(marker,flash+"\n"+marker,1)
page.write_text(html,encoding="utf8")
compile(app.read_text(encoding="utf8"),str(app),"exec")
print("Verified: only Jafari controls added, no OTP or SMS calls.")
PY

"${C[@]}" config -q
"${C[@]}" build customer-portal
"${C[@]}" up -d --no-deps --no-build --force-recreate customer-portal
ready=0
for i in $(seq 1 30);do
 if "${C[@]}" exec -T customer-portal python -c \
   'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8091/health",timeout=2).read()' \
   >/dev/null 2>&1;then ready=1;break;fi
 sleep 2
done
test "$ready" -eq 1
"${C[@]}" exec -T customer-portal python -c \
  'from pathlib import Path; s=Path("/srv/v2.py").read_text(); assert "JAFARI_PHONE_CHANGE_V1" in s; print("Jafari route present")'
trap - ERR
echo "SUCCESS: JAFARI ACCOUNT PHONE EDIT ENABLED (NO OTP)"
echo "No customer number or billing data was changed automatically."
echo "BACKUP=$BACKUP"
