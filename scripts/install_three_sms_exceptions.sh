#!/usr/bin/env bash
# Grant one manually initiated, narrowly scoped debt reminder per specified phone.
# App-only restart; absolutely no automatic SMS, payment or subscription changes.
set -Eeuo pipefail
umask 077
cd /opt/vpn-control-center
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
C=(docker compose -f docker-compose.yml -f docker-compose.sms.yml)
TARGET=patches/sms_aban_default.py
MARKER=_ABAN_MANUAL_ONCE_PHONES
test -s "$REPO/$TARGET"
test -s "$TARGET"
grep -q 'SMS_DEBT_DEFAULT_ABAN_V1' docker-compose.sms.yml
grep -q 'DEBT_SMS_LIVE_NOJUMP_V1' docker-compose.sms.yml
if grep -q "$MARKER" "$TARGET";then
 echo "ALREADY INSTALLED: three-phone manual SMS exception";exit 0
fi

BACKUP="/opt/hesab-backups/sms-three-exceptions-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP/patches"
cp -a "$TARGET" "$BACKUP/$TARGET"
echo "BACKUP=$BACKUP"

rollback(){
 trap - ERR
 echo "ERROR: restoring previous SMS guard"
 cp -a "$BACKUP/$TARGET" "$TARGET"
 "${C[@]}" up -d --no-deps --no-build --force-recreate app || true
 echo "Rollback attempted; check service health."
 exit 1
}
trap rollback ERR

python3 - "$REPO" <<'PY'
from pathlib import Path
import ast
import sys
repo=Path(sys.argv[1])
target=Path("patches/sms_aban_default.py")
incoming=(repo/target).read_text(encoding="utf-8")
existing=target.read_text(encoding="utf-8")
assert "SMS_DEBT_DEFAULT_ABAN_V1" in existing
assert "_ABAN_MANUAL_ONCE_PHONES" not in existing
assert "pg_advisory_xact_lock" in existing and "current_jalali_month_start" in existing
assert "pg_advisory_xact_lock" in incoming and "current_jalali_month_start" in incoming
assert "manual-exception-aban1" in incoming
tree=ast.parse(incoming)
for n in tree.body:
    if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="_ABAN_MANUAL_ONCE_PHONES" for t in n.targets):
        vals={x.value for x in n.value.args[0].elts}
        assert vals=={"09120758984","09126260485","09129743094"}, vals
        break
else:
    raise RuntimeError("Unexpected exception definition")
compile(incoming,str(target),"exec")
target.write_text(incoming,encoding="utf-8")
print("Exactly three operator-authorized SMS exceptions installed.")
PY

"${C[@]}" config -q
"${C[@]}" up -d --no-deps --no-build --force-recreate app

ready=0
for n in $(seq 1 30);do
 if "${C[@]}" exec -T app sh -lc \
   'grep -q "_ABAN_MANUAL_ONCE_PHONES" /app/app/main.py && grep -q "DEBT_SMS_LIVE_NOJUMP_V1" /app/app/main.py && curl -fsS http://127.0.0.1:8000/health >/dev/null' \
   >/dev/null 2>&1;then ready=1;break;fi
 sleep 2
done
test "$ready" -eq 1
trap - ERR
echo "SUCCESS: THREE ONE-TIME MANUAL SMS EXCEPTIONS ENABLED"
echo "No SMS has been queued or sent. Only a deliberate click in وصول بدهی queues SMS."
echo "All ordinary users remain duplicate-protected. Backup: $BACKUP"
