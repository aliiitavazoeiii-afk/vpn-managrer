#!/usr/bin/env bash
# V11: disposable real-HTTPS Caddy -> HMAC receiver integration.
# Runs ONLY on a fresh --internal Docker network, with no host ports,
# no live Caddyfile mount, no finance DB, no Maya/VPN calls.
set -Eeuo pipefail
umask 077

ROOT="$(cd "$(dirname "$0")" && pwd)"
test -s "$ROOT/receiver.py" || { echo "BLOCKED=RECEIVER_SOURCE_MISSING"; exit 2; }
command -v docker >/dev/null
CADDY_IMAGE="$(docker inspect -f '{{.Image}}' darma-general-caddy-1)"
docker image inspect "$CADDY_IMAGE" >/dev/null
docker image inspect python:3.12-slim >/dev/null || { echo "BLOCKED=PYTHON_IMAGE_NOT_CACHED"; exit 2; }

TMP="$(mktemp -d /root/hesab-v11-caddy-stage-XXXXXXXX)"
NET="hesab-v11-https-stage-$RANDOM-$$"
RECEIVER="hesab-v11-https-receiver-$RANDOM-$$"
CADDY="hesab-v11-https-caddy-$RANDOM-$$"
cleanup() {
  docker rm -f "$CADDY" "$RECEIVER" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  rm -rf -- "$TMP"
}
trap cleanup EXIT
mkdir -m 700 "$TMP/db"

python3 - "$TMP/receiver.json" <<'PY'
import json, os, secrets, sys
cfg = {
    "database_path": "/opt/vpn-control-center/maya_extra_sync/telemetry_v11/https-stage.sqlite3",
    "servers": {"maya4": {"enabled": True, "key_hex": secrets.token_hex(32)}},
}
with open(sys.argv[1], "x") as stream:
    json.dump(cfg, stream)
os.chmod(sys.argv[1], 0o600)
print("TEST_HMAC=EPHEMERAL")
PY

cat > "$TMP/Caddyfile" <<'CADDYFILE'
{
    admin off
    auto_https disable_redirects
}
https://staging-v11.invalid:8443 {
    tls internal
    @tv11SignedHeartbeat {
        path /api/control-room/v11/heartbeat
        method POST
    }
    handle @tv11SignedHeartbeat {
        reverse_proxy telemetry-v11:8199
    }
    handle {
        respond "staging-only-not-found" 404
    }
}
CADDYFILE
chmod 600 "$TMP/Caddyfile"
echo "=== V11 ISOLATED CADDY HTTPS TEST ==="
docker network create --internal "$NET" >/dev/null

docker run -d --name "$RECEIVER" \
  --network "$NET" --network-alias telemetry-v11 \
  --read-only --user 0:0 --cap-drop ALL \
  --security-opt no-new-privileges --memory 128m --cpus 0.20 --pids-limit 48 \
  --tmpfs /tmp:rw,noexec,nosuid,size=8m \
  --mount "type=bind,src=$ROOT/receiver.py,dst=/opt/hesab-v11/receiver.py,readonly" \
  --mount "type=bind,src=$TMP/receiver.json,dst=/etc/hesab-telemetry-v11/receiver.json,readonly" \
  --mount "type=bind,src=$TMP/db,dst=/opt/vpn-control-center/maya_extra_sync/telemetry_v11" \
  -e HESAB_RECEIVER_DEPLOYMENT=docker-internal \
  python:3.12-slim python3 -B /opt/hesab-v11/receiver.py >/dev/null

docker run -d --name "$CADDY" \
  --network "$NET" --network-alias staging-v11.invalid \
  --read-only --user 0:0 --cap-drop ALL \
  --security-opt no-new-privileges --memory 256m --cpus 0.30 --pids-limit 64 \
  --tmpfs /tmp:rw,nosuid,size=8m \
  --tmpfs /data:rw,nosuid,size=32m \
  --tmpfs /config:rw,nosuid,size=8m \
  -e XDG_DATA_HOME=/data -e XDG_CONFIG_HOME=/config \
  --mount "type=bind,src=$TMP/Caddyfile,dst=/etc/caddy/Caddyfile,readonly" \
  --entrypoint caddy "$CADDY_IMAGE" \
  run --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null

for id in "$RECEIVER" "$CADDY"; do
  ports="$(docker inspect -f '{{json .HostConfig.PortBindings}}' "$id")"
  if [[ "$ports" != "null" && "$ports" != "{}" ]]; then
    echo "FAIL=HOST_PORT_WAS_PUBLISHED"
    exit 1
  fi
