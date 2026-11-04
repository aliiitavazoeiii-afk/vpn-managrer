#!/usr/bin/env bash
# HESAB_V11_ROUTING_AND_DRIFT_AUDIT_V1 — strictly read-only.
# Reports network exposure, proxy candidates and source fingerprints only.
# No configs printed, no passwords, no environment variables, no service changes.
set -Eeuo pipefail
umask 077
cd /opt/vpn-control-center
echo "=== HESAB V11 HOST HTTPS / RUNTIME AUDIT (READ ONLY) ==="
printf 'UTC=';date -u '+%Y-%m-%dT%H:%M:%SZ'
echo "FRONT_PROXY_SERVICE_CANDIDATES"
for s in caddy nginx apache2 httpd traefik cloudflared haproxy docker; do
 status="$(systemctl is-active "$s" 2>/dev/null || true)"
 printf '%s=%s\n' "$s" "$status"
done
echo "LISTENING_PORTS_RELEVANT"
python3 - <<'PY'
import subprocess
try:
 r=subprocess.run(["ss","-H","-lntp"],capture_output=True,text=True,timeout=8)
 if r.returncode:
  print("LISTENERS_UNAVAILABLE")
 else:
  for line in r.stdout.splitlines():
   vals=line.split()
   if len(vals) < 5:continue
   port=vals[3].rsplit(":",1)[-1]
   if port in {"80","443","8000","8080","8081","8090","8091","8199","8443","9000"}:
    print("PORT", port, "LISTENING",
          "scope="+("loopback" if vals[3].startswith("127.") or vals[3].startswith("[::1]")
                   else "wildcard" if vals[3].startswith("0.0.0.0") or vals[3].startswith("[::]")
                   else "specific_bind"))
except (OSError,subprocess.TimeoutExpired):
 print("LISTENERS_UNAVAILABLE")
PY
echo "PUBLIC_HTTPS_ROUTE=NOT_TESTED (no DNS lookup or outbound HTTPS probe)"
echo "DOCKER_RUNTIME_APP_IDENTITY"
python3 - <<'PY'
import json,subprocess
name="vpn-control-center-app-1"
try:
 r=subprocess.run(["docker","inspect",name],capture_output=True,text=True,timeout=9)
 if r.returncode:
  print("DOCKER_APP_INSPECT=UNAVAILABLE")
 else:
  obj=json.loads(r.stdout)[0]
  print("IMAGE_SHA",str(obj.get("Image",""))[:72])
  print("CONTAINER_CREATED",str(obj.get("Created",""))[:32])
  for mount in obj.get("Mounts",[]):
   dst=str(mount.get("Destination",""))
   if dst.startswith("/srv/maya-live") or dst.startswith("/sms-patch") or dst=="/app/app/main.py":
    print("MOUNT",dst,"rw="+str(mount.get("RW",False)),"source=REDACTED")
except (OSError,ValueError,IndexError,subprocess.TimeoutExpired):
 print("DOCKER_APP_INSPECT=UNAVAILABLE")
PY
echo "SOURCE_FILE_FINGERPRINTS"
python3 - <<'PY'
from pathlib import Path
from datetime import datetime,timezone
import hashlib
base=Path("/opt/vpn-control-center")
files=("patches/maya1_control.py","docker-compose.yml","docker-compose.sms.yml",
       "scripts/maya_multi_panel_sync.py","scripts/maya_live_bridge.py")
for filename in files:
 p=base/filename
 if p.is_file():
  digest=hashlib.sha256(p.read_bytes()).hexdigest()
  print(filename,"bytes="+str(p.stat().st_size),"sha256="+digest,
        "mtime="+datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat())
 else:
  print(filename,"NOT_PRESENT")
PY
echo "ACTIVE_PYTHON_MAIN_FINGERPRINT"
docker compose -f docker-compose.yml -f docker-compose.sms.yml exec -T app python - <<'PY'
import hashlib
from pathlib import Path
p=Path("/app/app/main.py")
if p.is_file():
 print("RUNNING_APP_MAIN_SHA256",hashlib.sha256(p.read_bytes()).hexdigest())
 print("RUNNING_APP_MAIN_BYTES",p.stat().st_size)
else:
 print("RUNNING_APP_MAIN_NOT_FOUND")
PY
echo "FRONT_PROXY_CONTAINERS (NAMES ONLY)"
docker ps --format '{{.Names}}' | grep -Ei 'caddy|nginx|traefik|haproxy|cloudflared|proxy|apache' || true
echo "=== END. NO PRODUCTION CHANGES ==="
