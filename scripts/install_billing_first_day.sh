#!/usr/bin/env bash
# Safe rollout for first-of-next-Jalali-month billing.
# --check: only tests + reads unresolved payments (default).
# --install: requires no unresolved Ayria checkout, then backs up and installs.
set -Eeuo pipefail
umask 077
MODE="${1:---check}"
[[ "$MODE" == "--check" || "$MODE" == "--install" ]] || { echo "Usage: $0 [--check|--install]"; exit 2; }
[[ "${EUID:-$(id -u)}" -eq 0 ]] || { echo "Run as root"; exit 2; }

APP=/opt/vpn-control-center
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP"
C=(docker compose -f docker-compose.yml -f docker-compose.sms.yml)

echo "=== 1. Canonical billing calculation tests (read only) ==="
{
  cat "$REPO/customer_portal/billing_policy.py"
  printf '\n'
  cat "$REPO/customer_portal/billing_policy_test.py"
} | "${C[@]}" exec -T customer-portal python -

echo "=== 2. Unresolved payment attempts ==="
OPEN=$(
  "${C[@]}" exec -T db sh -lc \
    'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT COUNT(*) FROM ayria_payment_requests WHERE paid_at IS NULL AND status IN ('"'"'created'"'"','"'"'waiting'"'"');"' \
  | tr -d '[:space:]'
)
[[ "$OPEN" =~ ^[0-9]+$ ]] || { echo "STOP: Could not read payment status"; exit 1; }
echo "Unresolved created/waiting checkouts: $OPEN"
"${C[@]}" exec -T db sh -lc \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -P pager=off -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT status, COALESCE(sync_status, '"'NONE'"') AS sync_status, COUNT(*) FROM ayria_payment_requests WHERE paid_at IS NULL AND status IN ('"'"'created'"'"','"'"'waiting'"'"') GROUP BY status, sync_status ORDER BY status;"'

echo "=== 2b. Open payment request details (no customer PII) ==="
"${C[@]}" exec -T db sh -lc \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -P pager=off -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT r.id, r.status, COALESCE(r.sync_status, '\''NONE'\'') AS sync_status, r.amount_toman, r.created_at, COUNT(a.id) AS allocated_accounts FROM ayria_payment_requests r LEFT JOIN ayria_payment_allocations a ON a.request_id=r.id WHERE r.paid_at IS NULL AND r.status IN ('\''created'\'','\''waiting'\'') GROUP BY r.id, r.status, r.sync_status, r.amount_toman, r.created_at ORDER BY r.created_at;"'

if [[ "$MODE" == "--check" ]]; then
  echo "CHECK COMPLETE: no files, billing data or services were changed."
  exit 0
fi

if (( OPEN > 0 )); then
  echo "STOP: Open old payment URLs must be reconciled or confirmed canceled before installing the new billing policy."
  echo "No local files or database records were modified."
  exit 4
fi

echo "=== 3. Ensuring this release has not already been installed ==="
for f in patches/billing_cycle_live.py customer_portal/billing_policy.py customer_portal/billing_cycle_live.py; do
  [[ ! -e "$f" ]] || { echo "STOP: $f already exists; manual review required"; exit 1; }
done

echo "=== 4. Backing up files and database ==="
BACKUP="/opt/hesab-backups/billing-first-day-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP/files"
for f in docker-compose.sms.yml customer_portal/Dockerfile customer_portal/dashboard_v2.html; do
  mkdir -p "$BACKUP/files/$(dirname "$f")"
  cp -a "$f" "$BACKUP/files/$f"
done
"${C[@]}" exec -T db sh -lc \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "$BACKUP/database.dump"
test -s "$BACKUP/database.dump" || { echo "STOP: Database backup missing"; exit 1; }

rollback() {
  echo "RESTORING previous billing application files..."
  for f in docker-compose.sms.yml customer_portal/Dockerfile customer_portal/dashboard_v2.html; do
    cp -a "$BACKUP/files/$f" "$f"
  done
  rm -f patches/billing_cycle_live.py customer_portal/billing_policy.py customer_portal/billing_cycle_live.py
  "${C[@]}" build customer-portal || true
  "${C[@]}" up -d --no-deps --no-build --force-recreate app customer-portal || true
  echo "Rollback attempted. Verify both application health checks before continuing."
}

echo "=== 5. Adding only required new module references ==="
if ! python3 - <<'PY'
from pathlib import Path

compose = Path("docker-compose.sms.yml")
docker = Path("customer_portal/Dockerfile")
html = Path("customer_portal/dashboard_v2.html")

c = compose.read_text()
d = docker.read_text()
h = html.read_text()

