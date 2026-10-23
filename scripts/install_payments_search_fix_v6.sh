#!/usr/bin/env bash
# HESAB_PAYMENTS_SEARCH_FIX_V6_INSTALL
# Changes only HTML/JavaScript template of /payments. No DB, undo route, SMS,
# subscriptions or XUI edits. Preflight the actual installed template first.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == "0" ]] || { echo "STOP: sudo/root required";exit 2; }
REPO="$(cd "$(dirname "$0")/.." && pwd)"
BASE=/opt/vpn-control-center
cd "$BASE"
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for file in .env docker-compose.yml docker-compose.sms.yml patches/sms_native_v2.py "$REPO/patches/payments_search_fix_v6.py";do
  test -s "$file" || { echo "STOP: missing $file";exit 3; }
done
grep -Fq '/sms-patch/sms_native_v2.py' docker-compose.sms.yml || {
 echo "STOP: native template patch not mounted";exit 3;
}
compose config -q
python3 -m py_compile "$REPO/patches/payments_search_fix_v6.py" patches/sms_native_v2.py

# Determine which V5 payments template is installed, then execute the exact
# overlay against its static template without restarting production.
python3 - "$REPO" <<'PY'
import ast,sys
from pathlib import Path
repo=Path(sys.argv[1])
production=Path("patches/sms_native_v2.py").read_text(encoding="utf8")
overlay=(repo/"patches/payments_search_fix_v6.py").read_text(encoding="utf8")
candidates=[]
for node in ast.parse(production).body:
    if not isinstance(node,ast.Assign) or len(node.targets)!=1:continue
    target=node.targets[0]
    if not isinstance(target,ast.Name):continue
    if target.id not in ("_PF_TEMPLATE","_OP_PAYMENTS_TEMPLATE"):continue
    value=ast.literal_eval(node.value)
    candidates.append((node.lineno,target.id,value))
if not candidates:raise RuntimeError("Cannot identify current payments V5 template in production file")
line,name,template=max(candidates,key=lambda v:v[0])
assert (('id="pf-search"' in template) if name=="_PF_TEMPLATE"
        else ('id="op-pay-query"' in template)), "Unexpected payments V5 source"
scope={
  "TEMPLATES":{"payments.html":template},
  "env":type("E",(),{"loader":type("L",(),{"mapping":{}})()})()
}
exec(compile(overlay,"payments_search_fix_v6.py","exec"),scope)
patched=scope["TEMPLATES"]["payments.html"]
assert patched!=template
if name=="_PF_TEMPLATE":
    assert '#pf-days .pf-row[hidden]' in patched
    assert "terms.every(word=>haystack.includes(word))" in patched
else:
    assert '#op-pay-groups .op-pay-entry[hidden]' in patched
    assert "terms.every(w=>text.includes(w))" in patched
assert 'action="/payments/{{' in patched and '/undo"' in patched
print("PREFLIGHT SUCCESS: installed template",name,"line",line)
print("PREFLIGHT SUCCESS: payment search filters and original undo action preserved")
PY

BACK="/opt/hesab-backups/payments-search-v6-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACK"
cp -a patches/sms_native_v2.py "$BACK/sms_native_v2.py"
changed=0
rollback(){
  trap - ERR
  if [[ "$changed" == "1" ]];then
    echo "ROLLBACK: restoring prior payments template patch"
    cp -a "$BACK/sms_native_v2.py" patches/sms_native_v2.py
    compose up -d --no-deps --no-build --force-recreate app || true
  fi
  echo "BACKUP=$BACK"
  exit 1
}
trap rollback ERR
if ! grep -Fq '# HESAB_PAYMENTS_SEARCH_FIX_V6' patches/sms_native_v2.py;then
  changed=1
  printf '\n\n' >> patches/sms_native_v2.py
  cat "$REPO/patches/payments_search_fix_v6.py" >> patches/sms_native_v2.py
  python3 -m py_compile patches/sms_native_v2.py
  compose up -d --no-deps --no-build --force-recreate app
else
  echo "ALREADY INSTALLED: checking running app."
fi

ready=0
for i in $(seq 1 25);do
 if compose exec -T app python -c "from app.main import TEMPLATES, app" >/dev/null 2>&1;then
   ready=1;break
 fi
 sleep 2
done
[[ "$ready" == 1 ]] || {
  echo "STOP: app import/boot failed"
  compose logs --tail 50 app | sed -E 's/(PASSWORD|TOKEN|KEY)=[^ ]+/\1=[REDACTED]/g' || true
  false
}
compose exec -T app python - <<'PY'
from app.main import app,TEMPLATES
from jinja2 import Environment
import urllib.request
tpl=TEMPLATES["payments.html"]
safe='id="pf-search"' in tpl
operator='id="op-pay-query"' in tpl
print("Loaded payments template:", "safe-v5" if safe else "operator-v5" if operator else "unknown")
assert safe!=operator, "Unrecognized payment search page"
if safe:
    assert "#pf-days .pf-row[hidden]" in tpl
    assert "terms.every(word=>haystack.includes(word))" in tpl
    assert 'data-pf-id="{{ p.id }}"' in tpl
else:
    assert "#op-pay-groups .op-pay-entry[hidden]" in tpl
    assert "terms.every(w=>text.includes(w))" in tpl
assert "addEventListener(\"search\",apply)" in tpl
assert 'action="/payments/{{' in tpl and '/undo"' in tpl
Environment().parse(tpl)
routes=[r for r in app.routes if getattr(r,"path",None)=="/payments"
        and "GET" in (getattr(r,"methods",set()) or set())]
assert len(routes)==1,"Payments GET handler replaced or duplicated"
undo=[r for r in app.routes if getattr(r,"path",None)=="/payments/{pid}/undo"
      and "POST" in (getattr(r,"methods",set()) or set())]
assert len(undo)>=1,"Payment undo handler missing"
with urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=6) as resp:
    assert resp.status==200
print("VERIFIED: active payments search hidden rows, normalized text and undo intact")
PY
trap - ERR
echo "SUCCESS: PAYMENTS SEARCH FIXED AND VERIFIED"
echo "Only payments search UI changed. No financial records, undo operations or SMS touched."
echo "BACKUP=$BACK"
