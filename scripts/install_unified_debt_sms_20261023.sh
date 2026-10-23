#!/usr/bin/env bash
# HESAB_UNIFIED_DEBT_SMS_20261023
# Text-only change: canonical "debt" and "waiting renewal" phone drafts.
# No queued-message edits, SMS send, billing update, cron or XUI/SSH actions.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP: sudo/root required";exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for f in .env docker-compose.yml docker-compose.sms.yml patches/sms_aban_default.py patches/sms_native_v2.py;do
 test -s "$f" || { echo "STOP: missing $f";exit 3; }
done
for f in "$SRC/patches/sms_aban_default.py" "$SRC/patches/waiting_expiry_sms_v2.py";do
 test -s "$f" || { echo "STOP: missing GitHub source";exit 3; }
 python3 -m py_compile "$f"
done
grep -Fq 'SMS_DEBT_DEFAULT_ABAN_V1' patches/sms_aban_default.py || { echo "STOP: canonical SMS patch missing";exit 3; }
grep -Fq '# HESAB_WAITING_EXPIRY_SMS_V2' patches/sms_native_v2.py || { echo "STOP: waiting SMS patch missing";exit 3; }
grep -Fq '/sms-patch/sms_native_v2.py' docker-compose.sms.yml || { echo "STOP: live native mount missing";exit 3; }
grep -Fq '/sms-patch/sms_aban_default.py' docker-compose.sms.yml || { echo "STOP: live debt mount missing";exit 3; }
c config -q
BACKUP="/opt/hesab-backups/unified-debt-sms-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACKUP"
cp -a patches/sms_aban_default.py "$BACKUP/sms_aban_default.py"
cp -a patches/sms_native_v2.py "$BACKUP/sms_native_v2.py"
changed=0
rollback(){
 trap - ERR
 if [[ "$changed" == "1" ]];then
   echo "ROLLBACK: restoring the two SMS code files"
   cp -a "$BACKUP/sms_aban_default.py" patches/sms_aban_default.py
   cp -a "$BACKUP/sms_native_v2.py" patches/sms_native_v2.py
   c up -d --no-deps --no-build --force-recreate app || true
 fi
 echo "BACKUP=$BACKUP"
 exit 1
}
trap rollback ERR
changed=1

python3 - "$SRC" <<'PY'
import ast,os,tempfile,sys
from pathlib import Path
src=Path(sys.argv[1])
live_debt=Path("patches/sms_aban_default.py")
live_wait=Path("patches/sms_native_v2.py")
source_debt=(src/"patches/sms_aban_default.py").read_text(encoding="utf8")
source_wait=(src/"patches/waiting_expiry_sms_v2.py").read_text(encoding="utf8")
debt=live_debt.read_text(encoding="utf8")
wait=live_wait.read_text(encoding="utf8")
expected=(
 "سلام امروز موعد تمدید اکانت شماست\n"
 "لطفا برای تمدید وارد پنل کاربری خودتون بشید و نسبت به پرداخت اقدام فرمایید\n\n"
 " ساعت 10 شب اکانت هایی که پرداخت نداشتن مسدود خواهند شد و تا فردا همچنان امکان پرداخت هست.فردا ساعت 12 ظهر اکانت های پرداخت نشده حذف خواهند شد.\n\n"
 "فعال یا غیرفعال شدن اکانت ها سیستمی بوده و امکان فعال سازی اکانت بدون واریز ممکن نیست\n\n"
 "usersmanager.ir"
)
def locate_assignment(code,key):
    matches=[n for n in ast.parse(code).body
        if isinstance(n,ast.Assign) and len(n.targets)==1
        and isinstance(n.targets[0],ast.Name) and n.targets[0].id==key]
    if len(matches)!=1:raise RuntimeError("Missing/ambiguous assignment: "+key)
    node=matches[0]
    return ast.get_source_segment(code,node),ast.literal_eval(node.value)
def locate_function(code,key):
    matches=[n for n in ast.parse(code).body
        if isinstance(n,ast.FunctionDef) and n.name==key]
    if len(matches)!=1:raise RuntimeError("Missing/ambiguous function: "+key)
    return ast.get_source_segment(code,matches[0])
