#!/usr/bin/env bash
# HESAB_MESSAGES_WEB_INSTALL_V1: app-only, no Caddy/finance/SMS job changes.
set -Eeuo pipefail
umask 077
[[ $(id -u) -eq 0 ]] || { echo "STOP: root required"; exit 2; }
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd /opt/vpn-control-center
C=(docker compose -f docker-compose.yml -f docker-compose.sms.yml)
PATCH=patches/hesab_messages_web.py
CONF=docker-compose.sms.yml

echo "===== PREFLIGHT ====="
test -s "$CONF" && test -s "$REPO/$PATCH" && test -s patches/sms_admin.py
if grep -q HESAB_MESSAGES_HOSTED_WEB_V1 "$CONF"; then
  echo "ALREADY INSTALLED: Hosted Messages web UI"; exit 0
fi
"${C[@]}" config -q
"${C[@]}" exec -T app python -c 'import urllib.request;urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=5).read()'
"${C[@]}" exec -T customer-portal python -c 'import urllib.request;urllib.request.urlopen("http://127.0.0.1:8091/health",timeout=5).read()'
python3 -m py_compile "$REPO/$PATCH"
"${C[@]}" exec -T app python -c '
import ast,sys
from jinja2 import Environment
src=sys.stdin.read()
nodes=ast.parse(src).body
html=[n.value.value for n in nodes if isinstance(n,ast.Assign) and
 any(isinstance(t,ast.Name) and t.id=="_HM_HTML" for t in n.targets)
 and isinstance(n.value,ast.Constant)]
assert len(html)==1
Environment(autoescape=True).parse(html[0])
print("Hosted Python/Jinja validation: PASS")
' < "$REPO/$PATCH"

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
python3 - "$CONF" "$TMP" <<'PY'
from pathlib import Path
import sys
source=Path(sys.argv[1]).read_text(encoding="utf-8")
mount="      - ./patches/sms_admin.py:/sms-patch/sms_admin.py:ro\n"
compile_anchor="        python -m py_compile /app/app/main.py\n"
assert source.count(mount)==1, "Missing unique sms_admin volume"
assert source.count(compile_anchor)==1, "Missing unique startup compilation anchor"
assert "hesab_messages_web.py" not in source, "Already installed"
changed=source.replace(mount,mount+
    "      - ./patches/hesab_messages_web.py:/sms-patch/hesab_messages_web.py:ro\n",1)
changed=changed.replace(compile_anchor,
    "        if ! grep -q 'HESAB_MESSAGES_HOSTED_WEB_V1' /app/app/main.py; then\n"
    "          cat /sms-patch/hesab_messages_web.py >> /app/app/main.py\n"
    "        fi\n"+compile_anchor,1)
Path(sys.argv[2]).write_text(changed,encoding="utf-8")
print("Compose patch prepared")
PY

BACKUP="/opt/hesab-backups/hesab-messages-web-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP/patches"
cp -a "$CONF" "$BACKUP/docker-compose.sms.yml"
if [[ -f "$PATCH" ]]; then cp -a "$PATCH" "$BACKUP/patches/hesab_messages_web.py"; fi
test -s "$BACKUP/docker-compose.sms.yml"
echo "BACKUP=$BACKUP"
MODIFIED=0
rollback(){
  trap - ERR
  echo "ERROR: restoring previous admin files and Compose..."
  cp -a "$BACKUP/docker-compose.sms.yml" "$CONF"
  if [[ -f "$BACKUP/patches/hesab_messages_web.py" ]]; then
    cp -a "$BACKUP/patches/hesab_messages_web.py" "$PATCH"
  else
    rm -f "$PATCH"
  fi
  if [[ "$MODIFIED" == 1 ]];then
    "${C[@]}" up -d --no-deps --no-build --force-recreate app || true
  fi
  echo "Rollback attempted; SMS queue/financial data not modified."
  exit 1
}
trap rollback ERR
install -m 0644 "$REPO/$PATCH" "$PATCH"
cp "$TMP" "$CONF"
MODIFIED=1
"${C[@]}" config -q
echo "===== RECREATE ADMIN APP ONLY ====="
"${C[@]}" up -d --no-deps --no-build --force-recreate app
OK=0
for i in $(seq 1 40); do
  if "${C[@]}" exec -T app sh -lc \
    'grep -q HESAB_MESSAGES_HOSTED_WEB_V1 /app/app/main.py && curl -fsS http://127.0.0.1:8000/health >/dev/null' >/dev/null 2>&1; then OK=1;break;fi
  sleep 2
done
test "$OK" = 1
"${C[@]}" exec -T app python - <<'PY'
import http.client
def req(method,path,payload=None):
    c=http.client.HTTPConnection("127.0.0.1",8000,timeout=8)
    headers={"Content-Type":"application/x-www-form-urlencoded"} if payload else {}
    c.request(method,path,body=payload,headers=headers)
    response=c.getresponse()
    result=(response.status,response.read())
    c.close()
    return result
code,body=req("GET","/messages/")
assert not(code==200 and b"HESAB MESSAGES" in body), "SECURITY: anonymous message data exposed"
print("Anonymous hosted UI protected:",code)
code,body=req("POST","/messages/send",b"phone=09120000000&message=DO_NOT_SEND&csrf=invalid")
assert code in (301,302,303,307,308,401,403),"SECURITY: anonymous POST not rejected"
print("Anonymous invalid-CSRF POST rejected:",code)
PY
"${C[@]}" exec -T customer-portal python -c 'import urllib.request;urllib.request.urlopen("http://127.0.0.1:8091/health",timeout=5).read()'
trap - ERR
echo "SUCCESS: HESAB MESSAGES HOSTED UI ACTIVE"
echo "URL: https://hesab.filmjadiid.ir/messages/"
echo "BACKUP=$BACKUP"
echo "No SMS sent, no billing/finance/users changed."
