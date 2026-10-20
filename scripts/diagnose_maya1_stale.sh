#!/usr/bin/env bash
# HESAB_MAYA1_DIAG_ONLY_V1. Read-only diagnostics; no cron modification.
set -u
cd /opt/vpn-control-center || exit 1
echo '=== Existing integration: Maya1 (read-only audit) ==='
echo 'Cron service:'
systemctl is-active cron 2>/dev/null || true
echo 'Maya1 scheduled job:'
if test -s /etc/cron.d/hesab-maya1-sync; then
  grep -E 'maya1_readonly_sync.py|^#' /etc/cron.d/hesab-maya1-sync | head -8
else
  echo 'MISSING cron job'
fi
echo 'Snapshot and mapping modification time (no customer data):'
for p in maya1_sync/snapshot.json maya1_sync/mapping.json maya1_sync/daily_usage.json; do
  if test -f "$p"; then stat -c '%n | %y | %s bytes' "$p"; else echo "MISSING $p"; fi
done
echo 'Recent sync outcome (sensitive usernames omitted):'
if test -s /var/log/hesab-maya1-sync.log; then
  tail -30 /var/log/hesab-maya1-sync.log |
    grep -E 'MAYA1 VERIFIED|MAYA1 STOP|SYNC COMPLETE|roster changed|fingerprint|SSH export failed|Permission denied|timeout|Connection refused|No unique exact match|MAPPING MISMATCH|ALREADY_RECORDED|DAILY USAGE' |
    sed -E 's/(No unique exact match for:).*/\1 [redacted]/;s/(for:).*/\1 [redacted]/' | tail -14
else echo 'Sync log missing';fi
echo 'One manual READ-ONLY health check:'
if test -s scripts/maya1_readonly_sync.py; then
  python3 scripts/maya1_readonly_sync.py --check 2>&1 |
    sed -E 's/(No unique exact match for:).*/\1 [redacted]/' | tail -8
else echo 'Local Maya1 sync script missing';fi
echo 'No changes made to Maya1, cron, or finance.'
