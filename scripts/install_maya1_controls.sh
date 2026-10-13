#!/usr/bin/env bash
# MAYA1_CONTROLS_INSTALL_V1
# Upgrade a VERIFIED existing read-only maya1 sync with audited manual toggles.
# Does not change financial SQL, x-ui database directly, Caddy or customer-portal.
set -Eeuo pipefail
umask 077
[[ $(id -u) -eq 0 ]] || { echo "STOP: run as root"; exit 2; }
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE=/opt/vpn-control-center
HOST=94.184.4.38
EXPECTED_HOST_FP=SHA256:wbtVoThIOcMgKp9jeoQCneTNX1YRXvwNfyFTCT8Bt3s
KEY=/root/.ssh/hesab_maya1_control
C=(docker compose -f docker-compose.yml -f docker-compose.sms.yml)
cd "$BASE"

echo "===== PRECHECK: existing read-only integration and healthy services ====="
test -s scripts/maya1_readonly_sync.py
test -s patches/maya1_control.py
test -s maya1_sync/mapping.json
test -s maya1_sync/snapshot.json
grep -q MAYA1_CONTROL_INSTALL_V1 docker-compose.sms.yml
test -s "$REPO/scripts/maya1_xui_control.py"
test -s "$REPO/scripts/maya1_control_gateway.py"
test -s "$REPO/scripts/maya1_usage_daily.py"
test -s "$REPO/patches/maya1_control.py"
test -s "$REPO/scripts/maya1_readonly_sync.py"
"${C[@]}" config -q
"${C[@]}" exec -T app python -c \
  'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=5).read()'
"${C[@]}" exec -T customer-portal python -c \
  'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8091/health",timeout=5).read()'
python3 -m py_compile "$REPO/scripts/maya1_xui_control.py" \
 "$REPO/scripts/maya1_control_gateway.py" "$REPO/scripts/maya1_usage_daily.py" \
 "$REPO/scripts/maya1_readonly_sync.py" "$REPO/patches/maya1_control.py"
"${C[@]}" exec -T app python -c '
import ast,sys
from jinja2 import Environment
tree=ast.parse(sys.stdin.read())
values=[node.value.value for node in tree.body
        if isinstance(node,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=="_MC_PANEL" for t in node.targets)]
assert len(values)==1
Environment(autoescape=True).parse(values[0])
print("New control-room template: valid Jinja")
' < "$REPO/patches/maya1_control.py"
if grep -q MAYA1_CONTROL_WRITE_V1 patches/maya1_control.py; then
  echo "STOP: write controls already installed, do not double-install"
  exit 3
fi
python3 scripts/maya1_readonly_sync.py --check

echo "===== PRECHECK: owner-approved 141-user mapping ====="
ALLOW_B64="$(python3 - <<'PY'
import base64,json
from pathlib import Path
f=json.loads(Path("maya1_sync/mapping.json").read_text())
assert f["format"]=="MAYA1_CONTROL_MAPPING_V1"
assert f["expected_sha"]=="8e1509674cf0c06d1e8015064c8c3b69b76931311bce4489b1bbda49d50f37fb"
mapping=f["mapping"]
assert len(mapping)==145
names=sorted(k for k,v in mapping.items() if v.get("id") is not None)
assert len(names)==141 and len(set(names))==141
assert len({mapping[k]["id"] for k in names})==141
doc={"format":"MAYA1_ALLOWED_CLIENTS_V1","emails":names}
print(base64.b64encode(json.dumps(doc,separators=(",",":")).encode()).decode())
PY
)"
test -n "$ALLOW_B64"

