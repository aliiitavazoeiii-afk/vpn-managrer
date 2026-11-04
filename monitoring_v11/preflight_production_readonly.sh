#!/usr/bin/env bash
# HESAB_CONTROL_ROOM_V11_READONLY_PREFLIGHT
# Inspect actual running app, tunnel services and mounted telemetry paths.
# No secrets, no credentials, no writes, no service restarts, no git reset.
set -Eeuo pipefail
cd /opt/vpn-control-center
dc(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
echo "=== ADMIN HOST / SOURCE DIFFERENCES (READ ONLY) ==="
printf 'DATE_UTC='; date -u +%Y-%m-%dT%H:%M:%SZ
if [ -d .git ];then
 echo "LIVE_GIT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
 echo "LIVE_GIT_BRANCH=$(git branch --show-current 2>/dev/null || echo unknown)"
 echo "TRACKED_CHANGED_FILES:"
 git diff --name-only HEAD -- . ':!*.env' 2>/dev/null || true
else
 echo "LIVE_GIT=NO_CHECKOUT; compare runtime image and mounted files manually"
fi
echo "PRODUCTION_OVERLAY_MARKERS"
for marker in HESAB_CONTROL_ROOM_COMPACT_V10 HESAB_PAYMENT_TOTALS_V1 HESAB_CONTROL_ROOM_TUNNEL_TELEMETRY_V11;do
 if grep -qF "$marker" patches/maya1_control.py 2>/dev/null;then
   echo "$marker PRESENT"
 else
   echo "$marker ABSENT"
 fi
done
echo "COMPOSE_SERVICE_STATUS"
dc ps --format 'table {{.Name}}\t{{.Status}}' 2>/dev/null || dc ps
echo "PRODUCTION_PYTHON_ROUTES:"
dc exec -T app python - <<'PY'
from app import main as m
from jinja2 import Environment
routes=[r.path for r in m.app.routes if
        getattr(r,"path","").startswith("/control-room")]
print("CONTROL_ROOM_ROUTES",len(routes))
for p in ("/control-room","/control-room/v2/data","/control-room/v10/daily",
          "/control-room/maya-live/toggle","/control-room/v9/topup",
          "/control-room/v11/status"):
    print("ROUTE",p,("PRESENT" if p in routes else "MISSING"))
tpl=m.TEMPLATES.get("control_room.html","")
print("TEMPLATE_V10",("YES" if "t10-head-tools" in tpl else "NO"))
print("TEMPLATE_V11",("YES" if "tv11-overview" in tpl else "NO"))
print("TEMPLATE_CSRF",("YES" if "{{ ctrl_csrf }}" in tpl else "NO"))
Environment().parse(tpl)
import os
p="/srv/maya-live/phase1/status.json"
print("MAYA_LIVE_MOUNT",(os.path.isfile(p)))
print("TELEMETRY_MOUNT_PARENT",(os.path.isdir("/srv/maya-live")))
print("APP_UID",os.geteuid())
PY
echo "TELEMETRY_LOCAL_SERVICES"
for service in caddy nginx hesab-telemetry-v11;do
 echo "$service $(systemctl is-active "$service" 2>/dev/null || true)"
done
echo "=== CHECK SOURCE/PRODUCTION DRIFT AND VERIFIED BACKUPS BEFORE DEPLOY ==="
echo "READONLY_PREFLIGHT_COMPLETE"
