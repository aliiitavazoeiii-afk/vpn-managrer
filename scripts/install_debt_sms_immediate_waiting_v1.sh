#!/usr/bin/env bash
# HESAB_DEBT_SMS_WAITING_RESTORE_V1
# Surgical code-only repair: debt send button queues the SMS AND moves
# eligible accounts to "waiting" in one transaction; never sends SMS itself.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP: sudo/root required";exit 2; }
REPO="$(cd "$(dirname "$0")/.." && pwd)"
BASE=/opt/vpn-control-center
cd "$BASE"
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for path in .env docker-compose.yml docker-compose.sms.yml patches/sms_native_v2.py "$REPO/patches/sms_native_v2.py";do
  test -s "$path" || { echo "STOP: missing $path";exit 3; }
done
grep -Fq 'HESAB_NATIVE_SMS_V2_ADMIN' patches/sms_native_v2.py || {
  echo "STOP: unexpected production SMS code";exit 3;
}
grep -Fq '/sms-patch/sms_native_v2.py' docker-compose.sms.yml || {
  echo "STOP: native V2 patch not mounted";exit 3;
}
compose config -q
python3 -m py_compile "$REPO/patches/sms_native_v2.py" patches/sms_native_v2.py
BACK="/opt/hesab-backups/debt-sms-waiting-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACK"
cp -a patches/sms_native_v2.py "$BACK/sms_native_v2.py"
modified=0
rollback(){
  trap - ERR
  if [[ "$modified" == 1 ]];then
    echo "ROLLBACK: original SMS code restored"
    cp -a "$BACK/sms_native_v2.py" patches/sms_native_v2.py
    compose up -d --no-deps --no-build --force-recreate app || true
  fi
  echo "BACKUP=$BACK"
  exit 1
}
trap rollback ERR
modified=1
python3 - "$REPO" <<'PY'
from pathlib import Path
import ast,sys,os,tempfile
repo=Path(sys.argv[1])
target=Path("patches/sms_native_v2.py")
live=target.read_text(encoding="utf8")
source=(repo/"patches/sms_native_v2.py").read_text(encoding="utf8")
def unique_segment(text,name,kind):
    nodes=[n for n in ast.parse(text).body
           if isinstance(n,kind) and
           (n.name==name if isinstance(n,ast.FunctionDef)
           else len(n.targets)==1 and isinstance(n.targets[0],ast.Name)
           and n.targets[0].id==name)]
    if len(nodes)!=1:raise RuntimeError("Missing/duplicate native SMS component: "+name)
    return ast.get_source_segment(text,nodes[0])
for name,kind in [("_ns_enqueue",ast.FunctionDef),("_NS_SCRIPT",ast.Assign)]:
    old=unique_segment(live,name,kind)
    new=unique_segment(source,name,kind)
    if name=="_ns_enqueue":
        if "NATIVE_SMS_ALREADY_REGISTERED" not in old:
            raise RuntimeError("Unexpected live enqueue handler")
        if 'for waiting_sid in waiting_ids' not in new or '_followup_set(' not in new:
            raise RuntimeError("New atomic followup hook missing")
        if 'db.commit()' not in new or 'source=="debt"' not in new:
            raise RuntimeError("New queue function incomplete")
    else:
        if "data-debt-sms-form" not in old or "پیامک ثبت نشد:" not in old:
            raise RuntimeError("Unexpected live SMS button script")
        if 'newDesk=doc.querySelector(".debt-desk")' not in new:
            raise RuntimeError("New UI status refresh missing")
        if "به «در انتظار پرداخت» منتقل شد" not in new:
            raise RuntimeError("New user notice missing")
    if live.count(old)!=1:
        raise RuntimeError("Non-unique installed SMS component: "+name)
    live=live.replace(old,new,1)
compile(live,str(target),"exec")
if live!=target.read_text(encoding="utf8"):
    fd,tmp=tempfile.mkstemp(prefix=".sms-waiting-",dir=str(target.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf8") as fp:
            fp.write(live);fp.flush();os.fsync(fp.fileno())
        os.chmod(tmp,0o644)
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
print("STAGED: SMS handler + debt-page status refresh updated")
PY
compose up -d --no-deps --no-build --force-recreate app

# Check the REAL live web service, not GitHub source or inspect.getsource.
ready=0
for i in $(seq 1 24);do
 if compose exec -T app python -c 'from app.main import _ns_enqueue' >/dev/null 2>&1;then
   ready=1;break
 fi
 sleep 2
done
[[ "$ready" == 1 ]] || {
 echo "STOP: app did not load; see recent logs"
 compose logs --tail 50 app | sed -E 's/(PASSWORD|TOKEN|KEY)=[^ ]+/\1=[REDACTED]/g' || true
 false
}
compose exec -T app python - <<'PY'
from app.main import app,_ns_enqueue,TEMPLATES
import urllib.request
fn=_ns_enqueue.__code__
assert "waiting_ids" in fn.co_varnames, "handler did not prepare waiting account ids"
assert "_followup_set" in fn.co_names, "handler does not mark waiting"
assert any("debt SMS draft queued, not sent" in str(x) for x in fn.co_consts), "waiting audit marker not loaded"
page=TEMPLATES.get("debts.html","")
assert "به «در انتظار پرداخت» منتقل شد" in page, "updated message not in debt page"
assert "newDesk=doc.querySelector" in page, "AJAX refresh not enabled"
endpoints=[r for r in app.routes if getattr(r,"path",None)=="/sms/debt-send"
           and "POST" in (getattr(r,"methods",set()) or set())]
assert endpoints, "Debt send endpoint missing"
assert endpoints[-1].endpoint.__name__=="_ns_debt_send", "Unexpected debt send route"
with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=7) as res:
    assert res.status==200
print("VERIFIED: live app queues draft and marks eligible debt accounts waiting atomically")
print("VERIFIED: debt page refreshes inline; sent SMS/finance/SSH/XUI unchanged")
PY
trap - ERR
echo "SUCCESS: DEBT SMS AUTO-WAITING RESTORED"
echo "Queue-on-click moves eligible account to waiting; opening on phone still requires manual Send."
echo "No old drafts replayed, no billing or VPN status changed."
echo "BACKUP=$BACK"
