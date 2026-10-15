#!/usr/bin/env bash
# HESAB_NATIVE_SMS_V2_TEST_INSTALL
# Preserve production customizations and existing SMS queues.
set -Eeuo pipefail
umask 077
test "$(id -u)" -eq 0 || { echo "STOP: root required"; exit 2; }
SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
c() { docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
test -s "$SOURCE/patches/sms_native_v2.py"
test -s "$SOURCE/sms_gateway/server.py"
test -s sms_gateway/server.py
test -s .env
python3 -m py_compile "$SOURCE/patches/sms_native_v2.py" "$SOURCE/sms_gateway/server.py"
grep -Fq "AND phone=%s AND source='manual'" "$SOURCE/sms_gateway/server.py"
grep -Fq '# HESAB_NATIVE_SMS_V2_ADMIN' "$SOURCE/patches/sms_native_v2.py"
c config -q
for marker in SMS_GATEWAY_PATCH_V1 SMS_DEBT_DEFAULT_ABAN_V1 DEBT_SMS_LIVE_NOJUMP_V1 HESAB_BROWSER_SMS_BRIDGE_V1; do
  c exec -T app grep -q "$marker" /app/app/main.py || { echo "STOP: app missing $marker"; exit 3; }
done
if c exec -T app grep -q HESAB_NATIVE_SMS_V2_ADMIN /app/app/main.py; then
  echo "STOP: V2 already present; inspect instead"; exit 3
fi
if grep -Fq '# NATIVE_SMS_V2_SEPARATE_QUEUE' sms_gateway/server.py; then
  echo "STOP: gateway V2 already present; inspect instead"; exit 3
fi
python3 - "$SOURCE" <<'PY'
from pathlib import Path
import sys
s=Path("docker-compose.sms.yml").read_text()
g=Path("sms_gateway/server.py").read_text()
source=(Path(sys.argv[1])/"sms_gateway/server.py").read_text()
assert "# NATIVE_SMS_V2_SEPARATE_QUEUE" in source
assert "def db_conn(" in g and "require_token(" in g
assert "# NATIVE_SMS_V2_SEPARATE_QUEUE" not in g
mount="      - ./patches/sms_browser_bridge.py:/sms-patch/sms_browser_bridge.py:ro\n"
compile_line="        python -m py_compile /app/app/main.py\n"
assert s.count(mount)==1
assert s.count(compile_line)==1
assert s.count("cat /sms-patch/sms_browser_bridge.py >> /app/app/main.py")==1
assert "sms_native_v2.py" not in s
assert s.index("cat /sms-patch/sms_browser_bridge.py") < s.index(compile_line)
assert "      - ./patches/sms_nojump.py:/sms-patch/sms_nojump.py:ro" in s
print("PASS: live Compose is compatible with surgical V2 patch")
PY

BACKUP="/opt/hesab-backups/native-v2-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACKUP"
cp -a docker-compose.sms.yml "$BACKUP/"
cp -a sms_gateway/server.py "$BACKUP/"
if test -e patches/sms_native_v2.py; then
  cp -a patches/sms_native_v2.py "$BACKUP/"
fi
echo "Backing up production PostgreSQL before touching services..."
c exec -T db sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$BACKUP/db.dump"
test -s "$BACKUP/db.dump"
c exec -T db pg_restore -l < "$BACKUP/db.dump" >/dev/null

MODIFIED=0
rollback() {
  trap - ERR
  echo "ERROR: reverting SMS V2 files (never automatically restoring live DB)"
  if test "$MODIFIED" -eq 1; then
    cp -a "$BACKUP/docker-compose.sms.yml" docker-compose.sms.yml
    cp -a "$BACKUP/server.py" sms_gateway/server.py
    if test -f "$BACKUP/sms_native_v2.py"; then
      cp -a "$BACKUP/sms_native_v2.py" patches/sms_native_v2.py
    else
      rm -f patches/sms_native_v2.py
    fi
    c config -q || true
    c build sms-gateway || true
    c up -d --no-deps --no-build sms-gateway || true
    c up -d --no-deps --no-build --force-recreate app || true
  fi
  echo "Backup: $BACKUP"
  exit 1
}
trap rollback ERR
MODIFIED=1

python3 - "$SOURCE" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1])
target=Path("sms_gateway/server.py")
native=src.joinpath("sms_gateway/server.py").read_text().split("# NATIVE_SMS_V2_SEPARATE_QUEUE",1)[1]
full=target.read_text().rstrip()+"\n\n# NATIVE_SMS_V2_SEPARATE_QUEUE"+native
compile(full,str(target),"exec")
target.write_text(full)
patch=src.joinpath("patches/sms_native_v2.py").read_text()
compile(patch,"patches/sms_native_v2.py","exec")
Path("patches/sms_native_v2.py").write_text(patch)
compose=Path("docker-compose.sms.yml")
s=compose.read_text()
mount="      - ./patches/sms_browser_bridge.py:/sms-patch/sms_browser_bridge.py:ro\n"
s=s.replace(mount,mount+"      - ./patches/sms_native_v2.py:/sms-patch/sms_native_v2.py:ro\n",1)
before="        python -m py_compile /app/app/main.py\n"
extra=("        if ! grep -q 'HESAB_NATIVE_SMS_V2_ADMIN' /app/app/main.py; then\n"
       "          cat /sms-patch/sms_native_v2.py >> /app/app/main.py\n"
       "        fi\n")
s=s.replace(before,extra+before,1)
compose.write_text(s)
PY

c config -q
echo "Rebuilding SMS API only..."
c build sms-gateway
c up -d --no-deps --no-build sms-gateway
ready=0
for i in $(seq 1 35); do
  if c exec -T sms-gateway python - <<'PY' >/dev/null 2>&1
from server import app
paths = {getattr(r, "path", "") for r in app.router.routes}
assert "/v2/health" in paths and "/v2/jobs/next" in paths
PY
  then ready=1; break; fi
  sleep 2
done
test "$ready" -eq 1

echo "Restarting only admin app, keeping customer portal and DB running..."
c up -d --no-deps --no-build --force-recreate app
ready=0
for i in $(seq 1 40); do
  if c exec -T app sh -lc \
     'grep -q HESAB_NATIVE_SMS_V2_ADMIN /app/app/main.py && curl -fsS http://127.0.0.1:8000/health >/dev/null' >/dev/null 2>&1; then
    ready=1; break
  fi
  sleep 2
done
test "$ready" -eq 1
c exec -T app python - <<'PY'
from app.main import app
paths={getattr(r,"path","") for r in app.router.routes}
assert "/sms/native-v2/status" in paths
assert "/sms/send" in paths and "/sms/debt-send" in paths
print("PASS: V2 admin routes loaded")
PY
HTTP="$(curl -sS -o /dev/null -w '%{http_code}' https://hesab.filmjadiid.ir/sms-gateway/v2/health)"
echo "Unauthenticated V2 health HTTP: $HTTP"
test "$HTTP" = "401" || { echo "STOP: V2 not reachable publicly"; false; }
trap - ERR
echo "SUCCESS: V2 API and admin configured; no SMS queued or sent"
echo "Existing legacy sms_jobs, billing and customer portal untouched"
echo "Backup: $BACKUP"
