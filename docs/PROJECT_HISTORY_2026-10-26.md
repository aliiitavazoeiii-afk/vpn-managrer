# Hesab VPN — Full project history and technical decisions
**Updated: 2026-10-26 | Active development branch: manual-sms-batch-operator-open**

> This is a cumulative historical reference, not a claim that every commit is deployed. Initial historical facts are derived from the repository's older PROJECT_HANDOFF.md and Git commits from 2026-08-23 onward. Recent runtime observations are identified as operator-reported, not independently queried. Keep historical statements distinct from live database facts.

## 1. Identity, responsibility, and source of truth

- Project: Hesab VPN, a Persian subscription accounting / collection / customer-self-service platform for a VPN service. **Do not mix it with Darma ERP/pricing/expenses projects or their DBs.**
- GitHub: https://github.com/aliiitavazoeiii-afk/vpn-managrer ; **CURRENT WORKING BRANCH: manual-sms-batch-operator-open**; the default main branch and older sms-app branch do not necessarily have the recent production overlays.
- Last inspected branch commit at drafting: 43813caa (2026-10-26), before this documentation was committed.
- Production management server (operator confirmed 2026-10-26): IPv4 5.10.248.50, hostname historically ubuntu, application /opt/vpn-control-center. The source checkout used for recent updates was /tmp/tmp.gf0oloSYHt/repo; that temporary directory should not be treated as permanent.
- Admin domain: https://hesab.filmjadiid.ir. Customer portal domains include https://usersmanager.ir and https://moshtarakin.filmjadiid.ir (verify live routing, do not overwrite shared Caddy).
- Current service stack: FastAPI/Python, PostgreSQL 16, Docker Compose app/db/sms-gateway/customer-portal, shared Caddy and an independently managed root-only Maya X-UI broker over Unix socket. The Android/operator-message application is a separate component.
- Repository source and Git history are not a production DB backup. Production files can contain incremental patches not identical to GitHub files. Server secrets, keys, mappings, X-UI user data and the portal logo are intentionally absent from GitHub.

## 2. Chronology — from project start

### 2026-08-23 — Original application and install bundle

- Initial deployable subscription panel and hardened installer were committed. Original README documents importing **307 Excel subscriptions** from an encrypted seed and preserving exact display names and separately stored expiry, monthly fee and debt. Multiple subscriptions may share a phone without being merged.
- Basic app, PostgreSQL persistent volume, Persian/Jalali date handling, paid/unpaid state, free-account exemption and initial admin workflows were set up.
- **Dangerous historical installer:** root install.sh explicitly removes the app installation and database volume. It was meant for fresh bootstrap only. NEVER use it to update an existing server.

### 2026-08-30 to 2026-09-22 — Accounting/debt operations and admin UI

- UI work introduced debt-focused collection pages, search, Persian typography/Estedad and status colors; follow-up states and waiting groups, Jalali expiry editing, phone editing and user-management flows.
- Added group payment and later **partial or exact-amount payments** for waiting groups, bidirectional debt correction, and advance/prepayment behavior. The system supports multiple subscriptions under one phone and per-account financial history.
- Read affected code and the effective override order (patches/followup.py, waiting_*.py, group_pay.py, payment_undo.py, billing_anchor.py) before changing accounting behavior.
- Dashboard style went through multiple revisions (UI rescue, reference UI, focused dashboard, operator workspace). Do not blindly re-apply old styling installers over newer live patches.

### 2026-10-06 to 2026-10-07 — SMS, payment link and customer portal

- SMS gateway + Android app + Compose/Caddy route were built. Early iterations attempted native Android SMS sending and encountered modem/rate-limit, queue/ACK and sent-verification issues.
- Ayria provider checkout integration created verifiable payment attempts/allocations. Later confirmed callbacks/polling apply money to accounts and advance subscription/expiry with appropriate consistency checks.
- Added customer self-service portal: phone-oriented login, per-account cards/debts, aggregate versus single-account payments, payment returns/receipts, responsive Persian UI and logo, Safari/iOS handling, portal hostname routing.
- Began alignment from individual expiry dates to first-of-Jalali-month billing, with prorating; the legacy billing_anchor transition must not double-charge periods customers already paid.

### 2026-10-08 to 2026-10-12 — Financial correctness, accounts, portal UX

- Cancelled Ayria checkout references required provider-side re-verification and fresh references instead of replaying an old cancelled URL. Prevent duplicate payments and do not tell a customer to pay twice before reconciling.
- Fixed an actual SQL INSERT problem: payments.paid_at was omitted in a historical Ayria flow (subscription 345 was a diagnostic example). Production financial correctness is more important than cosmetic UI.
- Archived/deleted-user lifecycle was changed to preserve financial history using audit_events followup_cut instead of physically deleting account/payment rows. The older user_manage.py delete logic was destructive; current effective route order matters. Archive/search/re-add creates a new account rather than erasing history.
- On 2026-10-11, an older PROJECT_HANDOFF.md captured the state on branch sms-app. It is a **historical snapshot, not the current starting point**. Its billing_anchor figures (294 pending, 2 scheduled, 1 paid, and their financial sums), and 317-active screenshot were point-in-time observations, not current totals.
- 2026-10-12 commit series established canonical first-of-next-Jalali-month billing in customer_portal/billing_policy.py plus mirrored admin/customer rules and due-day tests; user explicitly wants first-day monthly accounting, accurate pro-rating, no duplicate charging.
- New portal notice, visual/styling and safe customer portal deployment, receipt/share UI, customer-login reporting, grouped account display and performance safeguards were added.

### 2026-10-13 to 2026-10-14 — Maya1 and richer Control Room

