#!/usr/bin/env bash
# HESAB_MAYA_NET_METER_HUB_V2_INSTALL
# Reversible admin UI + inactive scheduled SSH meter; NO billing / XUI changes.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo "STOP: run as root on management host";exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
LIVE=patches/maya1_control.py
PATCH="$SRC/patches/control_room_net_meter_v2_ui.py"
SERVICE=/etc/systemd/system/hesab-maya-net-meter-v2.service
TIMER=/etc/systemd/system/hesab-maya-net-meter-v2.timer
FILES="maya_net_meter_sensor_v2.py maya_net_meter_remote_setup_v2.sh maya_net_meter_collect_v2.py maya_net_meter_manage_v2.py"
for f in .env docker-compose.yml docker-compose.sms.yml "$LIVE" "$PATCH";do
 [[ -s "$f" ]] || { echo "STOP: missing $f";exit 3; }
done
grep -Fq 'maya1_control.py' docker-compose.sms.yml || { echo "STOP: mounted Maya overlay absent";exit 3; }
grep -Fq './maya_extra_sync:/srv/maya-live:ro' docker-compose.sms.yml || {
 echo "STOP: readonly live telemetry mount absent";exit 3;
}
for tag in HESAB_CONTROL_ROOM_PHASE1_V1 HESAB_CONTROL_ROOM_TABLE_V3 HESAB_CONTROL_ROOM_LIVE_VISUAL_V4;do
 grep -Fq "$tag" "$LIVE" || { echo "STOP: prerequisite $tag not installed";exit 3; }
done
if grep -Fq '# HESAB_CONTROL_ROOM_NET_METER_V2_UI' "$LIVE";then
 echo "ALREADY_INSTALLED: refuse duplicate";exit 0;
fi
# Two independent writers to the same phase1/status.json would corrupt the dashboard.
if grep -Rqs -- 'phase1_iran_metrics_collect_v1.py' /etc/cron.d /etc/systemd/system 2>/dev/null;then
 echo "STOP: legacy Phase1 NIC collector is still scheduled; disable it safely before installing V2";exit 3;
fi
if [[ -e /etc/cron.d/hesab-maya-net-meter-v2 ]];then
 echo "STOP: unexpected legacy meter cron may race with systemd timer";exit 3;
fi
for name in $FILES;do
 [[ -s "$SRC/scripts/$name" ]] || { echo "STOP: missing $name";exit 3; }
done
python3 -m py_compile "$PATCH" "$SRC/scripts/maya_net_meter_sensor_v2.py" \
 "$SRC/scripts/maya_net_meter_collect_v2.py" "$SRC/scripts/maya_net_meter_manage_v2.py"
bash -n "$SRC/scripts/maya_net_meter_remote_setup_v2.sh"
compose config -q
for file in "$SERVICE" "$TIMER";do
 if [[ -e "$file" ]] && ! grep -Fq 'HESAB_MAYA_NET_METER_V2' "$file";then
  echo "STOP: existing unit belongs to another service: $file";exit 3;
 fi
done
old="$(compose ps -q app)"
[[ -n "$old" ]] && [[ "$(docker inspect -f '{{.State.Running}}' "$old")" == true ]] || {
 echo "STOP: main admin app not running";exit 3;
}
echo "=== ISOLATED JINJA PRECHECK, NO PRODUCTION WRITES ==="
cat "$PATCH" | compose exec -T app python -c '
import sys
from app import main as m
from jinja2 import Environment
assert "id=\"c4-shell\"" in m.TEMPLATES["control_room.html"]
before=[(r.path,sorted(r.methods)) for r in m.app.routes if getattr(r,"path","").startswith("/control-room")]
exec(compile(sys.stdin.read(),"<meter-ui-preflight>","exec"),vars(m))
after=[(r.path,sorted(r.methods)) for r in m.app.routes if getattr(r,"path","").startswith("/control-room")]
assert before==after
html=m.TEMPLATES["control_room.html"]
assert "m2-warning" in html and "NIC_RX" in html
assert html.count("id=\"c2-search\"")==1
Environment().parse(html)
print("MAYA_NET_METER_UI_PREFLIGHT_OK")
'
B="/root/hesab-net-meter-v2-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$B/scripts"
cp -a "$LIVE" "$B/maya1_control.py"
docker inspect -f '{{.Image}}' "$old" > "$B/app-image-before.txt"
for name in $FILES;do
 if [[ -f "scripts/$name" ]];then cp -a "scripts/$name" "$B/scripts/$name";fi
