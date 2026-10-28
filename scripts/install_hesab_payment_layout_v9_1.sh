#!/usr/bin/env bash
# HESAB_PAYMENT_LAYOUT_V9_1: CSS-only payment layout correction.
# Two cards in one mobile row and a full-width black history bar.
# Does not change account/payment calculations, transaction ledger or routes.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo 'STOP: root required'; exit 2; }
ROOT=/opt/vpn-control-center
cd "$ROOT" || exit 2
CSS=customer_portal/services_custom_v9.css
PY=customer_portal/services_custom_v9.py
for path in "$CSS" "$PY" customer_portal/Dockerfile customer_portal/login_activity.py; do
  [[ -s "$path" ]] || { echo "STOP: missing $path"; exit 3; }
done
grep -q '# HESAB_CUSTOMER_V9' customer_portal/Dockerfile || { echo 'STOP: V9 not installed'; exit 3; }
grep -q 'def _v9_payment_layout' "$PY" || { echo 'STOP: V9 template changed'; exit 3; }
if grep -q 'HESAB_PAYMENT_LAYOUT_V9_1' "$CSS"; then
  echo 'ALREADY_INSTALLED: HESAB_PAYMENT_LAYOUT_V9_1'; exit 0
fi
compose() { docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
compose config -q
CURRENT="$(compose ps -q customer-portal)"
[[ -n "$CURRENT" ]] && [[ "$(docker inspect -f '{{.State.Running}}' "$CURRENT")" == true ]] || { echo 'STOP: portal is not running'; exit 3; }
docker exec "$CURRENT" python -c '
import server
assert callable(server._v9_payment_layout)
assert server._pla_previous_home is server._sv2_landing_v8
assert server._V2_DASH.count("hv9-history-jump")==1
assert "v7-transactions-card" not in server._V2_DASH
print("V9_PAYMENT_AND_LOGIN_AUDIT_VERIFIED")
'
# Verify all expected source markers before making ANY modifications.
python3 - "$CSS" "$PY" <<'PY'
from pathlib import Path
import sys
css, code = map(Path, sys.argv[1:])
s=code.read_text(encoding='utf-8')
assert s.count('href="/assets/services-custom-v9.css?v=v9a"')==2, 'V9 CSS links changed'
assert s.count('def _v9_payment_layout')==1, 'V9 payment wrapper changed'
assert 'HESAB_PAYMENT_LAYOUT_V9_1' not in css.read_text(encoding='utf-8'), 'Patch already applied'
print('PATCH_SOURCE_PREFLIGHT_OK')
PY
BACKUP="/root/hesab-payment-v9-1-backup-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
cp -a "$CSS" "$BACKUP/services_custom_v9.css"
cp -a "$PY" "$BACKUP/services_custom_v9.py"
docker inspect -f '{{.Image}}' "$CURRENT" > "$BACKUP/portal-image-id.txt"
echo "BACKUP=$BACKUP"
CHANGED=0
RECREATED=0
rollback() {
  local rc=$?
  trap - ERR EXIT
  if (( rc != 0 && CHANGED == 1 )); then
    echo 'ROLLBACK: restoring V9 payment stylesheet and template'
    cp -a "$BACKUP/services_custom_v9.css" "$CSS"
    cp -a "$BACKUP/services_custom_v9.py" "$PY"
    if (( RECREATED == 1 )); then
      compose build customer-portal && compose up -d --no-deps --force-recreate customer-portal || echo "ROLLBACK WARNING: check backup at $BACKUP"
    fi
  fi
  exit "$rc"
}
trap rollback ERR EXIT
CHANGED=1
cat >> "$CSS" <<'CSS'

/* HESAB_PAYMENT_LAYOUT_V9_1 — MOBILE: compact account count + wider debt. */
@media (max-width: 760px) {
  body:not(.hv5) .stats {
    display: grid !important;
    grid-template-columns: minmax(0, .83fr) minmax(0, 1.48fr) !important;
    align-items: stretch !important;
    gap: 10px !important;
    width: 100% !important;
    max-width: 100% !important;
  }
  body:not(.hv5) .stats > .stat,
  body:not(.hv5) .stats > .stat:last-child {
    grid-column: auto !important;
    grid-row: auto !important;
    min-width: 0 !important;
    width: auto !important;
    min-height: 108px !important;
    padding: 13px 11px !important;
    margin: 0 !important;
    border-radius: 20px !important;
    overflow: hidden !important;
    box-sizing: border-box !important;
  }
  body:not(.hv5) .stats > .stat:first-child {
    display: flex !important;
    flex-direction: column !important;
    justify-content: center !important;
    align-items: center !important;
    text-align: center !important;
    padding: 10px 5px !important;
  }
  body:not(.hv5) .stats > .stat:first-child .stat-head {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    flex-wrap: nowrap !important;
    width: 100% !important;
  }
  body:not(.hv5) .stats > .stat:first-child .stat-icon { display: none !important; }
  body:not(.hv5) .stats > .stat:first-child .stat-label {
    font-size: 11px !important;
    line-height: 1.5 !important;
    white-space: normal !important;
    text-align: center !important;
  }
  body:not(.hv5) .stats > .stat:first-child strong {
    font-size: 31px !important;
    margin-top: 7px !important;
    line-height: 1.25 !important;
  }
  body:not(.hv5) .stats > .stat:last-child .stat-head {
    display: flex !important;
    flex-wrap: nowrap !important;
    justify-content: space-between !important;
    gap: 6px !important;
  }
  body:not(.hv5) .stats > .stat:last-child .stat-label {
    font-size: 12px !important;
    white-space: nowrap !important;
  }
  body:not(.hv5) .stats > .stat:last-child .stat-icon {
    width: 29px !important;
    height: 29px !important;
    flex: 0 0 29px !important;
  }
  body:not(.hv5) .stats > .stat:last-child strong {
    font-size: clamp(20px, 5.5vw, 30px) !important;
    line-height: 1.5 !important;
    margin-top: 13px !important;
    white-space: nowrap !important;
    letter-spacing: -.04em !important;
    direction: ltr;
    text-align: right !important;
  }
}
/* Full-width narrow BLACK payment history navigation below both cards. */
.hv9-pay-nav {
  display: flex !important;
  width: 100% !important;
  margin: 12px 0 22px !important;
  padding: 0 !important;
  justify-content: stretch !important;
}
.hv9-pay-nav .hv9-history-jump {
  box-sizing: border-box !important;
  display: flex !important;
  justify-content: center !important;
  align-items: center !important;
  gap: 12px !important;
  width: 100% !important;
  min-height: 46px !important;
  padding: 10px 14px !important;
  background: #101114 !important;
  border: 1px solid #101114 !important;
  color: #fff !important;
  border-radius: 13px !important;
  box-shadow: 0 8px 16px rgba(0,0,0,.12) !important;
  text-decoration: none !important;
  font-size: 14px !important;
  font-weight: 850 !important;
}
.hv9-pay-nav .hv9-history-jump:hover,
.hv9-pay-nav .hv9-history-jump:focus-visible { background: #26272b !important; color: #fff !important; }
CSS
python3 - "$PY" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]);s=p.read_text(encoding='utf-8')
a='href="/assets/services-custom-v9.css?v=v9a"'
b='href="/assets/services-custom-v9.css?v=v9b"'
assert s.count(a)==2
p.write_text(s.replace(a,b),encoding='utf-8')
print('CACHE_VERSION_BUMPED=v9b')
PY
python3 -m py_compile "$PY"
compose config -q
echo 'BUILD: customer-portal ONLY'
compose build customer-portal
RECREATED=1
echo 'RECREATE: customer-portal ONLY'
compose up -d --no-deps --force-recreate customer-portal
NEW="$(compose ps -q customer-portal)"
[[ -n "$NEW" ]] || { echo 'STOP: portal container missing'; false; }
READY=0
for i in $(seq 1 50); do
  state="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$NEW")"
  if [[ "$state" == healthy ]]; then READY=1; break; fi
  sleep 2
done
[[ "$READY" -eq 1 ]] || { echo 'STOP: portal health failed'; false; }
docker exec -i "$NEW" python - <<'PY'
import server,urllib.request
assert server._pla_previous_home is server._sv2_landing_v8
assert 'href="/assets/services-custom-v9.css?v=v9b"' in server._V2_DASH
assert server._V2_DASH.count('hv9-history-jump') == 1
assert 'action="/pay-all"' in server._V2_DASH
assert 'action="/pay/{{ a.id }}"' in server._V2_DASH
assert 'HESAB_PAYMENT_LAYOUT_V9_1' in server._V9_CSS
url='http://127.0.0.1:8091/assets/services-custom-v9.css?v=v9b'
with urllib.request.urlopen(url,timeout=8) as resp:
    assert resp.status==200 and resp.headers.get_content_type()=='text/css'
    assert b'HESAB_PAYMENT_LAYOUT_V9_1' in resp.read()
print('PAYMENT_TWO_CARDS_AND_BLACK_HISTORY_OK')
PY
trap - ERR EXIT
echo 'SUCCESS: HESAB PAYMENT MOBILE LAYOUT V9.1 INSTALLED'
echo "BACKUP=$BACKUP"
