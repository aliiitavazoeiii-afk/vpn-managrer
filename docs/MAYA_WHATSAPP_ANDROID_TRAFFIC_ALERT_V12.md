# Maya traffic alerts in the EXISTING Hesab WhatsApp Android app (V12)

Source branch: feat/maya-low-traffic-android-alert-v12
Base: feat/maya-nic-traffic-history-v11

This ports the existing manual WhatsApp app from whatsapp-manual-operator-open
(the same package ID, same gateway token, same queue and operator-open behavior)
and adds OPTIONAL Android local notifications when a Maya server has fewer
than 10.0 GB remaining *according to the existing provisional RX estimate*.

- Phone checks a token-protected read-only endpoint under the existing
  HTTPS /sms-gateway proxy. No new public port, external push provider or
  private credentials in the APK.
- Android JobScheduler requests 15-minute background checks, persisted across
  reboots. The OS may delay them substantially during power saving/Doze and
  after force-stop. NOT a guaranteed real-time incident paging service.
- Notification body clearly says "مانده تخمینی"; no claim of verified
  datacenter billed direction. Unknown/stale/reset telemetry -> NO alert.
- One notification per server while below 10.0 GB, re-arm only after >=12 GB
  (typically a provider top-up). If already below 10 on enabling, notify once.
- Separate "ارسال اعلان آزمایشی" button verifies phone permission/channel
  without changing the traffic ledger.
- Old V9 purchase rows remain in database. Only rows matching the currently
  active V7 baseline epoch are credited; never double-count purchases included
  in new operator-reported balances.
- The app still opens WhatsApp manually; it NEVER sends WhatsApp/SMS automatically.
- This is a PHONE notification, not an automated WhatsApp message.

## Deploy backend first — MANAGEMENT HOST ONLY

Never run the repository root install.sh, compose down -v, or overwrite
database volumes. On the Hesab management host as root:

    cd /root
    git clone --depth 1 --branch feat/maya-low-traffic-android-alert-v12 \
      https://github.com/aliiitavazoeiii-afk/vpn-managrer.git \
      /root/hesab-maya-alert-v12-src
    bash -n /root/hesab-maya-alert-v12-src/scripts/install_maya_low_traffic_android_v12.sh
    bash /root/hesab-maya-alert-v12-src/scripts/install_maya_low_traffic_android_v12.sh

The installer verifies live V4 gateway source and V7 baseline and takes a
backup of sms_gateway/server.py and docker-compose.sms.yml. It appends only
the new endpoint code, mounts only ./maya_extra_sync/phase1 as read-only into
sms-gateway, rebuilds/recreates *only* sms-gateway, and checks the real token
protected route. On failure it restores the files and tries to recreate the
previous gateway. It does not restart X-UI, tunnels, customer portal or DB.

Endpoint: GET https://hesab.filmjadiid.ir/sms-gateway/v5/maya/low-traffic
Header: X-SMS-Gateway-Token: <the existing secret stored in the Android app>.
Never paste this token into chats, browser URL query strings or GitHub.

## Build/Install APK

GitHub Actions > Build Hesab WhatsApp Maya Low Traffic Alert V12, select
the feature branch, run the workflow and download the
Hesab-WhatsApp-Maya-Alert-V12 artifact. Install app-debug.apk.

The applicationId is the original ir.filmjadiid.hesabsms with the existing
debug suffix, package ir.filmjadiid.hesabsms.debug. versionCode 8.
GitHub Actions may have used a DIFFERENT debug signing certificate for the
original WhatsApp APK: Android will then refuse an in-place upgrade.
Do not uninstall until you have securely saved the existing gateway URL/token
in a private location; reinstallation removes local app preferences and device
ID. Never share tokens or private keys.

Open the app, keep the existing HTTPS gateway URL/token, turn on
"فعال‌کردن هشدار زیر ۱۰ گیگ", grant POST_NOTIFICATIONS on Android 13+.
Use "ارسال اعلان آزمایشی" to confirm phone notifications and optionally
"بررسی ترافیک همین الان" to request immediate background polling.
Allow background activity as appropriate in phone power settings.

Expected title when an estimate goes below 10GB:
  هشدار ترافیک مایا ۴
Body:
  مانده تخمینی: ۸٫۵۰ گیگ؛ کمتر از ۱۰ گیگ.
  مقدار دیتاسنتر تأیید نشده است.

Do not infer successful delivery from a GitHub commit alone; the backend
installer, APK build/install, Android permission and actual test must pass.
If operational response requires immediate guaranteed warning, use a
server-triggered push service (e.g., FCM with owner-provided credentials)
and separate monitoring of notification delivery, not periodic Android jobs.

## Read-only diagnosis

On management host (never expose secrets):

    systemctl is-active hesab-maya-net-meter-v2.timer
    python3 /opt/vpn-control-center/scripts/maya_net_meter_manage_v2.py status
    cd /opt/vpn-control-center
    docker compose -f docker-compose.yml -f docker-compose.sms.yml ps sms-gateway

The V7 baseline and V9 journal must remain consistent. If a server's meter
has restarted or telemetry is stale, the app suppresses alerts rather than
guessing remaining GB. Rebaseline only from a fresh operator-reported value.
