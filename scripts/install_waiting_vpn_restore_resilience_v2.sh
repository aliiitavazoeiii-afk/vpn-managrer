#!/usr/bin/env bash
# HESAB_WAITING_VPN_RESTORE_RESILIENCE_V2_INSTALL
# Safe all-account repair for operator-triggered Maya cut and paid restore.
# NO scheduled disconnection and NO XUI mutations during install preflight.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo "STOP: sudo/root required";exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
file=patches/maya1_control.py
test -s "$file"
test -s "$SRC/patches/waiting_vpn_restore_resilience_v2.py"
python3 -m py_compile "$SRC/patches/waiting_vpn_restore_resilience_v2.py"
for marker in HESAB_WAITING_VPN_CONTROL_V1 HESAB_MAYA_MANUAL_LINKS_V1;do
 grep -Fq "$marker" "$file" || { echo "STOP: missing prior $marker";exit 3; }
done
test -S maya_extra_sync/live.sock || { echo "STOP: original Maya control socket not running";exit 3; }
c config -q
if ! grep -Fq '# HESAB_WAITING_VPN_RESTORE_RESILIENCE_V2' "$file";then
 echo "=== PREFLIGHT: IMPORT LIVE APP + COMPILE V2 OVERRIDES IN MEMORY ==="
 if ! cat "$SRC/patches/waiting_vpn_restore_resilience_v2.py" | c exec -T app python -c '
import sys,importlib,traceback
try:
 m=importlib.import_module("app.main")
 assert hasattr(m,"_wvc_reconcile_once"),"Waiting payment worker missing"
 assert any(getattr(f,"__name__","")=="_wvc_startup" for f in m.app.router.on_startup),"Startup worker missing"
 original_disable=m._wvc_disable_one
 original_worker=m._wvc_reconcile_once
 source=sys.stdin.read()
 exec(compile(source,"<restore_resilience_v2_candidate>","exec"),vars(m))
 assert m._wvc_disable_one is not original_disable
 assert m._wvc_reconcile_once is not original_worker
 assert m._WVR_ORIGINAL_DISABLE_ONE is original_disable
 assert m._wvr_backoff(999)==3600
 assert m._wvr_backoff(1)==30
 assert m._WVC_PAYMENT_CHECK_INTERVAL==30
 print("PREFLIGHT_SUCCESS: updated callbacks loaded, old waiting routes and startup worker intact")
except Exception:
 print("PREFLIGHT_FAILED: no changes made")
 traceback.print_exc(limit=7)
 sys.exit(1)
';then
  echo "STOP: preflight failed; original app unchanged"
  exit 4
 fi
fi
backup="/opt/hesab-backups/waiting-restore-resilience-v2-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$backup"
cp -a "$file" "$backup/maya1_control.py"
changed=0
rollback(){
 trap - ERR
 if [[ "$changed" == 1 ]];then
  cp -a "$backup/maya1_control.py" "$file"
  c up -d --no-deps --no-build --force-recreate app || true
 fi
 echo "Backup: $backup"
 echo "No payments or client configurations changed by rollback."
 exit 1
}
trap rollback ERR
echo "=== SAFE JOURNAL SCHEMA EXTENSION (NO FINANCIAL TABLE ALTERATIONS) ==="
c exec -T db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
BEGIN;
ALTER TABLE waiting_vpn_controls
  ADD COLUMN IF NOT EXISTS restore_attempts INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_restore_error VARCHAR(100);
CREATE INDEX IF NOT EXISTS waiting_vpn_controls_retry_v2_idx
ON waiting_vpn_controls(next_retry_at,id)
WHERE state IN ('needs_review','disabled','activating');
COMMIT;
SQL
if ! grep -Fq '# HESAB_WAITING_VPN_RESTORE_RESILIENCE_V2' "$file";then
 changed=1
 printf '\n\n' >>"$file"
 cat "$SRC/patches/waiting_vpn_restore_resilience_v2.py" >>"$file"
 python3 -m py_compile "$file"
 c up -d --no-deps --no-build --force-recreate app
else
 echo "ALREADY_INSTALLED: running smoke test only"
fi
echo "=== POST-INSTALL RUNTIME SMOKE TEST ==="
smoke_ok=0
for i in $(seq 1 20);do
 if c exec -T app python - <<'PY' >/dev/null 2>&1
from app import main as m
from pathlib import Path
from sqlalchemy import text
assert "# HESAB_WAITING_VPN_RESTORE_RESILIENCE_V2" in Path("/app/app/main.py").read_text()
assert m._wvc_disable_one.__code__.co_names and m._wvc_disable_one is not m._WVR_ORIGINAL_DISABLE_ONE
assert m._WVR_ORIGINAL_DISABLE_ONE.__name__=="_wvc_disable_one"
assert "_wvr_restore_one" in m._wvc_reconcile_once.__code__.co_names
assert m._wvr_backoff(1)==30 and m._wvr_backoff(50)==3600
assert sum(getattr(r,"path",None)=="/followups/vpn/disable" and
 "POST" in (getattr(r,"methods",set()) or set()) for r in m.app.routes)==1
assert any(getattr(f,"__name__","")=="_wvc_startup" for f in m.app.router.on_startup)
g=m.get_db();db=next(g)
try:
 cols={r[0] for r in db.execute(text("""SELECT column_name FROM information_schema.columns
   WHERE table_name='waiting_vpn_controls' AND column_name IN
   ('restore_attempts','next_retry_at','last_restore_error')""")).all()}
 assert cols=={"restore_attempts","next_retry_at","last_restore_error"},cols
finally:g.close()
PY
 then smoke_ok=1;break;fi
 sleep 2
done
if [[ "$smoke_ok" != 1 ]];then
 echo "STOP: runtime smoke test failed; printing import diagnostics"
 c logs --tail 45 app 2>&1 | grep -E 'Traceback|Error|Exception|WVR_|Started|startup' | tail -25 || true
 false
fi
trap - ERR
echo "SUCCESS: automatic post-payment Maya XUI restore now resilient for ALL journal-owned waiting accounts."
echo "Only manual operator clicks can disable XUI; this V2 never auto-disables."
echo "Restore is triggered ONLY by newly recorded payment AND a fully settled active account."
echo "Ambiguous panel results get readback; temporary failures retry with capped hourly backoff."
echo "Unknown identity or missing server is NOT blindly toggled."
echo "Backup: $backup"
