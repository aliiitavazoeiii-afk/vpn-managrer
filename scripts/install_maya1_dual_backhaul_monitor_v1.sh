#!/usr/bin/env bash
# Maya1 newly migrated Backhaul1+Backhaul2 -> existing Hesab Control Room.
# Management VPS only. Collector file and cached JSON refreshed; NO app restart,
# tunnel/remote changes, Caddy, Xray, HAProxy, Docker containers or DB writes.
set -Eeuo pipefail
umask 077
[[ "$EUID" == 0 && $# == 1 && "$1" =~ ^[a-f0-9]{40}$ ]] || {
  echo "Usage: sudo bash install_maya1_dual_backhaul_monitor_v1.sh PINNED_COMMIT";exit 2;
}
REF="$1"
ROOT=/opt/vpn-control-center
COLLECTOR="$ROOT/scripts/maya_dual_hourly_collect_v1.py"
UI="$ROOT/patches/maya1_control.py"
SNAP="$ROOT/maya_extra_sync/dual_hourly_v1.json"
CFG=/root/.config/hesab-dual-hourly-v1.json
TMP=""
BACKUP=""
CHANGED=0

[[ -d "$ROOT" && -f "$COLLECTOR" && -f "$UI" &&
   -f "$CFG" && -f "$ROOT/docker-compose.yml" &&
   -f "$ROOT/docker-compose.sms.yml" ]] || {
  echo "STOP: not the already-deployed Hesab management host";exit 3;
}
[[ ! -L "$COLLECTOR" && ! -L "$UI" && ! -L "$CFG" ]] || {
  echo "STOP: protected monitoring files may not be symlinks";exit 3;
}
[[ -e "$SNAP" && ! -L "$SNAP" ]] || {
  echo "STOP: cached dual status missing, refusing unverified deployment";exit 3;
}
# Live admin overlay has already been upgraded for Maya3 dual-Backhaul.
# That same mode-aware UI can show Maya1 without any app restart.
grep -Fq 'HESAB_MAYA3_DUAL_BACKHAUL_VISUAL_V1' "$UI" &&
grep -Fq 'item.mode==="dual_backhaul"' "$UI" &&
grep -Fq 'Backhaul 2' "$UI" &&
grep -Fq 'HESAB_CONTROL_ROOM_DUAL_HOURLY_SIMPLE_V1' "$UI" || {
  echo "STOP: live Control Room does not support mode=dual_backhaul; no changes";exit 3;
}
command -v docker >/dev/null || { echo "STOP: Docker unavailable";exit 3; }
cd "$ROOT"
compose(){ docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
compose config -q
CID="$(compose ps -q app)"
[[ -n "$CID" && "$(docker inspect -f '{{.State.Running}}' "$CID")" == true ]] || {
  echo "STOP: management admin app is not running";exit 3;
}
# Restrict access to this installer in case two attempts run concurrently.
exec 9>/run/hesab-maya1-dual-monitor.lock
flock -n 9 || { echo "STOP: another sync installer running";exit 3; }
TMP="$(mktemp -d /root/.maya1-dual-monitor.XXXXXXXX)"
cleanup(){ [[ -z "$TMP" ]] || rm -rf "$TMP"; }
rollback(){
  local code=$?
  trap - EXIT
  if (( code != 0 && CHANGED == 1 ));then
    echo "SYNC_FAILED: restoring previous local collector and cached JSON"
    local rtemp
    rtemp="$(mktemp "$ROOT/scripts/.dual-restore.XXXXXXXX")"
    cp -a "$BACKUP/maya_dual_hourly_collect_v1.py" "$rtemp"
    mv -Tf "$rtemp" "$COLLECTOR"
    cp -a "$BACKUP/dual_hourly_v1.json" "$SNAP"
    echo "MONITOR_ROLLBACK_COMPLETE"
    echo "BACKUP=$BACKUP"
  fi
  cleanup
  exit "$code"
}
trap rollback EXIT

RAW="https://raw.githubusercontent.com/aliiitavazoeiii-afk/vpn-managrer/$REF/scripts/maya_dual_hourly_collect_v1.py"
curl -fsSL --proto '=https' --tlsv1.2 --connect-timeout 10 --max-time 50 \
  "$RAW" -o "$TMP/collector.py"
python3 -m py_compile "$TMP/collector.py"
# Verify source functionality and exact real remote new-helper output BEFORE any changes.
python3 - "$TMP/collector.py" <<'PY'
import importlib.util,sys
spec=importlib.util.spec_from_file_location("maya1_monitor_canary",sys.argv[1])
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
cfg=m.validate_config()
item=cfg.get("maya1")
assert item and item.get("enabled") is not False,"Maya1 not configured"
assert item["host"]=="94.184.4.38","Maya1 SSH host mismatch"
row=m.fetch("maya1",item)
assert row["state"]=="ok" and row["mode"]=="dual_backhaul",(
    "Maya1 restricted SSH still uses OLD sudo dual helper, "
    "or new helper is unavailable")
assert row["paths"]["backhaul"]["ip"]=="82.152.132.159","Maya1 BH1 IP mismatch"
assert row["paths"]["mieru"]["ip"]=="152.237.230.77","Maya1 BH2 IP mismatch"
for role in ("backhaul","mieru"):
    p=row["paths"][role]
    assert p["state"]=="healthy" and p["https_passed"]>=2,(
        "Maya1 "+role+" is not verified healthy")
print("MAYA1_NEW_DUAL_SSH_PREFLIGHT=PASS")
print("BACKHAUL1=82.152.132.159/21101")
print("BACKHAUL2=152.237.230.77/21102")
print("MAYA3_AND_MAYA4_SCHEMA_COMPATIBILITY=PRESERVED")
PY

BACKUP="/root/hesab-maya1-dual-monitor-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p -m 0700 "$BACKUP"
cp -a "$COLLECTOR" "$BACKUP/maya_dual_hourly_collect_v1.py"
cp -a "$SNAP" "$BACKUP/dual_hourly_v1.json"
echo "BACKUP=$BACKUP"

# Atomic local-only collector replacement. Existing hourly and manual-refresh
# services execute exactly this on-disk path each time; no daemon restart.
NEWFILE="$(mktemp "$ROOT/scripts/.dual-hourly.XXXXXXXX")"
install -o root -g root -m 0700 "$TMP/collector.py" "$NEWFILE"
CHANGED=1
mv -Tf "$NEWFILE" "$COLLECTOR"
python3 -m py_compile "$COLLECTOR"
python3 "$COLLECTOR"

python3 - "$SNAP" <<'PY'
import json,sys,time
doc=json.load(open(sys.argv[1],encoding="utf-8"))
assert doc.get("format")=="HESAB_DUAL_HOURLY_V1"
assert 0 <= time.time()-doc["collected_at"] <= 120
item=doc["servers"]["maya1"]
assert item["state"]=="ok" and item["mode"]=="dual_backhaul"
assert item["paths"]["backhaul"]["state"]=="healthy"
assert item["paths"]["mieru"]["state"]=="healthy"
assert item["paths"]["backhaul"]["ip"]=="82.152.132.159"
assert item["paths"]["mieru"]["ip"]=="152.237.230.77"
print("MAYA1_CACHED_DUAL_BACKHAUL_SNAPSHOT=VERIFIED")
for sid in ("maya-s3","maya4"):
    row=doc["servers"].get(sid,{})
    print("UNCHANGED_REMOTE_ROLE_SCHEMA",sid,"mode="+str(row.get("mode")),
          "state="+str(row.get("state")))
PY

# App already exposes read-only cached snapshot via its shared mount.
compose exec -T app python - <<'PY'
import json
from pathlib import Path
p=Path("/srv/maya-live/dual_hourly_v1.json")
doc=json.loads(p.read_text())
assert doc["format"]=="HESAB_DUAL_HOURLY_V1"
r=doc["servers"]["maya1"]
assert r["mode"]=="dual_backhaul" and r["state"]=="ok"
assert r["paths"]["backhaul"]["ip"]=="82.152.132.159"
assert r["paths"]["mieru"]["ip"]=="152.237.230.77"
from app import main as m
assert [x.path for x in m.app.routes].count("/control-room/dual-hourly/status")==1
assert 'item.mode==="dual_backhaul"' in m.TEMPLATES["control_room.html"]
assert "Backhaul 2" in m.TEMPLATES["control_room.html"]
print("CONTROL_ROOM_MAYA1_TWO_BACKHAUL_VIEW=READY")
PY
trap - EXIT
cleanup
echo "SUCCESS=MAYA1_DUAL_BACKHAUL_CONTROL_ROOM_SYNCED"
echo "HOURLY_TIMER_AND_MANUAL_REFRESH=UNCHANGED"
echo "NO_APP_RESTART_NO_VPN_CHANGES=TRUE"
echo "BACKUP=$BACKUP"
echo "ACTION: use the existing Control Room manual refresh button when needed"
