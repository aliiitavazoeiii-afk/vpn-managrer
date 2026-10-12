#!/usr/bin/env bash
# Deploy visual-only, AJAX debt-SMS controls without touching payments or SMS jobs.
set -Eeuo pipefail
umask 077
cd /opt/vpn-control-center
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
C=(docker compose -f docker-compose.yml -f docker-compose.sms.yml)
COMPOSE=docker-compose.sms.yml
PATCH=patches/sms_nojump.py
MARK=DEBT_SMS_LIVE_NOJUMP_V1
test -s "$REPO/$PATCH"
test -s "$COMPOSE"
test -s patches/sms_aban_default.py

if grep -q "$MARK" "$COMPOSE";then
  echo "ALREADY INSTALLED: SMS no-jump controls";exit 0
fi

echo "=== Backing up SMS app configuration ==="
BACKUP="/opt/hesab-backups/sms-nojump-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP/patches"
cp -a "$COMPOSE" "$BACKUP/docker-compose.sms.yml"
if test -e "$PATCH";then cp -a "$PATCH" "$BACKUP/$PATCH";fi
echo "BACKUP=$BACKUP"

rollback(){
  trap - ERR
  echo "ROLLBACK: previous admin config"
  cp -a "$BACKUP/docker-compose.sms.yml" "$COMPOSE"
  if test -f "$BACKUP/$PATCH";then cp -a "$BACKUP/$PATCH" "$PATCH";else rm -f "$PATCH";fi
  "${C[@]}" up -d --no-deps --no-build --force-recreate app || true
  exit 1
}
trap rollback ERR

python3 - "$REPO" <<'PY'
from pathlib import Path
import sys
repo=Path(sys.argv[1])
compose=Path("docker-compose.sms.yml")
target=Path("patches/sms_nojump.py")
patch=(repo/target).read_text(encoding="utf-8")
compile(patch,str(target),"exec")
assert "DEBT_SMS_LIVE_NOJUMP_V1" in patch
assert "window.__hesabSmsNoJumpV1" in patch
assert 'debt-sms-header-form' in patch
s=compose.read_text(encoding="utf-8")
anchor="      - ./patches/sms_aban_default.py:/sms-patch/sms_aban_default.py:ro\n"
runtime="        python -m py_compile /app/app/main.py\n"
assert s.count(anchor)==1 and s.count(runtime)==1, "Live compose anchors differ"
assert "DEBT_SMS_LIVE_NOJUMP_V1" not in s
s=s.replace(anchor,anchor+
    "      - ./patches/sms_nojump.py:/sms-patch/sms_nojump.py:ro\n",1)
s=s.replace(runtime,
    "        if ! grep -q 'DEBT_SMS_LIVE_NOJUMP_V1' /app/app/main.py; then\n"
    "          cat /sms-patch/sms_nojump.py >> /app/app/main.py\n"
    "        fi\n"+runtime,1)
target.write_text(patch,encoding="utf-8")
compose.write_text(s,encoding="utf-8")
PY

"${C[@]}" config -q
echo "=== Restarting admin only; no messages queued ==="
"${C[@]}" up -d --no-deps --no-build --force-recreate app
ready=0
for i in $(seq 1 30);do
 if "${C[@]}" exec -T app sh -lc \
    "grep -q '$MARK' /app/app/main.py && curl -fsS http://127.0.0.1:8000/health >/dev/null" \
    >/dev/null 2>&1;then ready=1;break;fi
 sleep 2
done
test "$ready" -eq 1
trap - ERR
echo "SUCCESS: DEBT SMS TWO BUTTONS + NO-REFRESH TRANSFER ACTIVE"
echo "No SMS sent, no billing or account changes. Backup: $BACKUP"
