#!/usr/bin/env bash
# HESAB_WAITING_VPN_CONTROL_V1_INSTALL
# Install operator-triggered disable + payment-confirmed enable ONLY for Maya XUI.
# No timed cutoffs, Shahan changes, XUI mutations during installation,
# billing data edits, payment route edits, or extra panel polling.
set -Eeuo pipefail
umask 077
[[ $(id -u) -eq 0 ]] || { echo "STOP: run as root";exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
BASE=/opt/vpn-control-center
cd "$BASE"
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for f in patches/maya1_control.py .env docker-compose.yml docker-compose.sms.yml;do
 test -s "$f" || { echo "STOP: missing $f";exit 3; }
done
test -s "$SRC/patches/waiting_vpn_control_v1.py"
python3 -m py_compile "$SRC/patches/waiting_vpn_control_v1.py"
for marker in HESAB_MAYA_MANUAL_LINKS_V1 HESAB_WAITING_SERVER_STATUS_V2;do
 grep -Fq "$marker" patches/maya1_control.py || {
   echo "STOP: first install verified Maya links and waiting UI V2 ($marker)";exit 3;
 }
done
grep -Fq "/srv/maya-live:ro" docker-compose.sms.yml || {
 echo "STOP: existing read-only Maya broker socket mount missing";exit 3;
}
test -S maya_extra_sync/live.sock || { echo "STOP: XUI control broker unavailable";exit 3; }
c config -q
backup="/opt/hesab-backups/waiting-vpn-controls-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$backup"
cp -a patches/maya1_control.py "$backup/maya1_control.py"
changed=0
rollback(){
 trap - ERR
 if [[ "$changed" == 1 ]];then
   echo "ROLLBACK: old web app patch file restored"
   cp -a "$backup/maya1_control.py" patches/maya1_control.py
   c up -d --no-deps --no-build --force-recreate app || true
 fi
 echo "The isolated waiting_vpn_controls database table is not financial data and is retained."
 echo "Backup: $backup"
 exit 1
}
trap rollback ERR
echo "=== ADD ISOLATED CONTROL JOURNAL (NOT A FINANCIAL TABLE) ==="
c exec -T db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
BEGIN;
CREATE TABLE IF NOT EXISTS waiting_vpn_controls (
  id BIGSERIAL PRIMARY KEY,
  subscription_id INTEGER NOT NULL,
  server TEXT NOT NULL CHECK (server IN ('maya1','maya-s3','maya4')),
  email VARCHAR(160) NOT NULL,
  state VARCHAR(24) NOT NULL CHECK (state IN
    ('disabling','disabled','activating','restored','needs_review')),
  payment_watermark BIGINT NOT NULL DEFAULT 0,
  disabled_at TIMESTAMPTZ,
  activated_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(subscription_id,server,email)
);
CREATE INDEX IF NOT EXISTS waiting_vpn_controls_pending_payment_idx
ON waiting_vpn_controls(subscription_id, payment_watermark)
WHERE state='disabled';
COMMIT;
SQL
if ! grep -Fq '# HESAB_WAITING_VPN_CONTROL_V1' patches/maya1_control.py;then
 changed=1
 printf '\n\n' >> patches/maya1_control.py
 cat "$SRC/patches/waiting_vpn_control_v1.py" >> patches/maya1_control.py
 python3 -m py_compile patches/maya1_control.py
 c up -d --no-deps --no-build --force-recreate app
else
 echo "ALREADY_INSTALLED: checking running app"
fi
ready=0
for i in $(seq 1 20);do
 if c exec -T app python - <<'PY' >/dev/null 2>&1
from app.main import app,TEMPLATES,_wvc_reconcile_once
from jinja2 import Environment
from pathlib import Path
src=Path("/app/app/main.py").read_text()
assert "# HESAB_WAITING_VPN_CONTROL_V1" in src
page=TEMPLATES.get("followups.html","")
assert page.count('class="waiting-vpn-stop-form"')==2
assert 'data-waiting-v2-filter="blocked"' in page
assert "/followups/pay-group" in page
assert "/followups/restore-group" in page
assert "data-waiting-renewal-form" in page
assert "data-waiting-v2-status-btn" in page
assert "window.__hesabWaitingVpnStopV1" in page
assert "data-waiting-vpn-expand" in page
Environment().parse(page)
for path,method in [("/followups","GET"),("/followups/vpn/disable","POST"),
                    ("/followups/connection-status","GET")]:
 assert sum(getattr(r,"path",None)==path and method in
  (getattr(r,"methods",set()) or set()) for r in app.routes)==1, path
assert callable(_wvc_reconcile_once)
PY
 then ready=1;break;fi
 sleep 2
done
if [[ "$ready" != 1 ]];then
 echo "STOP: smoke test failed; rolling back"
 false
fi
trap - ERR
echo "SUCCESS: waiting manual XUI cut + verified-payment auto-restore installed."
echo "CUTS: only after human click and confirmation, NEVER at a scheduled time."
echo "RECONNECT: only originally-confirmed waiting-page disabled clients, after actual full payment."
echo "Shahan SSH not changed; other existing disables are never automatically re-enabled."
echo "Backup: $backup"
