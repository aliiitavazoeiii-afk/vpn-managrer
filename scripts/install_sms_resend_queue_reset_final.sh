#!/usr/bin/env bash
# HESAB_SMS_RESEND_QUEUE_RESET_FINAL
# Surgical _ns_enqueue replacement ONLY. No queued SMS is transmitted,
# no database or account records are changed by this installer.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == "0" ]] || { echo "STOP: run as sudo/root";exit 2; }
REPO="$(cd "$(dirname "$0")/.." && pwd)"
BASE=/opt/vpn-control-center
cd "$BASE"
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for f in .env docker-compose.yml docker-compose.sms.yml patches/sms_native_v2.py patches/sms_aban_default.py "$REPO/patches/sms_native_v2.py" "$REPO/patches/sms_aban_default.py" "$REPO/patches/waiting_expiry_sms_v2.py" "$REPO/scripts/reset_native_sms_app_queue_v1.py";do
 test -s "$f" || { echo "STOP missing file: $f";exit 3; }
done
grep -Fq 'HESAB_NATIVE_SMS_V2_ADMIN' patches/sms_native_v2.py || { echo "STOP: unrecognized installed SMS admin patch";exit 3; }
grep -Fq '/sms-patch/sms_native_v2.py' docker-compose.sms.yml || { echo "STOP: SMS admin patch not mounted";exit 3; }
grep -Fq '/sms-patch/sms_aban_default.py' docker-compose.sms.yml || { echo "STOP: debt message patch not mounted";exit 3; }
grep -Fq 'SMS_DEBT_DEFAULT_ABAN_V1' patches/sms_aban_default.py || { echo "STOP: unfamiliar live debt message file";exit 3; }
grep -Fq 'HESAB_WAITING_EXPIRY_SMS_V2' patches/sms_native_v2.py || { echo "STOP: waiting message function missing";exit 3; }
compose config -q
python3 -m py_compile "$REPO/patches/sms_native_v2.py" "$REPO/scripts/reset_native_sms_app_queue_v1.py"
BACK="/opt/hesab-backups/sms-correction-final-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACK"
cp -a patches/sms_native_v2.py "$BACK/sms_native_v2.py"
cp -a patches/sms_aban_default.py "$BACK/sms_aban_default.py"
modified=0
rollback(){
 trap - ERR
 if [[ "$modified" == 1 ]];then
   echo "ROLLBACK: restoring SMS code only"
   cp -a "$BACK/sms_native_v2.py" patches/sms_native_v2.py
   cp -a "$BACK/sms_aban_default.py" patches/sms_aban_default.py
   compose up -d --no-deps --no-build --force-recreate app || true
 fi
 echo "BACKUP=$BACK"
 exit 1
}
trap rollback ERR
modified=1
python3 - "$REPO" <<'PY'
# Prepare BOTH live SMS files together before any service restart.
# Replacing two explicitly named AST nodes preserves unrelated production
# customizations and the old sent-message/financial audit data.
import ast, sys, os, tempfile
from pathlib import Path
repo=Path(sys.argv[1])
native_path=Path("patches/sms_native_v2.py")
debt_path=Path("patches/sms_aban_default.py")
native_live=native_path.read_text(encoding="utf8")
debt_live=debt_path.read_text(encoding="utf8")
native_source=(repo/"patches/sms_native_v2.py").read_text(encoding="utf8")
debt_source=(repo/"patches/sms_aban_default.py").read_text(encoding="utf8")
waiting_source=(repo/"patches/waiting_expiry_sms_v2.py").read_text(encoding="utf8")

expected=(
 "سلام امروز موعد تمدید اکانت شماست\n"
 "لطفا برای تمدید وارد پنل کاربری خودتون بشید و نسبت به پرداخت اقدام فرمایید\n\n"
 " ساعت 10 شب اکانت هایی که پرداخت نداشتن مسدود خواهند شد و تا فردا همچنان امکان پرداخت هست.فردا ساعت 12 ظهر اکانت های پرداخت نشده حذف خواهند شد.\n\n"
 "فعال یا غیرفعال شدن اکانت ها سیستمی بوده و امکان فعال سازی اکانت بدون واریز ممکن نیست\n\n"
 "usersmanager.ir"
)
def function_text(text,name):
    matched=[n for n in ast.parse(text).body
             if isinstance(n,ast.FunctionDef) and n.name==name]
    if len(matched)!=1:raise RuntimeError("Function missing or repeated: "+name)
    return ast.get_source_segment(text,matched[0])
def assignment(text,name):
    matched=[n for n in ast.parse(text).body if isinstance(n,ast.Assign)
             and len(n.targets)==1 and isinstance(n.targets[0],ast.Name)
             and n.targets[0].id==name]
    if len(matched)!=1:raise RuntimeError("Assignment missing or repeated: "+name)
    return ast.get_source_segment(text,matched[0]),ast.literal_eval(matched[0].value)
old_func=function_text(native_live,"_ns_enqueue")
new_func=function_text(native_source,"_ns_enqueue")
old_wait=function_text(native_live,"_ews_message")
new_wait=function_text(waiting_source,"_ews_message")
old_sms,previous=assignment(debt_live,"_ABAN_SMS_PATTERN")
new_sms,approved=assignment(debt_source,"_ABAN_SMS_PATTERN")
if approved!=expected:raise RuntimeError("GitHub canonical text does not match exact approved copy")
if not isinstance(previous,str) or not previous.startswith("سلام"):
    raise RuntimeError("Unknown previously installed SMS template")
