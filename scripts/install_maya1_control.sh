#!/usr/bin/env bash
# MAYA1_CONTROL_INSTALL_V1
# Pair restricted SSH key and install read-only x-ui view. No SQL writes, no x-ui writes.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" = 0 ]] || { echo "Run as root"; exit 2; }
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE=/opt/vpn-control-center
HOST=94.184.4.38
KEY=/root/.ssh/hesab_maya1_readonly
C=(docker compose -f docker-compose.yml -f docker-compose.sms.yml)
cd "$BASE"

echo "=== STATIC PYTHON/JINJA CHECKS ==="
python3 -m py_compile "$REPO/scripts/maya1_xui_export.py" "$REPO/scripts/maya1_readonly_sync.py" "$REPO/scripts/maya1_usage_daily.py" "$REPO/patches/maya1_control.py"
"${C[@]}" exec -T app python -c '
import ast,sys
from jinja2 import Environment
tree=ast.parse(sys.stdin.read())
values=[node.value.value for node in tree.body
        if isinstance(node,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=="_MC_PANEL" for t in node.targets)]
assert len(values)==1
Environment(autoescape=True).parse(values[0])
print("MAYA1 JINJA TEMPLATE VALID")
' < "$REPO/patches/maya1_control.py"

echo "=== CHECK: admin services and code ==="
test -s "$REPO/scripts/maya1_xui_export.py"
test -s "$REPO/scripts/maya1_readonly_sync.py"
test -s "$REPO/scripts/maya1_usage_daily.py"
test -s "$REPO/patches/maya1_control.py"
test -s docker-compose.sms.yml
if ! systemctl is-active --quiet cron; then
  echo "STOP: cron is not active. Start system cron first so snapshots can refresh every 5 min."
  exit 2
fi
"${C[@]}" config -q
"${C[@]}" exec -T app python - <<'PY'
import urllib.request
urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=6).read()
PY
"${C[@]}" exec -T db sh -c \
  'PGOPTIONS="-c default_transaction_read_only=on" PGPASSWORD="$POSTGRES_PASSWORD" psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM subscriptions"' \
  >/dev/null

echo "=== CHECK: admin route protected ==="
"${C[@]}" exec -T app python - <<'PY'
import http.client
c=http.client.HTTPConnection("127.0.0.1",8000,timeout=5)
c.request("GET","/control-room")
r=c.getresponse()
body=r.read()
c.close()
if r.status==200 and b'ref-control-page' in body:
    raise SystemExit("STOP: control-room is public without admin auth")
print("Unauthenticated request:",r.status)
PY

mkdir -p /root/.ssh
chmod 700 /root/.ssh
if [[ ! -f "$KEY" ]]; then
  echo "=== Create dedicated SSH key (no root password stored) ==="
  ssh-keygen -q -t ed25519 -N '' -f "$KEY" -C hesab-maya1-readonly
fi
test -s "$KEY.pub"
chmod 600 "$KEY"
PUB="$(cat "$KEY.pub")"
[[ "$PUB" =~ ^ssh-ed25519\  ]] || { echo "STOP: invalid SSH key"; exit 3; }

echo "=== PAIR MAYA1 (verify new SSH host fingerprint before accepting; then root password) ==="
# The remote authorized key is forced to one audited read-only command.
# Host key verification is never disabled.
EXPORT_B64="$(base64 -w0 < "$REPO/scripts/maya1_xui_export.py")"
read -r -d '' REMOTE <<EOF || true
set -eu
umask 077
mkdir -p /usr/local/sbin /root/.ssh
chmod 700 /root/.ssh
printf '%s' '$EXPORT_B64' | base64 -d > /usr/local/sbin/maya1-xui-export
chmod 700 /usr/local/sbin/maya1-xui-export
/usr/local/sbin/maya1-xui-export >/dev/null
touch /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
if ! grep -Fq '$PUB' /root/.ssh/authorized_keys; then
  printf '%s\n' 'restrict,command="/usr/local/sbin/maya1-xui-export" $PUB' >> /root/.ssh/authorized_keys
fi
printf '%s\n' 'MAYA1 RESTRICTED READ-ONLY KEY INSTALLED'
EOF
ssh -T -o StrictHostKeyChecking=ask \
  -o ConnectTimeout=12 \
  -o PreferredAuthentications=password,keyboard-interactive \
  -o PubkeyAuthentication=no \
  "root@$HOST" sh -se <<< "$REMOTE"

echo "=== INSTALL: local audit scripts without touching app ==="
mkdir -p scripts maya1_sync /opt/hesab-backups
cp "$REPO/scripts/maya1_readonly_sync.py" scripts/maya1_readonly_sync.py
cp "$REPO/scripts/maya1_usage_daily.py" scripts/maya1_usage_daily.py
chmod 700 scripts/maya1_readonly_sync.py scripts/maya1_usage_daily.py
chown root:root scripts/maya1_readonly_sync.py
chmod 750 maya1_sync

