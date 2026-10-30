#!/usr/bin/env bash
# HESAB_CONTROL_ROOM_LIVE_VISUAL_V4_INSTALL
# Scoped reversible UI plus read-only 3x-ui host-status sampler.
# No finance, server credentials, inbounds, XUI clients or dashboard landing changes.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo "STOP: root required";exit 2; }

SRC="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="/opt/vpn-control-center"
PATCH="$SRC/patches/control_room_live_visual_v4.py"
COLLECTOR_SRC="$SRC/scripts/maya_xui_host_metrics_v1.py"
LIVE="patches/maya1_control.py"
COLLECTOR_LIVE="scripts/maya_xui_host_metrics_v1.py"
TELEMETRY="maya_extra_sync/phase1/xui_status_v1.json"
CRON="/etc/cron.d/hesab-maya-xui-host-metrics"

cd "$ROOT"
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for path in .env docker-compose.yml docker-compose.sms.yml "$LIVE" "$PATCH" "$COLLECTOR_SRC"; do
 [[ -s "$path" ]] || { echo "STOP: required file missing: $path";exit 3; }
done
grep -Fq 'maya1_control.py' docker-compose.sms.yml || { echo "STOP: runtime Maya patch not mounted";exit 3; }
grep -Fq './maya_extra_sync:/srv/maya-live:ro' docker-compose.sms.yml || { echo "STOP: read-only Maya live telemetry mount missing";exit 3; }
for marker in 'HESAB_MAYA_CONTROL_ROOM_V2' 'HESAB_CONTROL_ROOM_PHASE1_V1' 'HESAB_CONTROL_ROOM_TABLE_V3';do
 grep -Fq "$marker" "$LIVE" || { echo "STOP: missing prerequisite $marker";exit 3; }
done
if grep -Fq '# HESAB_CONTROL_ROOM_LIVE_VISUAL_V4' "$LIVE";then
 echo "ALREADY_INSTALLED: V4 marker present. No duplicate installation."
 exit 0
fi
if [[ -e "$CRON" ]] && ! grep -Fq 'HESAB_MAYA_XUI_HOST_METRICS_V1' "$CRON";then
 echo "STOP: cron path already occupied by unrelated job";exit 3
fi
python3 -m py_compile "$PATCH" "$COLLECTOR_SRC"
c config -q
OLD="$(c ps -q app)"
[[ -n "$OLD" ]] && [[ "$(docker inspect -f '{{.State.Running}}' "$OLD")" == true ]] || {
 echo "STOP: admin app not healthy/running";exit 3;
}
echo "=== READ-ONLY PREFLIGHT IN SEPARATE APP PROCESS ==="
cat "$PATCH" | c exec -T app python -c '
import sys
from app import main as m
from jinja2 import Environment
code=sys.stdin.read()
assert "HESAB_CONTROL_ROOM_LIVE_VISUAL_V4" in code
before=[(r.path,sorted(r.methods)) for r in m.app.routes
        if getattr(r,"path","").startswith("/control-room")]
assert "id=\"c3-mode\"" in m.TEMPLATES["control_room.html"]
exec(compile(code,"<v4_preflight>","exec"),vars(m))
after=[(r.path,sorted(r.methods)) for r in m.app.routes
        if getattr(r,"path","").startswith("/control-room")]
assert after==before+[("/control-room/v4/host-metrics",["GET"])]
t=m.TEMPLATES["control_room.html"]
for marker in ("id=\"c4-shell\"","c4-server-card","id=\"c3-mode\"",
               "id=\"c2-users\"","mdl2-toolbar","c3Details(server,item)"):
 assert marker in t,marker
assert t.count("id=\"c2-cards\"")==1,t.count("id=\"c2-cards\"")
assert t.count("id=\"c2-search\"")==1,t.count("id=\"c2-search\"")
Environment().parse(t)
response=m._c4_status(None)
assert response.status_code==200
print("V4_LIVE_VISUAL_PREFLIGHT_OK")
'

