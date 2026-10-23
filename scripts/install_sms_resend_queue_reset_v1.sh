#!/usr/bin/env bash
# HESAB_SMS_RESEND_QUEUE_RESET_V1
# Surgical dedup fix + explicit queue purge with backups and live smoke test.
# This script NEVER auto-sends SMS or deletes rows/records.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP: sudo/root required";exit 2; }
REPO="$(cd "$(dirname "$0")/.." && pwd)"
BASE=/opt/vpn-control-center
cd "$BASE"
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for file in .env docker-compose.yml docker-compose.sms.yml patches/sms_native_v2.py "$REPO/patches/sms_native_v2.py" "$REPO/scripts/reset_native_sms_app_queue_v1.py";do
 test -s "$file" || { echo "STOP: missing expected file";exit 3; }
done
c config -q
grep -Fq 'HESAB_NATIVE_SMS_V2_ADMIN' patches/sms_native_v2.py || { echo "STOP: V2 SMS admin patch missing";exit 3; }
grep -Fq '/sms-patch/sms_native_v2.py' docker-compose.sms.yml || { echo "STOP: SMS V2 mount missing";exit 3; }
python3 -m py_compile "$REPO/patches/sms_native_v2.py" "$REPO/scripts/reset_native_sms_app_queue_v1.py"
BACK="/opt/hesab-backups/sms-resend-ui-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACK"
cp -a patches/sms_native_v2.py "$BACK/sms_native_v2.py"
changed=0
rollback(){
 trap - ERR
 if [[ "$changed" == "1" ]];then
   echo "RESTORE: previously loaded SMS code"
   cp -a "$BACK/sms_native_v2.py" patches/sms_native_v2.py
   c up -d --no-deps --no-build --force-recreate app || true
 fi
 echo "BACKUP=$BACK"
 exit 1
}
trap rollback ERR
changed=1
python3 - "$REPO" <<'PY'
from pathlib import Path
import sys
repo=Path(sys.argv[1])
src=(repo/"patches/sms_native_v2.py").read_text(encoding="utf8")
path=Path("patches/sms_native_v2.py")
live=path.read_text(encoding="utf8")
before="""SELECT id FROM native_sms_v2_jobs WHERE phone=:phone AND message=:body
          AND created_at > NOW() - INTERVAL '1 day' LIMIT 1"""
after="""SELECT id FROM native_sms_v2_jobs WHERE phone=:phone AND message=:body
          AND status <> 'cancelled'
          AND created_at > NOW() - INTERVAL '1 day' LIMIT 1"""
if after not in src:raise RuntimeError("Cannot verify source dedup rule")
if after in live and before not in live:
    print("ALREADY PATCHED: excludes cancelled, unsent drafts")
elif live.count(before)==1:
    live=live.replace(before,after,1)
    compile(live,str(path),"exec")
    path.write_text(live,encoding="utf8")
    print("PATCHED: cancelled draft no longer blocks a fresh reminder")
else:
    raise RuntimeError("Live manual SMS dedup differs; cannot update safely")
PY
c up -d --no-deps --no-build --force-recreate app
ok=0
for i in $(seq 1 24);do
 if c exec -T app python - <<'PY' >/dev/null 2>&1
from app.main import _ns_enqueue,app
import inspect
s=inspect.getsource(_ns_enqueue)
assert "status <> 'cancelled'" in s
assert "IDENTICAL_SMS_ALREADY_REGISTERED" in s
assert "HESAB_NATIVE_SMS_V2_ADMIN" in open("/app/app/main.py",encoding="utf8").read()
assert sum(getattr(r,"path",None)=="/sms/waiting-renewal" and
           "POST" in (getattr(r,"methods",set()) or set())
           for r in app.routes)==1
PY
 then ok=1;break;fi
 sleep 2
done
[[ "$ok" == "1" ]] || { echo "STOP: app did not load new dedup guard";false; }
trap - ERR
echo "SUCCESS: CANCELED-UNSENT SMS CAN BE REQUEUED"
echo "Preview how many Android messages remain:"
python3 "$REPO/scripts/reset_native_sms_app_queue_v1.py"
echo ""
echo "To clear the server-backed Android app list, execute separately:"
echo "sudo python3 $REPO/scripts/reset_native_sms_app_queue_v1.py --apply"
echo "Existing sent/paid history preserved; no SMS transmitted."
echo "BACKUP=$BACK"
