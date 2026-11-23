#!/usr/bin/env bash
# Read-only diagnostic of conflicting Maya1 Backhaul2/Mieru warnings.
# Management host only. No remote probes, no SSH, no writes/restarts.
set -Eeuo pipefail
ROOT=/opt/vpn-control-center
[[ -d "$ROOT" && -f "$ROOT/maya_extra_sync/dual_hourly_v1.json" &&
   -f "$ROOT/patches/maya1_control.py" ]] || {
  echo "STOP: run on Hesab Control Room management server";exit 2;
}
echo "=== CURRENT COLLECTOR SNAPSHOT (PUBLIC PATH DATA ONLY) ==="
python3 - "$ROOT" <<'PY'
import json,sys,time
from pathlib import Path
root=Path(sys.argv[1])
p=root/"maya_extra_sync/dual_hourly_v1.json"
d=json.loads(p.read_text(encoding="utf8"))
print("SNAPSHOT_FORMAT=",d.get("format"))
t=d.get("collected_at")
print("SNAPSHOT_AGE_S=",round(time.time()-t) if type(t)==int else "invalid")
for server in ("maya1","maya-s3","maya4"):
    row=d.get("servers",{}).get(server,{})
    print("SERVER",server,"state=",row.get("state"),
          "mode=",row.get("mode"),
          "interval_s=",row.get("health_interval_s"),
          "controller_age_s=",row.get("controller_age_s"))
    if server in ("maya1","maya-s3"):
        for role in ("backhaul","mieru"):
            x=row.get("paths",{}).get(role,{})
            sites=x.get("https_sites")
            print(" PATH",role,"foreign=",x.get("ip"),"routing_health=",x.get("state"),
                  "https=",str(x.get("https_passed"))+"/"+str(x.get("https_total")),
                  "sites=",sites)
src=(root/"patches/maya1_control.py").read_text(encoding="utf8")
for marker in ("HESAB_CONTROL_ROOM_DUAL_HOURLY_SIMPLE_V1",
               "HESAB_MAYA3_DUAL_BACKHAUL_VISUAL_V1",
               "HESAB_CONTROL_ROOM_THREE_SITE_V3",
               "HESAB_DUAL_HOURLY_MANUAL_REFRESH_V2"):
    print("ON_DISK",marker,marker in src)
print("ON_DISK_RENAMES_MIERU=",'item.mode==="dual_backhaul"' in src)
PY
echo "=== MANAGEMENT APP RUNTIME (READ ONLY) ==="
cd "$ROOT"
docker compose -f docker-compose.yml -f docker-compose.sms.yml exec -T app python - <<'PY'
from app import main
routes=[getattr(r,"path","") for r in main.app.routes]
for route in ("/control-room/dual-hourly/status",
              "/control-room/dual-hourly/refresh",
              "/control-room/dual-hourly/refresh-meta"):
    print("APP_ROUTE",route,"count=",routes.count(route))
for name in main.TEMPLATES:
    page=main.TEMPLATES[name]
    found=[k for k in ("Mieru","Backhaul 2","تست مسیر",
                        "Google","Cloudflare","Apple") if k in page]
    if found and ("control" in name.lower() or "dashboard" in name.lower()):
        print("PAGE",name,"labels=",",".join(found),
              "dual_role_aware=",'item.mode==="dual_backhaul"' in page,
              "v3_checks=",'raw.https_sites' in page)
print("CONTROL_ROOM_UI_V3=", "raw.https_sites" in
      main.TEMPLATES.get("control_room.html",""))
PY
echo "=== DASHBOARD PROBE SOURCE CANDIDATES (FILENAMES ONLY) ==="
python3 - "$ROOT" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1])
for folder in ("patches","scripts"):
    matches=[]
    for file in (root/folder).glob("*.py"):
        try:
            text=file.read_text(encoding="utf8")
        except (OSError,UnicodeError):
            continue
        if "تست مسیر" in text or ("mieru" in text.lower() and
              any(x in text.lower() for x in ("probe","health","warning","هشدار"))):
            matches.append(file.name)
    print(folder.upper(),",".join(sorted(matches)) or "none")
PY
echo "READ_ONLY_DIAGNOSTIC_COMPLETE"
