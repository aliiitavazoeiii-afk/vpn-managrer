#!/usr/bin/env bash
# HESAB_BROWSER_SMS_READONLY_AUDIT_V1
# Read-only SMS audit for a single phone. Does not print phone or message bodies.
set -Eeuo pipefail
cd /opt/vpn-control-center
if (( $# == 0 )); then
  read -r -p 'Mobile number (09xxxxxxxxx): ' INPUT_PHONE
else
  INPUT_PHONE="$1"
fi
if [[ ! "$INPUT_PHONE" =~ ^09[0-9]{9}$ ]]; then
  echo 'Invalid Iranian mobile number' >&2
  exit 2
fi
echo '=== Historical debt SMS jobs and browser intents ==='
docker compose -f docker-compose.yml -f docker-compose.sms.yml exec -T -e "SMS_LOOKUP_PHONE=$INPUT_PHONE" db sh -lc \
  'PGPASSWORD="$POSTGRES_PASSWORD" PGOPTIONS="-c default_transaction_read_only=on" psql -X -v ON_ERROR_STOP=1 -P pager=off -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v target_phone="$SMS_LOOKUP_PHONE"' <<'SQL'
SELECT id, source, status, attempts,
       to_char(created_at AT TIME ZONE 'Asia/Tehran','YYYY-MM-DD HH24:MI') AS created_tehran,
       to_char(sent_at AT TIME ZONE 'Asia/Tehran','YYYY-MM-DD HH24:MI') AS sent_tehran,
       to_char(delivered_at AT TIME ZONE 'Asia/Tehran','YYYY-MM-DD HH24:MI') AS delivered_tehran
FROM sms_jobs
WHERE phone = :'target_phone' AND source LIKE 'debt:%'
ORDER BY id DESC LIMIT 30;
SELECT id, source, cycle_key, status, moved_count,
       to_char(created_at AT TIME ZONE 'Asia/Tehran','YYYY-MM-DD HH24:MI') AS created_tehran
FROM sms_browser_intents
WHERE phone = :'target_phone'
ORDER BY id DESC LIMIT 30;
SQL
echo 'READ-ONLY complete. No SMS or accounting changes made.'