old_expr,old_text=locate_assignment(debt,"_ABAN_SMS_PATTERN")
new_expr,new_text=locate_assignment(source_debt,"_ABAN_SMS_PATTERN")
if new_text!=expected:raise RuntimeError("GitHub message does not match operator-approved text")
if not old_text or len(old_text)>1000 or "سلام" not in old_text:
    raise RuntimeError("Unrecognized existing debt SMS")
if debt.count(old_expr)!=1:raise RuntimeError("Debt message declaration not unique")
old_func=locate_function(wait,"_ews_message")
new_func=locate_function(source_wait,"_ews_message")
if "return _ABAN_SMS_PATTERN" not in new_func:raise RuntimeError("Waiting SMS is not canonical")
if wait.count(old_func)!=1:raise RuntimeError("Waiting message function not unique")
patched_debt=debt.replace(old_expr,new_expr,1)
patched_wait=wait.replace(old_func,new_func,1)
# Preserve all other routes and functionality in the rest of these files.
for code,label in [(patched_debt,str(live_debt)),(patched_wait,str(live_wait))]:
    compile(code,label,"exec")
if patched_debt.count("_ABAN_SMS_PATTERN.format(expiry=")<1:
    raise RuntimeError("Canonical debt server-send not found")
if patched_wait.count("_ews_queue_impl(")!=1:
    raise RuntimeError("Waiting SMS endpoint not found")
if patched_wait.count('env.filters["ews_message"]')!=1:
    raise RuntimeError("Waiting preview filter not found")
for path,code in ((live_debt,patched_debt),(live_wait,patched_wait)):
    fd,tmp=tempfile.mkstemp(prefix=".hesab-sms-staged-",dir=str(path.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf8") as f:
            f.write(code);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o644)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
print("STAGED: both canonical debtor SMS and waiting-payment SMS are identical.")
print("TEXT LENGTH:",len(expected))
print("No expiry is inserted into either message. Only future drafts change.")
PY
c up -d --no-deps --no-build --force-recreate app
ready=0
for n in $(seq 1 30);do
 if c exec -T app python - <<'PY' >/dev/null 2>&1
from app.main import app, env, TEMPLATES, _ABAN_SMS_PATTERN, _ews_message
from datetime import date
from jinja2 import Environment
expected=(
 "سلام امروز موعد تمدید اکانت شماست\n"
 "لطفا برای تمدید وارد پنل کاربری خودتون بشید و نسبت به پرداخت اقدام فرمایید\n\n"
 " ساعت 10 شب اکانت هایی که پرداخت نداشتن مسدود خواهند شد و تا فردا همچنان امکان پرداخت هست.فردا ساعت 12 ظهر اکانت های پرداخت نشده حذف خواهند شد.\n\n"
 "فعال یا غیرفعال شدن اکانت ها سیستمی بوده و امکان فعال سازی اکانت بدون واریز ممکن نیست\n\n"
 "usersmanager.ir"
)
assert _ABAN_SMS_PATTERN == expected
for expiry in (date(2026,9,21),date(2026,10,22),date(2025,1,1),None):
    assert _ews_message(expiry)==expected
assert env.filters["ews_message"](date(2026,9,21))==expected
debt=TEMPLATES["debts.html"]
wait=TEMPLATES["followups.html"]
assert debt.count(expected)==1
assert "g.first_expiry|ews_message" in wait
assert "data-waiting-renewal-form" in wait
for name,tpl in (("debts",debt),("followups",wait)):
    Environment().parse(tpl)
for path in ("/sms/waiting-renewal","/followups/sms-reminder"):
    assert sum(getattr(r,"path",None)==path and "POST" in (getattr(r,"methods",set()) or set()) for r in app.routes)==1
PY
 then ready=1;break;fi
 sleep 2
done
if [[ "$ready" != "1" ]];then
 echo "STOP: app did not verify new SMS on both routes"
 false
fi
trap - ERR
echo "SUCCESS: CANONICAL DEBT AND WAITING SMS VERIFIED ON RUNNING APP"
echo "Old prepared/queued SMS unchanged. No SMS sent. No automatic block/delete enabled."
echo "BACKUP=$BACKUP"
