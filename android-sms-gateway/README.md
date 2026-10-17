# Hesab VPN — manual WhatsApp opener for Android

Source branch: `whatsapp-manual-operator-open` (child of `manual-sms-batch-operator-open`).

This is the SAME Android app ID (`ir.filmjadiid.hesabsms`) and SAME existing site/API, queue, device ID, token and operator-open acknowledgement as the V4 Google Messages manual app. No server, database, website or queue changes.

## Behavior

1. The current Hesab site continues to enqueue the identical manual drafts (renewal messages, debt reminders and other existing SMS actions) into its existing `/sms-gateway/v4/drafts/pending` endpoint.
2. The Android app fetches the same queue every four seconds while it is visible.
3. For each draft tap **بازکردن پیام آماده در واتساپ**. The app turns Iranian `09xxxxxxxxx` into WhatsApp's required `989xxxxxxxxx` and builds an official `https://wa.me/98...?text=...` link. It explicitly targets installed WhatsApp (`com.whatsapp`) or WhatsApp Business (`com.whatsapp.w4b`) and uses their direct-app scheme as a fallback, **never the default SMS composer**.
4. The chat appears with the original text prefilled. The operator must manually tap WhatsApp's Send. The app has **no automatic WhatsApp send**, no telephony permissions, and cannot confirm message delivery.
5. Only after Android successfully launches WhatsApp, the app calls the unchanged `/sms-gateway/v4/drafts/{id}/operator-open` endpoint. This records **operator opened**, corresponding to the site's existing waiting state. It does not mean **sent** or **delivered**. If WhatsApp is absent/unable to launch, the pending marker is cleared and the draft remains in the queue.
6. Pending acknowledgement after opening WhatsApp is retried with the existing V4 logic until the existing site confirms; one at a time.

## Building the new APK

GitHub Actions > `Build Hesab WhatsApp Manual APK` > select branch `whatsapp-manual-operator-open` > **Run workflow** (or use the automatically triggered push run). Download artifact `Hesab-WhatsApp-Manual`, extract `Hesab-WhatsApp-Manual.apk` and install on Android.

The `app/build.gradle` `applicationId` is unchanged, versionCode increased to **7** and versionName to **4.1.0-whatsapp-manual**. Android might reject an in-place update if the debug APK's signing certificate differs between GitHub Actions builds. If it shows `INSTALL_FAILED_UPDATE_INCOMPATIBLE`, re-sign both builds with one consistent key to support upgrades, or manually record your server URL/token and reinstall the new APK. Uninstalling an existing app clears its locally stored token/device ID; after reinstall enter the same server URL/token again. The existing website and queue are untouched.

## Verification

The branch's GitHub Actions job checks that the Android manifest lacks `SEND_SMS`/`READ_SMS`, no SMS composer or background sender exists, API endpoints remain the same, and the new WhatsApp link helper's plain Java tests pass (Iranian number validation and exact UTF-8 Persian prefilled text).

Do not run any server install scripts for this change. It needs **only an APK update**, not a deployment on the Hesab VPS.