done
for file in "$SERVICE" "$TIMER";do
 if [[ -e "$file" ]];then cp -a "$file" "$B/$(basename "$file")";fi
done
CHANGED=0
rollback(){
 local rc=$?
 trap - EXIT
 if ((rc!=0 && CHANGED));then
  echo "ROLLBACK: restoring prior control room and meter units"
  cp -a "$B/maya1_control.py" "$LIVE"
  for name in $FILES;do
   if [[ -f "$B/scripts/$name" ]];then cp -a "$B/scripts/$name" "scripts/$name";
   else rm -f "scripts/$name";fi
  done
  for file in "$SERVICE" "$TIMER";do
   if [[ -f "$B/$(basename "$file")" ]];then cp -a "$B/$(basename "$file")" "$file";
   else rm -f "$file";fi
  done
  systemctl daemon-reload || true
  compose up -d --no-deps --no-build --force-recreate app || \
    echo "ROLLBACK RECREATE FAILED, restore from $B"
 fi
 exit "$rc"
}
trap rollback EXIT
CHANGED=1
mkdir -p scripts maya_extra_sync/phase1 /var/lib/hesab-maya-net-meter-v2
chmod 700 /var/lib/hesab-maya-net-meter-v2
for name in $FILES;do
 cp "$SRC/scripts/$name" "scripts/$name"
 chmod 700 "scripts/$name"
done
printf '\n\n' >>"$LIVE"
cat "$PATCH" >>"$LIVE"
python3 -m py_compile "$LIVE"
cat >"$SERVICE" <<'UNIT'
# HESAB_MAYA_NET_METER_V2
[Unit]
Description=Hesab Maya Physical Network RX/TX Meter (SSH pull)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=root
Group=root
WorkingDirectory=/opt/vpn-control-center
ExecStart=/usr/bin/python3 /opt/vpn-control-center/scripts/maya_net_meter_collect_v2.py
TimeoutStartSec=85
NoNewPrivileges=true
PrivateTmp=true
UNIT
cat >"$TIMER" <<'UNIT'
# HESAB_MAYA_NET_METER_V2
[Unit]
Description=Poll Maya physical RX/TX counters every minute

[Timer]
OnCalendar=*-*-* *:*:00
AccuracySec=10s
RandomizedDelaySec=2s
Unit=hesab-maya-net-meter-v2.service
Persistent=false

[Install]
WantedBy=timers.target
UNIT
chmod 0644 "$SERVICE" "$TIMER"
systemctl daemon-reload
compose up -d --no-deps --no-build --force-recreate app
ready=0
for i in $(seq 1 35);do
 if compose exec -T app python - <<'PY' >/dev/null 2>&1
from app import main as m
from jinja2 import Environment
t=m.TEMPLATES["control_room.html"]
assert t.count('id="m2-style"')==1
assert "مصرف مبنای سهمیه" in t
assert "HESAB_CONTROL_ROOM_NET_METER_V2_UI" in open("/app/app/main.py").read()
Environment().parse(t)
PY
 then ready=1;break;fi
 sleep 2
done
[[ "$ready" == 1 ]] || { echo "STOP: meter UI runtime verification failed";false; }
trap - EXIT
echo "SUCCESS: MAYA NETWORK METER V2 HUB INSTALLED (POLL TIMER INACTIVE)"
echo "BACKUP=$B"
echo "NEXT: pair three restricted SSH keys and verify each remote sensor."
echo "NEXT: confirm provider billable RX or TX and quota."
echo "THEN: systemctl enable --now hesab-maya-net-meter-v2.timer"