- Introduced audited, restricted-SSH **Maya1 X-UI inventory readback**, read-only sync, admin Control Room and snapshot-based daily usage. Later added exact-client manual enable/disable with CSRF, confirmation, bounded audits and a separate control socket/SSH forced-command key. Never modify entire inbounds, client UUIDs, finances or X-UI SQLite directly.
- Historical Maya1 initial validation: approximately **145 client labels, 141 owner-approved links, four explicitly excluded**. This was a strict legacy mapping requiring a roster count and approved digest; **it is NOT the current client count**.
- Original source / legacy integration uses /opt/vpn-control-center/maya1_sync/ with a 5-minute cron and scripts/maya1_readonly_sync.py, scripts/maya1_control_gateway.py and corresponding remote forced commands. A roster mismatch must fail closed, never auto-remap.
- Separate recent dynamic Maya API integration (see Oct 20) is NOT the same as the old fixed-roster SSH snapshot; keep both paths straight.

### 2026-10-15 to 2026-10-18 — SMS safety and explicit manual sending

- Native SMS V2 introduced isolated draft/claim queues and cautious Android delivery ACK handling; repeated real-world sends had stalled or got stuck around Android acknowledgement.
- Requirement evolved to operator-driven message preparation: Google Messages manual opening, then **WhatsApp/WhatsApp Business manual send app workflow** was requested. Sending is performed by a human; merely opening a draft must NOT be logged as carrier-verified SENT. A prior app-side release was described as 4.1.0-whatsapp-manual, but the release currently installed on the device must be checked separately.
- Admin debt and /followups waiting page were given explicit reminder buttons, batch draft list and a custom text box, with exact personalized text and no unsolicited automatic sends.
- Queue idempotency, deduplication, cancelled/delivered distinctions and historical audit events are critical. Do not run old aggressive SMS resend/reset installers on a live queue.

### 2026-10-20 to 2026-10-21 — Multi-Maya live management

- Built direct live X-UI snapshots for server IDs **maya1, maya-s3, maya4**, using scripts/maya_multi_panel_sync.py, scripts/maya_live_bridge.py, root-host systemd service hesab-maya-live.service and Unix socket /opt/vpn-control-center/maya_extra_sync/live.sock mounted into the admin app at /srv/maya-live/live.sock.
- Only the admin Control Room UI should change when working on live Maya management, not the main dashboard. The Control Room eventually gained three Maya cards, live user search, per-client enable/disable, manual linking, excluded/archived states, compact status and usage top-users for today and 30 days. Related files: patches/control_room_v2.py, maya_live_dashboard.py, maya_manual_links_v1.py, maya_dynamic_links_v1/v2.py and maya_live_exclusion_counts_v1.py.
- Matching is strict: verified approval takes precedence; exact normalized display name is allowed only when uniquely matched; conflicts, duplicates, archived/unmatched users must not be guessed or silently toggled. Manual approvals are server-side sensitive data, not GitHub.
- If a panel is plain HTTP, the management connection MUST go through a verified SSH loopback forward (StrictHostKeyChecking=yes). HTTPS uses verified TLS. Do not permit direct remote plaintext password transmission.
- Maya1 legacy fixed-roster path remains separate. **The Maya servers and foreign VPN tunnels are NOT the financial database; X-UI replacement should preserve users and only require connection repair.**
- Shahan SSH panel was investigated read-only. Its SSH auth/server-status view is manual-only; do not infer a live account action or schedule uncontrolled SSH probes from those diagnostics.

### 2026-10-23 — Debt SMS fixes and strict payment-driven Maya restore

- Extensive debt SMS updates unified fixed debt reminder copy across debt and waiting pages, one-time revised draft behavior, per-cycle idempotency, strict manual send semantics, cautious queue reset with validated DB backup, and preservation of sent evidence. Workflows and installers remain present in the repo.
- On /followups waiting page the operator requested a prominent **manual disable** action per exact account or carefully selected group; the system must NOT automatically disable all waiting users on a clock. A prior requested future cutoff time was a *proposal*, not the deployed rule.
- Initial journal-based Maya restore used table waiting_vpn_controls: operator-controlled disable, payment watermark, server/client email, state and subsequent successful payment. Re-enable requires a new payment after the manual cutoff plus fully paid/unexpired account, trusted exact Maya mapping and verified current X-UI status.
- Case **subscription 382 / Maya4**: manual cutoff really disabled X-UI, but ambiguous broker response recorded needs_review; payment ID 865 followed; first auto-worker ignored needs_review. This exposed missing retry/readback behavior.
- Case **subscription 242 / Maya1**: after manual disable and payment ID 941, admin manually re-enabled the X-UI client; journal still said disabled. Financial check was ready (paid, zero debt), so reconciliation clearly was not running.
- V2 fix: patches/waiting_vpn_restore_resilience_v2.py + scripts/install_waiting_vpn_restore_resilience_v2.sh and CI, adding needs_review retry, ambiguity readback, per-row bounded backoff, exact client CAS and no blind toggles. Successfully installed by operator, but was not enough to start the background loop.
- Root cause: FastAPI app's explicit custom lifespan prevented the old @app.on_event("startup") callback from starting the worker. V3 wrap: patches/waiting_vpn_worker_lifespan_v3.py + scripts/install_waiting_vpn_worker_lifespan_v3.sh; preserves the original lifespan, disables duplicate old registration, schedules one worker, writes a local heartbeat and confirms real completed scan at deployment.
- V3 runtime output supplied by operator: LIFESPAN_WORKER_ACTIVE True; WORKER_PASSES 1; WORKER_ERRORS 0; 382 became restored. Later 242 became restored and X-UI client_enabled True after it had already been manually enabled. **This proves the worker starts/reconciles; it is not yet proof of a brand-new disable -> actual payment -> automatic X-UI re-enable without human intervention.** Do not claim 100% completion of that end-to-end test.
- Read-only diagnostics: scripts/diagnose_waiting_auto_restore_v1.sh SID, scripts/diagnose_waiting_worker_runtime_v1.sh. V3 old AUTO_WORKER_REGISTERED=False is EXPECTED because on_startup was deliberately replaced by lifespan; check V3 heartbeat, not that old flag.

