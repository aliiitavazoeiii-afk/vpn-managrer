#!/usr/bin/env bash
set -Eeuo pipefail

REPO="aliiitavazoeiii-afk/vpn-managrer"
BRANCH="main"
DOMAIN="hesab.filmjadiid.ir"
APP_DIR="/opt/vpn-control-center"
TMP_DIR="/tmp/hesab-vpn-install.$$"
ARCHIVE="$TMP_DIR/repo.tar.gz"
PORT="8080"

cleanup(){ rm -rf "$TMP_DIR" 2>/dev/null || true; }
trap cleanup EXIT

[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "Run as root."; exit 1; }
[[ -n "${VPN_SEED_KEY:-}" ]] || { echo "ERROR: VPN_SEED_KEY is not set."; exit 2; }

export DEBIAN_FRONTEND=noninteractive
mkdir -p "$TMP_DIR"
apt-get update -y
apt-get install -y ca-certificates curl openssl tar gzip nginx certbot python3-certbot-nginx

if ! command -v docker >/dev/null 2>&1; then
  . /etc/os-release
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  ARCH="$(dpkg --print-architecture)"
  CODENAME="${VERSION_CODENAME:-${UBUNTU_CODENAME:-}}"
  echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${CODENAME} stable" >/etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

echo "[1/7] Removing the previous VPN manager installation and its database..."
if [[ -f "$APP_DIR/docker-compose.yml" ]]; then
  (cd "$APP_DIR" && docker compose down -v --remove-orphans) || true
fi
rm -rf "$APP_DIR"

echo "[2/7] Downloading the new source..."
curl -fL --retry 4 --retry-delay 2 "https://github.com/${REPO}/archive/refs/heads/${BRANCH}.tar.gz" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$TMP_DIR"
SRC="$(find "$TMP_DIR" -maxdepth 1 -mindepth 1 -type d -name 'vpn-managrer-*' | head -n1)"
[[ -f "$SRC/Dockerfile" && -f "$SRC/packed/main.00" && -f "$SRC/seed/users.enc" ]] || { echo "Incomplete source."; exit 3; }
mkdir -p "$APP_DIR"; cp -a "$SRC"/. "$APP_DIR"/; cd "$APP_DIR"

echo "[3/7] Creating fresh secrets..."
SECRET="$(openssl rand -hex 32)"
DBPASS="$(openssl rand -hex 18)"
ADMINPASS="$(openssl rand -base64 18 | tr -d '/+=' | head -c 20)"
cat >.env <<EOF
APP_NAME=Hesab VPN
APP_DOMAIN=$DOMAIN
APP_SECRET_KEY=$SECRET
ADMIN_USERNAME=admin
ADMIN_PASSWORD=$ADMINPASS
POSTGRES_DB=vpncontrol
POSTGRES_USER=vpncontrol
POSTGRES_PASSWORD=$DBPASS
SEED_KEY=$VPN_SEED_KEY
APP_PORT=$PORT
BIND_IP=127.0.0.1
EOF
chmod 600 .env

echo "[4/7] Building and starting the application..."
docker compose build --no-cache
docker compose up -d

echo "[5/7] Verifying the 307-record encrypted seed..."
OK=0
for _ in $(seq 1 75); do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then OK=1; break; fi
  sleep 2
done
if [[ "$OK" != 1 ]]; then
  docker compose logs --tail=250 app
  exit 4
fi

echo "[6/7] Configuring Nginx for $DOMAIN..."
cat >/etc/nginx/sites-available/hesab-vpn <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;
    client_max_body_size 10m;
    location / {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
ln -sfn /etc/nginx/sites-available/hesab-vpn /etc/nginx/sites-enabled/hesab-vpn
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable --now nginx
systemctl reload nginx

echo "[7/7] Enabling HTTPS..."
if certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect; then
  URL="https://$DOMAIN"
else
  URL="http://$DOMAIN"
  echo "WARNING: HTTPS certificate failed. Check that DNS points to this server, then run:"
  echo "certbot --nginx -d $DOMAIN --redirect"
fi

echo
echo "============================================================"
echo "Hesab VPN is ready"
echo "URL:      $URL"
echo "Username: admin"
echo "Password: $ADMINPASS"
echo "Records:  307"
echo "============================================================"
