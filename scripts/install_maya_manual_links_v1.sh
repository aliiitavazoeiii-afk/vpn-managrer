#!/usr/bin/env bash
# HESAB_MAYA_MANUAL_LINKS_INSTALL_V1. Only the /control-room XUI ID resolver.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == "0" ]] || { echo "STOP: root required";exit 2; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
BASE=/opt/vpn-control-center
cd "$BASE"
c(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
for f in patches/maya1_control.py docker-compose.sms.yml .env; do
 [[ -s "$f" ]] || { echo "STOP: missing $f";exit 2; }
done
for f in "$SRC/patches/maya_manual_links_v1.py" "$SRC/scripts/maya_apply_manual_links_v1.py"; do
 test -s "$f"
 python3 -m py_compile "$f"
done
grep -Fq 'HESAB_MAYA_LIVE_DASHBOARD_V1' patches/maya1_control.py || {
 echo "STOP: live control-room integration not installed";exit 3;
}
grep -Fq '/srv/maya-live:ro' docker-compose.sms.yml || {
 echo "STOP: safe approval file directory not mounted";exit 3;
}
c config -q
existing=0
if grep -Fq '# HESAB_MAYA_MANUAL_LINKS_V1' patches/maya1_control.py; then
 existing=1
 echo "EXISTING: checking live mapping overlay"
fi
mkdir -p /opt/hesab-backups
BACKUP="/opt/hesab-backups/maya-approval-overlay-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$BACKUP"
cp -a patches/maya1_control.py "$BACKUP/maya1_control.py"
changed=0
rollback(){
 trap - ERR
 if [[ "$changed" == "1" ]]; then
  echo "ROLLBACK: restoring previous control room patch (no finance writes)"
  cp -a "$BACKUP/maya1_control.py" patches/maya1_control.py
  c up -d --no-deps --no-build --force-recreate app || true
 fi
 echo "Backup: $BACKUP"
 exit 1
}
trap rollback ERR
cp -a "$SRC/scripts/maya_apply_manual_links_v1.py" scripts/maya_apply_manual_links_v1.py
chmod 700 scripts/maya_apply_manual_links_v1.py
if [[ "$existing" == "0" ]];then
 changed=1
 printf '\n\n' >> patches/maya1_control.py
 cat "$SRC/patches/maya_manual_links_v1.py" >> patches/maya1_control.py
 python3 -m py_compile patches/maya1_control.py
 c up -d --no-deps --no-build --force-recreate app
fi
ok=0
for i in $(seq 1 16);do
 if c exec -T app python - <<'PY' >/dev/null 2>&1
from app.main import app, TEMPLATES, _ma_approved, _ml_resolve
from pathlib import Path
assert "HESAB_MAYA_MANUAL_LINKS_V1" in Path("/app/app/main.py").read_text()
assert callable(_ml_resolve) and _ml_resolve.__code__.co_filename.endswith("/app/app/main.py")
assert isinstance(_ma_approved(),dict)
assert "control_room.html" in TEMPLATES
# Mount/StaticFiles lacks methods: enumerate safely.
assert sum(r.path=="/control-room" and "GET" in (getattr(r,"methods",set()) or set()) for r in app.routes)==1
PY
 then ok=1;break;fi
 sleep 2
done
if [[ "$ok" != "1" ]]; then
 echo "STOP: live manual-link resolver failed to load. No approval file modified."
 false
fi
trap - ERR
echo "SUCCESS: manual-link overlay installed; ready for a protected approval file."
echo "No links created by installer, XUI users unchanged, no timed automation enabled."
echo "Backup: $BACKUP"
