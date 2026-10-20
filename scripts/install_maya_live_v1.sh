#!/usr/bin/env bash
# HESAB_MAYA_LIVE_3SERVER_INSTALL_V1: Maya1, S3, Maya4 live API + guarded toggles.
# Never installs/updates x-ui itself. No automatic user disable. No financial DB writes.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo 'STOP: run as root'; exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for f in .env docker-compose.yml docker-compose.sms.yml patches/maya1_control.py; do
 [[ -s "$f" ]] || { echo "STOP: missing production $f"; exit 3; }
done
for f in scripts/maya_multi_panel_sync.py scripts/maya_live_bridge.py patches/maya_live_dashboard.py; do
 test -s "$SRC/$f" || { echo "STOP: source missing $f"; exit 3; }
 python3 -m py_compile "$SRC/$f"
done
c config -q
grep -Fq '# MAYA1_CONTROL_VIEW_V1' patches/maya1_control.py || {
 echo 'STOP: expected Maya1 control view absent; leave production unchanged'; exit 3;
}
grep -Fq 'maya1_control.py' docker-compose.sms.yml || {
 echo 'STOP: existing Maya1 patch not mounted'; exit 3;
}
grep -Fq 'maya1_sync' docker-compose.sms.yml || {
 echo 'STOP: existing Maya1 mapping not mounted'; exit 3;
}
if grep -Fq '# HESAB_MAYA_LIVE_DASHBOARD_V1' patches/maya1_control.py; then
 echo 'ALREADY_INSTALLED: live Maya dashboard exists.'; exit 0
fi
# Do not require Jinja2 on the Ubuntu host. Validate the template using
# the existing running app container where the production Jinja version lives.
# The host performs file/route checks and pipes ONLY the template source.
python3 - "$SRC" <<'PY' | c exec -T app python -c '
import sys
from jinja2 import Environment
text=sys.stdin.read()
assert text.strip(), "Empty dashboard template"
Environment().parse(text)
print("PASS: live dashboard Jinja template validated inside app container")
'
import sys,re
from pathlib import Path
source=Path(sys.argv[1])
p=(source/"patches/maya_live_dashboard.py").read_text(encoding="utf-8")
m=re.search(r"_ML_SECTION=r'''([\s\S]*?)'''",p)
assert m, "Dashboard section not found"
assert "app.add_api_route" in p and "maya-live/toggle" in p
assert "maya1" in (source/"scripts/maya_multi_panel_sync.py").read_text()
sys.stdout.write(m.group(1))
PY
BACKUP="/opt/hesab-backups/maya-live-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACKUP"
cp -a patches/maya1_control.py "$BACKUP/maya1_control.py"
cp -a docker-compose.sms.yml "$BACKUP/docker-compose.sms.yml"
if test -e /etc/systemd/system/hesab-maya-live.service; then
 cp -a /etc/systemd/system/hesab-maya-live.service "$BACKUP/live.service"
fi
mkdir -p scripts maya_extra_sync
chmod 750 maya_extra_sync
CHANGED=0
rollback(){
 trap - ERR
 if [[ "$CHANGED" == 1 ]]; then
  echo 'INSTALL FAILED; rolling back UI/service files (no finance was touched).'
  cp -a "$BACKUP/maya1_control.py" patches/maya1_control.py
  cp -a "$BACKUP/docker-compose.sms.yml" docker-compose.sms.yml
  if [[ -f "$BACKUP/live.service" ]]; then
   cp -a "$BACKUP/live.service" /etc/systemd/system/hesab-maya-live.service
   systemctl daemon-reload
   systemctl restart hesab-maya-live.service || true
  else
   systemctl stop hesab-maya-live.service || true
   systemctl disable hesab-maya-live.service || true
   rm -f /etc/systemd/system/hesab-maya-live.service
   systemctl daemon-reload
  fi
  c up -d --no-deps --no-build --force-recreate app || true
 fi
 echo "Backup retained: $BACKUP"
 exit 1
}
trap rollback ERR
CHANGED=1
cp -a "$SRC/scripts/maya_multi_panel_sync.py" scripts/maya_multi_panel_sync.py
cp -a "$SRC/scripts/maya_live_bridge.py" scripts/maya_live_bridge.py
chmod 700 scripts/maya_multi_panel_sync.py scripts/maya_live_bridge.py
printf '\n\n' >> patches/maya1_control.py
cat "$SRC/patches/maya_live_dashboard.py" >> patches/maya1_control.py
python3 -m py_compile patches/maya1_control.py
python3 - <<'PY'
from pathlib import Path
p=Path("docker-compose.sms.yml")
s=p.read_text()
mount='      - ./maya1_sync:/srv/maya1-sync:ro\n'
assert s.count(mount)==1,"Unexpected Maya1 snapshot mount"
if './maya_extra_sync:/srv/maya-live:ro' not in s:
 s=s.replace(mount,mount+'      - ./maya_extra_sync:/srv/maya-live:ro\n',1)
p.write_text(s)
PY
c config -q
cat >/etc/systemd/system/hesab-maya-live.service <<'UNIT'
[Unit]
Description=Hesab Maya1/S3/Maya4 verified 3x-ui control (local Unix socket)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/vpn-control-center
ExecStart=/usr/bin/python3 /opt/vpn-control-center/scripts/maya_live_bridge.py
Restart=always
RestartSec=3
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now hesab-maya-live.service
systemctl restart hesab-maya-live.service
for i in $(seq 1 25); do
 if systemctl is-active --quiet hesab-maya-live.service && test -S maya_extra_sync/live.sock;then break;fi
 sleep 1
done
test -S maya_extra_sync/live.sock
c up -d --no-deps --no-build --force-recreate app
READY=0
for i in $(seq 1 35); do
 if c exec -T app python - <<'PY' >/dev/null 2>&1
from app.main import app,TEMPLATES
import socket
assert sum(r.path=="/control-room/maya-live/data" for r in app.routes)==1
assert sum(r.path=="/control-room/maya-live/toggle" for r in app.routes)==1
assert 'HESAB_MAYA_LIVE_DASHBOARD_V1' in open("/app/app/main.py").read()
assert 'id="ml-view"' in TEMPLATES["control_room.html"]
assert '/srv/maya-live/live.sock' is not None
with socket.socket(socket.AF_UNIX) as sock:
 sock.settimeout(2)
 sock.connect("/srv/maya-live/live.sock")
PY
 then READY=1;break;fi
 sleep 2
done
test "$READY" == 1
trap - ERR
echo 'SUCCESS: live Maya1/S3/Maya4 UI and root-only broker installed.'
echo 'No X-UI clients changed during installation; no automatic actions enabled.'
echo 'Configure the 3 server panel URLs and passwords locally:'
echo '  sudo python3 /opt/vpn-control-center/scripts/maya_multi_panel_sync.py configure maya1'
echo '  sudo python3 /opt/vpn-control-center/scripts/maya_multi_panel_sync.py configure maya-s3'
echo '  sudo python3 /opt/vpn-control-center/scripts/maya_multi_panel_sync.py configure maya4'
echo 'Note: use username/password login (L) when no API token exists.'
echo "Backup: $BACKUP"
