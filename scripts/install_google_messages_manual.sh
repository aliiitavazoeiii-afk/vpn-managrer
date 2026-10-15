#!/usr/bin/env bash
# Single entrypoint for fresh or already-installed SMS V2 servers.
set -Eeuo pipefail
test "$(id -u)" -eq 0 || { echo "Run as root"; exit 2; }
SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
if grep -Fq '# GOOGLE_MESSAGES_MANUAL_HANDOFF_V1' sms_gateway/server.py; then
  echo "Already installed (manual handoff API present). No changes made."; exit 0
fi
if grep -Fq '# NATIVE_SMS_V2_SEPARATE_QUEUE' sms_gateway/server.py; then
  bash "$SOURCE/scripts/upgrade_manual_google_messages.sh"
else
  bash "$SOURCE/scripts/install_native_sms_v2_safe.sh"
fi
