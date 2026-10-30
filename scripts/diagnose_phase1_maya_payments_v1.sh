#!/usr/bin/env bash
# HESAB_PHASE1_READONLY_DIAG_V1 — no financial/XUI/SSH/config writes
set -Eeuo pipefail
cd /opt/vpn-control-center
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
echo "=== CONTROL ROOM / PAYMENT SAFETY DIAGNOSTIC — READ ONLY ==="
echo "CURRENT_UTC=$(date -u +%FT%TZ)"
echo "-- COMPOSE SERVICES --"
c ps
echo "-- MAYA LIVE SOCKET --"
if systemctl is-active --quiet hesab-maya-live.service;then echo MAYA_BROKER=ACTIVE;else echo MAYA_BROKER=NOT_ACTIVE;fi
if test -S maya_extra_sync/live.sock;then echo MAYA_SOCKET=PRESENT;else echo MAYA_SOCKET=MISSING;fi
echo "-- SAVED MAYA CONNECTION KIND, NO AUTH OR PRIVATE PATHS --"
python3 - <<'PY'
from pathlib import Path
import json,datetime
p=Path("/root/.config/hesab-maya-extra.json")
try:
 c=json.loads(p.read_text()) if p.is_file() else {}
 for k in ("maya1","maya-s3","maya4"):
  entry=c.get(k)
  if not isinstance(entry,dict):print("CONFIG",k,"NOT_CONFIGURED");continue
  print("CONFIG",k,"transport="+str(entry.get("transport","https")),
        "server="+str(entry.get("server","unknown")),
        "ssh_host="+str(entry.get("ssh_host","unset")) if entry.get("transport")=="ssh" else "url_host=[hidden]",
        "panel_auth="+str(entry.get("mode","unknown")))
except Exception as e:print("CONFIG_ERROR",type(e).__name__)
for key in ("maya1","maya-s3","maya4"):
 p=Path("/opt/vpn-control-center/maya_extra_sync/public")/(key+".json")
 if p.is_file():
  age=(datetime.datetime.now(datetime.timezone.utc).timestamp()-p.stat().st_mtime)/60
  print("SYNC_FILE",key,"age_min=",round(age,1),"bytes=",p.stat().st_size)
 else:print("SYNC_FILE",key,"ABSENT")
PY
echo "-- MAYA1 LIVE READONLY PANEL CHECK --"
if test -f scripts/maya_multi_panel_sync.py;then
 timeout 90 python3 scripts/maya_multi_panel_sync.py check maya1 2>&1 |
   sed -E 's/(password|token|api_key|secret)[= :]+[^ ]+/\1=[REDACTED]/gi' | tail -12 || true
fi
echo "-- WORKER HEARTBEAT AND AGGREGATE PAYMENT CONTROL STATES --"
c exec -T app python - <<'PY'
from pathlib import Path
from datetime import datetime,timezone
from sqlalchemy import text
import json
from app import main as m
print("RESTORE_OVERLAYS",{
 "v2":hasattr(m,"_wvr_restore_one"),
 "v3":hasattr(m,"_wvr3_lifespan"),
 "lifespan_v3_active":getattr(m.app.router,"lifespan_context",None) is getattr(m,"_wvr3_lifespan",None)
})
p=Path("/tmp/hesab-waiting-worker-v3.json")
if p.is_file():
 try:
  h=json.loads(p.read_text())
  print("WORKER_HEARTBEAT",{
   "stage":h.get("stage"),"scans":h.get("scan_completed"),
   "errors":h.get("errors"),
   "age_seconds":round(datetime.now(timezone.utc).timestamp()-h.get("heartbeat_at",0),1)
  })
 except Exception as e:print("WORKER_HEARTBEAT_ERROR",type(e).__name__)
else:print("WORKER_HEARTBEAT=MISSING")
g=m.get_db();db=next(g)
try:
 db.execute(text("SET TRANSACTION READ ONLY"))
 q="""SELECT c.server,c.state,COUNT(*) AS cnt,
 SUM(CASE WHEN EXISTS (
  SELECT 1 FROM payments p WHERE p.subscription_id=c.subscription_id
    AND p.id>c.payment_watermark AND p.amount_toman>0
 ) THEN 1 ELSE 0 END) AS with_new_payments
 FROM waiting_vpn_controls c GROUP BY c.server,c.state ORDER BY c.server,c.state"""
 for r in db.execute(text(q)).mappings():
  print("WAITING_CONTROL_GROUP",r["server"],r["state"],
        "count="+str(r["cnt"]),"post_cut_payment="+str(r["with_new_payments"]))
 print("RESTORE_NEEDS_REVIEW_COUNT",db.execute(text(
   "SELECT COUNT(*) FROM waiting_vpn_controls WHERE state='needs_review'"
 )).scalar())
 q="""SELECT c.subscription_id,c.server,c.state,c.restore_attempts,
 c.last_restore_error
 FROM waiting_vpn_controls c
 WHERE c.state IN ('needs_review','activating')
 ORDER BY c.updated_at DESC LIMIT 12"""
 for r in db.execute(text(q)).mappings():
  print("REVIEW_SID",int(r["subscription_id"]),"server",r["server"],
        "state",r["state"],"attempts",r["restore_attempts"] or 0,
        "error_type",str(r["last_restore_error"] or "").split(":")[0][:45])
except Exception as e:print("CONTROL_READ_ERROR",type(e).__name__)
finally:
 db.rollback();g.close()
PY
echo "-- RECENT WORKER ERROR TYPES ONLY --"
c logs --since 4h --tail 250 app 2>&1 |
 grep -E 'WVR3_SCAN_ERROR|WVR_WORKER_ROW_ERROR|WVR_RESTORE_CONFIRMED|WVR3_WORKER_STARTED' |
 sed -E 's/(password|token|api_key|secret)[= :]+[^ ]+/\1=[REDACTED]/gi' | tail -35 || true
echo "=== DONE. NO XUI, ACCOUNT, FINANCE, SSH OR CONFIG CHANGES ==="