mount = "      - ./patches/billing_anchor.py:/sms-patch/billing_anchor.py:ro\n"
runtime = "        python -m py_compile /app/app/main.py\n"
portal_copy = "COPY billing_migration.py .\n"
portal_sync = 'exec(compile(open("/srv/billing_sync.py", "r", encoding="utf-8").read(), "/srv/billing_sync.py", "exec"))\\n'
portal_compile = "python -m py_compile server.py v2.py billing_sync.py billing_migration.py"

assert c.count(mount) == 1 and c.count(runtime) == 1, "Admin compose anchors changed"
assert d.count(portal_copy) == 1 and d.count(portal_sync) == 1
assert d.count(portal_compile) == 1, "Customer portal Dockerfile changed"
assert "BILLING_FIRST_DAY_LIVE_V1" not in c
assert "billing_cycle_live.py" not in d

c = c.replace(mount, mount +
    "      - ./patches/billing_cycle_live.py:/sms-patch/billing_cycle_live.py:ro\n"
    "      - ./customer_portal/billing_policy.py:/sms-patch/billing_policy.py:ro\n", 1)
c = c.replace(runtime,
    "        if ! grep -q 'BILLING_FIRST_DAY_LIVE_V1' /app/app/main.py; then\n"
    "          cat /sms-patch/billing_cycle_live.py >> /app/app/main.py\n"
    "        fi\n" + runtime, 1)

d = d.replace(portal_copy, portal_copy + "COPY billing_policy.py .\nCOPY billing_cycle_live.py .\n", 1)
d = d.replace(portal_sync, portal_sync +
    'exec(compile(open("/srv/billing_cycle_live.py", "r", encoding="utf-8").read(), "/srv/billing_cycle_live.py", "exec"))\\n', 1)
d = d.replace(portal_compile, portal_compile +
    " billing_policy.py billing_cycle_live.py", 1)

replacements = {
    "لطفاً توجه داشته باشید تمامی اکانت‌ها تا یک آبان محاسبه می‌شود.":
    "مبلغ تمدید هر اکانت فقط از روز سررسید واقعی آن تا یکم ماه بعد محاسبه می‌شود.",
    "از این پس سررسید تمامی اکانت‌ها یکم هر ماه خواهد بود.":
    "اکانت‌هایی که هنوز به سررسید نرسیده‌اند، فعلاً بدهی ندارند. بعد از پرداخت، تاریخ تمدید به یکم ماه بعد منتقل می‌شود.",
    "تمدید همه اکانت‌ها تا یکم آبان ماه":
    "تسویه اکانت‌های سررسیدشده تا یکم ماه بعد",
    "{{ a.transition_target_jalali or '۱۴۰۵/۰۸/۰۱' }}":
    "{{ a.transition_target_jalali or a.expiry_jalali }}",
    "<span>مبلغ این دوره</span>":
    "<span>بدهی تا یکم ماه بعد</span>",
}
# Preserve any independent visual/custom CSS changes on the live server.
for old, new in replacements.items():
    if old in h:
        h = h.replace(old, new, 1)

compose.write_text(c)
docker.write_text(d)
html.write_text(h)
PY
then
  rollback
  echo "STOP: Local customizations need review before applying patch."
  exit 1
fi

install -m 0644 "$REPO/customer_portal/billing_policy.py" customer_portal/billing_policy.py
install -m 0644 "$REPO/customer_portal/billing_cycle_live.py" customer_portal/billing_cycle_live.py
install -m 0644 "$REPO/patches/billing_cycle_live.py" patches/billing_cycle_live.py

echo "=== 6. Static validation and compose config ==="
if ! (python3 -m py_compile customer_portal/billing_policy.py customer_portal/billing_cycle_live.py patches/billing_cycle_live.py && "${C[@]}" config -q); then
  rollback
  exit 1
fi

echo "=== 7. Building customer portal (admin app image is preserved) ==="
if ! "${C[@]}" build customer-portal; then
  rollback
  exit 1
fi

echo "=== 8. Restarting only portal and admin ==="
if ! "${C[@]}" up -d --no-deps --no-build --force-recreate customer-portal app; then
  rollback
  exit 1
fi

echo "=== 9. Testing both health endpoints ==="
for i in $(seq 1 30); do
  APP_OK=0
  PORTAL_OK=0
  if curl -fsS http://127.0.0.1:8080/health >/dev/null 2>&1; then APP_OK=1; fi
  if "${C[@]}" exec -T customer-portal python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8091/health',timeout=3).read()" \
    >/dev/null 2>&1; then PORTAL_OK=1; fi
  if (( APP_OK == 1 && PORTAL_OK == 1 )); then
    echo "SUCCESS: FIRST-DAY BILLING ACTIVE"
    echo "BACKUP: $BACKUP"
    echo "SMS HAS NOT BEEN SENT. Check a sample debtor and future-expiry customer first."
    exit 0
  fi
  sleep 2
done
"${C[@]}" logs --tail=45 app customer-portal
rollback
echo "FAILED: One or both applications not healthy"
exit 1