### 2026-10-24 — User-facing notice only

- Changed customer portal welcome modal from 'تمامی اکانت‌ها تا تاریخ یکم آبان محاسبه می‌شوند.' to **'تمامی اکانت‌ها تا تاریخ یکم آذر محاسبه می‌شوند.'** in customer_portal/dashboard_v2.html.
- Kept second sentence 'از این پس سررسید اکانت شما یکم هر ماه خواهد بود.'.
- Added isolated deployment scripts/install_portal_notice_azar_v1.sh with backup, customer-portal-only rebuild and runtime verification; CI succeeded.
- **This was a copy-only change. It does NOT move stored subscription expiry dates, settle bills, or alter billing algorithms.** Never treat the welcome message as proof of account-date migration.

### 2026-10-25 to 2026-10-26 — Rebuilt Maya1 server and administrative reconnection

- Operator moved/rebuilt the Maya1 Iran server and imported X-UI user data without intended user changes. In this discussion, **Maya1 current IP was 94.184.4.38**, distinct from the accounting management host 5.10.248.50.
- Previous read-only check, before rebuild: maya1 total=144 linked=116 unmatched=28 snapshot_saved=False. This command computes primarily exact-name matches, while the authenticated Control Room additionally uses approved mapping; do not conflate its linked count with confirmed Control Room link count.
- Post-rebuild diagnostic showed both live and legacy source still targeting Maya1's address, with old HTTPS panel settings on TCP 2095. New X-UI panel was plain HTTP (new custom panel path). Broker and direct checks returned SSL WRONG_VERSION_NUMBER: it was a protocol/path mismatch, not lost billing data.
- Git commit series a5ce4710 / 3532562f / 43813caa: scripts/diagnose_maya1_after_rebuild_v1.sh read-only checks and extension of scripts/bootstrap_maya_ssh_tunnel.sh to support **maya1**, with restricted root SSH key forwarding only 127.0.0.1:2095 and strict known-host verification. The host key fingerprint was separately confirmed from the actual Maya1 console against the network key by operator. Never record panel path, password, keys or tokens in repo.
- Operator reported **'ok shod' (fixed)** after the SSH pairing/configuration discussion. The final successful check maya1 output and latest X-UI linked/unmatched counts were NOT pasted to this conversation, so treat live restoration as *operator-confirmed, not independently proven by a final readback*.
- **Important:** fixed-roster legacy scripts/maya1_readonly_sync.py and scripts/maya1_control_gateway.py still contain hardcoded HOST=94.184.4.38 and expected legacy roster 145 / approved mapping SHA. The IP stayed the same in the logs, but a rebuild can remove the old remote forced-command SSH exporter/gateway even when dynamic live X-UI works. Do not assume 5-minute legacy sync/control.sock work because live broker succeeds. Inspect these separately before making changes, preserve existing mapping files and restore safely only if needed.
- Host SSH public fingerprint displayed in the conversation was SHA256:wbtVoThIOcMgKp9jeoQCneTNX1YRXvwNfyFTCT8Bt3s. Do not blindly trust a fingerprint from the management host itself; independently verify against the actual Maya1 console for any future rebuild. Credentials are never put in the chat/repo.

## 3. Architecture / current code topology

