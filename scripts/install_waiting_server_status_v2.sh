#!/usr/bin/env bash
# HESAB_WAITING_SERVER_STATUS_V2_INSTALL
# Only updates /followups template in admin app. No panel, DB, cron or user changes.
set -Eeuo pipefail
umask 077
[[ $(id -u) == 0 ]] || { echo "STOP: sudo/root required";exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
BASE=/opt/vpn-control-center
cd "$BASE"
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
test -s patches/maya1_control.py
test -s "$SRC/patches/waiting_server_status_v2.py"
python3 -m py_compile "$SRC/patches/waiting_server_status_v2.py"
for marker in HESAB_WAITING_SERVER_STATUS_V1 HESAB_MAYA_MANUAL_LINKS_V1;do
 grep -Fq "$marker" patches/maya1_control.py || {
   echo "STOP: missing installed $marker";exit 3;
 }
done
c config -q
backup="/opt/hesab-backups/waiting-layout-v2-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$backup"
cp -a patches/maya1_control.py "$backup/maya1_control.py"
changed=0
rollback(){
 trap - ERR
 if [[ "$changed" == 1 ]];then
   echo "RESTORING: old waiting layout from backup"
   cp -a "$backup/maya1_control.py" patches/maya1_control.py
   c up -d --no-deps --no-build --force-recreate app || true
 fi
 echo "Backup: $backup"
 exit 1
}
trap rollback ERR
if ! grep -Fq '# HESAB_WAITING_SERVER_STATUS_V2' patches/maya1_control.py;then
 changed=1
 printf '\n\n' >> patches/maya1_control.py
 cat "$SRC/patches/waiting_server_status_v2.py" >> patches/maya1_control.py
 python3 -m py_compile patches/maya1_control.py
 c up -d --no-deps --no-build --force-recreate app
else
 echo "RESUME: waiting V2 already present; verifying."
fi
ready=0
for i in $(seq 1 15);do
 if c exec -T app python - <<'PY' >/dev/null 2>&1
from app.main import app,TEMPLATES
from pathlib import Path
from jinja2 import Environment
src=Path("/app/app/main.py").read_text()
assert "HESAB_WAITING_SERVER_STATUS_V2" in src
tpl=TEMPLATES.get("followups.html","")
assert 'class="wss-summary"' not in tpl
assert 'class="wss-child"' not in tpl
assert 'data-waiting-v2-status-btn' in tpl
assert tpl.count('data-waiting-v2-filter="blocked"')==1
assert 'data-waiting-v2-filter="active"' in tpl
assert 'id="waiting-search"' in tpl
assert 'data-wss-sid="{{ s.id }}"' in tpl
assert "/followups/restore-group" in tpl
assert "/followups/pay-group" in tpl
assert "data-waiting-renewal-form" in tpl
assert "data-waiting-sms-reminder-box" in tpl
assert tpl.count("window.__hesabWaitingStatusV2")==2
assert "window.__hesabWaitingStatusV1" not in tpl
assert sum(getattr(r,"path",None)=="/followups" and "GET" in
           (getattr(r,"methods",set()) or set()) for r in app.routes)==1
Environment().parse(tpl)
PY
 then ready=1;break;fi
 sleep 2
done
if [[ "$ready" != 1 ]];then
 echo "STOP: waiting UI smoke test did not pass; no payment/account changes made."
 echo "CHECK: sanitized smoke below (no env/secrets)"
 c exec -T app python - <<'PY' || true
from app.main import TEMPLATES
s=TEMPLATES.get("followups.html","")
print("Template found:",bool(s))
for x in ('data-waiting-v2-status-btn','class="wss-summary"','data-waiting-v2-filter="blocked"','/followups/pay-group','/followups/restore-group'):
 print(x, s.count(x))
PY
 false
fi
trap - ERR
echo "SUCCESS: /followups compact search + status filter/action button installed."
echo "No DB, Maya XUI, Shahan SSH or automatic payment/control logic changed."
echo "Backup: $backup"
