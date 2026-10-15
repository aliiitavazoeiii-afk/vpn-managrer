# Hesab → Google Messages Web — browser bridge v0.2.0

A lightweight Chrome Manifest V3 extension plus two same-origin endpoints in the Hesab admin. The original Android SMS gateway app is NOT used. No unofficial Google Account access, remote code injection, or third-party SMS provider.

## One-click, no gateway queue

1. Click SEND SMS in the Hesab dashboard. A content script captures the form before the legacy backend handler.
2. The admin server creates one durable sms_browser_intents record through POST /sms/browser/begin, checking duplicates and matching the canonical debt reminder.
3. Chrome opens the paired Google Messages Web session. Only a UNIQUE visible contact choice showing the expected phone digits is eligible for an automated click to send. The extension fills the exact Persian body and clicks Send once.
4. If Google Messages UI indicates submission, Chrome calls POST /sms/browser/finish with the one-time token. In one DB transaction, the admin records browser_submitted and moves eligible overdue accounts to waiting, then refreshes the debts page.
5. A browser-submitted message is NOT a verified SMS delivery. No Delivered status is stored. Any uncertain attempt is never retried automatically.

## Deploy BACKEND FIRST

Read PROJECT_HANDOFF.md before any production modifications. Do not run install.sh, docker compose down -v, git reset --hard, or any action that can erase app or customer data.

On the Ubuntu management server, use a separate checkout rather than switching branches in the live tree. For example, as root:

    cd /opt
    git clone --depth 1 -b google-messages-chrome-bridge https://github.com/aliiitavazoeiii-afk/vpn-managrer.git /opt/hesab-browser-bridge-src
    bash /opt/hesab-browser-bridge-src/scripts/install_browser_sms_bridge.sh

The installer checks existing SMS/Aban/no-jump runtime markers, makes a verified PostgreSQL dump and a Compose backup, adds only a read-only bridge patch mount and startup append, and recreates ONLY the admin app without a Docker image rebuild. It leaves customer portal, DB volume, payments, and old SMS jobs untouched. The existing direct POST /sms/send and /sms/debt-send paths are blocked after deploying; the extension exclusively uses /sms/browser/begin and /sms/browser/finish.

A GitHub commit alone DOES NOT deploy to the live server. The above command is required. The installer must print SUCCESS before proceeding.

## Install extension without repeated Remove / Reinstall

Extract the inner Hesab-Google-Messages-Bridge.zip from GitHub Actions Artifacts. Open chrome://extensions, enable Developer Mode, and choose Load unpacked to select the extracted folder containing manifest.json. Use the SAME Chrome profile in which messages.google.com/web/ is paired.

For future changes keep the same folder: overwrite the six extension files IN PLACE and click Reload (circular arrow) on the existing extension card. Do not remove it or move the folder. Admin message templates, canonical debt status, and queue protections are now server-controlled, so routine panel visual/template changes do NOT require a new extension build. Chrome Google Messages DOM changes may still require updates. True unattended extension updates require distribution through Chrome Web Store; the unpacked GitHub artifact cannot silently auto-update itself.

Fresh installs default to one-click enabled. If the setting was previously disabled, enable it once via the popup. Exact phone verification is mandatory for automated send, regardless of the checkbox.

## Test and safety

Do not reactivate the former Android Gateway. First test only with a phone and test account YOU OWN, never an actual customer. Write a fresh, unique Persian message, click the Hesab button ONCE, and inspect the Google conversation for matching recipient, outgoing bubble and body. Then verify Hesab displayed browser submission status. The generic SMS page does not modify debt states. For a controlled overdue test account, eligible debt moves to waiting only after successful UI submission and database acknowledgement.

Errors such as EXISTING_LEGACY_SMS_CHECK_HISTORY, EXISTING_BROWSER_INTENT_PENDING, DEBT_MESSAGE_CHANGED_REVIEW_REQUIRED, DRAFT_READY_REVIEW_RECIPIENT, AMBIGUOUS_SEND or TIMEOUT all require a manual check of the Google conversation. NEVER retry uncertain sends automatically.

This project is based on DOM automation. Google Messages Web does not offer a general official SMS automation API. There is no guarantee that Google will preserve these HTML selectors or that a browser UI submission will result in carrier delivery. One-click fails closed when exact recipient identity is ambiguous.