| Domain | Code and operational services | Safety-critical invariant |
|---|---|---|
| Admin & finance | packed/main.* + Dockerfile ordered patches; service app | Account, debt, audit, payments are in PostgreSQL, not X-UI |
| Customer self-service | customer_portal/server.py, v2.py, billing_sync.py, billing_cycle_live.py, dashboard_v2.html; customer-portal service | Provider-confirmed payments, correctly allocated, fair expiry progression |
| Payments | payments, billing_anchor, ayria_payment_requests / allocations | No duplicate credits, no double charge, never change history casually |
| Waiting/followup | patches/followup.py, waiting_*.py, group_pay.py | Explicit status and exact affected subscriptions |
| SMS drafts and queue | patches/sms_native_v2.py, sms_gateway/server.py, operator Android app | No unsupported claim of carrier SEND; no automatic retries/duplicates |
| Maya management | scripts/maya_multi_panel_sync.py, scripts/maya_live_bridge.py, patches/maya_live_dashboard.py and manual/dynamic link overlays | Verified exact X-UI identity, no blind toggle |
| Maya1 legacy | scripts/maya1_readonly_sync.py, maya1_control_gateway.py, maya1_sync/* | Frozen mapping must not be regenerated blindly; stale fallback separate from live |
| Paid-only restore | patches/waiting_vpn_control_v1.py, waiting_vpn_restore_resilience_v2.py, waiting_vpn_worker_lifespan_v3.py, table waiting_vpn_controls | Only previously operator-cut clients and later fully settled, confirmed payments |

### Boot/deploy reality

- Root Dockerfile assembles packed/main.* then **ordered** patches. Later overlays can replace routes/functions/templates; use the deployed effective file when diagnosing, not isolated GitHub definitions alone.
- docker-compose.sms.yml appends runtime billing and SMS patches before uvicorn. Source edits to image-baked code require rebuild; mounted/runtime app patch edits require only the scoped recreation specified by their safe installer.
- Canonical Compose invocation: docker compose -f docker-compose.yml -f docker-compose.sms.yml ...
- A GitHub commit is **not** production deployment. Never assume a CI test or import-only smoke test means a running daemon actually executes. V3 worker required a live scan heartbeat.
- Customer portal Dockerfile copies and executes its own modules and loads dashboard_v2.html at process import. A message/template change needs the customer-portal image rebuild/recreate, without touching app/db.
- Service credentials: .env, /root/.config/hesab-maya-extra.json (0600), SSH keys under /root/.ssh, approved_links.json under /opt/vpn-control-center/maya_extra_sync/ (mounted /srv/maya-live), and credentials on actual X-UI hosts. Keep them off GitHub.

## 4. VPN tunnel repos are adjacent, not identical

- Separate repo https://github.com/aliiitavazoeiii-afk/frp-tunnel manages the network tunnels on Iran/foreign servers. It is NOT the Hesab finance/control repo, and changing foreign endpoints does not automatically update the X-UI management credentials.
- Previous conversations included Maya3 Trust/Mieru (sometimes triple-carrier Naive), plus a separate Maya4 Naive-lite deployment and replacement manager; these are distinct possible installed stacks. **Always detect the actual installed services and commands before advising a replacement.** The generic triple-carrier lane3 menu is not necessarily installed on Maya4 Naive-lite.
- User priority: preserve X-UI identity, UUID, client names and configuration after Iran/foreign server replacement, and avoid any customer-side config changes. Current foreign/SSH target, chosen tunnel branch and successful health are NOT proven here; query the host before commands.

## 5. Critical production safety rules

1. NEVER run root install.sh, docker compose down -v, docker volume rm, rm -rf /opt/vpn-control-center, git reset --hard on server, or destructive DB migrations without backup/reconciliation.
2. Before anything financial or SMS-queue-mutating: inspect actual DB schema, open Ayria checkouts, status, per-account payments and provider verification, and make a validated backup. Do not delete/replay confirmed payment or sent evidence.
3. Only touch the component the user requested (Maya Control Room vs main dashboard; customer-portal notice vs finance; Android app vs site). Separate Hesab VPN from all Darma projects.
4. Do not print or paste private panel URLs with secret path, passwords, API tokens, SSH private keys, device pairing tokens, .env, customer phone numbers, subscription exports or X-UI UUIDs.
5. For manual X-UI toggles: allow only exactly matched approved clients, check current state, perform single-client state transition, read back, record audit; on uncertainty retry only with explicit reconciliation, not blind repeat.
6. For automatic re-enable: require journal-owned manual cutoff + payment after cutoff + fully settled current account + valid expiry + approved X-UI mapping; guard duplicates, instrument worker health; **never schedule blanket waiting-user deactivation without new explicit instruction and separate safeguards**.
7. On rebuild: snapshot/bkp X-UI including complete inbound/settings before server is erased, but do not publish backup to repository; repair secure API/SSH link, compare active/unmatched counts, verify legacy sync independently.
8. All installers must be narrow, backup-first, fail-closed, with runtime validation and rollback. Keep existing production-only assets and shared Caddy config.
9. Always distinguish code present, CI passing, installed file, live worker/daemon running, confirmed production result and operator-reported result.

## 6. Useful operational commands (read-only unless noted)

~~~bash
cd /opt/vpn-control-center
docker compose -f docker-compose.yml -f docker-compose.sms.yml ps
sudo systemctl status hesab-maya-live.service --no-pager
sudo python3 /opt/vpn-control-center/scripts/maya_multi_panel_sync.py check maya1
sudo python3 /opt/vpn-control-center/scripts/maya_multi_panel_sync.py check maya-s3
sudo python3 /opt/vpn-control-center/scripts/maya_multi_panel_sync.py check maya4
sudo bash /opt/vpn-control-center/scripts/diagnose_maya1_after_rebuild_v1.sh
sudo bash /opt/vpn-control-center/scripts/diagnose_waiting_auto_restore_v1.sh 242
sudo bash /opt/vpn-control-center/scripts/diagnose_waiting_worker_runtime_v1.sh
~~~

NOTE: Recent scripts exist first in the GitHub checkout, not necessarily under /opt/vpn-control-center/scripts. Run from the source checkout (then scripts/...) when needed; do not assume files are installed to both locations. Above paths must be checked for actual existence.

## 7. Open risks / pending work

- Maya1 post-rebuild final counts and whether its *legacy SSH forced-command snapshot, daily usage and control gateway* were repaired after dynamic link success: **NOT VERIFIED**. A dynamic check alone does not validate cron.
- Full end-to-end test of **new manual disable -> later actual payment -> automatically enable the same disabled X-UI client without operator help** remains unconfirmed in shared logs. V3 startup and reconciliation of old rows were verified.
- Any current SMS/WhatsApp Android app installed version and manual-send outcome needs live operator confirmation. Do not infer from GitHub APK/build workflow alone.
- First-of-month billing actual live balances vs portal notice: must be verified from DB if user wants financial changes.
- Maya3/Maya4 count, live mapping, and tunnel availability may have changed since prior observations. Never hardcode historical totals in logic.
- Recovery design for foreign tunnel changes and X-UI reimports requires separate host inspection before executing traffic changes.
- The historical /opt/vpn-control-center live source differs from repository source in places; inspect current source markers and Compose mounts before any installer.

## 8. Important reference commits

- Initial commit: 2026-08-23, first deployable bundle (8ba7489 and neighboring commits).
- Original old handoff: 73a4a90 (2026-10-11).
- Canonical billing: 11dc9e2 and ef30c4e (2026-10-12).
- Maya1 SSH mapping/control: 2197a2c, 00ab5ec, 9f2b5a1 (2026-10-13).
- Three-Maya live API: f7b5e9f, 3c9e13a, 1eb1a67, 89d4c11 (2026-10-20).
- Waiting cutoff + paid restoration: a5a099b, a87e090, f2897e1, aacee59, 1bcb574 and 0403983 (2026-10-23).
- Portal Aban -> Azar notice: e7039ba, cd8b252 and 09a9f62 (2026-10-24).
- Maya1 after-rebuild secure SSH diagnose/bootstrap: a5ce471, 3532562, 43813ca (2026-10-26).

**Continue with docs/00_NEW_CHAT_READ_FIRST.md; this historical file does not by itself authorize installation or production writes.**


## 2026-10-26 — Customer services landing V1 (code committed, NOT deployed)

- New customer_portal/services_home_v1.py creates a monochrome subscriber landing page before the existing financial V2 dashboard.
- Existing original homepage remains reachable at /?view=payments; current payment POST routes, Ayria verification/ledger, database and account-deactivation endpoints were not intentionally changed.
- Shows live PostgreSQL-derived subscription count, earliest expiry and total existing debt; accounts with different expiries should open the existing detailed payment page for individual values.
- Cloudflare Speedtest browser integration is a candidate UI wired through a version-pinned ESM external import; requires actual device/browser, network and build/runtime testing before deployment. Results are only copied locally for manual support; NO server-side result submission or storage.
- Cloudflare Radar card currently opens a public Radar page, NOT authenticated Radar API integration, Iranian ISP live incident classifier or locally cached live data.
- Server-health card deliberately shows unknown/pending; no invented uptime or green state. Per-account Maya identity and verified tunnel-level health monitoring still to be designed.
- Support contact is deliberately unconfigured and not advertised as working; valid support details/workflow must be supplied and then connected.
- Payment history is NOT yet a dedicated verified ledger view: the button goes to existing payment detail page pending a read-only payment history implementation. It must not imply historical rows are displayed until implemented.
- Commits: edac3c406f7c9512b68f435b7e6a16c20f7c217e (landing overlay), 959785fcd884017c071779cf13ceac5cee1f483c (Dockerfile wiring).
- Status: SOURCE ONLY, no production deploy and no runtime/browser/CI success claims. Before deploy: validate Dockerfile build, overlay FastAPI route operation, browser UI (including Safari), speedtest CORS/import/results and redirect links; backup and only recreate customer-portal with rollback.


## 2026-10-26 evening — Customer services dashboard V2 (source and installer committed, production NOT YET verified)

- UI overhaul by owner request: keep actual white/black visual palette and original Persian Vazirmatn font; large subscription card (earliest current expiry, summed current debt, button to untouched existing /?view=payments financial page), separate large server-health card, colorful illustrated 3D-like SVG speedtest/Radar cards, full-width support card with a headset operator illustration and exactly TWO contact actions (WhatsApp message, telephone call).
- Customer services source: customer_portal/services_home_v2.py, services_ui_v2.html, services_ui_v2.css, services_ui_v2.js. No new database tables, no X-UI toggles, no changes to billing/finance routes; all additions are limited to the customer-portal service.
- New authenticated read-only GET /payments/history displays latest 100 recorded payments by joining payments to the signed-in phone's subscriptions. It does not show an unverified checkout as paid, mutate payments or expose other phone accounts. Only a valid existing customer session permits the view.
- Cloudflare speed test uses browser-side @cloudflare/speedtest version 1.15.0 with officially documented getDownloadBandwidth / getUploadBandwidth / getUnloadedLatency / getUnloadedJitter methods. Short, explicit measurement profile avoids massive default transfers. Results remain in browser and can be copied for manual WhatsApp support. Cloudflare may collect aggregate test data, and client/CORS/CDN availability in Iran MUST be tested on a real device after deployment; user consent is explicit (click).
- Iran connectivity card opens official https://radar.cloudflare.com/outages/ir for live public observations. Internal Radar API fusion and ISP-specific data are NOT implemented. The Maya tunnel health card intentionally displays unknown/unconfigured, never simulated healthy or incident status; owner will provide the future monitoring criteria. No new scheduled disable process.
- Support URLs come ONLY from optional server-side environment variables HESAB_SUPPORT_WHATSAPP (country-code digits) and HESAB_SUPPORT_PHONE (digits, optional '+'). Invalid/missing values render non-clickable 'soon' buttons to avoid publishing invented phone numbers. Two options, no ticket/chat.
- Compose passes only those optional variables into customer-portal. Dockerfile runs the v2 services patch AFTER current v2/billing overlays; original v1 overlay may still be present in repository. Installer scripts/install_customer_services_v2.sh backs up existing portal Dockerfile, Compose override, targeted new files, captures prior image ID, validates build, recreates ONLY customer-portal, and attempts rollback on any error. This is not an invitation to run the destructive root install.sh.
- The source history for V2 spans 0a2ed976, 2420aecc, f3c11475, 74872459, 4159a0e4, 148aed7a, 45c692b6, 53610a91, cbda5557, b239594c, plus later fixes.
- CI workflow .github/workflows/test-customer-services-v2.yml checks Python syntax, JS syntax, Bash parsing, Jinja RTL render, no imaginary support links and customer portal Docker image build. Creating CI is not evidence of passing CI; check GitHub status and user's actual portal runtime after install.
- **Runtime status at authoring: not deployed and not tested on live customer device**. Owner must run the server command and report install/healthcheck output and signed-in visual/payment/radar/speedtest checks. Never present backend/link placeholders as functioning live monitoring.

### Safe release notes

Production directory is /opt/vpn-control-center. Obtain a fresh checkout of the active manual-sms-batch-operator-open branch in a separate temporary/root directory; do not overwrite the live checkout with git reset. Run the dedicated scripts/install_customer_services_v2.sh with checked-out source path. Rollback with the same script --rollback /root/hesab-services-v2-backup-TIMESTAMP. Never touch .env, customer_portal/logo.png, financial DB/volumes or shared Caddy. The install action changes only the portal container's runtime and targeted portal source/build definitions. A test plan should include signed-out login, signed-in home, multiple accounts, a read-only history page, original checkout /?view=payments, receipt return and Safari gating. Any discrepancy requires rollback and inspection before further changes.


## 2026-10-26 late evening — Customer services V2 first deployment failed and rolled back; V3 installer prepared

- Owner ran previous V2 installer from GitHub commit 617c5457 using an interactive shell that had `set -e`; SSH session unexpectedly ended on failed command. The exact failed command / build output was not captured. **Do not attribute root cause definitively to any specific build step.**
- Read-only diagnostics supplied by owner: customer-portal healthy /health HTTP 200; backup /root/hesab-services-v2-backup-20261026T171344Z; live Dockerfile and docker-compose.sms.yml exactly match the saved backup; no services_home_v1.py nor services_home_v2.py marker in live Dockerfile; existing Dockerfile contains billing-cycle COPY and server.py append, live Compose customer-portal includes a command override. Current application startup log was clean. No evidence of live new-dashboard activation.
- To avoid depending on GitHub's v1 overlay or replacing live Dockerfile/Compose, added scripts/install_customer_services_v3.sh. It copies only services_home_v2.py plus its CSS/JS/HTML, appends an isolated build layer to **the live Dockerfile**, preserves existing command and Compose untouched, backs up all target files and previous image ID, checks syntax, builds and recreates **customer-portal ONLY**, checks /health and both assets, and attempts portal-only rollback on any error.
- A new deployment must run in a dedicated Bash subprocess rather than setting `set -e` on the operator's interactive SSH. Log all stdout and stderr to a root-only install log. Existing user/password/financial data, Android app, X-UI broker, systemd services and Caddy must remain unchanged.
- V3 compatibility script is not production-verified until owner posts SUCCESS and logs. After deploy check signed-in landing, exact historical payments, original Ayria checkout, login, mobile browser Cloudflare speed test, and new support buttons. Support contact variables are not in live Compose yet; missing buttons remain safely disabled. Server status is deliberately unmonitored/unknown.

## 2026-10-26 evening — V3 installed but UI shadowed by login activity; V4 safe route repair

- Owner executed scoped V3 installer: Docker customer-portal image built and re-created, PORTAL_ASSETS_OK and SUCCESS with backup `/root/hesab-services-v3-backup-20261026T173332Z`. However the logged-in customer page looked unchanged.
- Owner's **actual container introspection** showed `V2_LOADED=True`, `V2_LOAD_COUNT=2`, payment history and new JavaScript route present, but both active GET / endpoint and its FastAPI dependency call were `_pla_home_with_activity`, not `_sv2_landing`.
- Root cause confirmed from current GitHub `customer_portal/login_activity.py`: the production Compose command mounts and appends this module at container startup **after** image-baked `services_home_v2.py`. Its `_pla_previous_home=v2_home` always calls the previous financial dashboard and shadows the new landing. GitHub Docker build/health success could not detect this runtime override. DO NOT disable/remove the login activity report or alter the financial route.
- Source for precise repair: `customer_portal/services_after_login_activity_v4.py`. This is an append-only late shim to the **existing mounted** login_activity.py. It checks the active unique GET / route is still `_pla_home_with_activity`, then changes only the wrapper's upstream reference to `_sv2_landing`. Thus /login logging, once-per-day visits, and existing audit table remain; the V2 page continues to fall back to original `v2_home` for `/?view=payments`, checkout cookie, pending/failed payment notices and welcome modal.
- Installer `scripts/install_customer_services_route_v4.sh`: verifies live bind mount /srv/login_activity.py, existing V2 code, portal running and expected host source; backs up login_activity.py under /root/hesab-services-v4-*; patches only this file, checks syntax, recreates only customer-portal with `--no-build --no-deps`, verifies health and that `server._pla_previous_home is server._sv2_landing` while `server.app` still routes through the logging wrapper. On failure it restores the file and recreates portal. No Git reset, DB writes, Docker image rebuild or shared Caddy changes.
- Regression test: `scripts/test_customer_services_route_v4.py`, covered by customer services workflow. V4 is **committed but not yet operator-deployed**; do not claim success until actual installer output and authenticated browser page inspection. V3 customer portal is currently healthy.
- Note: existing `/?welcome=1` intentionally shows the original modal/payment view. Once notice is acknowledged, navigating to `/` without the welcome query should show the new dashboard. This preserves the previously authorized Azar notice.
- Security caveat: the historical /login uses phone-only authentication (see login_activity.py header), not verified SIM ownership. The V2 read-only payment history could expose private payment details to anyone who can log in using a known phone; review authentication and authorization before treating payment history as privacy-hardened.

## 2026-10-26 — V4 installer false-negative preflight (not deployed)

- Operator's first V4 installation stopped *before backup or modifications* with `STOP: dashboard V2 missing`. Their preceding in-container introspection had already confirmed `V2_LOADED=True`, `PAYMENT_HISTORY=True` and GET / route owned by `_pla_home_with_activity`.
- Root cause: original V4 install preflight grepped for `HESAB_CUSTOMER_SERVICES_V2` in `/srv/server.py`; this literal marker belongs to `services_home_v2.py` source, whereas server.py only includes a dynamic `exec(compile(open(...)))` reference. The grep was invalid and failed closed; no production changes from V4 attempt.
- Fixed `scripts/install_customer_services_route_v4.sh` to import the *active container* `server` module and assert exactly one GET / route, `_sv2_landing` loaded, `_pla_home_with_activity` active, `_pla_previous_home is v2_home`, correct FastAPI dependency, and payment history route present before any file modification. Existing backup/no-build/app-only rollback retained.
- Do not claim successful V4 deployment until new installer executes and checks pass. Preserve login audit and payment paths. The owner reported live customer UI still old at this checkpoint.


## 2026-10-26 — Exact reference screenshot V5 archive ready (NOT YET DEPLOYED)
- Owner asked to make the customer portal look like the last supplied screenshot, especially authentic 3D illustration cards and customer support agent's head extending beyond its panel.
- Unlike previous hand-drawn SVG approximation, prepared a self-contained ZIP containing four small cropped JPEG illustrations directly extracted from the user-provided screenshot, responsive HTML, exact visual CSS, limited read-only asset serving module, late login-activity routing shim and scoped installer.
- GitHub release source: `releases/hesab_exact_visual_v5.zip.b64`, decode with `base64 -d`; ZIP SHA-256 `4f88a25a32777f19d6adecbcff5d678671c7993735e87579f7714852b3c04841`.
- Full design and safe installation handoff: `docs/HESAB_SERVICES_EXACT_VISUAL_V5.md`. Local ZIP integrity/Python/Bash/Jinja smoke tests passed. Production deployment and actual browser pixel/behavior checks not yet confirmed.
- V5 reuses existing payment, session and Cloudflare routines, retains daily login activity wrapper, modifies no payment table and only rebuilds/recreates customer-portal. Server health LEDs are decorative pending actual monitoring; contact actions remain disabled until production contact numbers are supplied. Never claim live uptime from this illustration.


## 2026-10-26 — HQ V6 visual artwork quality correction, NOT YET deployed
- Customer reported that the V5 layout was satisfactory, but the four illustrated icons/artworks appeared dramatically blurry on the actual site.
- Root cause in previously delivered V5 zip: `services_visual_v5/{server,speed,globe,support}.jpg` were aggressively compressed JPEGs of ~4.5–7.7 KB at ~235–486 px widths. They are too small for hi-DPI desktop/mobile rendering.
- Prepared `hesab_hq_v6_release.zip` as a ChatGPT conversation artifact (NOT in GitHub binary files). It contains four transparent high-quality WebP pictures of about 1254 px (support 1448 px) and 183–303 KB each, plus a scoped installer `install_hesab_hq_v6.sh`.
- Installer preflights live V5 runtime and mounted login-audit chain, and existing Dockerfile V5 layer. It backs up existing `services_visual_v5.html`, `services_visual_v5.py`, `services_visual_v5.css` and any prior -hq.webp, copies images, replaces four image URLs with versioned `-hq.webp?v=hq6`, adds WebP entries to the V5 image asset allowlist and correct MIME type, and removes CSS radial masks on those images to preserve detailed edges. No changes to login, payment, DB, V2 routes, X-UI, Caddy or Compose. Rebuild/recreate ONLY customer-portal; smoke checks verify HQ endpoint bytes, image/webp MIME, the active V5 template, and `_pla_previous_home is _sv2_landing`. On failure, attempts source rollback and portal-only rebuild.
- Zip exact SHA256: `1f164232019b5dd9df5bd1fe2a9f778ddd363f84b8610c4936080796cde93ed1`. Source ZIP exists as a conversation artifact `hesab_hq_v6_release.zip`, requiring operator upload to root on management server; a GitHub commit alone does not make these image binaries accessible to the server.
- Offline checks: ZIP integrity, bash -n, WebP transparency + dimensions, V5 template replacement, Python compile and Jinja render passed. **No claim of live V6 deployment.** Await operator's zip upload and successful installer output. Existing green server illustration remains *decorative*, since no verified tunnel monitoring is connected.


## 2026-10-26 night — Customer UI V7 patch archive ready (NOT deployed)

- Owner requested minimal text on the exact V5 + HQ V6 screenshot design. Prepared conversation artifact `hesab_customer_v7_release.zip`, SHA256 `d73d47056682aa65ab13705e3814d39c38c9730f0a66ec58b3f6cd2659dd14db`; it has V7 overlay module/CSS/JS, a scoped backup/rollback installer, safe ID-only server mapping builder, and Persian README.
- Main: larger header brand with no subtitle or greeting, larger subscription heading no description, no payment-history button, no explanatory Speedtest/Radar subtitles; persistent HQ 3D artwork and site design preserved.
- Original payment view at `/?view=payments`: 3 cards (number, debt, transactions). Remove only the **visual** projected expiry panel and arrow; label existing `a.expiry_jalali` as `تاریخ سررسید`. Financial billing and Ayria amounts, CSRF, payment POSTs, receipts and anchor policy untouched.
- Transaction history shown **inside** existing payment view, read-only from canonical `payments` ledger scoped by signed-in phone. Ayria multi-account allocations sharing one payment reference become one grouped transaction with summed recorded amounts. Displays account/group, Jalali date, Tehran time, amount; no unverified checkout results shown as paid.
- Server card: correctly styled heading, no old service-connection subtitle, shows masked signed-in phone and mapped server names where verified by private read-only admin snapshots; minimal `sid: label` export only, no credentials or raw X-UI rosters in customer portal. Unknown mappings remain visibly unknown. Static server illustration LEDs remain decorative; live health checks not implemented.
- /speed-test is a dedicated browser test page. Animated needle is a **non-measurement progress animation**; numeric speeds come only from the pre-existing Cloudflare browser speedtest module. Copy report / WhatsApp share available only after test. Internet page `/internet-status` uses optional server-side `CLOUDFLARE_RADAR_API_TOKEN` (Cloudflare Account > Radar > Read); secure 15-minute server cache, displays genuine 7d NetFlows index and officially reported Iran outages. NO invented city percentages/speed losses; when token/data unavailable, reports unavailability and links to official Radar.
- Support: owner explicitly supplied 09197118017; `tel:09197118017` opens phone OS prompt; `https://wa.me/989197118017` is best-effort contact (not verified WhatsApp membership).
- Scoped install `install_hesab_customer_v7.sh RELEASE_DIR` protects all preexisting V5/V6 images, loads V7 AFTER V5 but BEFORE runtime-mounted login-activity wrapper; backs up Dockerfile, portal-only compose override, new source; builds/recreates only customer-portal; asserts live `_pla_previous_home is _sv2_landing_v7`, ledger and customer routes remain, health/assets; failure attempts portal-only rollback. No DB schema/write or admin app change. Manual rollback script included.
- Offline validated Python module parse, JS syntax, Bash syntax, V5 home transformation, FastAPI isolated runtime test using mocked read-only ledger and Jinja, ZIP integrity; mapping generator additionally checks Maya1 legacy approval fingerprint; not deployed on production.
- IMPORTANT: Existing portal auth still trusts phone entry without SIM ownership verification; inline financial history remains exposed to anyone who can enter a known account phone. Plan OTP security separately. This release does not claim to fix that.


## 2026-10-26 — V7 release now stored in GitHub; no manual ZIP upload needed

- The V7 release ZIP was committed as ASCII base64 at `releases/hesab_customer_v7_release.zip.b64` on branch `manual-sms-batch-operator-open`.
- GitHub publication commit: `56f257fac2ec047f36d748dc6f2a58790e96703f`. Connector read-back of the GitHub file **exactly matched** the user-visible V7 ZIP's base64, 24,532 encoded characters. Original ZIP SHA256 remains `d73d47056682aa65ab13705e3814d39c38c9730f0a66ec58b3f6cd2659dd14db`.
- Install from management server: clone the branch, verify a pinned commit, `base64 -d releases/hesab_customer_v7_release.zip.b64 > release.zip`, verify `sha256sum`, extract to a temporary directory with Python's zipfile, run `bash install_hesab_customer_v7.sh EXTRACTED_DIR`. The production installer handles customer-portal-only backups and app rebuild/recreate.
- User does not need to download or use WinSCP. This is a published GitHub artifact, **not a claim it has been deployed or checked on the production server**. Previous V5/V6 live behavior was acknowledged by the user.


## 2026-10-28 — Customer portal V8 first-login, direct Radar, quick jet test, sanitized live Maya metrics (prepared, NOT deployed)

- Owner confirmed V7 on production with `V7_LAYOUT_PAYMENT_HISTORY_AND_LOGIN_AUDIT_OK`, `V7_ASSET_SMOKE_OK`, `SUCCESS: HESAB CUSTOMER EXPERIENCE V7 INSTALLED`, and backup `/root/hesab-customer-v7-backup-20261026T195649Z`.
- Reported first successful incognito login still showed legacy payment dashboard until refresh. Source-level root cause: `v2_login` redirects to `/?welcome=1`; `_sv2_landing_v7` explicitly treats `welcome` as a financial-page override. V8 wraps the original login in memory (preserving cookie and login activity report) to redirect to plain `/`; V8 home also handles a legacy welcome URL, but preserves original payments for `?view=payments`, payment errors, disabled status, and checkout-cookie return.
- V8 redirects home Radar card directly to the official Cloudflare Radar Iran 24-hour traffic page `https://radar.cloudflare.com/traffic/ir?dateRange=1d` in a new tab; **no API token or intermediary explanation page**. Existing `/internet-status` may remain for bookmarks.
- Dedicated speed page uses a CSS-animated jet with running engine/smoke and elapsed `mm:ss` timer, no analogue needle or footer. Separate V8 JS runs a smaller explicit measurement set with version-pinned `@cloudflare/speedtest@1.15.0`, reports real measured download/upload/latency/jitter, supports report copy / WhatsApp. Lower request counts can reduce duration but cannot guarantee time across networks; animation does not represent measured network speed.
- Maya customer mapping/aggregate: status exporter `hesab_status_export_v8.py` uses read-only unix-socket `op=snapshot` from existing management Control Room for maya1, maya-s3, maya4, approved admin mapping / legacy Maya1 fingerprint, existing read-only synchronized client IDs, and read-only uniqueness-checked finance name matching; writes ONLY sanitized ID-to-server mapping and per-server aggregates, never credentials, X-UI client emails, IPs, auth keys, phones, database contents. Portal imports this JSON from a **read-only directory mount**, refreshing via isolated 2-minute systemd timer; mapping fallback uses last previously approved V7 label on unavailable server. Per-server stats distinguish configured enabled users from last-online activity within 5 minutes; response-ms is management->panel API response, **NOT user VPN ping**; quality/health is not claimed to be excellent without actual VPN-path probes. Unavailable/stale values show unknown.
- Prepared source release as ASCII base64 GitHub file `releases/hesab_customer_v8_release.zip.b64` (ZIP SHA256 `1cca643f513eab2f462df9bebfb617bb4abe28042a018729052e105486d0d9a1`), containing services_custom_v8.py/css/js, host exporter, scoped installer and README. Single secure installer copies only new files, appends its own V8 Dockerfile layer after production V7, adds sanitized data volume to **customer-portal only**, rebuilds/recreates only this service, retains V7 login-audit wrapper, verifies live routes and assets, creates V8-only systemd timer and backs up all files. On failure attempts rollback. NO automatic X-UI toggles, billing or database writes; preserve all other services and private admin credentials.
- Local verification: V7 source template transformation, first-login 303 redirect/cookie wrapper, dedicated speed handler replacement, Radar direct link, server health template, Python compile, JS `node --check`, installer `bash -n`, ZIP integrity and checksum passed. **Not tested on production**; require operator-run install output and browser tests before declaring live V8 success.
- Existing customer authentication is still phone-number-only (no OTP), an inherited privacy limitation. Don't claim it provides SIM ownership assurance.
