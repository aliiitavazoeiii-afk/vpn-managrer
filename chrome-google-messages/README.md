# Hesab → Google Messages Web (Chrome Extension)

An **experimental desktop-only** Google Chrome / Microsoft Edge extension for the Hesab VPN admin. No SMS Gateway app, API token, cloud SMS provider, Selenium process, or new Android app.

## How it works

```
Admin click on hesab.filmjadiid.ir (/sms or /debts)
  └─ Chrome content script intercepts original HTML form BEFORE server POST
      └─ Extension creates a Google Messages Web tab in same browser profile
          └─ Google Messages Web (already paired to phone) handles sending
              └─ Existing Google Messages Android app uses the phone/network
```

**Google Messages Web is not an official programmable SMS API.** Google can change its UI, break recipient selection or block DOM automation. The extension's result `SUBMITTED` means the visible Google Messages compose UI appeared to accept the send, not verified carrier delivery. The bridge will NEVER auto-retry an uncertain send.

### Critical production constraints

1. **Stop all previous Hesab Android SMS Gateway instances first**. Do not turn them back on while testing this extension. Previously queued jobs on the server remain, and a restarted gateway can send them. Inspect the queue before enabling anything.
2. The installed extension intercepts form submissions to `/sms/send` and `/sms/debt-send`. The old backend is NOT called by the intercepted click. **Old SMS job status in the dashboard will not automatically change.**
3. For debt reminders, the prior form used to move the customer from `وصول بدهی` to `در انتظار`. In bridge preview mode this is intentionally **NOT automatic**; operator must confirm Google Messages submission and manage the follow-up manually. Do not misrepresent a browser UI action as delivery.
4. On browsers/devices without the extension, the existing site form STILL POSTS to the old queue. Do not use that old button from another device. A future server change should disable the old Android queue endpoint before production rollout.
5. Google Messages may choose **SMS or RCS** for the target based on recipient configuration. This is not a direct SMS provider API and cannot override mobile operator/Android transport restrictions.

## Install (Chrome or Edge, on your computer)

1. On your Nothing Phone 1, stop or uninstall the old custom Gateway apps. Keep Google Messages as the default texting app.
2. On the same computer/browser Chrome profile where you paired [Google Messages for Web](https://messages.google.com/web/), install the extension:
   - Extract the downloaded `Hesab-Google-Messages-Bridge.zip`.
   - Open `chrome://extensions/`.
   - Enable **Developer mode**.
   - Click **Load unpacked** and choose the extracted folder containing `manifest.json`.
3. Open or refresh `https://hesab.filmjadiid.ir/sms` (or `/debts`). You should see a small banner `Google Messages Bridge فعال`.
4. Leave **Automatic sending disabled** in extension popup at first.
5. On the Hesab SMS page, send a test message to **a number you own**. The extension opens a new Google Messages Web tab and tries to select that phone and pre-fill the exact Persian text. Confirm the number and text, then click **Send** manually in Google Messages Web.
6. Confirm the test appears in Google Messages and is received. Once verified, the popup has an optional **auto send after click** checkbox. This clicks Send once only after matching the recipient selection and full message text. If anything is ambiguous, it does NOT send and leaves the tab for manual inspection.

## Why not use a generic Chrome Store extension?

Generic extensions often only open a contact/new conversation (no text field) or have broad access to your message history. This project is scoped to the *exact two origins* `hesab.filmjadiid.ir` and `messages.google.com`, does not read message history, store phone/message text permanently, collect tokens, or connect to any third-party server. The Chrome tab session stays with Google.

This is a **proof of concept**, not a production delivery-confirmation service. Treat any unsuccessful or uncertain result as potentially submitted: inspect the Google Messages conversation first. Never blindly retry debt messages.

## Implementation

- Manifest V3 and no dependencies, native Node service, Selenium, Android app, or native host.
- All request sources are checked against the exact Hesab origin.
- Form capture-phase interception prevents legacy Android Gateway queue insertion for that click.
- Only valid Iranian mobile numbers accepted; recipient is normalized to `+989xxxxxxxxx`.
- 2-minute duplicate guard in the site and 3-minute guard in the extension memory.
- Strict form size max 1000 chars; no automatic retries.
- New Google tab per request avoids overwriting any existing chat draft.
- Optional auto-send requires exact matching phone option, exact message text and a visible enabled Send control; submits once and distinguishes "submitted" from delivered.
- No browsing permissions for other sites, no Google tokens or secret reads.

## Troubleshooting

- **No green banner**: refresh Hesab admin tab after installing; ensure correct Chrome profile and exact domain.
- **Google Messages pairing screen**: pair in that same Chrome profile.
- **MANUAL_RECIPIENT**: Google changed autocomplete markup or multiple contacts match. Choose the intended number manually; the script will not pick a different number.
- **DRAFT_READY**: click Send yourself in the Google tab.
- **AMBIGUOUS_SEND**: do not retry; look at the Google conversation first.
- **Old panel says queued/delivered**: these are historical Android Gateway entries; the bridge does not edit them.

## v0.1.3 — recipient selection and Persian draft

- The Google Messages suggestion list is now checked repeatedly instead of only one second after entering the phone.
- When one result visibly contains the exact requested Iranian mobile number, the extension attempts to select that result and fill the message.
- If there is one name-only contact suggestion, it may open the conversation for **draft preparation only**. The destination was not verifiably matched to the number; the user must check it and click Send manually. Auto-send is blocked for this scenario, even if the popup option was enabled.
- If no safe suggestion is found, the extension allows roughly 28 seconds for the user to click the intended contact, then fills the draft as soon as the composer appears. If this window expires, the attempt stops; do not expect text to appear afterward.
- Always check the recipient and the exact Persian text before pressing Send. Selecting a recipient or filling a draft is **not** a successful send or delivery receipt.
- Until verified with a self-owned test number, keep automatic sending disabled. Neither the backend SMS queue nor debt accounting is updated by this extension.
