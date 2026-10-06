# Hesab SMS Gateway for Android

Personal Android SMS relay for the Hesab dashboard.

## What it does

1. Runs a foreground service on the owner's Android phone.
2. Polls `https://hesab.filmjadiid.ir/sms-gateway/` over HTTPS.
3. Claims queued SMS jobs.
4. Sends them with Android `SmsManager` using the selected physical SIM.
5. Reports `sent`, `delivered`, or `failed` back to the dashboard.
6. Restarts after boot when Gateway was left enabled.

No gateway token is embedded in the APK. Enter the server-generated token once after installation.

The debug APK is built automatically by GitHub Actions on pushes to the `sms-app` branch.
