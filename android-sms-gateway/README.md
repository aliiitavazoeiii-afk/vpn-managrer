# Hesab Messages V2 — isolated Android preview

**Branch:** `hesab-messages-v2` (not deployed; does not change the live `sms-app` app, SMS database, Caddy, or billing).

Hesab Messages is an experimental personal SMS app and a dashboard-connected SMS gateway in **one Android app**. It upgrades the existing `ir.filmjadiid.hesabsms` Java Android project so the future release can preserve its settings and gateway token. GitHub Actions creates a separately installable **debug** package `ir.filmjadiid.hesabsms.debug` for preview/testing.

## Implemented

- Android-local inbox and conversation history via the system SMS provider, with manual composing/sending.
- Opt-in default SMS role, SMS_DELIVER receiver and local SMS storage.
- Gateway setup/settings still live under "اتصال به داشبورد"; HTTPS endpoints remain the existing `hesab.filmjadiid.ir/sms-gateway` APIs.
- Work SMS are saved in the **local phone SMS provider** when Hesab is the default SMS app. Personal messages are **never uploaded to the accounting server**.
- Explicit per-segment PendingIntents with unique URIs for sent and delivered results, vendor `errorCode` and SIM diagnostics, duplicate-receipt prevention, and a durable local status outbox. The foreground Gateway service retries the status upload, not the SMS.
- **Only one work SMS in flight at a time.** Waits for all *send* callbacks (not delivery receipts) before taking the next job. A 20-second minimum dispatch gap is a cautious default, not a guarantee of delivery or a universal carrier rate.
- If a send callback fails or never completes for 3 minutes, the gateway stops claiming more messages. Restarting service alone does not auto-resend. A visible button lets the owner resume after inspecting the last job.
- The existing dashboard's live financial data, reminder wording, follow-up state, and customer portal are untouched.

## IMPORTANT: Not production-ready as a default SMS app

- **MMS is not implemented** (the prototype only retains raw WAP push data and warns the owner). It cannot decode/show MMS photos or attachments or send MMS.
- **RCS is not implemented**; Google Messages proprietary RCS read/delivered ticks will not transfer to a third-party SMS app. Native SMS carrier receipts are supported when provided.
- Contact name resolution, attachment handling, robust duplicate inbound SMS checks, notification grouping, accessibility QA, background OEM compatibility, and extensive device-level SMS tests remain incomplete.
- Do **not** set this preview as the default SMS handler on a primary phone that receives essential messages or MMS. Use a test phone/SIM until fully validated.
- Sending and receiving are subject to Android/system/carrier constraints; a custom app cannot bypass legitimate rate controls.
- `result=0` previously reported by Android needs verification on the actual handset. V2 reports per-segment result and optional `errorCode`; it does not assume an operator restriction is the cause.
- A user's Google Messages history stored in the Android SMS provider can generally be read with permission, but **RCS** history may not be visible.

## Preview build

Go to GitHub Actions -> **Build Hesab Messages V2 preview** -> latest successful run -> artifact `Hesab-Messages-V2-PREVIEW`. Debug APK has package suffix `.debug`, separate preferences, and **does not inherit the current gateway token**. The user must enter the token on the test device; never send tokens/passwords into chat.

## Controlled smoke-test checklist

1. Install APK on a **spare Android phone** or emulator with telephony support and a test SIM. Open app and verify inbox permissions.
2. Do NOT make it default on a primary phone. On a spare phone, opt in to default SMS role and verify receiving/reading a short SMS.
3. Send a short manual SMS to your own secondary number. Check the Android SMS provider sent state, then recipient delivery.
4. Use the settings screen to connect to the existing gateway with a **test** device/session only. Queue *one* safe SMS and verify send/delivered/failed callbacks and server record, including SIM sub ID.
5. Test a multipart Persian SMS and one failed callback. Verify the queue halts; inspect the last job before pressing "resume".
6. Confirm dashboard SMS appears in the same conversation and that personal SMS content does not go to the server.
7. Only after MMS support and broader QA should production/default-SMS replacement be considered.

## Build source

Gradle 8.7, Android Gradle Plugin 8.5.2, Java 17, compileSdk 35, targetSdk 34, minSdk 26.
