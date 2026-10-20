#!/usr/bin/env bash
# HESAB_MAYA_EXTRA_READONLY_INSTALL_V1: safe Maya S3 / Maya4 dashboard extension.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo 'STOP: sudo/root required'; exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
test -s "$SRC/scripts/maya_multi_panel_sync.py"
test -s "$SRC/patches/maya_extra_panel.py"
test -s patches/maya1_control.py || { echo "STOP: Maya1 integration missing"; exit 3; }
grep -Fq '# MAYA1_CONTROL_VIEW_V1' patches/maya1_control.py || { echo 'STOP: existing Maya1 view not found'; exit 3; }
grep -Fq 'maya1_control.py' docker-compose.sms.yml || { echo 'STOP: Maya1 mount missing'; exit 3; }
grep -Fq 'maya1_sync' docker-compose.sms.yml || { echo 'STOP: Maya1 snapshot mount missing'; exit 3; }
c config -q
python3 -m py_compile "$SRC/patches/maya_extra_panel.py" "$SRC/scripts/maya_multi_panel_sync.py"
if grep -Fq '# HESAB_MAYA_EXTRA_DASHBOARD_V1' patches/maya1_control.py; then
  echo "ALREADY_INSTALLED: Maya S3/Maya4 read-only views exist"; exit 0
fi
BACKUP="/opt/hesab-backups/maya-extra-ro-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACKUP"
cp -a patches/maya1_control.py "$BACKUP/maya1_control.py"
cp -a docker-compose.sms.yml "$BACKUP/docker-compose.sms.yml"
mkdir -p scripts maya_extra_sync/public
chmod 750 maya_extra_sync maya_extra_sync/public
# No database mutation at all. Existing Maya1 snapshot, mappings, and control service untouched.
CHANGED=0
rollback(){
  trap - ERR
  if [[ "$CHANGED" == "1" ]]; then
    cp -a "$BACKUP/maya1_control.py" patches/maya1_control.py
    cp -a "$BACKUP/docker-compose.sms.yml" docker-compose.sms.yml
    rm -f /etc/cron.d/hesab-maya-extra-readonly
    c up -d --no-deps --no-build --force-recreate app || true
  fi
  echo "BACKUP=$BACKUP";exit 1
}
trap rollback ERR
CHANGED=1
cp -a "$SRC/scripts/maya_multi_panel_sync.py" scripts/maya_multi_panel_sync.py
chmod 700 scripts/maya_multi_panel_sync.py
cat "$SRC/patches/maya_extra_panel.py" >> patches/maya1_control.py
python3 -m py_compile patches/maya1_control.py
python3 - <<'PY'
from pathlib import Path
p=Path("docker-compose.sms.yml")
s=p.read_text()
marker="      - ./maya1_sync:/srv/maya1-sync:ro\n"
assert s.count(marker)==1, "Maya1 mount changed; STOP"
assert "./maya_extra_sync/public:" not in s, "Maya extra mount already exists"
s=s.replace(marker,marker+"      - ./maya_extra_sync/public:/srv/maya-extra-sync:ro\n",1)
p.write_text(s)
PY
c config -q
c up -d --no-deps --no-build --force-recreate app
READY=0
for i in $(seq 1 30); do
 if c exec -T app python - <<'PY' >/dev/null 2>&1
from app.main import TEMPLATES
assert "HESAB_MAYA_EXTRA_DASHBOARD_V1" in open("/app/app/main.py").read()
assert "maya_extra_reports" in TEMPLATES["control_room.html"]
assert "سرورهای جدید مایا" in TEMPLATES["control_room.html"]
PY
 then READY=1;break;fi
 sleep 2
done
test "$READY" == 1
if ! systemctl is-active --quiet cron; then
 echo 'WARNING: cron inactive. Set it up before expecting auto-refresh.'
else
 cat >/etc/cron.d/hesab-maya-extra-readonly <<'CRON'
*/5 * * * * root /usr/bin/flock -n /run/hesab-maya-extra-sync.lock /usr/bin/python3 /opt/vpn-control-center/scripts/maya_multi_panel_sync.py sync >> /var/log/hesab-maya-extra-sync.log 2>&1
CRON
 chmod 644 /etc/cron.d/hesab-maya-extra-readonly
fi
trap - ERR
echo 'SUCCESS: Maya S3 and Maya4 read-only sections installed; no live server connected yet.'
echo 'NEXT (locally, on this server):'
echo '  sudo python3 /opt/vpn-control-center/scripts/maya_multi_panel_sync.py configure maya-s3'
echo '  sudo python3 /opt/vpn-control-center/scripts/maya_multi_panel_sync.py configure maya4'
echo '  sudo python3 /opt/vpn-control-center/scripts/maya_multi_panel_sync.py sync'
echo 'Use a valid HTTPS 3x-ui URL and panel API token; credentials remain root-only.'
echo "BACKUP=$BACKUP"
