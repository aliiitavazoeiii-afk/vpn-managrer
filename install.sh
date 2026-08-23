#!/usr/bin/env bash
set -Eeuo pipefail

REPO="aliiitavazoeiii-afk/vpn-managrer"
BRANCH="main"
APP_DIR="/opt/vpn-control-center"
TMP_DIR="/tmp/vpncc-install.$$"
ARCHIVE="$TMP_DIR/repo.tar.gz"

cleanup(){ rm -rf "$TMP_DIR" 2>/dev/null || true; }
trap cleanup EXIT

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "ERROR: run this installer with sudo/root." >&2
  exit 1
fi

if [[ ! -r /etc/os-release ]]; then
  echo "ERROR: Ubuntu/Debian is required." >&2
  exit 1
fi
. /etc/os-release
case "${ID:-}" in
  ubuntu|debian) ;;
  *) [[ " ${ID_LIKE:-} " == *" debian "* ]] || { echo "ERROR: Ubuntu/Debian is required." >&2; exit 1; } ;;
esac

export DEBIAN_FRONTEND=noninteractive
mkdir -p "$TMP_DIR"

echo "============================================================"
echo " VPN Control Center - GitHub installer"
echo " Management VPS only; nothing is installed on VPN servers."
echo "============================================================"

apt-get update -y
apt-get install -y ca-certificates curl openssl tar gzip coreutils iproute2

if ! command -v docker >/dev/null 2>&1; then
  echo "[1/6] Installing Docker..."
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  ARCH="$(dpkg --print-architecture)"
  CODENAME="${VERSION_CODENAME:-${UBUNTU_CODENAME:-}}"
  echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${CODENAME} stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
else
  echo "[1/6] Docker already installed."
fi

docker compose version >/dev/null

ENV_KEEP=""
if [[ -d "$APP_DIR" ]]; then
  echo "[2/6] Stopping previous installation..."
  if [[ -f "$APP_DIR/docker-compose.yml" ]]; then
    (cd "$APP_DIR" && docker compose down --remove-orphans) || true
  fi
  if [[ -f "$APP_DIR/.env" ]]; then
    ENV_KEEP="$TMP_DIR/.env.keep"
    cp "$APP_DIR/.env" "$ENV_KEEP"
  fi
fi

echo "[3/6] Downloading complete source from GitHub..."
curl -fL --retry 4 --retry-delay 2 --connect-timeout 20 \
  "https://github.com/${REPO}/archive/refs/heads/${BRANCH}.tar.gz" \
  -o "$ARCHIVE"

tar -xzf "$ARCHIVE" -C "$TMP_DIR"
SRC_DIR="$(find "$TMP_DIR" -maxdepth 1 -mindepth 1 -type d -name 'vpn-managrer-*' | head -n1)"
[[ -n "$SRC_DIR" && -f "$SRC_DIR/docker-compose.yml" && -f "$SRC_DIR/app/main.py" ]] || {
  echo "ERROR: downloaded GitHub source is incomplete." >&2
  exit 2
}

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"
cp -a "$SRC_DIR"/. "$APP_DIR"/
cd "$APP_DIR"

NEW_ADMIN="$(openssl rand -hex 12)"
if [[ -n "$ENV_KEEP" && -f "$ENV_KEEP" ]]; then
  cp "$ENV_KEEP" .env
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
  FOUND=""
  for P in $(seq 8080 8099); do
    if ! ss -lnt 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:)$P$"; then FOUND="$P"; break; fi
  done
  [[ -n "$FOUND" ]] || { echo "ERROR: ports 8080-8099 are all in use." >&2; exit 3; }
  PORT="$FOUND"
  if grep -q '^APP_PORT=' .env; then sed -i "s/^APP_PORT=.*/APP_PORT=$PORT/" .env; else echo "APP_PORT=$PORT" >> .env; fi
fi

echo "[4/6] Building application..."
docker compose build --no-cache app

echo "[5/6] Starting database and application..."
docker compose up -d

echo "[6/6] Running health checks..."
OK=0
for _ in $(seq 1 90); do
  H="$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/health" 2>/dev/null || true)"
  L="$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/login" 2>/dev/null || true)"
  if [[ "$H" == "200" && "$L" == "200" ]]; then OK=1; break; fi
  sleep 2
 done

if [[ "$OK" != "1" ]]; then
  echo
  echo "ERROR: application did not pass health checks." >&2
  echo "--- docker compose ps ---" >&2
  docker compose ps >&2 || true
  echo "--- app logs ---" >&2
  docker compose logs --tail=300 app >&2 || true
  echo "--- db logs ---" >&2
  docker compose logs --tail=120 db >&2 || true
  exit 4
fi

PUBLIC_IP="$(curl -4fsS --max-time 5 https://api.ipify.org 2>/dev/null || true)"
if [[ -z "$PUBLIC_IP" ]]; then PUBLIC_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"; fi
PUBLIC_IP="${PUBLIC_IP:-YOUR_SERVER_IP}"
ADMIN_USER="$(grep '^ADMIN_USERNAME=' .env | cut -d= -f2- || true)"
ADMIN_USER="${ADMIN_USER:-admin}"

echo
cat <<OUT
============================================================
VPN Control Center READY
URL:      http://${PUBLIC_IP}:${PORT}
Username: ${ADMIN_USER}
Password: ${NEW_ADMIN}
============================================================
Next:
1) Login with the credentials above.
2) Settings -> upload vpn-sait.xlsx.
3) Servers -> add ONE X-UI server first and test Sync.
OUT
