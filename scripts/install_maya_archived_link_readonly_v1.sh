#!/usr/bin/env bash
# Install archived-identity display-only compatibility in Maya control room.
set -Eeuo pipefail
umask 077
[[ $(id -u) == 0 ]] || { echo 'STOP: sudo/root needed';exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
cd /opt/vpn-control-center
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
f=patches/maya1_control.py
test -s "$f"
for marker in HESAB_MAYA_MANUAL_LINKS_V1 HESAB_MAYA_EXCLUSION_COUNTS_V1 HESAB_MAYA_CONTROL_ROOM_V2;do
 grep -Fq "$marker" "$f" || { echo "STOP: missing $marker";exit 3; }
done
python3 -m py_compile "$SRC/patches/maya_archived_link_readonly_v1.py" "$SRC/scripts/fix_maya_davari_afrogh_v1.py"
c config -q
BACK="/opt/hesab-backups/maya-archived-display-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACK"
cp -a "$f" "$BACK/maya1_control.py"
modified=0
rollback(){
 trap - ERR
 if [[ "$modified" == 1 ]]; then
   echo "ROLLBACK: restore previous admin-only patch"
   cp -a "$BACK/maya1_control.py" "$f"
   c up -d --no-deps --no-build --force-recreate app || true
 fi
 echo "Backup: $BACK"
 exit 1
}
trap rollback ERR
cp -a "$SRC/scripts/fix_maya_davari_afrogh_v1.py" scripts/fix_maya_davari_afrogh_v1.py
chmod 700 scripts/fix_maya_davari_afrogh_v1.py
if ! grep -Fq '# HESAB_MAYA_ARCHIVED_LINK_READONLY_V1' "$f"; then
 modified=1
 printf '\n\n' >>"$f"
 cat "$SRC/patches/maya_archived_link_readonly_v1.py" >>"$f"
 python3 -m py_compile "$f"
 c up -d --no-deps --no-build --force-recreate app
fi
ready=0
for i in $(seq 1 15);do
 if c exec -T app python - <<'PY' >/dev/null 2>&1
from pathlib import Path
from app.main import app,TEMPLATES,_ml_resolve,_ma_approved
assert "HESAB_MAYA_ARCHIVED_LINK_READONLY_V1" in Path("/app/app/main.py").read_text()
assert "آرشیوشده · فقط نمایش" in TEMPLATES["control_room.html"]
assert callable(_ml_resolve) and isinstance(_ma_approved(),dict)
assert sum(getattr(r,"path",None)=="/control-room" and
           "GET" in (getattr(r,"methods",set()) or set())
           for r in app.routes)==1
PY
 then ready=1;break;fi
 sleep 2
done
[[ "$ready" == 1 ]] || { echo "STOP: runtime smoke test failed";false; }
trap - ERR
echo 'SUCCESS: archived Maya #24 display-only guard loaded.'
echo 'No XUI changes or financial writes.'
echo "Backup: $BACK"