BACKUP="/root/hesab-control-room-v4-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$BACKUP"
cp -a "$LIVE" "$BACKUP/maya1_control.py"
docker inspect -f '{{.Image}}' "$OLD" > "$BACKUP/app-image-before.txt"
for p in "$COLLECTOR_LIVE" "$TELEMETRY";do
 if [[ -e "$p" ]];then
  mkdir -p "$BACKUP/$(dirname "$p")"
  cp -a "$p" "$BACKUP/$p"
 fi
done
if [[ -e "$CRON" ]];then cp -a "$CRON" "$BACKUP/cron";fi
echo "BACKUP=$BACKUP"
CHANGED=0
rollback(){
 local rc=$?
 trap - EXIT
 if (( rc != 0 )) && (( CHANGED ));then
  echo "ROLLBACK: restore V3 Control Room, collector and cron"
  cp -a "$BACKUP/maya1_control.py" "$LIVE"
  for p in "$COLLECTOR_LIVE" "$TELEMETRY";do
   if [[ -e "$BACKUP/$p" ]];then cp -a "$BACKUP/$p" "$p";else rm -f "$p";fi
  done
  if [[ -e "$BACKUP/cron" ]];then cp -a "$BACKUP/cron" "$CRON";else rm -f "$CRON";fi
  c up -d --no-deps --no-build --force-recreate app || \
   echo "ROLLBACK RECREATE FAILED: recover from $BACKUP"
 fi
 exit "$rc"
}
trap rollback EXIT
CHANGED=1
mkdir -p scripts maya_extra_sync/phase1
chmod 750 maya_extra_sync/phase1
cp "$COLLECTOR_SRC" "$COLLECTOR_LIVE"
chmod 700 "$COLLECTOR_LIVE"
python3 -m py_compile "$COLLECTOR_LIVE"

echo "=== ONE READ-ONLY XUI CPU/RAM POLL ==="
# Unsupported server/status versions are recorded as unavailable, not fatal.
python3 "$COLLECTOR_LIVE"

echo "=== INSTALL CONTROL ROOM VISUAL ==="
printf '\n\n' >> "$LIVE"
cat "$PATCH" >> "$LIVE"
python3 -m py_compile "$LIVE"
c up -d --no-deps --no-build --force-recreate app

READY=0
for i in $(seq 1 35);do
 if c exec -T app python - <<'PY' >/dev/null 2>&1
from app import main as m
from jinja2 import Environment
paths=[r.path for r in m.app.routes]
for path in ("/control-room","/control-room/v2/data",
             "/control-room/phase1/status","/control-room/v4/host-metrics",
             "/control-room/maya-live/toggle"):
 assert paths.count(path)==1,path
t=m.TEMPLATES["control_room.html"]
assert t.count('id="c4-shell"')==1
assert t.count('id="c2-cards"')==1
assert t.count('id="c2-search"')==1
assert 'c4FetchMetrics()' in t
assert 'id="c3-mode"' in t
assert 'mdl2-toolbar' in t
Environment().parse(t)
assert m._c4_status(None).status_code==200
PY
 then READY=1;break;fi
 sleep 2
done
[[ "$READY" == 1 ]] || { echo "STOP: V4 runtime Jinja/API not verified";false; }

echo "=== SCHEDULE READ-ONLY HOST METRICS ==="
cat >"$CRON" <<'CRONDEF'
# HESAB_MAYA_XUI_HOST_METRICS_V1 - GET /panel/api/server/status only
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
*/2 * * * * root /usr/bin/python3 /opt/vpn-control-center/scripts/maya_xui_host_metrics_v1.py >> /var/log/hesab-maya-xui-host-metrics.log 2>&1
CRONDEF
chmod 644 "$CRON"
grep -Fq 'HESAB_MAYA_XUI_HOST_METRICS_V1' "$CRON"
trap - EXIT
echo "SUCCESS: CONTROL ROOM LIVE VISUAL V4 INSTALLED"
if systemctl is-active --quiet cron;then
 echo "XUI_SNAPSHOT_METRICS=READ_ONLY_EVERY_2_MINUTES"
else
 echo "WARNING: cron service is inactive; periodic CPU/RAM refresh is not yet running"
fi
echo "BACKUP=$BACKUP"
echo "NOTE: Purchased-provider traffic quota is not sourced by 3x-ui status; stays unknown until verified."
