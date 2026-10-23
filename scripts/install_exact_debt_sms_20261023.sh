#!/usr/bin/env bash
# HESAB_EXACT_DEBT_SMS_20261023 — no send, no user controls, no schedules
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP: sudo required";exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)/patches/sms_aban_default.py"
cd /opt/vpn-control-center
LIVE=patches/sms_aban_default.py
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for f in "$SRC" "$LIVE" .env docker-compose.sms.yml docker-compose.yml;do
  test -s "$f" || { echo "STOP: missing $f";exit 2; }
done
grep -Fq 'SMS_DEBT_DEFAULT_ABAN_V1' "$LIVE" || { echo "STOP: unfamiliar debt SMS patch";exit 2; }
grep -Fq './patches/sms_aban_default.py:/sms-patch/sms_aban_default.py:ro' docker-compose.sms.yml || {
 echo "STOP: SMS patch not mounted";exit 2;
}
compose config -q
STAGED="$(mktemp /opt/vpn-control-center/patches/.debt-sms-XXXXXXXX.py)"
BACK="/opt/hesab-backups/debt-message-$(date +%Y%m%d-%H%M%S)-$$.py"
mkdir -p /opt/hesab-backups
cp -a "$LIVE" "$BACK"
changed=0
rollback(){
 trap - ERR
 if [[ "$changed" == 1 ]];then
   cp -a "$BACK" "$LIVE"
   compose up -d --no-deps --no-build --force-recreate app || true
 fi
 echo "BACKUP=$BACK"
 exit 1
}
trap rollback ERR
trap 'rm -f "$STAGED"' EXIT
python3 - "$SRC" "$LIVE" "$STAGED" <<'PY'
import ast,sys
from pathlib import Path
source=Path(sys.argv[1]).read_text(encoding="utf8")
live=Path(sys.argv[2]).read_text(encoding="utf8")
expected=(
 "سلام امروز موعد تمدید اکانت شماست\n"
 "لطفا برای تمدید وارد پنل کاربری خودتون بشید و نسبت به پرداخت اقدام فرمایید\n\n"
 " ساعت 10 شب اکانت هایی که پرداخت نداشتن مسدود خواهند شد و تا فردا همچنان امکان پرداخت هست.فردا ساعت 12 ظهر اکانت های پرداخت نشده حذف خواهند شد.\n\n"
 "فعال یا غیرفعال شدن اکانت ها سیستمی بوده و امکان فعال سازی اکانت بدون واریز ممکن نیست"
)
def assignment(code):
    tree=ast.parse(code)
    found=[n for n in tree.body if isinstance(n,ast.Assign) and len(n.targets)==1 and
        isinstance(n.targets[0],ast.Name) and n.targets[0].id=="_ABAN_SMS_PATTERN"]
    if len(found)!=1:raise ValueError("Canonical SMS assignment ambiguous")
    n=found[0]
    return ast.get_source_segment(code,n),ast.literal_eval(n.value)
old_exp,old=assignment(live)
new_exp,new=assignment(source)
if new!=expected:raise ValueError("Exact operator message differs in GitHub source")
if not old or len(old)>1000 or "سلام" not in old:raise ValueError("Unknown SMS template")
if live.count(old_exp)!=1:raise ValueError("Non-unique message declaration")
result=live.replace(old_exp,new_exp,1)
compile(result,sys.argv[2],"exec")
if "_ABAN_SMS_PATTERN.format(expiry=" not in result or "_aban_display_text = _ABAN_SMS_PATTERN.replace" not in result:
    raise ValueError("Canonical debt SMS path changed; refusing update")
Path(sys.argv[3]).write_text(result,encoding="utf8")
print("PASS: exact operator-provided message, characters:",len(expected))
PY
chmod 0644 "$STAGED"
if ! cmp -s "$STAGED" "$LIVE";then
  changed=1
  mv "$STAGED" "$LIVE"
  compose up -d --no-deps --no-build --force-recreate app
fi
ok=0
for i in $(seq 1 30);do
 if compose exec -T app python - <<'PY' >/dev/null 2>&1
from app.main import _ABAN_SMS_PATTERN,TEMPLATES
from jinja2 import Environment
expected=(
 "سلام امروز موعد تمدید اکانت شماست\n"
 "لطفا برای تمدید وارد پنل کاربری خودتون بشید و نسبت به پرداخت اقدام فرمایید\n\n"
 " ساعت 10 شب اکانت هایی که پرداخت نداشتن مسدود خواهند شد و تا فردا همچنان امکان پرداخت هست.فردا ساعت 12 ظهر اکانت های پرداخت نشده حذف خواهند شد.\n\n"
 "فعال یا غیرفعال شدن اکانت ها سیستمی بوده و امکان فعال سازی اکانت بدون واریز ممکن نیست"
)
assert _ABAN_SMS_PATTERN==expected
tpl=TEMPLATES["debts.html"]
assert tpl.count(expected)==1
assert 'id="debt-message-{{ loop.index0 }}"' in tpl
Environment().parse(tpl)
PY
 then ok=1;break;fi
 sleep 2
done
[[ "$ok" == 1 ]] || { echo "STOP: app did not confirm exact message";false; }
trap - ERR
echo "SUCCESS: EXACT DEBT SMS LOADED AND PREVIEW VERIFIED"
echo "Only future SMS drafts changed. No queued SMS, no XUI/SSH user changes, no 22:00/12:00 jobs."
echo "BACKUP=$BACK"
