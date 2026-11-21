#!/usr/bin/env bash
# HESAB_DEBTS_AZAR1_RENEWAL_TEXT_V1
# Only changes the canonical message used by the debts page and new manual
# WhatsApp drafts; NEVER sends messages or changes finance, XUI or deadlines.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP=ROOT_REQUIRED"; exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
TARGET=patches/sms_aban_default.py
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for file in .env docker-compose.yml docker-compose.sms.yml "$TARGET" "$SRC/$TARGET";do
  [[ -s "$file" ]] || { echo "STOP=MISSING_FILE $file"; exit 3; }
done
grep -Fq '# SMS_DEBT_DEFAULT_ABAN_V1' "$TARGET" || { echo "STOP=DEBT_PATCH_UNEXPECTED"; exit 3; }
grep -Fq './patches/sms_aban_default.py:/sms-patch/sms_aban_default.py:ro' docker-compose.sms.yml || {
  echo "STOP=DEBT_MOUNT_MISSING"; exit 3;
}
grep -Fq 'cat /sms-patch/sms_aban_default.py >> /app/app/main.py' docker-compose.sms.yml || {
  echo "STOP=DEBT_PATCH_NOT_IN_RUNTIME_ORDER"; exit 3;
}
compose config -q
compose exec -T app python3 -c 'import urllib.request;urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=5).read()'
# The human-approved text says "today": do not install it on later dates.
python3 - <<'PY'
from datetime import datetime,date
from zoneinfo import ZoneInfo
if datetime.now(ZoneInfo("Asia/Tehran")).date()!=date(2026,11,22):
    raise SystemExit("STOP=DAY_SPECIFIC_AZAR1_TEXT_NOT_VALID_TODAY")
print("TEHRAN_DATE_AZAR1=PASS")
PY
STAGED="$(mktemp /root/debt-azar1-stage.XXXXXX)"
trap 'rm -f "$STAGED"' EXIT
python3 - "$SRC/$TARGET" "$TARGET" "$STAGED" <<'PY'
import ast,sys
from pathlib import Path
def extract(code):
    nodes=[n for n in ast.parse(code).body if isinstance(n,ast.Assign)
           and len(n.targets)==1 and isinstance(n.targets[0],ast.Name)
           and n.targets[0].id=="_ABAN_SMS_PATTERN"]
    if len(nodes)!=1:raise ValueError("ambiguous message")
    return ast.get_source_segment(code,nodes[0]),ast.literal_eval(nodes[0].value)
source=Path(sys.argv[1]).read_text(encoding="utf-8")
live=Path(sys.argv[2]).read_text(encoding="utf-8")
new_assignment,new=extract(source)
old_assignment,old=extract(live)
expected=(
 "سلام، امروز اکانت شما تموم می‌شه.\n\n"
 "تا ساعت ۱۸ امروز برای پرداخت فرصت دارید و بعد از این ساعت، اکانت شما قطع خواهد شد.\n\n"
 "امکان پرداخت تا ساعت ۱۲ ظهر روز ۲ آذر وجود داره و بعد از اون اکانت شما حذف خواهد شد.\n\n"
 "اکانت شما به محض پرداخت مجدداً متصل خواهد شد.\n\n"
 "usersmanager.ir"
)
if new!=expected or len(new)>1000:raise ValueError("unexpected source text")
if not old.startswith("سلام") or "usersmanager.ir" not in old:
    raise ValueError("unrecognized old message")
if live.count(old_assignment)!=1:raise ValueError("old message not unique")
patched=live.replace(old_assignment,new_assignment,1)
compile(patched,"live-debt-staged","exec")
if patched.replace(new_assignment,old_assignment,1)!=live:
    raise ValueError("non-message content modified")
Path(sys.argv[3]).write_text(patched,encoding="utf8")
print("SINGLE_CANONICAL_MESSAGE_ONLY=PASS")
PY
# If the source and running app are already correct, stop without restart.
if cmp -s "$STAGED" "$TARGET" && compose exec -T app python3 - <<'PY' >/dev/null 2>&1
from app.main import _ABAN_SMS_PATTERN,TEMPLATES
assert _ABAN_SMS_PATTERN.endswith("\n\nusersmanager.ir")
assert "تا ساعت ۱۸ امروز" in _ABAN_SMS_PATTERN
assert _ABAN_SMS_PATTERN in TEMPLATES["debts.html"]
PY
then
  echo "ALREADY_INSTALLED=YES"; exit 0
fi
BACKUP="/root/hesab-azar1-text-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BACKUP"
cp -a "$TARGET" "$BACKUP/sms_aban_default.py"
echo "BACKUP=$BACKUP"
CHANGED=0
rollback(){
  code=$?
  trap - EXIT
  if ((code!=0 && CHANGED));then
    echo "ROLLBACK=RESTORE_OLD_MESSAGE"
    cp -a "$BACKUP/sms_aban_default.py" "$TARGET"
    compose up -d --no-deps --no-build --force-recreate app ||
      echo "WARNING=VERIFY_APP_AFTER_ROLLBACK"
  fi
  exit "$code"
}
trap rollback EXIT
install -m 0644 "$STAGED" "$TARGET"
CHANGED=1
python3 -m py_compile "$TARGET"
compose up -d --no-deps --no-build --force-recreate app
READY=0
for i in $(seq 1 30);do
  if compose exec -T app python3 - <<'PY' >/dev/null 2>&1
from app.main import _ABAN_SMS_PATTERN,TEMPLATES
import urllib.request
expected=(
 "سلام، امروز اکانت شما تموم می‌شه.\n\n"
 "تا ساعت ۱۸ امروز برای پرداخت فرصت دارید و بعد از این ساعت، اکانت شما قطع خواهد شد.\n\n"
 "امکان پرداخت تا ساعت ۱۲ ظهر روز ۲ آذر وجود داره و بعد از اون اکانت شما حذف خواهد شد.\n\n"
 "اکانت شما به محض پرداخت مجدداً متصل خواهد شد.\n\n"
 "usersmanager.ir"
)
assert _ABAN_SMS_PATTERN==expected
assert expected in TEMPLATES["debts.html"]
try:
    from app.main import _ews_message
except ImportError:
    pass
else:
    assert _ews_message(None)==expected
urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=5).read()
PY
  then READY=1;break;fi
  sleep 2
done
[[ "$READY" == 1 ]] || { echo "STOP=APP_RUNTIME_MESSAGE_NOT_VERIFIED"; false; }
trap - EXIT
echo "SUCCESS=AZAR1_MESSAGE_WITH_USERSMANAGER_IR"
echo "NO_SEND_NO_ACCOUNT_OR_FINANCE_CHANGES=YES"
echo "ONLY_NEW_DRAFTS_AFFECTED=YES"
echo "BACKUP=$BACKUP"