echo "===== PIN SSH HOST FINGERPRINT ====="
mkdir -p /root/.ssh
chmod 700 /root/.ssh
SCAN="$(ssh-keyscan -T 8 -t ed25519 "$HOST" 2>/dev/null | grep 'ssh-ed25519' | head -1)"
test -n "$SCAN"
FP="$(printf '%s\n' "$SCAN" | ssh-keygen -lf - | awk '{print $2}')"
[[ "$FP" == "$EXPECTED_HOST_FP" ]] || {
  echo "STOP: maya1 SSH host fingerprint mismatch! Found $FP"
  exit 4
}
if ! ssh-keygen -F "$HOST" -f /root/.ssh/known_hosts >/dev/null 2>&1; then
  printf '%s\n' "$SCAN" >> /root/.ssh/known_hosts
  chmod 600 /root/.ssh/known_hosts
fi

echo "===== GENERATE SEPARATE CONTROL-ONLY SSH KEY ====="
if [[ ! -e "$KEY" ]]; then
  ssh-keygen -q -t ed25519 -N '' -f "$KEY" -C hesab-maya1-control
fi
test -s "$KEY.pub"
chmod 600 "$KEY"
PUB="$(cat "$KEY.pub")"
[[ "$PUB" == ssh-ed25519\ * ]] || { echo "STOP: unexpected key"; exit 5; }

echo "===== INSTALL FORCED COMMAND ON MAYA1 ====="
REMOTE_B64="$(base64 -w0 < "$REPO/scripts/maya1_xui_control.py")"
read -r -d '' REMOTE <<EOF || true
set -eu
umask 077
mkdir -p /etc/hesab-maya1 /root/.ssh /usr/local/sbin
chmod 700 /etc/hesab-maya1 /root/.ssh
printf '%s' '$REMOTE_B64' | base64 -d > /usr/local/sbin/maya1-xui-control
python3 -m py_compile /usr/local/sbin/maya1-xui-control
chmod 700 /usr/local/sbin/maya1-xui-control
printf '%s' '$ALLOW_B64' | base64 -d > /etc/hesab-maya1/allowed-clients.json
chmod 600 /etc/hesab-maya1/allowed-clients.json
touch /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
if ! grep -Fq '$PUB' /root/.ssh/authorized_keys; then
  printf '%s\n' 'restrict,command="/usr/local/sbin/maya1-xui-control --execute" $PUB' >> /root/.ssh/authorized_keys
fi
printf '%s\n' 'MAYA1 CONTROL FORCED COMMAND PREPARED'
EOF
ssh -T -o StrictHostKeyChecking=yes -o ConnectTimeout=12 \
  -o PreferredAuthentications=password,keyboard-interactive \
  -o PubkeyAuthentication=no "root@$HOST" sh -se <<< "$REMOTE"

echo "===== VERIFY LOCAL X-UI AUTHENTICATION ON MAYA1 ====="
if [[ "${MAYA1_AUTH_ALREADY_CONFIGURED:-0}" == "1" ]]; then
  echo "Resuming after successful panel configuration; do not request panel credentials again."
else
  echo "Run this installer directly from a terminal, not via a heredoc or piped script."
  echo "Credentials are entered on maya1 and are never shown or copied to the dashboard."
  if [[ ! -t 0 ]]; then
    echo "STOP: interactive X-UI setup needs a real terminal."
    echo "If credentials were already saved on maya1, rerun with MAYA1_AUTH_ALREADY_CONFIGURED=1."
    exit 5
  fi
  ssh -tt -o StrictHostKeyChecking=yes -o ConnectTimeout=12 \
    -o PreferredAuthentications=password,keyboard-interactive \
    -o PubkeyAuthentication=no "root@$HOST" \
    'python3 /usr/local/sbin/maya1-xui-control --configure'
fi
ssh -T -o StrictHostKeyChecking=yes -o ConnectTimeout=12 \
  -o PreferredAuthentications=password,keyboard-interactive \
  -o PubkeyAuthentication=no "root@$HOST" \
  'python3 /usr/local/sbin/maya1-xui-control --check'

echo "===== BACKUP DASHBOARD APP FILES ====="
BACKUP="/opt/hesab-backups/maya1-controls-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
for file in patches/maya1_control.py scripts/maya1_readonly_sync.py scripts/maya1_usage_daily.py scripts/maya1_control_gateway.py; do
  if [[ -f "$file" ]]; then
    mkdir -p "$BACKUP/$(dirname "$file")"
    cp -a "$file" "$BACKUP/$file"
  fi