echo "=== DRY-RUN: check 145 users and all 141 exact IDs ==="
python3 scripts/maya1_readonly_sync.py --check
echo "=== FIRST LIVE SNAPSHOT (still read-only to x-ui and DB) ==="
python3 scripts/maya1_readonly_sync.py --sync

echo "=== PREPARE SAFE APP-ONLY PATCH ==="
if grep -q 'MAYA1_CONTROL_INSTALL_V1' docker-compose.sms.yml; then
  echo "ALREADY INSTALLED: updating snapshot only, no app restart needed."
  exit 0
fi
BACKUP="/opt/hesab-backups/maya1-control-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
cp -a docker-compose.sms.yml "$BACKUP/docker-compose.sms.yml"
if [[ -e patches/maya1_control.py ]]; then
  cp -a patches/maya1_control.py "$BACKUP/maya1_control.py"
fi

rollback(){
  trap - ERR
  echo "ERROR: restoring previous app compose configuration"
  cp -a "$BACKUP/docker-compose.sms.yml" docker-compose.sms.yml
  if [[ -f "$BACKUP/maya1_control.py" ]]; then
    cp -a "$BACKUP/maya1_control.py" patches/maya1_control.py
  else
    rm -f patches/maya1_control.py
  fi
  "${C[@]}" up -d --no-deps --no-build --force-recreate app || true
  echo "Rollback attempted. No subscription or x-ui change."
  exit 1
}
trap rollback ERR

python3 - "$REPO" <<'PY'
from pathlib import Path
import ast,sys
repo=Path(sys.argv[1])
admin=(repo/"patches/maya1_control.py").read_text(encoding="utf8")
compile(admin,"maya1_control.py","exec")
assert "MAYA1_CONTROL_VIEW_V1" in admin
assert "UPDATE subscriptions" not in admin and "DELETE FROM" not in admin
source=Path("docker-compose.sms.yml").read_text(encoding="utf8")
mount="      - ./patches/sms_admin.py:/sms-patch/sms_admin.py:ro\n"
compile_anchor="        python -m py_compile /app/app/main.py\n"
assert source.count(mount)==1, "Unknown app mount structure"
assert source.count(compile_anchor)==1, "Unknown app command structure"
assert "MAYA1_CONTROL_INSTALL_V1" not in source
assert "/srv/maya1-sync" not in source
source=source.replace(mount,mount+
    "      - ./patches/maya1_control.py:/sms-patch/maya1_control.py:ro\n"
    "      - ./maya1_sync:/srv/maya1-sync:ro\n",1)
source=source.replace(compile_anchor,
    "        # MAYA1_CONTROL_INSTALL_V1\n"
    "        if ! grep -q 'MAYA1_CONTROL_VIEW_V1' /app/app/main.py; then\n"
    "          cat /sms-patch/maya1_control.py >> /app/app/main.py\n"
    "        fi\n"+compile_anchor,1)
Path("patches/maya1_control.py").write_text(admin,encoding="utf8")
Path("docker-compose.sms.yml").write_text(source,encoding="utf8")
print("App-only compose patch prepared. Existing portal/Darma/Caddy configuration unchanged.")
PY
"${C[@]}" config -q

echo "=== RECREATE ONLY ADMIN APP (not db, portal, Caddy or x-ui) ==="
"${C[@]}" up -d --no-deps --no-build --force-recreate app

HEALTH=0
for i in $(seq 1 35); do
  if "${C[@]}" exec -T app python -c \
     'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=3).read()' \
     >/dev/null 2>&1; then HEALTH=1; break; fi
  sleep 2
done
test "$HEALTH" -eq 1
"${C[@]}" exec -T app grep -q MAYA1_CONTROL_VIEW_V1 /app/app/main.py

echo "=== SECURITY: ensure anonymous control room is not exposed ==="
"${C[@]}" exec -T app python - <<'PY'
import http.client
c=http.client.HTTPConnection("127.0.0.1",8000,timeout=5)
c.request("GET","/control-room")
r=c.getresponse()
body=r.read()
c.close()
assert not (r.status==200 and b'mc-root' in body), "SECURITY: anonymous user sees maya1 inventory"
print("Anonymous control-room test:",r.status)
PY

echo "=== ACTIVATE 5-MINUTE REFRESH ==="
cat > /etc/cron.d/hesab-maya1-sync <<'CRON'
*/5 * * * * root /usr/bin/python3 /opt/vpn-control-center/scripts/maya1_readonly_sync.py --sync >> /var/log/hesab-maya1-sync.log 2>&1
CRON
chmod 644 /etc/cron.d/hesab-maya1-sync
trap - ERR
echo "SUCCESS: MAYA1 READ-ONLY CONTROL ROOM ACTIVE"
echo "Open: https://hesab.filmjadiid.ir/control-room"
echo "Backup: $BACKUP"
echo "No DB writes, no expiry changes, no x-ui user changes, no customer-portal changes."
