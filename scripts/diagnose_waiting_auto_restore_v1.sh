#!/usr/bin/env bash
# HESAB_WAITING_RESTORE_DIAGNOSTIC_V1
# Read-only diagnostics. No XUI toggle, financial mutation or billing refresh.
set -Eeuo pipefail
sid="382"
if [[ $# -gt 0 ]];then sid="$1";fi
[[ "$sid" =~ ^[1-9][0-9]{0,7}$ ]] || { echo 'Use a positive account id, e.g. 382';exit 2; }
cd /opt/vpn-control-center
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
echo "=== CONTROL / PAYMENT / XUI READ-ONLY DIAGNOSTICS FOR SID $sid ==="
c exec -T -e DIAG_SID="$sid" app python - <<'PY'
import os,traceback
from sqlalchemy import text
from app import main as m

sid=int(os.environ["DIAG_SID"])
print("ACCOUNT_ID",sid)
print("AUTO_WORKER_REGISTERED",any(
    getattr(func,"__name__","")=="_wvc_startup" for func in m.app.router.on_startup))
print("AUTO_WORKER_INTERVAL_SEC",getattr(m,"_WVC_PAYMENT_CHECK_INTERVAL","not_installed"))
print("AUTO_WORKER_ENABLED_IN_APP",hasattr(m,"_wvc_reconcile_once"))
print("DYNAMIC_LINK_PATCH",hasattr(m,"_mdl_post_link"))
generator=m.get_db()
db=next(generator)
try:
    sub=db.get(m.Subscription,sid)
    if not sub:
        print("ACCOUNT_MISSING");raise SystemExit(0)
    print("FINANCE_RECORD",{
       "payment_status":sub.payment_status,
       "expiry_date":str(sub.expiry_date),
       "stored_debt_toman":str(sub.debt_toman),
       "is_free":bool(sub.is_free)})
    st=m._followup_states(db).get(sid)
    debt=m.current_debt_for(sub,m.today_local())
    print("FOLLOWUP_STATE",st or "none")
    print("CALCULATED_DEBT",int(debt or 0))
    print("AUTO_ENABLE_READY",m._wvc_ready(db,sid,False))
    payments=db.execute(text("""
      SELECT id,paid_at,amount_toman
      FROM payments WHERE subscription_id=:sid
      ORDER BY id DESC LIMIT 6
    """),{"sid":sid}).mappings().all()
    print("LAST_PAYMENTS",[
      {"id":int(p["id"]),"paid_at":str(p["paid_at"]),"amount_toman":int(p["amount_toman"])}
      for p in payments])
    try:
        controls=db.execute(text("""
           SELECT id,server,email,state,payment_watermark,disabled_at,activated_at,updated_at,
              (SELECT COALESCE(MAX(p.id),0) FROM payments p
                 WHERE p.subscription_id=c.subscription_id) AS max_payment_id,
              (SELECT COUNT(*) FROM payments p
                 WHERE p.subscription_id=c.subscription_id
                 AND p.id>c.payment_watermark) AS payment_after_cut
           FROM waiting_vpn_controls c
           WHERE c.subscription_id=:sid
           ORDER BY id
        """),{"sid":sid}).mappings().all()
    except Exception as ex:
        db.rollback()
        print("CONTROL_QUERY_FAILED",type(ex).__name__,str(ex)[:170])
        controls=[]
    if not controls:
        print("NO_VPN_WAITING_CONTROL_ROWS")
    for r in controls:
        item=dict(r)
        for key in ("id","payment_watermark","max_payment_id","payment_after_cut"):
            item[key]=int(item[key])
        for key in ("disabled_at","activated_at","updated_at"):
            item[key]=str(item[key])
        print("CONTROL_ROW",item)
        try:
            server=item["server"]
            live=m._ml_one(server,db)     # Snapshot only, never toggle
            rows=[x for x in live["rows"] if
                  str(x.get("email","")).casefold()==str(item["email"]).casefold()]
            print("XUI_LIVE",{
               "server":server,"matches":len(rows),
               "matched_sid":rows[0].get("sid") if len(rows)==1 else None,
               "link_reason":rows[0].get("reason") if len(rows)==1 else None,
               "client_enabled":rows[0].get("client_enabled") if len(rows)==1 else None,
               "control_ambiguous":rows[0].get("control_ambiguous") if len(rows)==1 else None,
            })
        except Exception as ex:
            print("XUI_READ_FAILED",item["server"],type(ex).__name__,str(ex)[:140])
    print("=== END READ-ONLY INSPECTION ===")
except Exception as exc:
    print("DIAG_ERROR",type(exc).__name__,str(exc)[:250])
    traceback.print_exc(limit=4)
    raise SystemExit(1)
finally:
    generator.close()
PY
echo "=== RELEVANT WORKER LOGS (last 3 hours) ==="
c logs --since 3h app 2>&1 | grep -E 'WVC_AUTO_ENABLE_REVIEW|WVC_WORKER_ERROR|WVC_MANUAL_DISABLE_ERROR' | tail -25 || true
echo "=== DIAGNOSTICS FINISHED; NO STATE CHANGED ==="
