#!/usr/bin/env bash
# HESAB_MAYA_DYNAMIC_LINKS_V2_INSTALL: prominent always-visible picker in control room
# UI and approved-link policy only. Does not toggle XUI, change billing or poll remote servers.
set -Eeuo pipefail
umask 077
[[ $(id -u) == 0 ]] || { echo "STOP: root required";exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
BASE=/opt/vpn-control-center
cd "$BASE"
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
test -s patches/maya1_control.py
test -s "$SRC/patches/maya_dynamic_links_v2.py"
python3 -m py_compile "$SRC/patches/maya_dynamic_links_v2.py"
for marker in HESAB_MAYA_DYNAMIC_LINKS_V1 HESAB_MAYA_CONTROL_ROOM_V2 HESAB_WAITING_VPN_CONTROL_V1;do
 grep -Fq "$marker" patches/maya1_control.py || {
  echo "STOP: missing prerequisite $marker; no changes";exit 3;
 }
done
c config -q

echo "=== PREFLIGHT: CURRENT-APP UI AND ROUTE COMPATIBILITY ==="
if ! grep -Fq '# HESAB_MAYA_DYNAMIC_LINKS_V2' patches/maya1_control.py;then
  if ! cat "$SRC/patches/maya_dynamic_links_v2.py" | c exec -T app python -c '
import importlib,sys,traceback
try:
 m=importlib.import_module("app.main")
 candidate=sys.stdin.read()
 exec(compile(candidate,"<maya_dynamic_links_v2_candidate>","exec"),vars(m))
 from jinja2 import Environment
 tpl=m.TEMPLATES["control_room.html"]
 Environment().parse(tpl)
 assert tpl.count("id=\"mdl2-open\"")==1
 assert tpl.count("window.__hesabMayaPickerV2=true")==1
 assert len([r for r in m.app.routes if getattr(r,"path",None)=="/control-room/maya-link/approve"])==1
 print("PREFLIGHT_SUCCESS: prominent picker compatible with live control room")
except Exception:
 print("PREFLIGHT_FAILED: app unchanged")
 traceback.print_exc(limit=8)
 sys.exit(1)
';then
   echo "STOP: preflight failed without modifying running files"
   exit 4
  fi
fi
backup="/opt/hesab-backups/maya-new-links-v2-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$backup"
cp -a patches/maya1_control.py "$backup/maya1_control.py"
changed=0
rollback(){
 trap - ERR
 if [[ "$changed" == 1 ]];then
  echo "RESTORE: prior app patch from $backup"
  cp -a "$backup/maya1_control.py" patches/maya1_control.py
  c up -d --no-deps --no-build --force-recreate app || true
 fi
 echo "Backup: $backup"
 exit 1
}
trap rollback ERR
if ! grep -Fq '# HESAB_MAYA_DYNAMIC_LINKS_V2' patches/maya1_control.py;then
 changed=1
 printf '\n\n' >>patches/maya1_control.py
 cat "$SRC/patches/maya_dynamic_links_v2.py" >>patches/maya1_control.py
 python3 -m py_compile patches/maya1_control.py
 c up -d --no-deps --no-build --force-recreate app
else
 echo "ALREADY_INSTALLED: verify running app only"
fi
echo "=== VERIFY LIVE APP ==="
if ! c exec -T app python - <<'PY'
from app.main import app,TEMPLATES,_MDL_APPROVED_REASONS
from pathlib import Path
from jinja2 import Environment
from sqlalchemy import text
from app.main import get_db
assert "HESAB_MAYA_DYNAMIC_LINKS_V2" in Path("/app/app/main.py").read_text()
tpl=TEMPLATES["control_room.html"]
assert tpl.count('id="mdl2-open"')==1
assert tpl.count("window.__hesabMayaPickerV2=true")==1
assert tpl.count("id=\"c2-cards\"")==1
assert "exact_name_conflict" in _MDL_APPROVED_REASONS
assert 'data-waiting' not in tpl
assert 'approved_archived_read_only' in tpl
Environment().parse(tpl)
for path,method in [
 ("/control-room","GET"),
 ("/control-room/v2/data","GET"),
 ("/control-room/maya-link/approve","POST"),
 ("/control-room/maya-link/account","GET"),
 ("/followups/vpn/disable","POST"),
]:
 assert sum(getattr(r,"path",None)==path and
            method in (getattr(r,"methods",set()) or set())
            for r in app.routes)==1,path
generator=get_db();db=next(generator)
try:db.execute(text("SELECT 1 FROM maya_new_approved_links LIMIT 1")).all()
finally:generator.close()
print("RUNTIME_SUCCESS: picker and approved link policy loaded")
PY
then
 echo "STOP: runtime validation failed; reverting UI"
 false
fi
trap - ERR
echo "SUCCESS: prominent Maya matching picker installed on /control-room."
echo "No XUI client toggled, no payments changed; only live approved matches can be saved by operator."
echo "Backup: $backup"
