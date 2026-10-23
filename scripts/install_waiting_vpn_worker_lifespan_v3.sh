#!/usr/bin/env bash
# HESAB_WAITING_VPN_WORKER_LIFESPAN_V3_INSTALL
# Fix startup scheduling only: no billing edits or new XUI control protocol.
set -Eeuo pipefail
umask 077
[[ $(id -u) == 0 ]] || { echo "STOP: root required";exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
target=patches/maya1_control.py
test -s "$target"
test -s "$SRC/patches/waiting_vpn_worker_lifespan_v3.py"
python3 -m py_compile "$SRC/patches/waiting_vpn_worker_lifespan_v3.py"
for marker in HESAB_WAITING_VPN_CONTROL_V1 HESAB_WAITING_VPN_RESTORE_RESILIENCE_V2; do
  grep -Fq "$marker" "$target" || {
    echo "STOP: missing $marker in production patch";exit 3;
  }
done
c config -q
if ! grep -Fq '# HESAB_WAITING_VPN_WORKER_LIFESPAN_V3' "$target";then
  echo "=== PREFLIGHT: WRAP ACTUAL CUSTOM LIFESPAN IN MEMORY ==="
  if ! cat "$SRC/patches/waiting_vpn_worker_lifespan_v3.py" | c exec -T app python -c '
import sys,traceback
try:
 from app import main as m
 assert hasattr(m,"_wvr_restore_one"),"V2 restore missing"
 old=m.app.router.lifespan_context
 assert callable(old)
 prev=[f for f in m.app.router.on_startup if f is m._wvc_startup]
 assert len(prev)==1,"Expected one startup callback"
 src=sys.stdin.read()
 exec(compile(src,"<waiting_worker_lifespan_v3>","exec"),vars(m))
 assert m.app.router.lifespan_context is m._wvr3_lifespan
 assert m._WVR3_ORIGINAL_LIFESPAN is old
 assert not any(f is m._wvc_startup for f in m.app.router.on_startup)
 assert callable(m._wvc_reconcile_once)
 print("PREFLIGHT_SUCCESS: original custom lifespan preserved; duplicate old startup registration removed")
except Exception:
 print("PREFLIGHT_FAILED: no production changes")
 traceback.print_exc(limit=8)
 sys.exit(1)
';then
    echo "STOP: preflight failed without changes";exit 4;
  fi
fi
backup="/opt/hesab-backups/waiting-worker-lifespan-v3-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$backup"
cp -a "$target" "$backup/maya1_control.py"
changed=0
rollback(){
 trap - ERR
 if [[ "$changed" == 1 ]];then
   echo "ROLLBACK: restoring previous worker registration"
   cp -a "$backup/maya1_control.py" "$target"
   c up -d --no-deps --no-build --force-recreate app || true
 fi
 echo "Backup: $backup"
 exit 1
}
trap rollback ERR
if ! grep -Fq '# HESAB_WAITING_VPN_WORKER_LIFESPAN_V3' "$target";then
  changed=1
  printf '\n\n' >> "$target"
  cat "$SRC/patches/waiting_vpn_worker_lifespan_v3.py" >> "$target"
  python3 -m py_compile "$target"
  echo "=== RECREATE WEB APP WITH ACTUAL LIFESPAN WORKER ==="
  echo "Eligible fully settled manually-cut clients may be restored after startup."
  c up -d --no-deps --no-build --force-recreate app
else
  echo "ALREADY_INSTALLED: checking actually running worker"
fi
echo "=== VERIFY REAL UVICORN WORKER HEARTBEAT (NOT IMPORT-ONLY) ==="
ready=0
for i in $(seq 1 45);do
 if c exec -T app python - <<'PY' >/dev/null 2>&1
from app import main as m
from pathlib import Path
import json,time
assert m.app.router.lifespan_context is m._wvr3_lifespan
assert m._WVR3_ORIGINAL_LIFESPAN is not m._wvr3_lifespan
assert not any(f is m._wvc_startup for f in m.app.router.on_startup)
p=Path("/tmp/hesab-waiting-worker-v3.json")
h=json.loads(p.read_text())
assert h["scan_completed"]>=1,h
assert h["last_completed_at"] is not None,h
assert 0<=time.time()-h["heartbeat_at"]<=120,h
assert h["scan_started"]>=h["scan_completed"]>=1,h
PY
 then ready=1;break;fi
 sleep 2
done
if [[ "$ready" != 1 ]];then
 echo "STOP: no successful live worker scan confirmed; checking logs before rollback"
 c logs --tail 90 app 2>&1 | grep -E 'WVR3_|WVR_|WVC_|Traceback|ERROR|Error|Exception' | tail -50 || true
 false
fi
echo "=== FINAL REAL-WORKER STATUS ==="
c exec -T app python - <<'PY'
import json,time
from pathlib import Path
from sqlalchemy import text
from app import main as m
h=json.loads(Path("/tmp/hesab-waiting-worker-v3.json").read_text())
print("LIFESPAN_WORKER_ACTIVE",h["scan_completed"]>=1)
print("WORKER_PASSES",h["scan_completed"])
print("WORKER_ERRORS",h["errors"])
print("LAST_WORKER_ERROR",h["last_error"])
print("HEARTBEAT_AGE_SECONDS",round(time.time()-h["heartbeat_at"],1))
g=m.get_db();db=next(g)
try:
 db.execute(text("SET TRANSACTION READ ONLY"))
 for row in db.execute(text("""
   SELECT subscription_id,server,state,restore_attempts,next_retry_at,
          last_restore_error FROM waiting_vpn_controls
   WHERE subscription_id IN (242,382)
   ORDER BY subscription_id,server
 """)).mappings().all():
  print("REFERENCE_CONTROL",dict(row))
finally:
 db.rollback();g.close()
PY
trap - ERR
echo "SUCCESS: background restore worker executed inside the real FastAPI lifespan."
echo "Existing payment checks, manual-only disable rules and XUI safeguards unchanged."
echo "Backup: $backup"
