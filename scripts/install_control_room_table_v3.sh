#!/usr/bin/env bash
# HESAB_CONTROL_ROOM_TABLE_V3_INSTALL
# Scoped admin UI/read-only usage data; no XUI toggle, finance or extra services.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo 'STOP: root required';exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
ROOT=/opt/vpn-control-center
PATCH="$SRC/patches/control_room_table_v3.py"
LIVE=patches/maya1_control.py
cd "$ROOT"
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for f in .env docker-compose.yml docker-compose.sms.yml "$LIVE" "$PATCH";do
  [[ -s "$f" ]] || { echo "STOP: missing file $f";exit 3; }
done
c config -q
grep -Fq 'maya1_control.py' docker-compose.sms.yml || {
  echo "STOP: no mounted Maya overlay";exit 3;
}
grep -Fq '# HESAB_CONTROL_ROOM_PHASE1_V1' "$LIVE" || {
  echo "STOP: Phase1 UI not installed";exit 3;
}
if grep -Fq '# HESAB_CONTROL_ROOM_TABLE_V3' "$LIVE";then
  echo "ALREADY_INSTALLED: version V3 marker present; do not append twice";exit 0
fi
python3 -m py_compile "$PATCH"
old="$(c ps -q app)"
[[ -n "$old" ]] && [[ "$(docker inspect -f '{{.State.Running}}' "$old")" == true ]] || {
  echo "STOP: main admin app not running";exit 3;
}
echo "=== PREFLIGHT IN ISOLATED PROCESS (NO PRODUCTION CHANGES) ==="
cat "$PATCH" | c exec -T app python -c '
import sys
from app import main as m
from jinja2 import Environment
assert "p1-monitor" in m.TEMPLATES["control_room.html"]
assert "c3-table-controls" not in m.TEMPLATES["control_room.html"]
source=sys.stdin.read()
assert source.startswith("# HESAB_CONTROL_ROOM_TABLE_V3")
old=m._cr2_one
before=[(r.path,sorted(r.methods)) for r in m.app.routes if getattr(r,"path","").startswith("/control-room")]
exec(compile(source,"<control_room_v3_preflight>","exec"),vars(m))
after=[(r.path,sorted(r.methods)) for r in m.app.routes if getattr(r,"path","").startswith("/control-room")]
assert before==after,"Control room routes were unexpectedly changed"
assert m._C3_ORIGINAL_ONE is old
html=m.TEMPLATES["control_room.html"]
for x in ("id=\"c3-table-controls\"","id=\"c3-mode\"","c3VisibleRows",
          "c3Details","c3-detail-button","mdl2-toolbar",
          "id=\"c2-users\"","id=\"p1-monitor\""):
 assert x in html,x
assert html.count("id=\"c2-search\"")==1
assert html.count("c3Details(server,item)")==1
Environment().parse(html)
print("CONTROL_ROOM_V3_JINJA_AND_ROUTES_PASS")
'
BACKUP="/root/hesab-control-room-table-v3-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$BACKUP"
cp -a "$LIVE" "$BACKUP/maya1_control.py"
docker inspect -f '{{.Image}}' "$old" > "$BACKUP/app-image-before.txt"
echo "BACKUP=$BACKUP"
CHANGED=0
rollback() {
  local result=$?
  trap - EXIT
  if (( result != 0 )) && (( CHANGED ));then
    echo "ROLLBACK: restoring previous UI overlay"
    cp -a "$BACKUP/maya1_control.py" "$LIVE"
    c up -d --no-deps --no-build --force-recreate app || \
      echo "ROLLBACK RECREATE FAILED; inspect $BACKUP"
  fi
  exit "$result"
}
trap rollback EXIT
CHANGED=1
printf '\n\n' >> "$LIVE"
cat "$PATCH" >> "$LIVE"
python3 -m py_compile "$LIVE"
echo "RECREATING ONLY ADMIN APP — no XUI/user/payment writes"
c up -d --no-deps --no-build --force-recreate app
ready=0
for attempt in $(seq 1 35);do
  if c exec -T app python - <<'PY' >/dev/null 2>&1
from app import main as m
from jinja2 import Environment
assert m._C3_ORIGINAL_ONE is not m._cr2_one
assert m.TEMPLATES["control_room.html"].count('id="c3-table-controls"')==1
assert m.TEMPLATES["control_room.html"].count('id="c2-search"')==1
assert 'c3Details(server,item)' in m.TEMPLATES["control_room.html"]
assert 'mdl2-toolbar' in m.TEMPLATES["control_room.html"]
assert 'id="p1-monitor"' in m.TEMPLATES["control_room.html"]
Environment().parse(m.TEMPLATES["control_room.html"])
paths=[r.path for r in m.app.routes]
assert paths.count("/control-room")==1
assert paths.count("/control-room/v2/data")==1
assert paths.count("/control-room/maya-live/toggle")==1
assert paths.count("/control-room/phase1/status")==1
PY
  then ready=1;break;fi
  sleep 2
done
[[ "$ready" == 1 ]] || { echo "STOP: runtime V3 checks failed";false; }
trap - EXIT
echo "SUCCESS: CONTROL ROOM TABLE V3 INSTALLED"
echo "BACKUP=$BACKUP"
echo "Financial records, user states and existing Maya toggles untouched."