if "PREVIOUS_SMS_UNCERTAIN_OR_PENDING_REVIEW" not in new_func:
    raise RuntimeError("Correction guard missing")
if "NATIVE_SMS_ALREADY_REGISTERED" not in old_func:
    raise RuntimeError("Existing send function unexpected")
if "return _ABAN_SMS_PATTERN" not in new_wait:
    raise RuntimeError("Waiting SMS does not point to canonical text")
def replace_once(s,old,new,name):
    if s.count(old)!=1:raise RuntimeError("Nonunique "+name)
    return s.replace(old,new,1)
new_native=replace_once(native_live,old_func,new_func,"native queue")
new_native=replace_once(new_native,old_wait,new_wait,"waiting SMS")
new_debt=replace_once(debt_live,old_sms,new_sms,"canonical debt SMS")
compile(new_native,str(native_path),"exec")
compile(new_debt,str(debt_path),"exec")
for p,new in [(native_path,new_native),(debt_path,new_debt)]:
    if p.read_text(encoding="utf8")==new:
        print("ALREADY MATCHES:",p,flush=True)
        continue
    fd,tmp=tempfile.mkstemp(prefix=".sms-fixed-",dir=str(p.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf8") as out:
            out.write(new);out.flush();os.fsync(out.fileno())
        os.chmod(tmp,0o644)
        os.replace(tmp,p)
        print("UPDATED:",p,flush=True)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
print("ALL COMPONENTS STAGED: canonical text, waiting text, safe correction drafts",flush=True)
PY
compose up -d --no-deps --no-build --force-recreate app
echo "==== Verifying the running app; no silent assertions ===="
ok=0
for attempt in $(seq 1 18);do
  # The only retry condition is the app not yet accepting imports after
  # restart; once importing works, always print all individual checks.
  if compose exec -T app python -c 'from app.main import _ns_enqueue' >/dev/null 2>&1;then
    ok=1
    break
  fi
  sleep 2
done
[[ "$ok" == 1 ]] || {
 echo "STOP: app failed to import after restart"
 compose logs --tail 65 app | sed -E 's/(PASSWORD|TOKEN|KEY)=[^ ]+/\1=[REDACTED]/g' || true
 false
}
compose exec -T app python - <<'PY'
from app.main import app, _ns_enqueue, _ABAN_SMS_PATTERN, _ews_message
from datetime import date
from pathlib import Path
import sys
print("Loaded handler:",_ns_enqueue.__name__)
print("Loaded source file:",_ns_enqueue.__code__.co_filename)
# Constants come from the LIVE compiled function, not a saved Python source
# that can be stale or appended with several overlay definitions.
constants=str(_ns_enqueue.__code__.co_consts)
new_guard="PREVIOUS_SMS_UNCERTAIN_OR_PENDING_REVIEW" in constants
correction="CORRECTED_SMS_ALREADY_REGISTERED" in constants
cancel_guard="status <> 'cancelled'" in constants
expected=(
 "سلام امروز موعد تمدید اکانت شماست\n"
 "لطفا برای تمدید وارد پنل کاربری خودتون بشید و نسبت به پرداخت اقدام فرمایید\n\n"
 " ساعت 10 شب اکانت هایی که پرداخت نداشتن مسدود خواهند شد و تا فردا همچنان امکان پرداخت هست.فردا ساعت 12 ظهر اکانت های پرداخت نشده حذف خواهند شد.\n\n"
 "فعال یا غیرفعال شدن اکانت ها سیستمی بوده و امکان فعال سازی اکانت بدون واریز ممکن نیست\n\n"
 "usersmanager.ir"
)
canonical=_ABAN_SMS_PATTERN==expected
waiting=all(_ews_message(d)==expected for d in
        (date(2026,9,21),date(2026,10,23),None))
routes=[r for r in app.routes if getattr(r,"path",None)=="/sms/debt-send"
        and "POST" in (getattr(r,"methods",set()) or set())]
print("New corrective guard loaded:",new_guard)
print("Correction idempotency loaded:",correction)
print("Cancelled draft dedup loaded:",cancel_guard)
print("Debt SMS matches approved complete message:",canonical)
print("Waiting SMS uses same text regardless of expiry:",waiting)
print("Debt POST endpoints:",[getattr(getattr(r,"endpoint",None),"__name__","<unnamed>") for r in routes])
if not (new_guard and correction and cancel_guard and canonical and waiting and routes):
   raise SystemExit("STOP: one of the above live checks failed")
print("APP VERIFIED: correction route and canonical text loaded")
PY
echo "==== Checking live HTTP health ===="
compose exec -T app python - <<'PY'
import urllib.request
with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=6) as response:
    print("APP HEALTH:",response.status)
    assert response.status==200
PY
trap - ERR
echo "SUCCESS: HISTORICAL DEBT SMS CORRECTION DRAFT ALLOWED"
echo "Prior sent/opened history untouched. Uncertain or pending messages remain blocked."
echo "==== Backing up DB and clearing SERVER-BACKED Android draft list ===="
if ! python3 "$REPO/scripts/reset_native_sms_app_queue_v1.py" --apply;then
  echo "QUEUE RESET FAILED. Corrected SMS code remains installed, but queued drafts may remain."
  echo "No automatic SMS was sent. Inspect error above; do not repeat blindly."
  exit 1
fi
echo "No message sent and no payment or account state changed."
echo "BACKUP=$BACK"

echo "SUCCESS: ONE-PASS CORRECTION INSTALLED AND PHONE APP QUEUE CLEARED"
