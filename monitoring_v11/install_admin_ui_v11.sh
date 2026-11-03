#!/bin/bash
# HESAB_TELEMETRY_V11_SAFE_UI_INSTALL
# Explicit approval only. Does not touch finance, XUI, tunnel, or SMS.
set -Eeuo pipefail
umask 077
[[ $(id -u) -eq 0 && $# -eq 2 && "$2" == "--apply" ]] || {
 echo "Usage as root: bash $0 /separate/feature/checkout --apply";exit 2;
}
SRC=$(realpath "$1")
ROOT=/opt/vpn-control-center
[[ "$SRC" != "$ROOT" ]] || { echo "STOP: source must be separate checkout";exit 2; }
PATCH=$SRC/monitoring_v11/control_room_overlay.py
cd "$ROOT"
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
TARGET=patches/maya1_control.py
for p in "$PATCH" "$TARGET" .env docker-compose.yml docker-compose.sms.yml;do
 test -s "$p" || { echo "STOP: missing $p";exit 3; }
done
grep -Fq HESAB_CONTROL_ROOM_COMPACT_V10 "$TARGET" || {
 echo "STOP: V10 unavailable";exit 3;
}
if grep -Fq HESAB_CONTROL_ROOM_TUNNEL_TELEMETRY_V11 "$TARGET";then
 echo "ALREADY_INSTALLED";exit 0;
fi
compose config -q
python3 -m py_compile "$PATCH" "$TARGET"
cat "$PATCH" | compose exec -T app python -c '
import sys
from app import main as m
from jinja2 import Environment
before=[r.path for r in m.app.router.routes]
for p in ("/control-room/v10/daily","/control-room/v9/topup",
          "/control-room/maya-live/toggle"):
 assert before.count(p)==1,p
assert "t10-head-tools" in m.TEMPLATES["control_room.html"]
exec(compile(sys.stdin.read(),"<v11-preflight>","exec"),vars(m))
after=[r.path for r in m.app.router.routes]
assert len(after)==len(before)+3
for p in ("/control-room/v11/status","/control-room/v11/events",
          "/control-room/v11/samples"):
 assert after.count(p)==1,p
Environment().parse(m.TEMPLATES["control_room.html"])
print("PREFLIGHT_PASS")
'
BACK="/opt/hesab-backups/control-room-v11-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$BACK"
chmod 700 "$BACK"
cp -a "$TARGET" "$BACK/maya1_control.py"
cp -a docker-compose.yml docker-compose.sms.yml "$BACK/"
compose exec -T db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$BACK/postgres-before-v11.dump"
test "$(stat -c %s "$BACK/postgres-before-v11.dump")" -gt 1024
compose exec -T db pg_restore -l < "$BACK/postgres-before-v11.dump" > /dev/null
echo "BACKUP_CREATED=$BACK; verify restore separately before authorizing real rollout."
changed=0
rollback(){
 status=$?
 trap - ERR EXIT
 if (( status != 0 && changed == 1 ));then
   echo "ROLLBACK: restore prior admin overlay"
   cp -a "$BACK/maya1_control.py" "$TARGET"
   compose up -d --no-deps --no-build --force-recreate app || true
 fi
 exit "$status"
}
trap rollback ERR EXIT
changed=1
printf '\n\n' >> "$TARGET"
cat "$PATCH" >> "$TARGET"
python3 -m py_compile "$TARGET"
compose up -d --no-deps --no-build --force-recreate app
ready=0
for i in $(seq 1 30);do
 if compose exec -T app python - <<'PY' > /dev/null 2>&1
from app import main as m
from jinja2 import Environment
names=[r.path for r in m.app.router.routes]
for p in ("/control-room/v10/daily","/control-room/v9/topup",
          "/control-room/maya-live/toggle","/control-room/v11/status",
          "/control-room/v11/events","/control-room/v11/samples"):
 assert names.count(p)==1,p
assert "tv11-overview" in m.TEMPLATES["control_room.html"]
Environment().parse(m.TEMPLATES["control_room.html"])
PY
 then ready=1;break;fi
 sleep 2
done
(( ready == 1 ))
code=$(curl -sS --max-time 9 -o /dev/null -w '%{http_code}' https://hesab.filmjadiid.ir/control-room/v11/status || true)
[[ "$code" != 200 ]] || { echo "STOP: signed-out telemetry unexpectedly public";false; }
trap - ERR EXIT
echo "SUCCESS: V11 UI DEPLOYED; BACKUP=$BACK; SIGNED_OUT_HTTP=$code"
echo "NO XUI/FINANCE/AGENT/RECEIVER OR SMS CHANGES"
