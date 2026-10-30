#!/usr/bin/env bash
# HESAB_MAYA_NET_METER_REMOTE_SETUP_V2 — execute on EACH Maya Linux host as root.
# Args: PHYSICAL_NIC, management IPv4, local sensor source. Public key read from STDIN.
# No XUI config, firewall, traffic shaping, iptables or network changes.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo "STOP: root required";exit 2; }
[[ "$#" == 3 ]] || { echo "USAGE: $0 IFACE MANAGEMENT_IPV4 /root/maya_net_meter_sensor_v2.py < key.pub"; exit 2; }
IFACE="$1";MANAGER="$2";SOURCE="$3"
[[ "$IFACE" =~ ^[a-zA-Z0-9_.:-]{1,24}$ && "$IFACE" != lo ]] || { echo "Invalid NIC";exit 3; }
[[ -s "$SOURCE" ]] || { echo "Missing meter sensor file";exit 3; }
python3 - "$MANAGER" <<'PY'
import ipaddress,sys
address=ipaddress.ip_address(sys.argv[1])
assert address.version==4 and address.is_global
PY
test -d "/sys/class/net/$IFACE" || { echo "NIC_NOT_FOUND $IFACE";exit 3; }
IFS= read -r PUBLIC_KEY || { echo "Public key missing";exit 3; }
[[ "$PUBLIC_KEY" =~ ^ssh-ed25519[[:space:]]+[a-zA-Z0-9+/=]+([[:space:]].*)?$ ]] || {
 echo "Missing valid ed25519 public key on stdin";exit 3;
}
read -r KEY_TYPE KEY_MATERIAL KEY_COMMENT <<< "$PUBLIC_KEY"
KEY_LINE="ssh-ed25519 $KEY_MATERIAL"
python3 -m py_compile "$SOURCE"
install -d -m 0755 /usr/local/libexec
install -o root -g root -m 0755 "$SOURCE" /usr/local/libexec/hesab-net-meter
/usr/local/libexec/hesab-net-meter "$IFACE" >/dev/null || {
 echo "Sensor selftest failed";exit 3;
}
if ! id hesab-meter >/dev/null 2>&1;then
 useradd --system --create-home --home-dir /var/lib/hesab-meter --shell /bin/sh hesab-meter
fi
HOME_DIR="$(getent passwd hesab-meter | cut -d: -f6)"
[[ "$HOME_DIR" == /var/lib/hesab-meter ]] || { echo "STOP: existing meter account has wrong home";exit 3; }
install -d -o hesab-meter -g hesab-meter -m 0700 "$HOME_DIR/.ssh"
touch "$HOME_DIR/.ssh/authorized_keys"
chown hesab-meter:hesab-meter "$HOME_DIR/.ssh/authorized_keys"
chmod 0600 "$HOME_DIR/.ssh/authorized_keys"
RESTRICT="from=\"$MANAGER\",restrict,command=\"/usr/local/libexec/hesab-net-meter $IFACE\" $KEY_LINE"
if grep -Fq "$KEY_LINE" "$HOME_DIR/.ssh/authorized_keys";then
 grep -Fqx "$RESTRICT" "$HOME_DIR/.ssh/authorized_keys" || {
   echo "STOP: same key already has different restrictions; inspect manually";exit 4;
 }
else
 printf '%s\n' "$RESTRICT" >>"$HOME_DIR/.ssh/authorized_keys"
fi
echo "REMOTE_MAYA_NET_METER_V2_READY interface=$IFACE"
echo "REMOTE_COMMAND_FIXED=TRUE; SSH_FROM_ONLY=$MANAGER; NO_XUI_CHANGES"
echo "METRICS_ONLY_RX_TX; quota/direction configured later on management server"
