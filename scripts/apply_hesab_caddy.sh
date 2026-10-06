#!/usr/bin/env bash
set -euo pipefail

CADDY_CONTAINER="${CADDY_CONTAINER:-darma-general-caddy-1}"
VPN_NETWORK="${VPN_NETWORK:-vpn-control-center_default}"
BASE_CADDY="${BASE_CADDY:-/opt/darma-general/Caddyfile}"
HESAB_CADDY="${HESAB_CADDY:-/opt/vpn-control-center/Caddyfile.hesab}"

for f in "$BASE_CADDY" "$HESAB_CADDY"; do
  test -f "$f" || { echo "Missing: $f" >&2; exit 1; }
done

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
cat "$BASE_CADDY" "$HESAB_CADDY" > "$TMP"

echo "== Validate combined Caddy config =="
docker run --rm   -v "$TMP:/etc/caddy/Caddyfile:ro"   caddy:2-alpine   caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

echo "== Ensure shared Caddy can reach Hesab network =="
if ! docker inspect "$CADDY_CONTAINER"   --format '{{json .NetworkSettings.Networks}}'   | grep -q "\"$VPN_NETWORK\""; then
  docker network connect "$VPN_NETWORK" "$CADDY_CONTAINER"
fi

echo "== Load combined config without editing Darma files =="
docker cp "$TMP" "$CADDY_CONTAINER:/tmp/Caddyfile.with-hesab"
docker exec "$CADDY_CONTAINER"   caddy reload --config /tmp/Caddyfile.with-hesab --adapter caddyfile

echo "SUCCESS: Hesab + SMS Gateway route loaded"
