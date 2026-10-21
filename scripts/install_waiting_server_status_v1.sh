#!/usr/bin/env bash
# HESAB_WAITING_SERVER_STATUS_INSTALL_V1: read-only labels inside /followups.
# Does not touch payments, user flags, Shahan SSH, XUI, customer portal or dashboard.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == "0" ]] || { echo "STOP: run as root";exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
BASE=/opt/vpn-control-center
cd "$BASE"
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for f in .env docker-compose.yml docker-compose.sms.yml patches/maya1_control.py;do
 test -s "$f" || { echo "STOP: missing $f";exit 3; }
done
for marker in HESAB_MAYA_LIVE_DASHBOARD_V1 HESAB_MAYA_MANUAL_LINKS_V1 HESAB_MAYA_CONTROL_ROOM_V2;do
 grep -Fq "$marker" patches/maya1_control.py || { echo "STOP: missing installed $marker";exit 3; }
done
# Already running and supported usage sampler cron; NO new SSH poller/daemon.
test -f /etc/cron.d/hesab-maya-usage || {
 echo "STOP: 5-minute Maya sampler cron is not installed";exit 3;
}
grep -Fq maya_usage_sampler_v1.py /etc/cron.d/hesab-maya-usage || {
 echo "STOP: Maya usage sampler cron is different";exit 3;
}
grep -Fq '/srv/maya-live:ro' docker-compose.sms.yml || {
 echo "STOP: read-only Maya data mount missing";exit 3;
}
for f in patches/waiting_server_status_v1.py scripts/maya_usage_sampler_v1.py scripts/build_shahan_waiting_status_v1.py;do
 test -s "$SRC/$f"
 python3 -m py_compile "$SRC/$f"
done
c config -q
BACKUP="/opt/hesab-backups/waiting-status-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACKUP"
cp -a patches/maya1_control.py "$BACKUP/maya1_control.py"
if test -f scripts/maya_usage_sampler_v1.py;then
 cp -a scripts/maya_usage_sampler_v1.py "$BACKUP/maya_usage_sampler_v1.py"
fi
if test -f maya_extra_sync/shahan_waiting_status_v1.json;then
 cp -a maya_extra_sync/shahan_waiting_status_v1.json "$BACKUP/shahan_waiting_status_v1.json"
fi
modified=0
rollback(){
 trap - ERR
 if [[ "$modified" == 1 ]];then
  echo "ROLLBACK: waiting layout patch / Maya sampler restoration"
  cp -a "$BACKUP/maya1_control.py" patches/maya1_control.py
  if test -f "$BACKUP/maya_usage_sampler_v1.py";then
   cp -a "$BACKUP/maya_usage_sampler_v1.py" scripts/maya_usage_sampler_v1.py
  fi
  if test -f "$BACKUP/shahan_waiting_status_v1.json";then
   cp -a "$BACKUP/shahan_waiting_status_v1.json" maya_extra_sync/shahan_waiting_status_v1.json
  fi
  c up -d --no-deps --no-build --force-recreate app || true
 fi
 echo "Backup: $BACKUP"
 exit 1
}
trap rollback ERR
mkdir -p scripts maya_extra_sync
modified=1
cp "$SRC/scripts/maya_usage_sampler_v1.py" scripts/maya_usage_sampler_v1.py
cp "$SRC/scripts/build_shahan_waiting_status_v1.py" scripts/build_shahan_waiting_status_v1.py
chmod 700 scripts/maya_usage_sampler_v1.py scripts/build_shahan_waiting_status_v1.py
# Only local MariaDB information transferred earlier; NO contact with Shahan.
python3 scripts/build_shahan_waiting_status_v1.py
if ! grep -Fq '# HESAB_WAITING_SERVER_STATUS_V1' patches/maya1_control.py;then
 printf '\n\n' >> patches/maya1_control.py
 cat "$SRC/patches/waiting_server_status_v1.py" >> patches/maya1_control.py
 python3 -m py_compile patches/maya1_control.py
 c up -d --no-deps --no-build --force-recreate app
else
 echo "RESUME: status patch present, verifying after data-source refresh"
fi
OK=0
for i in $(seq 1 15);do
 if c exec -T app python - <<'PY' >/dev/null 2>&1
from app.main import app,TEMPLATES,_wss_status_data
from jinja2 import Environment
from pathlib import Path
assert "HESAB_WAITING_SERVER_STATUS_V1" in Path("/app/app/main.py").read_text()
assert callable(_wss_status_data)
tpl=TEMPLATES.get("followups.html","")
assert tpl.count('class="wss-summary"')==1
assert tpl.count('data-wss-sid="{{ s.id }}"')==1
assert tpl.count('class="wss-child"')==1
assert tpl.count('data-waiting-toggle')>=1
assert "/followups/pay-group" in tpl or "/followups/{{ s.id }}/pay" in tpl
assert sum(getattr(r,"path",None)=="/followups" and
           "GET" in (getattr(r,"methods",set()) or set()) for r in app.routes)==1
assert sum(getattr(r,"path",None)=="/followups/connection-status" and
           "GET" in (getattr(r,"methods",set()) or set()) for r in app.routes)==1
Environment().parse(tpl)
PY
 then OK=1;break;fi
 sleep 2
done
if [[ "$OK" != "1" ]];then
 echo "STOP: waiting template/runtime smoke check failed"
 false
fi
# Same existing sampler already used for bandwidth every 5 minutes. One-shot
# status baseline (no new timer/cron) so initial waiting labels don't stay blank.
if ! python3 scripts/maya_usage_sampler_v1.py;then
 echo "NOTE: first Maya access sample failed; existing 5-minute cron will retry."
fi
trap - ERR
echo "SUCCESS: waiting server status UI installed with unchanged compact row height."
echo "STATUS: Shahan is MANUAL SNAPSHOT only; no SSH or XUI toggle or automation."
echo "NOTE: Refresh /followups with Ctrl+F5."
echo "Backup: $BACKUP"
