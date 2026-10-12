#!/usr/bin/env bash
# Customer portal paint/render performance hotfix; NO accounting changes.
# Apply only CSS optimization and stylesheet cache bust. Rebuild portal only.
set -Eeuo pipefail
umask 077

ROOT="/opt/vpn-control-center"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
C=(docker compose -f docker-compose.yml -f docker-compose.sms.yml)
ASSET="customer_portal/v2_polish.css"
DASH="customer_portal/dashboard_v2.html"
LOGIN="customer_portal/login_v2.html"
MARKER="PORTAL_PERFORMANCE_LITE_V1"

echo "=== PRE-FLIGHT ==="
for f in "$ASSET" "$DASH" "$LOGIN" customer_portal/Dockerfile customer_portal/billing_cycle_live.py; do
  test -s "$f" || { echo "STOP: missing $f"; exit 2; }
done
test -s "$REPO/customer_portal/v2_performance.css"
test -s "$REPO/scripts/test_portal_large_accounts.py"
if grep -q "$MARKER" "$ASSET"; then
  echo "ALREADY APPLIED: performance CSS marker exists; no changes made"
  exit 0
fi
"${C[@]}" config -q
"${C[@]}" ps app db customer-portal

BACKUP="/opt/hesab-backups/portal-performance-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP/customer_portal"
cp -p "$ASSET" "$BACKUP/$ASSET"
cp -p "$DASH" "$BACKUP/$DASH"
cp -p "$LOGIN" "$BACKUP/$LOGIN"
echo "BACKUP=$BACKUP"

rollback(){
  trap - ERR
  echo "ERROR: restoring previous portal styles and HTML..."
  cp -p "$BACKUP/$ASSET" "$ASSET"
  cp -p "$BACKUP/$DASH" "$DASH"
  cp -p "$BACKUP/$LOGIN" "$LOGIN"
  "${C[@]}" build customer-portal || true
  "${C[@]}" up -d --no-deps --no-build --force-recreate customer-portal || true
  echo "Rollback of portal UI attempted. Verify service health."
  exit 1
}
trap rollback ERR

echo "=== PATCHING CSS AND CACHE VERSION ==="
python3 - "$REPO" <<'PY'
import re
import sys
from pathlib import Path

repo = Path(sys.argv[1])
p = Path("customer_portal")
style_path = p / "v2_polish.css"
addition = (repo / "customer_portal/v2_performance.css").read_text(encoding="utf-8")
old_style = style_path.read_text(encoding="utf-8")
assert "PORTAL_PERFORMANCE_LITE_V1" in addition
assert "PORTAL_PERFORMANCE_LITE_V1" not in old_style
style_path.write_text(old_style + "\n\n" + addition + "\n", encoding="utf-8")

for file in ("dashboard_v2.html", "login_v2.html"):
    path = p / file
    old = path.read_text(encoding="utf-8")
    fresh, changed = re.subn(
        r'(/assets/v2_polish\.css)(?:\?v=[^"]*)?',
        r'\1?v=perf-lite-1',
        old,
    )
    if changed != 1:
        raise RuntimeError(f"{file}: expected exactly one stylesheet URL, got {changed}")
    path.write_text(fresh, encoding="utf-8")
print("CSS overlay applied without modifying billing code.")
PY

echo "=== REBUILDING CUSTOMER PORTAL ONLY ==="
"${C[@]}" build customer-portal
"${C[@]}" up -d --no-deps --no-build --force-recreate customer-portal

echo "=== WAITING FOR PORTAL ==="
ready=0
for i in $(seq 1 35); do
  if "${C[@]}" exec -T customer-portal python -c \
    'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8091/health",timeout=2).read()' \
    >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
test "$ready" -eq 1

echo "=== VERIFYING CSS AND LARGE-ACCOUNT RENDER ==="
"${C[@]}" exec -T customer-portal python -c \
  'import urllib.request; raw=urllib.request.urlopen("http://127.0.0.1:8091/assets/v2_polish.css?v=perf-lite-1",timeout=5).read().decode("utf-8"); assert "PORTAL_PERFORMANCE_LITE_V1" in raw; print("CSS deployed successfully")'

"${C[@]}" exec -T customer-portal sh -lc \
  'PORTAL_TEST_BASE=/srv python -' \
  < "$REPO/scripts/test_portal_large_accounts.py"

echo "=== DATA QUALITY CHECK (AGGREGATE ONLY, READ-ONLY) ==="
"${C[@]}" exec -T db sh -lc \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -P pager=off -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT COUNT(*) AS subscriptions, COUNT(*) FILTER (WHERE display_name IS NULL OR LENGTH(BTRIM(display_name)) = 0) AS blank_names FROM subscriptions;"' || true
"${C[@]}" exec -T db sh -lc \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -P pager=off -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT COALESCE(MAX(n),0) AS max_accounts_per_phone, COUNT(*) FILTER (WHERE n >= 10) AS groups_with_10_plus FROM (SELECT COUNT(*) AS n FROM subscriptions GROUP BY phone) grouped;"' || true

echo "=== APP, DB, PORTAL HEALTH ==="
"${C[@]}" ps app db customer-portal

trap - ERR
echo "SUCCESS: PORTAL PERFORMANCE LITE DEPLOYED"
echo "Only portal CSS/stylesheet URL were changed, with backup at $BACKUP"
echo "Accounts, debts, payments, login policy and service configuration were not changed."
