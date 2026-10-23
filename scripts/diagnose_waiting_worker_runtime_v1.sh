#!/usr/bin/env bash
# HESAB_WAITING_WORKER_RUNTIME_DIAG_V1
# Read-only: checks eligibility, worker registration, process/log health.
set -Eeuo pipefail
cd /opt/vpn-control-center
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
echo "=== CONTAINERS ==="
c ps app db
echo "=== RUNTIME AND RESTORE JOB ELIGIBILITY ==="
c exec -T app python - <<'PY'
from app import main as m
from sqlalchemy import text
from datetime import datetime,timezone

print("UTC_NOW",datetime.now(timezone.utc).isoformat())
print("WORKER_FUNCTION",getattr(m._wvc_reconcile_once,"__code__",None).co_filename)
print("V2_ENABLED",hasattr(m,"_wvr_restore_one"))
print("STARTUP_HANDLER_NAMES",[getattr(f,"__name__",type(f).__name__) for f in m.app.router.on_startup])
context=getattr(m.app.router,"lifespan_context",None)
print("LIFESPAN_CONTEXT",str(context)[:250])
g=m.get_db();db=next(g)
try:
 db.execute(text("SET TRANSACTION READ ONLY"))
 rows=db.execute(text("""
   SELECT c.id,c.subscription_id,c.server,c.state,
          c.payment_watermark,c.restore_attempts,c.next_retry_at,
          c.updated_at,
          EXISTS (SELECT 1 FROM payments p
                    WHERE p.subscription_id=c.subscription_id
                    AND p.id>c.payment_watermark AND p.amount_toman>0) AS later_payment,
          (c.state='disabled'
             OR (c.state='needs_review'
                   AND (c.next_retry_at IS NULL OR c.next_retry_at<=NOW()))
             OR (c.state='activating'
                   AND c.updated_at<NOW()-INTERVAL '240 seconds')) AS state_due
   FROM waiting_vpn_controls c
   ORDER BY c.updated_at,c.id LIMIT 30
 """)).mappings().all()
 for row in rows:
  data=dict(row)
  for k in ("next_retry_at","updated_at"):
   data[k]=str(data[k])
  print("CONTROL_ELIGIBILITY",data)
 print("TOTAL_CONTROL_ROWS",db.execute(text(
   "SELECT COUNT(*) FROM waiting_vpn_controls")).scalar())
 print("STATE_COUNTS",[(a,b) for a,b in db.execute(text(
   "SELECT state,COUNT(*) FROM waiting_vpn_controls GROUP BY state ORDER BY state")).all()])
except Exception as ex:
 print("DIAG_DB_ERROR",type(ex).__name__,str(ex)[:180])
finally:
 db.rollback();g.close()
PY
echo "=== APPLICATION LOGS (last 5h; startup and V2 worker errors) ==="
c logs --since 5h --tail 250 app 2>&1 | grep -E -i 'WVR_|WVC_|started server|application startup|lifespan|traceback|error|exception' | tail -100 || true
echo "=== FINISHED; NO DB/USER/XUI CHANGES ==="
