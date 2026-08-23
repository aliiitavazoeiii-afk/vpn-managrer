#!/usr/bin/env bash
set -Eeuo pipefail

RAW="https://raw.githubusercontent.com/aliiitavazoeiii-afk/vpn-managrer/main"
APP_DIR="/opt/vpn-control-center"
BUNDLE_SHA="baed5c357e6f09d3783cc15d15faf8c1a941a3aea0aec1a60c3a981877847ba2"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run with sudo/root." >&2
  exit 1
fi

[[ -r /etc/os-release ]] || { echo "Ubuntu/Debian required" >&2; exit 1; }
. /etc/os-release
case "${ID:-}" in ubuntu|debian) ;; *) [[ " ${ID_LIKE:-} " == *" debian "* ]] || { echo "Ubuntu/Debian required" >&2; exit 1; };; esac
export DEBIAN_FRONTEND=noninteractive

echo "== VPN Control Center installer =="
echo "Management VPS only. Nothing is installed on your VPN/X-UI servers."

apt-get update -y
apt-get install -y ca-certificates curl openssl tar gzip coreutils

if ! command -v docker >/dev/null 2>&1; then
  echo "Installing Docker..."
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  ARCH="$(dpkg --print-architecture)"
  CODENAME="${VERSION_CODENAME:-${UBUNTU_CODENAME:-}}"
  echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${CODENAME} stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

docker compose version >/dev/null

ENV_KEEP=""
if [[ -d "$APP_DIR" ]]; then
  if [[ -f "$APP_DIR/docker-compose.yml" ]]; then
    (cd "$APP_DIR" && docker compose down --remove-orphans) || true
  fi
  if [[ -f "$APP_DIR/.env" ]]; then
    ENV_KEEP="/tmp/vpncc.env.keep.$$"
    cp "$APP_DIR/.env" "$ENV_KEEP"
  fi
  rm -rf "$APP_DIR"
fi

TMP_B64="/tmp/vpncc.bundle.$$.b64"
TMP_TGZ="/tmp/vpncc.bundle.$$.tar.gz"
curl -fL --retry 3 --connect-timeout 15 "$RAW/bundle.b64" -o "$TMP_B64"
base64 -d "$TMP_B64" > "$TMP_TGZ"
rm -f "$TMP_B64"
ACTUAL_SHA="$(sha256sum "$TMP_TGZ" | awk '{print $1}')"
[[ "$ACTUAL_SHA" == "$BUNDLE_SHA" ]] || { echo "Bundle checksum mismatch" >&2; rm -f "$TMP_TGZ"; exit 3; }
tar -xzf "$TMP_TGZ" -C /opt
rm -f "$TMP_TGZ"
cd "$APP_DIR"

NEW_ADMIN="$(openssl rand -hex 12)"
if [[ -n "$ENV_KEEP" && -f "$ENV_KEEP" ]]; then
  mv "$ENV_KEEP" .env
  if grep -q '^ADMIN_PASSWORD=' .env; then
    sed -i "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=$NEW_ADMIN|" .env
  else
    echo "ADMIN_PASSWORD=$NEW_ADMIN" >> .env
  fi
else
  cp .env.example .env
  SECRET="$(openssl rand -hex 32)"
  DBPASS="$(openssl rand -hex 16)"
  sed -i "s|CHANGE_THIS_TO_A_LONG_RANDOM_SECRET|$SECRET|" .env
  sed -i "s|CHANGE_THIS_LONG_PASSWORD|$NEW_ADMIN|" .env
  sed -i "s|CHANGE_THIS_DB_PASSWORD|$DBPASS|" .env
fi
chmod 600 .env

PORT="$(grep '^APP_PORT=' .env | cut -d= -f2- || true)"
PORT="${PORT:-8080}"
if ss -lnt 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:)$PORT$"; then
  for P in $(seq 8080 8099); do
    if ! ss -lnt 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:)$P$"; then PORT="$P"; break; fi
  done
  if grep -q '^APP_PORT=' .env; then sed -i "s/^APP_PORT=.*/APP_PORT=$PORT/" .env; else echo "APP_PORT=$PORT" >> .env; fi
fi

echo "Building containers..."
docker compose build --no-cache app
docker compose up -d

printf 'Waiting for application'
OK=0
for _ in $(seq 1 75); do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1 && curl -fsS "http://127.0.0.1:${PORT}/login" >/dev/null 2>&1; then
    OK=1; break
  fi
  printf '.'; sleep 2
done
echo

if [[ "$OK" != 1 ]]; then
  echo "ERROR: app did not become healthy. App logs:" >&2
  docker compose ps >&2 || true
  docker compose logs --tail=250 app >&2 || true
  exit 2
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"; IP="${IP:-YOUR_SERVER_IP}"
ADMIN_USER="$(grep '^ADMIN_USERNAME=' .env | cut -d= -f2- || true)"; ADMIN_USER="${ADMIN_USER:-admin}"

echo
cat <<OUT
============================================================
VPN Control Center READY
URL:      http://${IP}:${PORT}
Username: ${ADMIN_USER}
Password: ${NEW_ADMIN}
============================================================
1) Login
2) Settings -> upload vpn-sait.xlsx
3) Servers -> add ONE X-UI server first and test Sync
OUT
