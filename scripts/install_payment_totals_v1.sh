#!/usr/bin/env bash
# HESAB_PAYMENT_TOTALS_V1_INSTALL
# Only modifies the admin /payments presentation + read-only GET aggregate.
# Existing POST undo, DB, customer portal, SMS, XUI and other services untouched.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == "0" ]] || { echo "STOP: root required";exit 2; }

ROOT=/opt/vpn-control-center
PATCH_REF=eaa4c5ea3d71785680d407943079d9cd9c415665
TEMP="$(mktemp -d /root/hesab-pay-totals-v1.XXXXXX)"
PATCH="$TEMP/payment_totals_v1.py"
URL="https://raw.githubusercontent.com/aliiitavazoeiii-afk/vpn-managrer/$PATCH_REF/patches/payment_totals_v1.py"
curl -fsSL --retry 3 --connect-timeout 12 "$URL" -o "$PATCH"
python3 -m py_compile "$PATCH"
cd "$ROOT"
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
TARGET=patches/sms_native_v2.py
for f in .env docker-compose.yml docker-compose.sms.yml "$TARGET";do
  [[ -s "$f" ]] || { echo "STOP: production file absent $f";exit 3; }
done
grep -Fq '/sms-patch/sms_native_v2.py' docker-compose.sms.yml || {
  echo "STOP: admin overlay not mounted";exit 3;
}
grep -Fq '# HESAB_OPERATOR_WORKSPACE_V5' "$TARGET" || {
  echo "STOP: expected V5 payments workspace missing";exit 3;
}
if grep -Fq '# HESAB_PAYMENT_TOTALS_V1' "$TARGET";then
  echo "ALREADY_INSTALLED: V1 present; no file changes";exit 0;
fi
compose config -q
python3 -m py_compile "$TARGET"

echo "=== PREFLIGHT: CURRENT LIVE PAYMENTS TEMPLATE, NO CHANGES ==="
cat "$PATCH" | compose exec -T app python -c '
import sys
from jinja2 import Environment
from app import main as m
old=m.TEMPLATES.get("payments.html","")
assert bool(old),"Current /payments template missing"
assert "pts-total-card" not in old,"Payments totals already loaded"
routes=[r for r in m.app.router.routes
        if getattr(r,"path",None)=="/payments"
        and "GET" in (getattr(r,"methods",set()) or set())]
assert len(routes)==1
undo=[r for r in m.app.router.routes
      if getattr(r,"path",None)=="/payments/{pid}/undo"
      and "POST" in (getattr(r,"methods",set()) or set())]
assert undo,"Original payment undo route missing"
source=sys.stdin.read()
exec(compile(source,"<payments-totals-v1-preflight>","exec"),vars(m))
new=m.TEMPLATES["payments.html"]
assert new!=old
assert new.count("pts-total-card")>=2
assert "pts-day-heading" in new or "data-pf-amount" in new
assert "request.state.pts_total" in new
assert "admin_phone_suggestion_directory" not in source
Environment().parse(new)
routes=[r for r in m.app.router.routes
        if getattr(r,"path",None)=="/payments"
        and "GET" in (getattr(r,"methods",set()) or set())]
assert len(routes)==1 and routes[0].endpoint is m._pts_payments_page
print("PASS: runtime layout="+m._PTS_LAYOUT+"; undo preserved; Jinja valid")
'

BACKUP="/opt/hesab-backups/payment-totals-v1-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACKUP"
cp -a "$TARGET" "$BACKUP/sms_native_v2.py"
echo "BACKUP=$BACKUP"

MODIFIED=0
on_exit(){
  local rc=$?
  trap - EXIT
  if (( rc != 0 )) && (( MODIFIED == 1 ));then
    echo "INSTALL FAILED. Restoring admin overlay and recreating ONLY app..."
    cp -a "$BACKUP/sms_native_v2.py" "$TARGET"
    compose up -d --no-deps --no-build --force-recreate app || \
      echo "ROLLBACK RESTART FAILED; backup remains $BACKUP"
  fi
  exit "$rc"
}
trap on_exit EXIT

MODIFIED=1
printf '\n\n' >> "$TARGET"
cat "$PATCH" >> "$TARGET"
python3 -m py_compile "$TARGET"
echo "RECREATE: admin app only; no DB/image build"
compose up -d --no-deps --no-build --force-recreate app

READY=0
for i in $(seq 1 35);do
  if compose exec -T app python - <<'PY' >/dev/null 2>&1
from app.main import app,TEMPLATES,_pts_payments_page,_PTS_LAYOUT
from jinja2 import Environment
from sqlalchemy import func
from app.main import get_db,Payment
assert _PTS_LAYOUT in ("operator-v5","safe-v5")
tpl=TEMPLATES["payments.html"]
assert "جمع کل پرداخت‌های ثبت‌شده" in tpl
assert "جمع واریزی روز" in tpl
assert "request.state.pts_total" in tpl
assert ('pts-day-heading' in tpl) if _PTS_LAYOUT=="operator-v5" else ('data-pf-amount' in tpl)
Environment().parse(tpl)
routes=[r for r in app.router.routes
    if r.path=="/payments" and "GET" in r.methods]
assert len(routes)==1 and routes[0].endpoint is _pts_payments_page
undo=[r for r in app.router.routes
    if r.path=="/payments/{pid}/undo" and "POST" in r.methods]
assert undo
g=get_db();db=next(g)
try:
    count,total=db.query(func.count(Payment.id),func.coalesce(func.sum(Payment.amount_toman),0)).one()
    assert int(count or 0)>=0
    assert total is not None
finally:g.close()
PY
  then READY=1;break;fi
  sleep 2
done
[[ "$READY" == 1 ]] || { echo "STOP: runtime payment page not verified";false; }

compose exec -T app python - <<'PY'
from app.main import _PTS_LAYOUT,Payment,get_db
from sqlalchemy import func
g=get_db();db=next(g)
try:
    count,total=db.query(func.count(Payment.id),func.coalesce(func.sum(Payment.amount_toman),0)).one()
    print("VERIFIED_LAYOUT",_PTS_LAYOUT)
    print("VERIFIED_LEDGER_PAYMENT_COUNT",int(count or 0))
    print("VERIFIED_LEDGER_TOTAL_TOMAN",int(total or 0))
finally:g.close()
PY

trap - EXIT
echo "SUCCESS: ADMIN PAYMENTS GLOBAL + DAILY TOTALS V1 INSTALLED"
echo "BACKUP=$BACKUP"
echo "Existing payment undo, accounting, SMS and customer portal were not changed."
