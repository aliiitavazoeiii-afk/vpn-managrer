#!/usr/bin/env bash
# HESAB_MAYA_NET_METER_PAIR_V2 — management host => one Maya server
# Verify remote SSH host key from actual server console, then run this script.
# Does not change SSH daemon, firewall, XUI, finance, or VPN services.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo "STOP: management root required";exit 2; }
[[ "$#" -eq 3 || "$#" -eq 4 ]] || { echo "Usage: $0 maya1|maya-s3|maya4 SERVER_IP PHYSICAL_NIC [SSH_PORT]";exit 2; }
SERVER="$1";IP="$2";NIC="$3";PORT="${4:-22}"
case "$SERVER" in maya1|maya-s3|maya4);; *)echo "STOP: unknown Maya server";exit 2;;esac
cd /opt/vpn-control-center
SCRIPT=scripts/maya_net_meter_manage_v2.py
[[ -s "$SCRIPT" && -s scripts/maya_net_meter_remote_setup_v2.sh ]] || {
 echo "STOP: hub installation required";exit 3;
}
python3 "$SCRIPT" init "$SERVER" "$IP" "$NIC" "$PORT"
PUB="/root/.ssh/hesab_meter_$(printf '%s' "$SERVER" | tr '-' '_').pub"
[[ -s "$PUB" ]] || { echo "STOP: public key missing";exit 3; }
echo "=== VERIFY REMOTE SSH HOST FINGERPRINT BEFORE CONTINUING ==="
echo "On ACTUAL $SERVER console run: ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub"
echo "Compare it with the SSH host key's fingerprint. Never remove known_hosts blindly."
read -r -p "Fingerprint independently verified? Type VERIFIED: " ANSWER
[[ "$ANSWER" == VERIFIED ]] || { echo "ABORT: SSH identity not confirmed";exit 3; }
ssh -p "$PORT" -o StrictHostKeyChecking=ask -o ConnectTimeout=10 "root@$IP" 'echo VERIFIED_REMOTE_SSH'
echo "=== TRANSFER METER FILES, NO OTHER FILES ==="
scp -P "$PORT" -o StrictHostKeyChecking=yes -o ConnectTimeout=10 \
 scripts/maya_net_meter_sensor_v2.py scripts/maya_net_meter_remote_setup_v2.sh \
 "$PUB" "root@$IP:/root/"
echo "=== INSTALL RESTRICTED READONLY SENSOR ==="
ssh -T -p "$PORT" -o StrictHostKeyChecking=yes -o ConnectTimeout=10 "root@$IP" \
  "bash /root/maya_net_meter_remote_setup_v2.sh '$NIC' '5.10.248.50' /root/maya_net_meter_sensor_v2.py < /root/$(basename "$PUB")"
echo "=== VERIFY SENSOR OUTPUT FROM DEDICATED SSH KEY ==="
python3 "$SCRIPT" verify "$SERVER"
echo "SUCCESS: $SERVER RX/TX READONLY SENSOR PAIRED"
echo "Remaining quota requires a confirmed RX/TX billing direction and provider baseline."
