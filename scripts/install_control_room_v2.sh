#!/usr/bin/env bash
# HESAB_CONTROL_ROOM_V2_INSTALL: modify /control-room ONLY, without homepage/dashboard changes.
# Finance untouched, customer portal untouched. Daily usage only on local SQLite.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP: run as root";exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for f in .env docker-compose.yml docker-compose.sms.yml patches/maya1_control.py; do
 test -s "$f" || { echo "STOP: missing $f";exit 3; }
done
grep -Fq 'HESAB_MAYA_LIVE_DASHBOARD_V1' patches/maya1_control.py || {
 echo 'STOP: live Maya integration not installed; no changes';exit 3;
}
grep -Fq '/srv/maya-live:ro' docker-compose.sms.yml || {
 echo 'STOP: required Maya live data mount missing; no changes';exit 3;
}
if grep -Fq 'HESAB_MAYA_CONTROL_ROOM_V2' patches/maya1_control.py; then
 echo 'ALREADY_INSTALLED: no files modified';exit 0;
fi
for file in patches/control_room_v2.py scripts/maya_usage_sampler_v1.py; do
 test -s "$SRC/$file" || { echo "STOP: missing $SRC/$file";exit 3; }
 python3 -m py_compile "$SRC/$file"
done
c config -q
# Parse new template with existing application's actual Jinja2, not system python.
python3 - "$SRC/patches/control_room_v2.py" <<'PY' | c exec -T app python -c '
import sys
from jinja2 import Environment
Environment().parse(sys.stdin.read())
print("PASS: Control Room V2 template parsed in app container")
'
import ast,sys
with open(sys.argv[1],encoding="utf-8") as f:tree=ast.parse(f.read())
target=next(n.value for n in tree.body if isinstance(n,ast.Assign) and
            any(isinstance(t,ast.Name) and t.id=="_CR2_TEMPLATE" for t in n.targets))
sys.stdout.write(ast.literal_eval(target))
PY
BACKUP="/opt/hesab-backups/control-room-v2-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACKUP"
cp -a patches/maya1_control.py "$BACKUP/maya1_control.py"
test ! -e /etc/cron.d/hesab-maya-usage || cp -a /etc/cron.d/hesab-maya-usage "$BACKUP/cron"
CHANGED=0
rollback(){
 trap - ERR
 if [[ "$CHANGED" == 1 ]]; then
   echo 'ROLLBACK: restoring previous control room code/cron.'
   cp -a "$BACKUP/maya1_control.py" patches/maya1_control.py
   if [[ -f "$BACKUP/cron" ]]; then
      cp -a "$BACKUP/cron" /etc/cron.d/hesab-maya-usage
   else
      rm -f /etc/cron.d/hesab-maya-usage
   fi
   c up -d --no-deps --no-build --force-recreate app || true
 fi
 echo "Backup: $BACKUP"
 exit 1
}
trap rollback ERR
CHANGED=1
mkdir -p scripts maya_extra_sync
chmod 750 maya_extra_sync
cp "$SRC/scripts/maya_usage_sampler_v1.py" scripts/maya_usage_sampler_v1.py
chmod 700 scripts/maya_usage_sampler_v1.py
# First confirm live paths without touching usage DB.
python3 scripts/maya_usage_sampler_v1.py --check
printf '\n\n' >> patches/maya1_control.py
cat "$SRC/patches/control_room_v2.py" >> patches/maya1_control.py
python3 -m py_compile patches/maya1_control.py
# Recreate ONLY admin web, not DB/SMS/customer portal/other services.
c up -d --no-deps --no-build --force-recreate app
READY=0
for i in $(seq 1 35); do
 if c exec -T app python - <<'PY' >/dev/null 2>&1
from app.main import app,TEMPLATES
from jinja2 import Environment
names={r.path for r in app.routes if "GET" in (r.methods or set())}
assert "/control-room" in names
assert "/control-room/v2/data" in names
assert sum(r.path=="/control-room" and "GET" in (r.methods or set()) for r in app.routes)==1
tpl=TEMPLATES["control_room.html"]
assert 'HESAB_MAYA_CONTROL_ROOM_V2' in open("/app/app/main.py").read()
assert 'id="c2-cards"' in tpl
assert "iran_servers" not in tpl and "foreign_servers" not in tpl
assert 'id="c2-top-today"' in tpl and 'id="c2-top-30"' in tpl
Environment().parse(tpl)
PY
 then READY=1;break;fi
 sleep 2
done
test "$READY" == 1
# First two observations create the daily traffic baseline; never treat
# historical lifetime counters as today's traffic.
python3 scripts/maya_usage_sampler_v1.py
cat >/etc/cron.d/hesab-maya-usage <<'CRON'
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
*/5 * * * * root /usr/bin/python3 /opt/vpn-control-center/scripts/maya_usage_sampler_v1.py >> /var/log/hesab-maya-usage.log 2>&1
CRON
chmod 644 /etc/cron.d/hesab-maya-usage
trap - ERR
echo 'SUCCESS: Control Room V2 installed with live Maya cards and sampled usage.'
echo 'ONLY /control-room template and GET/data endpoints changed; home dashboard unchanged.'
echo 'No XUI clients toggled; NO 22:00 automation enabled.'
echo "Backup: $BACKUP"
