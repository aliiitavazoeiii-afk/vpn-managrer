#!/usr/bin/env bash
# HESAB_MAYA_LOW_TRAFFIC_ALERT_V12_INSTALL
# Management host only. Appends a read-only owner-token endpoint to the
# existing SMS gateway (WhatsApp draft queue unchanged), mounts ONLY Maya
# phase1 telemetry read-only. Never runs root install.sh, app/db recreate,
# VPN/XUI/finance mutations, Caddy changes, or SMS replays.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "STOP=ROOT_REQUIRED"; exit 2; }
SOURCE="$(cd "$(dirname "$0")/.." && pwd)"
ROOT=/opt/vpn-control-center
cd "$ROOT"
PATCH="$SOURCE/patches/sms_maya_low_traffic_v12.py"
LIVE=sms_gateway/server.py
COMPOSE=docker-compose.sms.yml
STAMP='HESAB_MAYA_LOW_TRAFFIC_ALERT_V12'
MOUNT='      - ./maya_extra_sync/phase1:/srv/maya-live/phase1:ro'
for p in "$PATCH" "$LIVE" "$COMPOSE" docker-compose.yml sms_gateway/Dockerfile \
         maya_extra_sync/phase1/status.json \
         maya_extra_sync/phase1/provisional_meter_baseline_v7.json;do
  [[ -s "$p" ]] || { echo "STOP=MISSING_REQUIRED_FILE $p";exit 3; }
done
python3 -m py_compile "$PATCH" "$LIVE"
grep -Fq '@app.get("/v4/drafts/pending")' "$LIVE" || {
  echo "STOP=WRONG_SMS_GATEWAY_SOURCE";exit 3;
}
grep -Fq 'def require_token(' "$LIVE" || {
  echo "STOP=GATEWAY_TOKEN_AUTH_MISSING";exit 3;
}
grep -Fq 'sms-gateway:' "$COMPOSE" || {
  echo "STOP=SMS_GATEWAY_COMPOSE_SERVICE_MISSING";exit 3;
}
if grep -Fq "$STAMP" "$LIVE";then
  echo "ALREADY_INSTALLED=YES"
  docker compose -f docker-compose.yml -f "$COMPOSE" ps sms-gateway
  exit 0
fi
[[ ! -e /root/.hesab-maya-alert-v12-lock ]] || {
 echo "STOP=OTHER_INSTALL_LOCK_PRESENT";exit 3;
}
compose(){ docker compose -f docker-compose.yml -f "$COMPOSE" "$@"; }
compose config -q
BEFORE="$(compose ps -q sms-gateway)"
[[ -n "$BEFORE" && "$(docker inspect -f '{{.State.Running}}' "$BEFORE")" == true ]] || {
  echo "STOP=SMS_GATEWAY_NOT_RUNNING";exit 3;
}
# Validate against LIVE server without writing or recreating anything.
python3 - "$LIVE" "$PATCH" <<'PY'
import sys,ast
from pathlib import Path
before=Path(sys.argv[1]).read_text(encoding="utf8")
patch=Path(sys.argv[2]).read_text(encoding="utf8")
ast.parse(before+"\n\n"+patch)
for mark in ('/v5/maya/low-traffic','_ma12_calculate','require_token'):
    assert mark in patch,mark
assert before.count('@app.get("/v4/drafts/pending")')==1
print("PYTHON_APPEND_PREFLIGHT=PASS")
PY
python3 - "$COMPOSE" "$MOUNT" <<'PY'
from pathlib import Path
import sys
doc=Path(sys.argv[1]).read_text()
mount=sys.argv[2]
anchor="  sms-gateway:\n    build:"
if mount not in doc and doc.count(anchor)!=1:
    raise SystemExit("STOP=SMS_GATEWAY_COMPOSE_LAYOUT_CHANGED")
print("READ_ONLY_MOUNT_PREFLIGHT=PASS")
PY

BACKUP="/root/hesab-maya-alert-v12-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BACKUP"
cp -a "$LIVE" "$BACKUP/server.py"
cp -a "$COMPOSE" "$BACKUP/docker-compose.sms.yml"
docker inspect -f '{{.Image}}' "$BEFORE" > "$BACKUP/old-gateway-image-id"
echo "BACKUP=$BACKUP"
CHANGED=0
rollback(){
  result=$?
  trap - EXIT
  if ((result!=0&&CHANGED));then
    echo "ROLLBACK=RESTORING_EXISTING_SMS_GATEWAY"
    cp -a "$BACKUP/server.py" "$LIVE"
    cp -a "$BACKUP/docker-compose.sms.yml" "$COMPOSE"
    compose config -q || true
    compose build sms-gateway || true
    compose up -d --no-deps --force-recreate sms-gateway ||
      echo "WARNING=CHECK_GATEWAY_RUNTIME_AFTER_ROLLBACK"
  fi
  exit "$result"
}
trap rollback EXIT
CHANGED=1
printf '\n\n' >> "$LIVE"
cat "$PATCH" >> "$LIVE"
python3 -m py_compile "$LIVE"
python3 - "$COMPOSE" "$MOUNT" <<'PY'
import sys
from pathlib import Path
p=Path(sys.argv[1]); content=p.read_text()
mount=sys.argv[2]
if mount not in content:
    anchor="  sms-gateway:\n    build:"
    if content.count(anchor)!=1:
        raise SystemExit("STOP=UNEXPECTED_COMPOSE_FORMAT")
    content=content.replace(anchor,"  sms-gateway:\n    volumes:\n"+mount+"\n    build:",1)
    p.write_text(content)
PY
compose config -q
echo "REBUILD_ONLY_SMS_GATEWAY=YES"
compose build sms-gateway
compose up -d --no-deps --force-recreate sms-gateway
READY=0
for i in $(seq 1 24);do
  if compose exec -T sms-gateway python3 - <<'PY' >/dev/null 2>&1
from server import app
import os,json,urllib.request
assert len([r for r in app.routes if r.path=="/v5/maya/low-traffic"])==1
req=urllib.request.Request("http://127.0.0.1:8090/v5/maya/low-traffic",
    headers={"X-SMS-Gateway-Token":os.environ["SMS_GATEWAY_TOKEN"]})
with urllib.request.urlopen(req,timeout=5) as response:
    payload=json.loads(response.read())
assert payload["ok"] is True and payload["estimate_only"] is True
assert set(payload["servers"])=={"maya1","maya-s3","maya4"}
assert all(item["state"]=="provisional" for item in payload["servers"].values())
PY
  then READY=1;break;fi
  sleep 2
done
[[ "$READY" == 1 ]] || {
 echo "STOP=OWNER_ALERT_ENDPOINT_READBACK_FAILED"; false;
}
trap - EXIT
echo "SUCCESS=HESAB_MAYA_LOW_TRAFFIC_ALERT_V12_BACKEND_INSTALLED"
echo "APP_DB_CADDY_XUI_TUNNELS_MODIFIED=NO"
echo "TOKEN_PROTECTED_READONLY_ENDPOINT=YES"
echo "BACKUP=$BACKUP"
