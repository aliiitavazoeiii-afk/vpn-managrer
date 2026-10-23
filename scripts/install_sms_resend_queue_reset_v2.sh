#!/usr/bin/env bash
# HESAB_SMS_RESEND_QUEUE_RESET_V2
# Surgical _ns_enqueue replacement ONLY. No queued SMS is transmitted,
# no database or account records are changed by this installer.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == "0" ]] || { echo "STOP: run as sudo/root";exit 2; }
REPO="$(cd "$(dirname "$0")/.." && pwd)"
BASE=/opt/vpn-control-center
cd "$BASE"
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for f in .env docker-compose.yml docker-compose.sms.yml patches/sms_native_v2.py "$REPO/patches/sms_native_v2.py" "$REPO/scripts/reset_native_sms_app_queue_v1.py";do
 test -s "$f" || { echo "STOP missing file: $f";exit 3; }
done
grep -Fq 'HESAB_NATIVE_SMS_V2_ADMIN' patches/sms_native_v2.py || { echo "STOP: unrecognized installed SMS admin patch";exit 3; }
grep -Fq '/sms-patch/sms_native_v2.py' docker-compose.sms.yml || { echo "STOP: SMS admin patch not mounted";exit 3; }
compose config -q
python3 -m py_compile "$REPO/patches/sms_native_v2.py" "$REPO/scripts/reset_native_sms_app_queue_v1.py"
BACK="/opt/hesab-backups/sms-correction-v2-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACK"
cp -a patches/sms_native_v2.py "$BACK/sms_native_v2.py"
modified=0
rollback(){
 trap - ERR
 if [[ "$modified" == 1 ]];then
   echo "ROLLBACK: restoring SMS code only"
   cp -a "$BACK/sms_native_v2.py" patches/sms_native_v2.py
   compose up -d --no-deps --no-build --force-recreate app || true
 fi
 echo "BACKUP=$BACK"
 exit 1
}
trap rollback ERR
modified=1
python3 - "$REPO" <<'PY'
import ast,sys,os,tempfile
from pathlib import Path
repo=Path(sys.argv[1])
dest=Path("patches/sms_native_v2.py")
live=dest.read_text(encoding="utf8")
source=(repo/"patches/sms_native_v2.py").read_text(encoding="utf8")
def get(code):
    tree=ast.parse(code)
    matches=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_ns_enqueue"]
    if len(matches)!=1:raise RuntimeError("Expected one native SMS enqueue function")
    return ast.get_source_segment(code,matches[0])
old=get(live)
new=get(source)
if 'PREVIOUS_SMS_UNCERTAIN_OR_PENDING_REVIEW' not in new or 'source="manual"' not in new:
    raise RuntimeError("Cannot verify new safe correction flow in source")
if '_ns_clean_phone' not in old or 'NATIVE_SMS_ALREADY_REGISTERED' not in old:
    raise RuntimeError("Installed SMS enqueue is unexpected")
if live.count(old)!=1:
    raise RuntimeError("Live enqueue function not unique")
updated=live.replace(old,new,1)
compile(updated,str(dest),"exec")
if updated==live:
    print("Already installed revised message guard")
else:
    fd,tmp=tempfile.mkstemp(prefix=".sms-correction-",dir=str(dest.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf8") as f:
            f.write(updated);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o644)
        os.replace(tmp,dest)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    print("Installed corrected _ns_enqueue function (only function changed)")
PY
compose up -d --no-deps --no-build --force-recreate app
ok=0
for attempt in $(seq 1 25);do
 if compose exec -T app python - <<'PY' >/dev/null 2>&1
from app.main import app,_ns_enqueue,_ABAN_SMS_PATTERN
import inspect
body=inspect.getsource(_ns_enqueue)
assert "PREVIOUS_SMS_UNCERTAIN_OR_PENDING_REVIEW" in body
assert 'source="manual"' in body
assert "status <> 'cancelled'" in body
assert _ABAN_SMS_PATTERN.endswith("usersmanager.ir")
assert sum(getattr(r,"path",None)=="/sms/debt-send"
           and "POST" in (getattr(r,"methods",set()) or set()) for r in app.routes)==1
PY
 then ok=1;break;fi
 sleep 2
done
[[ "$ok" == 1 ]] || { echo "STOP: new SMS safety checks failed";false; }
trap - ERR
echo "SUCCESS: HISTORICAL DEBT SMS CORRECTION DRAFT ALLOWED"
echo "Prior sent/opened history untouched. Uncertain or pending messages remain blocked."
echo "Queue reset script backup validation was updated; run separately with --apply."
echo "No message sent and no payment or account state changed."
echo "BACKUP=$BACK"
