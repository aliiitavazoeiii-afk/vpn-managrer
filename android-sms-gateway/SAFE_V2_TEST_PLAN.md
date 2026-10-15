# Hesab SMS Gateway — Native V2 test-only release

This is a continuation of the existing Hesab repository, not a replacement for
the customer, billing or transaction systems.

## Why this version is deliberately limited

- This build uses the dedicated `native_sms_v2_jobs` queue. It does **not**
  consume or automatically retry old `sms_jobs` records.
- This build can send **only** to the explicit 11-digit `09xxxxxxxxx`
  test phone entered in the app. The Android telephony call itself checks
  this allowlist again.
- The V2 API also filters by `test_phone` **before claiming** a job.
  It rejects older V2 clients that do not pass the test phone.
- A successful **SENT** callback means accepted for sending by Android/carrier;
  it does not prove customer delivery. Only a positive delivery receipt
  may change a record to `delivered`.
- Each operator-initiated test session sends at most **one** successfully
  acknowledged SMS, then disables the foreground worker. There is also a
  minimum 90-second cooldown.
- Failed, lost, or ambiguous attempts pause the sender and are never retried
  automatically. A stuck claimed/attempting record requires operator review.
- This is **not yet** an approved customer-sending release.

## Inspect the Ubuntu server first (read-only)

On the production server:

```bash
cd /opt/vpn-control-center
docker compose -f docker-compose.yml -f docker-compose.sms.yml ps
curl -sS -o /dev/null -w 'Public V2 health HTTP %{http_code}\n' \
  https://hesab.filmjadiid.ir/sms-gateway/v2/health
docker compose -f docker-compose.yml -f docker-compose.sms.yml \
  exec -T app sh -lc "grep -c 'HESAB_NATIVE_SMS_V2_ADMIN' /app/app/main.py || true"
```

For the public V2 health endpoint, HTTP 401 without the private token means
the V2 handler exists. HTTP 404/502 does **not** prove V2 is ready. Confirm
the actual server source, Compose routing and DB before any test. A V1-only
deployment is not suitable for this APK.

**Do not** simply pull/recreate production services or insert customer SMS
into an old queue to make the check pass. Existing old SMS jobs must be
reconciled separately.

## Install and test (only after V2 server is confirmed)

1. On the phone, STOP / uninstall any older actively running Hesab Gateway.
   Keep Google Messages as the default SMS app. Do not run multiple gateways.
2. Download the `Hesab-SMS-Gateway` artifact from the latest successful
   `Build Hesab SMS Gateway APK` GitHub Actions run on branch
   `android-sms-safe-v2`; unzip it and install the APK.
3. Open the app. Set the HTTPS server URL, private gateway token, and your
   own test phone (`09...`). Select the **actual physical SIM** explicitly.
4. Tap **تست اتصال به سایت**; this must pass against V2 before enabling sending.
5. Make sure the new `native_sms_v2_jobs` queue contains no earlier pending
   test jobs to your own number. From the Hesab SMS page queue exactly **one**
   manual SMS to your test phone, only after the native patch is installed.
6. Tap **شروع Gateway آزمایشی**. Verify: correct destination, Persian text,
   message visible in Google Messages, and Android `sent` callback.
7. If SMS was accepted, the sender will stop after this one job. Do not
   equate `sent` with `delivered`. A new test requires a new explicit Start.
8. If a failure, uncertainty or missing callback appears: STOP. Do not
   press Send again and do not clear any SQL statuses to force a retry.
   Capture the job ID, HTTP status and Android screen for diagnosis.

## Safe rollout requirement

The separately committed Python V2 API must be deployed and the existing
`patches/sms_native_v2.py` must be appended **after**
`sms_browser_bridge.py` and `sms_nojump.py`. The Git repository
contains these pieces, but the current production deployment has not been
verified from this checkout.

An installation step for production should back up Compose configuration,
the PostgreSQL database and app route configuration, confirm the old Android
Gateway is stopped, and avoid modifying the old SMS queue or subscription
payments. Only after the isolated one-number test passes should customer
delivery be considered.
