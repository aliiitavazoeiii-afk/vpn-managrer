#!/usr/bin/env bash
# Installs ONLY the canonical Aban default SMS message for debt collection.
# Does not send SMS, touch database or rebuild customer portal.
set -Eeuo pipefail
umask 077
cd /opt/vpn-control-center
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
C=(docker compose -f docker-compose.yml -f docker-compose.sms.yml)
COMPOSE=docker-compose.sms.yml
TARGET=patches/sms_aban_default.py
MARKER=SMS_DEBT_DEFAULT_ABAN_V1

test -s "$REPO/$TARGET"
test -s "$COMPOSE"
test -s patches/sms_admin.py

if grep -q "$MARKER" "$COMPOSE"; then
    echo "ALREADY INSTALLED: Aban SMS patch exists in compose."
    exit 0
fi

BACKUP="/opt/hesab-backups/sms-aban-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP/patches"
cp -a "$COMPOSE" "$BACKUP/docker-compose.sms.yml"
if test -e "$TARGET"; then
    cp -a "$TARGET" "$BACKUP/$TARGET"
fi
echo "BACKUP=$BACKUP"

rollback(){
    trap - ERR
    echo "ERROR: Restoring SMS app files"
    cp -a "$BACKUP/docker-compose.sms.yml" "$COMPOSE"
    if test -e "$BACKUP/$TARGET"; then
        cp -a "$BACKUP/$TARGET" "$TARGET"
    else
        rm -f "$TARGET"
    fi
    "${C[@]}" up -d --no-deps --no-build --force-recreate app || true
    exit 1
}
trap rollback ERR

python3 - "$REPO" <<'PY'
from pathlib import Path
import sys
repo=Path(sys.argv[1])
target=Path("patches/sms_aban_default.py")
compose=Path("docker-compose.sms.yml")
source=(repo/"patches/sms_aban_default.py").read_text()
compile(source,str(target),"exec")
if "SMS_DEBT_DEFAULT_ABAN_V1" not in source:
    raise SystemExit("Refusing unversioned patch")
cfg=compose.read_text()
mount="      - ./patches/sms_admin.py:/sms-patch/sms_admin.py:ro\n"
runtime="        python -m py_compile /app/app/main.py\n"
assert cfg.count(mount)==1
assert cfg.count(runtime)==1
assert "SMS_DEBT_DEFAULT_ABAN_V1" not in cfg
cfg=cfg.replace(mount,mount+"      - ./patches/sms_aban_default.py:/sms-patch/sms_aban_default.py:ro\n",1)
cfg=cfg.replace(runtime,
    "        if ! grep -q 'SMS_DEBT_DEFAULT_ABAN_V1' /app/app/main.py; then\n"
    "          cat /sms-patch/sms_aban_default.py >> /app/app/main.py\n"
    "        fi\n"+runtime,1)
target.write_text(source)
compose.write_text(cfg)
PY

"${C[@]}" config -q
"${C[@]}" up -d --no-deps --no-build --force-recreate app

ready=0
for _ in $(seq 1 30); do
    if "${C[@]}" exec -T app python -c \
      'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=3).read()' \
      >/dev/null 2>&1; then
       ready=1
       break
    fi
    sleep 2
done
test "$ready" -eq 1
"${C[@]}" exec -T app grep -q "$MARKER" /app/app/main.py
echo "SUCCESS: SMS REMINDER DEFAULT UPDATED"
echo "No messages were sent. Accounts, payments and dates unchanged."
trap - ERR
