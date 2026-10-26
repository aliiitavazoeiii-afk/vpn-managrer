#!/usr/bin/env bash
# HESAB_MAYA_SSH_HTTP_TUNNEL_V1
# Pair an OpenSSH key restricted to forwarding a single X-UI loopback port.
# No firewall changes, no X-UI config changes, no app restart.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo "STOP: run with sudo/root"; exit 2; }
[[ "$#" -eq 3 ]] || { echo "Usage: $0 maya1|maya-s3|maya4 REMOTE_IPV4 XUI_PORT"; exit 2; }
SERVER="$1"; HOST="$2"; REMOTE_PORT="$3"
case "$SERVER" in
  maya1) KEY="/root/.ssh/hesab_maya1_tunnel";;
  maya-s3) KEY="/root/.ssh/hesab_maya_s3_tunnel";;
  maya4) KEY="/root/.ssh/hesab_maya4_tunnel";;
  *) echo "STOP: unsupported server";exit 2;;
esac
python3 - "$HOST" "$REMOTE_PORT" <<'PY'
import sys,ipaddress
host=ipaddress.ip_address(sys.argv[1])
assert host.version==4 and host.is_global,"Public IPv4 expected"
port=int(sys.argv[2])
assert 1<=port<=65535
PY
mkdir -p /root/.ssh
chmod 700 /root/.ssh
if [[ ! -s "$KEY" ]]; then
  [[ ! -e "$KEY.pub" ]] || { echo "STOP: orphan public key; inspect before continuing";exit 3; }
  ssh-keygen -q -t ed25519 -N '' -f "$KEY" -C "hesab-$SERVER-ssh-http-protection"
fi
chmod 600 "$KEY"
[[ -s "$KEY.pub" ]] || { echo "STOP: missing public key";exit 3; }
PUB="$(cat "$KEY.pub")"
[[ "$PUB" == ssh-ed25519\ * ]] || { echo "STOP: key format invalid";exit 3; }
RESTRICT="restrict,port-forwarding,permitopen=\"127.0.0.1:$REMOTE_PORT\" $PUB"
ENCODED="$(printf '%s' "$RESTRICT" | base64 -w0)"
echo ""
echo "=== REMOTE SSH HOST TRUST ==="
echo "Before accepting a new SSH fingerprint, compare it with the fingerprint"
echo "shown by running on the REAL $SERVER server:"
echo "  ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub"
echo "If they differ, cancel with Ctrl-C."
echo ""
echo "=== PAIR RESTRICTED KEY (may request remote SSH password) ==="
ssh -T -o StrictHostKeyChecking=ask -o ConnectTimeout=12 "root@$HOST" bash -s <<REMOTE
set -Eeuo pipefail
mkdir -p /root/.ssh
chmod 700 /root/.ssh
touch /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
LINE="\$(printf '%s' '$ENCODED' | base64 -d)"
if ! grep -Fqx "\$LINE" /root/.ssh/authorized_keys; then
 printf '%s\n' "\$LINE" >> /root/.ssh/authorized_keys
fi
echo 'REMOTE: restricted SSH forwarding key installed; X-UI unchanged'
REMOTE
echo ""
echo "=== VERIFY TUNNEL AUTH (no new public port) ==="
python3 - "$HOST" "$REMOTE_PORT" "$KEY" <<'PY'
import subprocess,socket,sys,time
host,remote,key=sys.argv[1],sys.argv[2],sys.argv[3]
bind=socket.socket()
bind.bind(("127.0.0.1",0))
port=bind.getsockname()[1]
bind.close()
cmd=["ssh","-N","-T","-i",key,
 "-o","IdentitiesOnly=yes","-o","BatchMode=yes",
 "-o","StrictHostKeyChecking=yes","-o","ExitOnForwardFailure=yes",
 "-o","ConnectTimeout=8","-L",f"127.0.0.1:{port}:127.0.0.1:{remote}",
 "root@"+host]
process=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,
 stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 for attempt in range(50):
  if process.poll() is not None:raise RuntimeError("SSH tunnel command failed")
  with socket.socket() as probe:
   probe.settimeout(.2)
   if probe.connect_ex(("127.0.0.1",port))==0:
    print("SUCCESS: RESTRICTED SSH TUNNEL KEY VERIFIED")
    break
  time.sleep(.1)
 else:raise RuntimeError("SSH tunnel not ready")
finally:
 process.terminate()
 try:process.wait(timeout=4)
 except subprocess.TimeoutExpired:
  process.kill();process.wait()
PY
echo "NEXT: sudo python3 /opt/vpn-control-center/scripts/maya_multi_panel_sync.py configure $SERVER"
echo "Enter your existing HTTP panel URL. API credentials will travel through SSH only."
