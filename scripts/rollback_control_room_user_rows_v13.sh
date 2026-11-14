#!/usr/bin/env bash
# HESAB_CONTROL_ROOM_USER_ROWS_V13_ROLLBACK
# Restore ONLY the admin overlay copied by the V13 installer; abort on
# checksum conflict so later unrelated changes are never overwritten.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == "0" && "$#" == 1 ]] || {
 echo "USAGE: bash $0 /root/hesab-control-room-rows-v13-TIMESTAMP-PID";exit 2;
}
BACKUP="$1"
case "$BACKUP" in /root/hesab-control-room-rows-v13-*) ;; *)
 echo "STOP=INVALID_BACKUP_PATH";exit 3;; esac
[[ -d "$BACKUP" && ! -L "$BACKUP" ]] || {
 echo "STOP=BACKUP_FOLDER_MISSING";exit 3; }
for f in maya1_control.py installed-sha256.txt;do
 [[ -s "$BACKUP/$f" && ! -L "$BACKUP/$f" ]] ||
 { echo "STOP=BACKUP_INCOMPLETE:$f";exit 3; }
done
cd /opt/vpn-control-center
LIVE=patches/maya1_control.py
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
grep -Fq HESAB_CONTROL_ROOM_USER_ROWS_V13 "$LIVE" ||
 { echo "STOP=V13_NOT_PRESENT";exit 3; }
sha256sum -c "$BACKUP/installed-sha256.txt" ||
 { echo "STOP=ADMIN_UI_HAS_SUBSEQUENT_CHANGES";exit 3; }
compose config -q
CURRENT="/root/hesab-rows-v13-before-rollback-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$CURRENT"
cp -a "$LIVE" "$CURRENT/maya1_control.py"
rollback_again(){
 code=$?
 trap - EXIT
 if ((code!=0));then
   cp -a "$CURRENT/maya1_control.py" "$LIVE"
   compose up -d --no-deps --no-build --force-recreate app ||
    echo "WARNING=ADMIN_RESTART_AFTER_FAILED_ROLLBACK"
 fi
 exit "$code"
}
trap rollback_again EXIT
cp -a "$BACKUP/maya1_control.py" "$LIVE"
python3 -m py_compile "$LIVE"
compose up -d --no-deps --no-build --force-recreate app
READY=0
for i in $(seq 1 30);do
 if compose exec -T app python - <<'PY' >/dev/null 2>&1
from app import main as m
from jinja2 import Environment
t=m.TEMPLATES["control_room.html"]
assert "r13-compact-list-style" not in t
assert 'id="c3-mode"' in t
assert 'id="c2-users"' in t
assert any(r.path=="/control-room" for r in m.app.router.routes)
Environment().parse(t)
PY
 then READY=1;break;fi
 sleep 2
done
[[ "$READY" == "1" ]] ||
 { echo "STOP=ROLLBACK_RUNTIME_NOT_CONFIRMED";false; }
trap - EXIT
echo "SUCCESS=CONTROL_ROOM_USER_ROWS_V13_ROLLED_BACK"
echo "RESTORED=$BACKUP"
echo "SAFETY_COPY=$CURRENT"