done
echo "TEST_NETWORK=DISPOSABLE_INTERNAL_ONLY"
echo "HOST_PORT_PUBLICATION=NONE"
echo "CADDY_IMAGE=EXISTING_LOCAL_IMAGE"

docker run --rm -i --network "$NET" --read-only \
  --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,src=$TMP/receiver.json,dst=/config.json,readonly" \
  python:3.12-slim python3 - <<'PY'
import hashlib, hmac, json, secrets, ssl, time
import urllib.error, urllib.request

with open("/config.json") as f:
    cfg = json.load(f)
key = bytes.fromhex(cfg["servers"]["maya4"]["key_hex"])
# Synthetic self-signed Caddy CA: certificate verification is intentionally
# bypassed ONLY for this isolated .invalid test site, NEVER for production.
context = ssl._create_unverified_context()
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=context),
)
base = "https://staging-v11.invalid:8443"
endpoint = base + "/api/control-room/v11/heartbeat"

def call(url, body=None, headers=None):
    request = urllib.request.Request(
        url, data=body, headers=headers or {},
        method="POST" if body is not None else "GET",
    )
    try:
        with opener.open(request, timeout=3) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code

for trial in range(30):
    try:
        ready = call(base + "/healthz")
        if ready == 404:
            break
    except (OSError, ValueError):
        pass
    time.sleep(0.5)
else:
    raise RuntimeError("ISOLATED_CADDY_TLS_NOT_READY")

timestamp = int(time.time())
nonce = secrets.token_hex(16)
payload = {
    "schema": "hesab-tunnel-v11", "server_id": "maya4",
    "sent_at": timestamp, "nonce": nonce, "tunnel_type": "unidentified",
    "system": {
        "cpu_pct": None, "ram_pct": None, "disk_pct": None,
        "uptime_s": None, "interface": "synthetic",
        "rx_bytes": None, "tx_bytes": None, "tcp443_listen": "unknown",
    },
    "services": {},
    "controller": {"state": "unavailable", "age_s": None, "paths": {}},
    "haproxy": {}, "foreign_ips": {},
    "quota": {"state": "unknown", "remaining_gb": None},
    "xui_online": None, "vpn_end_to_end": "not_tested",
}
body = json.dumps(payload, separators=(",", ":")).encode()
signature = hmac.new(key, str(timestamp).encode() + b"." + body, hashlib.sha256).hexdigest()
headers = {
    "Content-Type": "application/json",
    "X-Hesab-Server": "maya4",
    "X-Hesab-Time": str(timestamp),
    "X-Hesab-Nonce": nonce,
    "X-Hesab-Signature": "sha256=" + signature,
}
valid = call(endpoint, body, headers)
replay = call(endpoint, body, headers)
bad = dict(headers)
bad["X-Hesab-Signature"] = "sha256=" + "0" * 64
invalid = call(endpoint, body, bad)
unmatched = call(endpoint)
not_health = call(base + "/healthz")
assert valid == 202, ("valid", valid)
assert replay in (409, 429), ("replay", replay)
assert invalid == 401, ("invalid", invalid)
assert unmatched == 404, ("non_post", unmatched)
assert not_health == 404, ("health_proxy_exposed", not_health)
print("SYNTHETIC_TLS_PROXY=PASS")
print("POST_ONLY_HEARTBEAT=202")
print("REPLAY=REJECTED")
print("INVALID_HMAC=401")
print("NON_POST_ROUTE=404")
print("RECEIVER_HEALTH_NOT_PROXY_EXPOSED=YES")
print("PRODUCTION_CERTIFICATE_TRUST=NOT_TESTED")
print("MAYA_VPN_HEALTH=NOT_TESTED")
PY

python3 - "$TMP/db/https-stage.sqlite3" <<'PY'
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as db:
    s=db.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    n=db.execute("SELECT COUNT(*) FROM replays").fetchone()[0]
assert (s,n)==(1,1),(s,n)
print("STAGING_SAMPLES=1")
print("STAGING_REPLAYS=1")
print("ISOLATED_CADDY_HTTPS_TEST=PASS")
PY
echo "LIVE_CADDYFILE_CHANGED=NO"
echo "LIVE_CONTAINERS_TOUCHED=NO"
echo "TEMPORARY_RESOURCES_CLEANUP=ON_EXIT"
