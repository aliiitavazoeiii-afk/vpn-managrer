#!/usr/bin/env bash
# HESAB_CUSTOMER_SERVICES_V2: ONLY customer-portal may be rebuilt/recreated.
set -Eeuo pipefail
umask 077
ROOT=/opt/vpn-control-center
cd "$ROOT"
FILES="services_home_v2.py services_ui_v2.html services_ui_v2.css services_ui_v2.js"
compose() { docker compose -f docker-compose.yml -f docker-compose.sms.yml "$@"; }
restore() {
  backup="$1"
  [ -s "$backup/Dockerfile" ] && [ -s "$backup/docker-compose.sms.yml" ] || { echo "Invalid backup"; return 1; }
  cp -a "$backup/Dockerfile" customer_portal/Dockerfile
  cp -a "$backup/docker-compose.sms.yml" docker-compose.sms.yml
  for name in $FILES; do
    if [ -e "$backup/$name" ]; then cp -a "$backup/$name" "customer_portal/$name";
    else rm -f "customer_portal/$name"; fi
  done
  compose config -q
  compose build customer-portal
  compose up -d --no-deps --force-recreate customer-portal
}
[ "$(id -u)" = 0 ] || { echo "STOP: root required"; exit 2; }
if [ "${1:-}" = "--rollback" ]; then restore "${2:?backup path required}";exit;fi
SRC="${1:?pass checked-out source directory}"
for name in $FILES; do [ -s "$SRC/customer_portal/$name" ] || { echo "Missing $name";exit 2; };done
[ -s customer_portal/logo.png ] || { echo "STOP: private logo mount missing";exit 3; }
[ -s customer_portal/Dockerfile ] && [ -s docker-compose.sms.yml ] || exit 3
compose config -q
OLD=$(compose ps -q customer-portal)
[ -n "$OLD" ] && [ "$(docker inspect -f '{{.State.Running}}' "$OLD")" = true ] || {
  echo "STOP: existing customer portal must be running";exit 3;
}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP="/root/hesab-services-v3-backup-$STAMP"
mkdir -p "$BACKUP"
cp -a customer_portal/Dockerfile "$BACKUP/Dockerfile"
cp -a docker-compose.sms.yml "$BACKUP/docker-compose.sms.yml"
for name in $FILES; do
  if [ -e "customer_portal/$name" ]; then cp -a "customer_portal/$name" "$BACKUP/$name";fi
done
docker inspect -f '{{.Image}}' "$OLD" > "$BACKUP/previous-image-id.txt"
echo "BACKUP: $BACKUP"
echo "COMPAT: preserving existing Compose and portal command; no new overlay v1 required"
MODIFIED=0
on_error() {
  result=$?
  trap - ERR
  if [ "$MODIFIED" = 1 ]; then
    echo "FAILED: attempting portal-only rollback"
    restore "$BACKUP" || echo "ROLLBACK ERROR: use recorded backup and inspect container"
  fi
  echo "INSTALL FAILED; backup=$BACKUP";exit "$result"
}
trap on_error ERR
MODIFIED=1
for name in $FILES; do cp -a "$SRC/customer_portal/$name" "customer_portal/$name";done
python3 - <<'PY'
from pathlib import Path
import ast
root=Path("customer_portal")
ast.parse((root/"services_home_v2.py").read_text(encoding="utf-8"))
p=root/"Dockerfile"
s=p.read_text()
if "COPY server.py ." not in s or "CMD " not in s:
    raise RuntimeError("STOP: Unexpected existing portal Dockerfile; refusing edit")
if "HESAB_CUSTOMER_SERVICES_V3" in s:
    raise RuntimeError("STOP: V3 already present; refusing double-install")
# Append an isolated layer after all pre-existing Dockerfile instructions,
# preserving the original command, previous runtime overlays, and file order.
s += """
# HESAB_CUSTOMER_SERVICES_V3
COPY services_home_v2.py services_ui_v2.html services_ui_v2.css services_ui_v2.js /srv/
RUN echo 'exec(compile(open("/srv/services_home_v2.py", "r", encoding="utf-8").read(), "/srv/services_home_v2.py", "exec"))' >> /srv/server.py \\
 && python -m py_compile /srv/server.py /srv/services_home_v2.py
"""
p.write_text(s)
PY
compose config -q
python3 -m py_compile customer_portal/services_home_v2.py
echo "BUILD: customer-portal only"
compose build customer-portal
echo "RECREATE: customer-portal only"
compose up -d --no-deps --force-recreate customer-portal
CID=$(compose ps -q customer-portal)
[ -n "$CID" ] || { echo "STOP: portal container missing";false; }
OK=0
for attempt in $(seq 1 35); do
  health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$CID")
  if [ "$health" = "healthy" ]; then OK=1;break;fi
  sleep 2
done
[ "$OK" = 1 ] || { echo "STOP: portal healthcheck failed";false; }
docker exec "$CID" python -c 'import urllib.request; u="http://127.0.0.1:8091"; assert all(urllib.request.urlopen(u+p,timeout=6).status==200 for p in ("/health","/assets/services-v2.css","/assets/services-v2.js")); print("PORTAL_ASSETS_OK")'
echo "SUCCESS: HESAB CUSTOMER SERVICES V3; backup=$BACKUP"
echo "Important: Verify actual logged-in user, Ayria payment page, history and Cloudflare from mobile."
echo "Optional contacts: HESAB_SUPPORT_WHATSAPP and HESAB_SUPPORT_PHONE in server-only .env."
