#!/usr/bin/env bash
# HESAB_MAYA_EXCLUSION_COUNTS_INSTALL_V1: only /control-room labels and server summary.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == "0" ]] || { echo "STOP: need sudo/root";exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
BASE=/opt/vpn-control-center
cd "$BASE"
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
test -s "$SRC/patches/maya_live_exclusion_counts_v1.py" || {
 echo "STOP: missing exclusion patch";exit 2;
}
for marker in HESAB_MAYA_LIVE_DASHBOARD_V1 HESAB_MAYA_CONTROL_ROOM_V2 HESAB_MAYA_MANUAL_LINKS_V1; do
 grep -Fq "$marker" patches/maya1_control.py || {
 echo "STOP: $marker is not installed";exit 3;
 }
done
python3 -m py_compile "$SRC/patches/maya_live_exclusion_counts_v1.py"
c config -q
BACKUP="/opt/hesab-backups/maya-exclusion-counts-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACKUP"
cp -a patches/maya1_control.py "$BACKUP/maya1_control.py"
CHANGED=0
rollback(){
 trap - ERR
 if [[ "$CHANGED" == 1 ]]; then
  cp -a "$BACKUP/maya1_control.py" patches/maya1_control.py
  c up -d --no-deps --no-build --force-recreate app || true
 fi
 echo "STOP: exclusion label patch failed; restored old app if changed."
 echo "Backup: $BACKUP"
 exit 1
}
trap rollback ERR
if ! grep -Fq '# HESAB_MAYA_EXCLUSION_COUNTS_V1' patches/maya1_control.py; then
 CHANGED=1
 printf '\n\n' >> patches/maya1_control.py
 cat "$SRC/patches/maya_live_exclusion_counts_v1.py" >> patches/maya1_control.py
 python3 -m py_compile patches/maya1_control.py
 c up -d --no-deps --no-build --force-recreate app
else
 echo "RESUME: count patch already installed; verifying current web app."
fi
OK=0
for n in $(seq 1 14);do
 if c exec -T app python - <<'PY' >/dev/null 2>&1
from app.main import app,TEMPLATES,_ml_one
from pathlib import Path
assert "HESAB_MAYA_EXCLUSION_COUNTS_V1" in Path("/app/app/main.py").read_text()
tpl=TEMPLATES["control_room.html"]
assert 'count(data.excluded||0)+" مستثنا' in tpl
assert '"بدون نیاز"' in tpl
assert 'app' and callable(_ml_one)
assert sum(getattr(r,"path",None)=="/control-room" and
           "GET" in (getattr(r,"methods",set()) or set())
           for r in app.routes)==1
PY
 then OK=1; break; fi
 sleep 2
done
[[ "$OK" == 1 ]] || { echo "STOP: runtime check failed";false; }
trap - ERR
echo "SUCCESS: site now separates excluded Maya users from truly unresolved clients."
echo "Only the control-room page changed; no XUI or finance actions."
echo "Backup: $BACKUP"