done
MODIFIED=0
rollback(){
  trap - ERR
  echo "ERROR: trying to restore previous dashboard files..."
  systemctl stop hesab-maya1-controls.service >/dev/null 2>&1 || true
  systemctl disable hesab-maya1-controls.service >/dev/null 2>&1 || true
  for file in patches/maya1_control.py scripts/maya1_readonly_sync.py scripts/maya1_usage_daily.py scripts/maya1_control_gateway.py; do
    if [[ -f "$BACKUP/$file" ]]; then
      cp -a "$BACKUP/$file" "$file"
    else
      rm -f "$file"
    fi
  done
  if [[ "$MODIFIED" == 1 ]]; then
    "${C[@]}" up -d --no-deps --no-build --force-recreate app || true
  fi
  echo "ROLLBACK ATTEMPTED. Source x-ui client data and finance unchanged."
  exit 1
}
trap rollback ERR

echo "===== INSTALL USAGE HISTORY AND CONTROL GATEWAY ====="
cp "$REPO/patches/maya1_control.py" patches/maya1_control.py
cp "$REPO/scripts/maya1_readonly_sync.py" scripts/maya1_readonly_sync.py
cp "$REPO/scripts/maya1_usage_daily.py" scripts/maya1_usage_daily.py
cp "$REPO/scripts/maya1_control_gateway.py" scripts/maya1_control_gateway.py
chmod 700 scripts/maya1_readonly_sync.py scripts/maya1_usage_daily.py scripts/maya1_control_gateway.py
MODIFIED=1
python3 scripts/maya1_readonly_sync.py --sync

echo "===== ENABLE LOCAL UNIX SOCKET DAEMON (NO NEW NETWORK PORT) ====="
cat > /etc/systemd/system/hesab-maya1-controls.service <<'UNIT'
[Unit]
Description=Hesab VPN Maya1 manual x-ui controls via restricted SSH
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/vpn-control-center
ExecStart=/usr/bin/python3 /opt/vpn-control-center/scripts/maya1_control_gateway.py
Restart=on-failure
RestartSec=3
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now hesab-maya1-controls.service
sleep 2
systemctl is-active --quiet hesab-maya1-controls.service
test -S maya1_sync/control.sock

echo "===== RECREATE ONLY ADMIN APP; LEAVE PORTAL/CADDY/DB/X-UI RUNNING ====="
"${C[@]}" up -d --no-deps --no-build --force-recreate app
OK=0
for i in $(seq 1 40); do
  if "${C[@]}" exec -T app python -c \
    'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=3).read()' \
    >/dev/null 2>&1; then OK=1;break;fi
  sleep 2
done
test "$OK" -eq 1
"${C[@]}" exec -T app grep -q MAYA1_CONTROL_WRITE_V1 /app/app/main.py
"${C[@]}" exec -T app python - <<'PY'
import os,socket
path="/srv/maya1-sync/control.sock"
assert os.path.exists(path)
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
s.settimeout(4)
s.connect(path)
s.close()
print("Admin container can reach local control socket")
PY

echo "===== CHECK UNAUTHENTICATED ACCESS IS BLOCKED ====="
"${C[@]}" exec -T app python - <<'PY'
import http.client
c=http.client.HTTPConnection("127.0.0.1",8000,timeout=6)
c.request("GET","/control-room")
r=c.getresponse()
body=r.read()
c.close()
assert not (r.status==200 and b'mc-root' in body), "SECURITY: inventory exposed to anonymous"
print("Unauthenticated control room HTTP:",r.status)
PY
trap - ERR
echo "SUCCESS: MAYA1 MANUAL CONTROL + DAILY USAGE INSTALLED"
echo "Dashboard: https://hesab.filmjadiid.ir/control-room"
echo "Saved original app files in: $BACKUP"
echo "This installation did NOT toggle any user."
