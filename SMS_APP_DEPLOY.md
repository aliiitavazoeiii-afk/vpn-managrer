# Hesab SMS Gateway

Branch: `sms-app`

This adds:

- `/sms` inside the existing authenticated Hesab dashboard.
- A separate `sms-gateway` API container that only lets the paired Android phone claim/report queued jobs.
- An Android foreground-service app that polls the queue and sends SMS from the selected physical SIM.
- SMS sent/delivery status reporting back to Hesab.
- No changes to the Darma project files. The existing shared Caddy config is only read and a combined config is loaded into the running Caddy container.

## Production server deployment

Run from the Hesab server:

```bash
set -e

cd /opt/vpn-control-center

rm -rf /tmp/hesab-sms-src
git clone --depth 1 --branch sms-app   https://github.com/aliiitavazoeiii-afk/vpn-managrer.git   /tmp/hesab-sms-src

mkdir -p patches sms_gateway scripts deploy

cp -f /tmp/hesab-sms-src/patches/sms_admin.py patches/sms_admin.py
cp -f /tmp/hesab-sms-src/docker-compose.sms.yml docker-compose.sms.yml
cp -a /tmp/hesab-sms-src/sms_gateway/. sms_gateway/
cp -f /tmp/hesab-sms-src/scripts/apply_hesab_caddy.sh scripts/apply_hesab_caddy.sh
cp -f /tmp/hesab-sms-src/deploy/Caddyfile.hesab.sms deploy/Caddyfile.hesab.sms

chmod 700 scripts/apply_hesab_caddy.sh

if ! grep -q '^SMS_GATEWAY_TOKEN=' .env; then
  printf '\nSMS_GATEWAY_TOKEN=%s\n' "$(openssl rand -hex 32)" >> .env
fi
chmod 600 .env

docker compose   -f docker-compose.yml   -f docker-compose.sms.yml   build sms-gateway

docker compose   -f docker-compose.yml   -f docker-compose.sms.yml   up -d sms-gateway

docker compose   -f docker-compose.yml   -f docker-compose.sms.yml   up -d --no-deps --force-recreate --no-build app

sleep 5

docker compose   -f docker-compose.yml   -f docker-compose.sms.yml   ps

curl -fsS http://127.0.0.1:8080/health && echo
```

## Route through the existing shared Caddy

```bash
cd /opt/vpn-control-center

cp -f deploy/Caddyfile.hesab.sms Caddyfile.hesab

./scripts/apply_hesab_caddy.sh

curl -fsS https://hesab.filmjadiid.ir/sms-gateway/health && echo
```

Expected:

```json
{"ok":true,"service":"Hesab SMS Gateway"}
```

The Darma Caddyfile is not modified.

## Pair the Android phone

Show the private gateway token locally on the server:

```bash
cd /opt/vpn-control-center
grep '^SMS_GATEWAY_TOKEN=' .env | cut -d= -f2-
```

Do not put this token in GitHub or send it to customers.

In the Android app:

- Server: `https://hesab.filmjadiid.ir`
- Gateway Token: paste the value above
- Select the SIM that should send customer messages
- Grant SMS + Phone permissions
- Tap **شروع Gateway**
- Tap **تست اتصال به سایت**
- Allow background/battery exemption when Android asks

Then open:

`https://hesab.filmjadiid.ir/sms`

Queue a test SMS to your own number first.

## Stop / rollback SMS only

This does not touch the main Hesab database or Darma.

```bash
cd /opt/vpn-control-center

docker compose   -f docker-compose.yml   -f docker-compose.sms.yml   stop sms-gateway

docker compose   -f docker-compose.yml   up -d --no-deps --force-recreate app

# Reload the normal Hesab route you had before if needed.
```
