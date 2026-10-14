#!/usr/bin/env bash
# HESAB_SHORT_DEBT_SMS_TEXT_V1
# Text-only update to the canonical debt reminder. Does not enqueue or resend
# SMS and does not alter debt/followup/payment records or customer portal.
set -Eeuo pipefail
umask 077

[[ "$(id -u)" -eq 0 ]] || { echo "STOP: run as root"; exit 2; }
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd /opt/vpn-control-center
FILE=patches/sms_aban_default.py
SOURCE="$REPO/$FILE"
COMPOSE=docker-compose.sms.yml
C=(docker compose -f docker-compose.yml -f "$COMPOSE")

echo "==== PRECHECK: source, host and Compose ===="
test -s "$SOURCE" && test -s "$FILE" && test -s "$COMPOSE"
grep -Fq 'SMS_DEBT_DEFAULT_ABAN_V1' "$SOURCE"
grep -Fq 'SMS_DEBT_DEFAULT_ABAN_V1' "$FILE"
grep -Fq './patches/sms_aban_default.py:/sms-patch/sms_aban_default.py:ro' "$COMPOSE"
grep -Fq "cat /sms-patch/sms_aban_default.py >> /app/app/main.py" "$COMPOSE"
"${C[@]}" config -q
"${C[@]}" exec -T app python -c 'import urllib.request;urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5).read()'
python3 -m py_compile "$SOURCE" "$FILE"

STAGED="$(mktemp)"
trap 'rm -f "$STAGED"' EXIT
python3 - "$SOURCE" "$FILE" "$STAGED" <<'PY'
import ast
from pathlib import Path
import sys
source=Path(sys.argv[1]).read_text(encoding="utf-8")
live=Path(sys.argv[2]).read_text(encoding="utf-8")
def get(s):
    tree=ast.parse(s)
    matches=[n for n in tree.body if isinstance(n,ast.Assign) and
             len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and
             n.targets[0].id == "_ABAN_SMS_PATTERN"]
    if len(matches)!=1:
        raise SystemExit("STOP: canonical SMS pattern missing/ambiguous")
    assignment=ast.get_source_segment(s,matches[0])
    value=ast.literal_eval(matches[0].value)
    return assignment,value
original,old=get(live)
proposed,new=get(source)
if old.count("{expiry}")!=1 or "usersmanager.ir" not in old:
    raise SystemExit("STOP: unrecognized live template, refusing blind edit")
if new.count("{expiry}")!=1 or not new.endswith("usersmanager.ir"):
    raise SystemExit("STOP: new template failed validity checks")
if "برای تمدید با شماره همراه خودتون" not in new:
    raise SystemExit("STOP: new text isn't the user-requested SMS")
if live.count(original)!=1:
    raise SystemExit("STOP: template replacement not unique")
result=live.replace(original,proposed,1)
compile(result,sys.argv[2],"exec")
Path(sys.argv[3]).write_text(result,encoding="utf-8")
print("Text-only patch: VALID")
print("New length (example ۵ شهریور):",len(new.format(expiry="۵ شهریور")))
PY

mkdir -p /opt/hesab-backups
BACKUP="/opt/hesab-backups/debt-sms-text-$(date +%Y%m%d-%H%M%S)-$$.py"
cp -a "$FILE" "$BACKUP"
test -s "$BACKUP"
echo "BACKUP=$BACKUP"

MODIFIED=0
rollback() {
  trap - ERR
  echo "ERROR: restoring original SMS template"
  cp -a "$BACKUP" "$FILE"
  if [[ "$MODIFIED" -eq 1 ]]; then
    "${C[@]}" up -d --no-deps --no-build --force-recreate app || true
  fi
  echo "ROLLBACK ATTEMPTED; no SMS queued by installer."
  exit 1
}
trap rollback ERR

install -m 0644 "$STAGED" "$FILE"
MODIFIED=1
"${C[@]}" up -d --no-deps --no-build --force-recreate app

ready=0
for i in $(seq 1 35); do
  if "${C[@]}" exec -T app sh -lc \
    'grep -Fq "برای تمدید با شماره همراه خودتون وارد این سایت بشید" /app/app/main.py && curl -fsS http://127.0.0.1:8000/health >/dev/null' \
    >/dev/null 2>&1; then ready=1; break; fi
  sleep 2
done
test "$ready" -eq 1

"${C[@]}" exec -T app python - <<'PY'
from app.main import _ABAN_SMS_PATTERN
assert _ABAN_SMS_PATTERN.count("{expiry}")==1
assert _ABAN_SMS_PATTERN.endswith("usersmanager.ir")
assert "نسبت به پرداخت اقدام فرمایید" in _ABAN_SMS_PATTERN
print("Runtime SMS template confirmed.")
PY

trap - ERR
echo "SUCCESS: SHORT DEBT SMS TEMPLATE ENABLED"
echo "Only new debt SMS requests use the new template; existing queue unchanged."
echo "No messages sent automatically."
echo "BACKUP=$BACKUP"
