#!/usr/bin/env bash
# HESAB_MAYA_DYNAMIC_LINKS_V1_INSTALL
# Adds manual XUI->Hesab ID approval in /control-room. No clients toggled.
set -Eeuo pipefail
umask 077
[[ $(id -u) == 0 ]] || { echo "STOP: sudo/root required"; exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
BASE=/opt/vpn-control-center
cd "$BASE"
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
test -s patches/maya1_control.py
test -s "$SRC/patches/maya_dynamic_links_v1.py"
python3 -m py_compile "$SRC/patches/maya_dynamic_links_v1.py"
for marker in HESAB_MAYA_MANUAL_LINKS_V1 HESAB_MAYA_CONTROL_ROOM_V2 HESAB_WAITING_VPN_CONTROL_V1; do
  grep -Fq "$marker" patches/maya1_control.py || {
    echo "STOP: required live dashboard patch $marker not installed"; exit 3;
  }
done
grep -Fq "/srv/maya-live:ro" docker-compose.sms.yml || {
 echo "STOP: existing approved mappings/sampler not mounted";exit 3;
}
c config -q
# DRY RUN in an isolated Python process of the EXISTING, RUNNING app.
# This compiles/loads the candidate overlay into an in-memory module only:
# no HTTP, SSH, XUI request, DB write, service reload or scheduled job.
if ! grep -Fq '# HESAB_MAYA_DYNAMIC_LINKS_V1' patches/maya1_control.py; then
  echo "=== PREFLIGHT: ISOLATED REAL-APP LOAD (NO CHANGES) ==="
  if ! cat "$SRC/patches/maya_dynamic_links_v1.py" | c exec -T app python -c '
import importlib,sys,traceback
try:
  m=importlib.import_module("app.main")
  source=sys.stdin.read()
  assert "# HESAB_MAYA_DYNAMIC_LINKS_V1" in source,"Patch source missing"
  exec(compile(source,"<maya_new_links_candidate>","exec"),vars(m))
  from jinja2 import Environment
  page=m.TEMPLATES["control_room.html"]
  Environment().parse(page)
  assert page.count("b.onclick=()=>window.hesabLinkMaya(server,item)")==1,"Matching action not unique"
  assert "window.hesabLinkMaya=(server,item)=>" in page,"Matching dialog missing"
  assert len([r for r in m.app.routes if getattr(r,"path",None)=="/control-room/maya-link/approve"])==1,"Approval route duplicate"
  assert len([r for r in m.app.routes if getattr(r,"path",None)=="/control-room/maya-link/account"])==1,"Lookup route duplicate"
  print("PREFLIGHT_SUCCESS: candidate imports and Jinja renders against current app")
except Exception:
  print("PREFLIGHT_FAILED: no application files or services changed")
  traceback.print_exc(limit=8)
  sys.exit(1)
';then
    echo "STOP: candidate failed before app restart; see PREFLIGHT_FAILED traceback."
    exit 4
  fi
fi
backup="/opt/hesab-backups/maya-new-links-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$backup"
cp -a patches/maya1_control.py "$backup/maya1_control.py"
changed=0
rollback(){
  trap - ERR
  if [[ "$changed" == 1 ]]; then
    cp -a "$backup/maya1_control.py" patches/maya1_control.py
    c up -d --no-deps --no-build --force-recreate app || true
  fi
  echo "Backup: $backup"
  echo "Existing accounts, approvals, XUI states and financial records unchanged."
  exit 1
}
trap rollback ERR
echo "=== CREATE A SEPARATE MANUAL LINK TABLE, NO BILLING UPDATE ==="
c exec -T db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
BEGIN;
CREATE TABLE IF NOT EXISTS maya_new_approved_links (
  server TEXT NOT NULL CHECK (server IN ('maya1','maya-s3','maya4')),
  email VARCHAR(160) NOT NULL,
  subscription_id BIGINT NOT NULL CHECK(subscription_id>0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY(server,email),
  UNIQUE(server,subscription_id)
);
COMMIT;
SQL
if ! grep -Fq '# HESAB_MAYA_DYNAMIC_LINKS_V1' patches/maya1_control.py;then
  changed=1
  printf '\n\n' >>patches/maya1_control.py
  cat "$SRC/patches/maya_dynamic_links_v1.py" >>patches/maya1_control.py
  python3 -m py_compile patches/maya1_control.py
  c up -d --no-deps --no-build --force-recreate app
else
  echo "Existing patch found; verification only."
fi
ready=0
for i in $(seq 1 20);do
 if c exec -T app python - <<'PY' >/dev/null 2>&1
from app.main import app,TEMPLATES,_ml_resolve,_mdl_get_account,_mdl_post_link
from jinja2 import Environment
from pathlib import Path
from sqlalchemy import text
from app.main import get_db
tpl=TEMPLATES["control_room.html"]
assert "# HESAB_MAYA_DYNAMIC_LINKS_V1" in Path("/app/app/main.py").read_text()
assert tpl.count('b.onclick=()=>window.hesabLinkMaya(server,item)')==1
assert "window.hesabLinkMaya=(server,item)=>" in tpl
assert 'class="c2-card"' in tpl or 'c2-card' in tpl
assert 'data-waiting' not in tpl
Environment().parse(tpl)
for path,method in (
 ("/control-room/maya-link/approve","POST"),
 ("/control-room/maya-link/account","GET"),
 ("/control-room","GET"),
 ("/followups","GET"),
):
 assert sum(getattr(r,"path",None)==path and method in (getattr(r,"methods",set()) or set()) for r in app.routes)==1,path
gen=get_db();db=next(gen)
try:
 assert db.execute(text("SELECT COUNT(*) FROM maya_new_approved_links")).scalar() >= 0
finally:
 gen.close()
PY
 then ready=1;break;fi
 sleep 2
done
if [[ "$ready" != 1 ]];then
  echo "STOP: runtime validation failed; checking the reason BEFORE rollback"
  if c exec -T app python - <<'PY'
import importlib,traceback,sys
try:
  m=importlib.import_module("app.main")
  from pathlib import Path
  from jinja2 import Environment
  from sqlalchemy import text
  s=Path("/app/app/main.py").read_text()
  print("PATCH_IN_RUNNING_MODULE:",hasattr(m,"_mdl_post_link"))
  print("SOURCE_MARKER:", "# HESAB_MAYA_DYNAMIC_LINKS_V1" in s)
  print("APP_ROUTE_APPROVE:",sum(getattr(r,"path",None)=="/control-room/maya-link/approve" for r in m.app.routes))
  print("APP_ROUTE_ACCOUNT:",sum(getattr(r,"path",None)=="/control-room/maya-link/account" for r in m.app.routes))
  tpl=m.TEMPLATES.get("control_room.html","")
  print("ACTION_BUTTON:",tpl.count("b.onclick=()=>window.hesabLinkMaya(server,item)"))
  print("DIALOG_PRESENT:","window.hesabLinkMaya=(server,item)=>" in tpl)
  print("UNEXPECTED_WAITING_ANCHOR:","data-waiting" in tpl)
  Environment().parse(tpl)
  gen=m.get_db()
  db=next(gen)
  try:print("LINK_TABLE_COUNT:",db.execute(text("SELECT COUNT(*) FROM maya_new_approved_links")).scalar())
  finally:gen.close()
except Exception:
  traceback.print_exc(limit=7)
  sys.exit(1)
PY
  then :; else
    echo "DIAGNOSTIC: import or template check failed; restoring backup."
  fi
  false
fi
trap - ERR
echo "SUCCESS: control-room manual matching for new Maya clients installed."
echo "No XUI changes, no payment changes, no new background jobs."
echo "Existing 5-minute sampler remains authoritative for waiting-status data."
echo "Backup: $backup"
