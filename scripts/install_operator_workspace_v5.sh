#!/usr/bin/env bash
# HESAB_OPERATOR_WORKSPACE_V5_INSTALL
# Backup-first scoped admin-only update. No SQL UPDATE of subscriptions/payments.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo 'STOP: run with sudo'; exit 2; }
SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }

for p in .env docker-compose.yml docker-compose.sms.yml sms_gateway/server.py patches/sms_native_v2.py; do
  [[ -s "$p" ]] || { echo "STOP: missing $p"; exit 3; }
done
test -s "$SOURCE/patches/operator_workspace_v5.py"
c config -q
python3 -m py_compile "$SOURCE/patches/operator_workspace_v5.py"
if grep -Fq '# HESAB_OPERATOR_WORKSPACE_V5' patches/sms_native_v2.py; then
  echo 'ALREADY_INSTALLED: V5 admin workspace is present'; exit 0
fi

# Only where needed: existing guarded installer enables V4/renewal routes.
if ! grep -Fq '# HESAB_WAITING_EXPIRY_SMS_V2' patches/sms_native_v2.py; then
  echo 'Installing missing expiry reminder prerequisite first...'
  bash "$SOURCE/scripts/install_waiting_expiry_sms_v2.sh"
fi
grep -Fq '# GOOGLE_MESSAGES_BATCH_OPEN_V4' sms_gateway/server.py || {
  echo 'STOP: manual V4 queue is missing'; exit 3;
}
grep -Fq '# HESAB_WAITING_EXPIRY_SMS_V2' patches/sms_native_v2.py || {
  echo 'STOP: expiry reminder prerequisite missing'; exit 3;
}
grep -Fq 'sms_native_v2.py' docker-compose.sms.yml || {
  echo 'STOP: native SMS V2 mount missing'; exit 3;
}

echo 'Read-only compatibility checks for active admin pages...'
c exec -T app python - <<'PY'
from app.main import app,TEMPLATES
required=("user_status.html","add_user_page.html","payments.html","sms.html","followups.html")
assert all(name in TEMPLATES for name in required), "STOP: template drift"
page=TEMPLATES["user_status.html"]
assert 'id="lc-list"' in page and '<script>' in page
assert 'lc-filter' in page and "data-lc-row" in page
assert "waiting-head-pay waiting-pay-tools" in TEMPLATES["followups.html"]
assert "HESAB_OPERATOR_WORKSPACE_V5" not in open('/app/app/main.py').read()
assert any(r.path=="/payments" for r in app.routes)
assert any(r.path=="/add-user" for r in app.routes)
print("PASS: existing admin screens compatible")
PY

python3 - "$SOURCE" <<'PY'
from pathlib import Path
import sys,re
source=(Path(sys.argv[1])/"patches/operator_workspace_v5.py").read_text()
current=Path("patches/sms_native_v2.py").read_text()
anchor="message=_ABAN_SMS_PATTERN.format(expiry=jdate(earliest))"
assert current.count(anchor)==1, "STOP: source of debt SMS changed; do not modify blindly"
assert current.count("# HESAB_OPERATOR_WORKSPACE_V5")==0
assert source.count("# HESAB_OPERATOR_WORKSPACE_V5")==1
assert "_op_sms_render(db,\"debt\",earliest)" not in current
combined=current.replace(anchor,'message=_op_sms_render(db,"debt",earliest,min(eligible,key=lambda s:(s.expiry_date,s.id)).display_name)')+"\n\n"+source
compile(combined,"sms_native_v2.py","exec")
assert combined.count('message=_op_sms_render(db,"debt",earliest,min(eligible,key=lambda s:(s.expiry_date,s.id)).display_name)')==1
for label in ('/sms/templates/save','/payments','/users','/user-status','/add-user'):
  assert label in combined
print("PASS: isolated SMS-render substitution and templates compile")
PY

BACKUP="/opt/hesab-backups/operator-workspace-v5-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACKUP"
cp -a patches/sms_native_v2.py "$BACKUP/sms_native_v2.py"
cp -a docker-compose.sms.yml "$BACKUP/docker-compose.sms.yml"
echo 'Saving PostgreSQL backup before changing application code...'
c exec -T db sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$BACKUP/db.dump"
test -s "$BACKUP/db.dump"
c exec -T db pg_restore -l < "$BACKUP/db.dump" >/dev/null

CHANGED=0
rollback(){
  trap - ERR
  if [[ "$CHANGED" == "1" ]]; then
    echo 'ERROR: reverting app code only; DB backup retained for review.'
    cp -a "$BACKUP/sms_native_v2.py" patches/sms_native_v2.py
    c up -d --no-deps --no-build --force-recreate app || true
  fi
  echo "BACKUP=$BACKUP";exit 1
}
trap rollback ERR
CHANGED=1
python3 - "$SOURCE" <<'PY'
from pathlib import Path
import sys
p=Path("patches/sms_native_v2.py")
source=(Path(sys.argv[1])/"patches/operator_workspace_v5.py").read_text()
current=p.read_text()
anchor="message=_ABAN_SMS_PATTERN.format(expiry=jdate(earliest))"
assert current.count(anchor)==1
merged=current.replace(anchor,'message=_op_sms_render(db,"debt",earliest,min(eligible,key=lambda s:(s.expiry_date,s.id)).display_name)')
merged+="\n\n"+source
compile(merged,str(p),"exec")
p.write_text(merged)
PY
c up -d --no-deps --no-build --force-recreate app
READY=0
for i in $(seq 1 35); do
  if c exec -T app python - <<'PY' >/dev/null 2>&1
from app.main import app,TEMPLATES,_op_sms_validate,_op_sms_render
from datetime import date
assert _op_sms_validate("سلام {تاریخ_انقضا}")=="سلام {تاریخ_انقضا}"
routes={p:sum(r.path==p and "GET" in r.methods for r in app.routes)
 for p in ("/users","/user-status","/add-user","/payments","/sms")}
assert all(v==1 for v in routes.values()),routes
assert any(r.path=="/sms/templates/save" and "POST" in r.methods for r in app.routes)
assert "op-users-pages" in TEMPLATES["user_status.html"]
assert "op-pay-day" in TEMPLATES["payments.html"]
assert "recent_users" in TEMPLATES["add_user_page.html"]
assert "تاریخ_انقضا" in TEMPLATES["sms.html"]
assert "data-waiting-renewal-form" in TEMPLATES["followups.html"]
PY
  then READY=1;break;fi
  sleep 2
done
test "$READY" -eq 1
trap - ERR
echo 'SUCCESS: V5 users list, add-user history, payment calendar grouping and SMS text settings installed'
echo 'Existing SMS jobs, payment rows, and subscription records remain unchanged.'
echo 'BACKUP='"$BACKUP"
