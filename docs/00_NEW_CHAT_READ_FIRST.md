# Hesab VPN — READ THIS FIRST in every new chat
**Updated 2026-10-26 | CURRENT BRANCH: manual-sms-batch-operator-open**

## A. Mandatory first-read sequence

You are inheriting an established real production system. Do not suggest reinstalling, starting a new app, or resetting any database. Before proposing a code edit or deployment:

1. Read this entire file.
2. Read docs/PROJECT_HISTORY_2026-10-26.md (complete chronology and constraints).
3. Read root PROJECT_HANDOFF.md (historical 2026-10-11 snapshot only; **sms-app is not today's branch**).
4. Read root README.md ONLY for initial product semantics and its explicit dangerous-install warning. NEVER execute root install.sh.
5. Inspect current branch Git commits and relevant latest source/actual runtime overlays, including root Dockerfile, docker-compose.yml, docker-compose.sms.yml. Inspect the last-matching routes/patches before edits.
6. For production issues, request/redact targeted **read-only** diagnostic output if necessary. Do not infer that a Git commit has deployed or that a CI pass verifies the live system.

Source of truth for code: https://github.com/aliiitavazoeiii-afk/vpn-managrer/tree/manual-sms-batch-operator-open

Historical docs: https://github.com/aliiitavazoeiii-afk/vpn-managrer/blob/manual-sms-batch-operator-open/docs/PROJECT_HISTORY_2026-10-26.md

The latest user message in the originating chat on 2026-10-26 reported the Maya1 post-rebuild reconnection **"ok shod"** (working). This is operator-reported success; no final complete count/cron verification was supplied.

## B. Product and infrastructure

- Hesab VPN is a Persian **VPN subscription finance, billing, support and three-X-UI-server operator console**, not the VPN tunneling code itself.
- Administration: https://hesab.filmjadiid.ir ; customer portal: https://usersmanager.ir and older https://moshtarakin.filmjadiid.ir (verify current aliases before Caddy changes).
- Management host last reported 5.10.248.50; production /opt/vpn-control-center. Last temporary Git checkout /tmp/tmp.gf0oloSYHt/repo is not guaranteed permanent.
- Server stack: Python/FastAPI main app; PostgreSQL persistent DB; SMS gateway; separate FastAPI customer portal; Docker Compose; shared Caddy. Main Compose services: app, db, sms-gateway, customer-portal.
- Canonical Compose invocation:
  ~~~bash
  docker compose -f docker-compose.yml -f docker-compose.sms.yml ps
  ~~~
- Root Dockerfile assembles packed/main.* and ordered Python patches, so the last-loaded override can be authoritative. docker-compose.sms.yml appends runtime SMS and billing overlays. customer_portal/Dockerfile copies/executes its own billing and v2 modules.
- Persistent finance data: subscriptions, payments, audit_events, billing_anchor, ayria_payment_requests / allocations. The temporary X-UI server itself is not the authoritative Hesab financial database.
- Credentials and untracked production artifacts: .env, customer_portal/logo.png, Maya mapping approvals, SSH keys/known_hosts, root X-UI panel config, Android tokens; **NEVER publish these in GitHub or a chat**.

## C. Current important behavior and what not to change

### Finances and customer portal

- Original initial seed: 307 subscriptions with exact imported names. Actual current totals are dynamic; never quote initial counts as current.
- Multiple accounts per phone are separate subscription IDs, not merged. Partial/full/group payments and advance payments must be correctly allocated per account.
- Archive/"delete" workflow is audit-based followup_cut and keeps historical payments. Don't bring back old physical account deletion.
- Ayria provider callback/polling must confirm the transaction, apply it ONCE, maintain paid_at, update expiry/owing amount and avoid retries that duplicate credit or charge. A cancelled reference must be reconciled before creating a new checkout.
- The billing policy aligns subscription dues to first of Jalali months, with fair pro-rating, and is implemented in customer_portal/billing_policy.py and admin/customer overlays. Use existing tests; verify live state before editing.
- On 2026-10-24 only the **welcome NOTICE TEXT** changed from "یکم آبان" to "یکم آذر": scripts/install_portal_notice_azar_v1.sh; customer_portal/dashboard_v2.html. This DOES NOT automatically extend all real expiries by a month. Never infer real balances from UI copy.
- Customer portal template is loaded into memory; safe notice deployment rebuilds/recreates **only customer-portal**, not billing app/database.

### SMS/WhatsApp

- SMS workflows evolved Android native queues -> Google Messages human opening -> optional WhatsApp manual send. The crucial invariant is **a prepared/opened message is not proof that a carrier actually sent it**; the operator must send manually and history must never be falsely marked delivered.
- Keep SMS copy consistent across debt and /followups waiting screens; operator can queue several drafts and open individually.
- No automatic SMS retries/resends without dedup, verified status, backup and explicit instruction. Prior Android issues included stuck queues and ack failures. Do not run historical reset scripts blindly.
- WhatsApp manual APK/app changes are separate from Hesab website changes; verify installed app and distribution separately before claiming availability.

### Maya1 / Maya3 / Maya4 Control Room

- Server IDs in the code are EXACT strings: maya1, maya-s3, maya4.
- Live management: scripts/maya_multi_panel_sync.py + scripts/maya_live_bridge.py and systemd hesab-maya-live.service. Broker socket host path /opt/vpn-control-center/maya_extra_sync/live.sock; in app /srv/maya-live/live.sock.
- Panel config on management host: /root/.config/hesab-maya-extra.json (0600), which holds sensitive information. DO NOT print or paste it verbatim, even during debugging.
- HTTPS only with correct certificate verification; plain HTTP X-UI requires loopback SSH port-forward and strict SSH host-key verification. SSH pairing script scripts/bootstrap_maya_ssh_tunnel.sh supports maya1, maya-s3, maya4.
- User matching priority: explicit operator approvals, pre-existing approved Maya1 matches, unique exact normalized names. Exclusions, removed/archived, duplicate/conflicting matches and missing identity are NOT safe to toggle. Never auto-guess identities.
- User requested **Control Room-only** modifications for Maya server features, preserving main dashboard layout. Live Maya controls and matching UI code reside in patches/maya_live_dashboard.py, maya_manual_links_v1.py, maya_dynamic_links_v1/v2.py, control_room_v2.py.
- X-UI enable/disable is an exact single-client guarded action: verify server + email + SID + expected current status, perform CAS-like toggle, verify server response/readback. Never edit X-UI SQLite or all inbounds when a user requests a single account action.
- Maya1 also has **OLDER** fixed-inventory read-only SSH snapshot and control gateway: scripts/maya1_readonly_sync.py, scripts/maya1_control_gateway.py, /opt/vpn-control-center/maya1_sync. Those enforce a historical 145-client mapping and use cron every five minutes. The newer live broker is separate; fixing one does not necessarily fix the other.

### Manual waiting-page cutoffs and auto-restoration (critical)

- There is NO deployed blanket timer that disables every waiting user. Manual operator click is required for cutoff. A previous request specifying a future time must not be treated as current authority for a scheduler.
- The DB journal waiting_vpn_controls records manual cutoff server/client, state and payment watermark.
- Auto-restore only for that journal-owned exact user, after **new positive payment since cutoff**, fully paid/zero debt, valid expiry, safe identity match, confirmatory X-UI readback; uncertain results retry with bounded backoff. Unknown/manual non-journal disables are not candidates.
- V1 patches/waiting_vpn_control_v1.py; V2 patches/waiting_vpn_restore_resilience_v2.py and installer; V3 patches/waiting_vpn_worker_lifespan_v3.py and installer.
- FastAPI custom lifespan caused the old on_startup worker never to start. V3 wraps the actual lifespan, retains old initialization/teardown, and exposes a heartbeat at /tmp/hesab-waiting-worker-v3.json INSIDE the app container. Inspect this to confirm live worker passes, not the old AUTO_WORKER_REGISTERED value.
- On 2026-10-23, operator output showed actual worker pass and zero errors; previously stalled SID 382 and later SID 242 journals were restored. SID 242 had already been manually enabled, so a fresh real-payment/no-manual-assist X-UI enable still needs explicit end-to-end validation.

## D. Most recent issue: Maya1 rebuilt, dashboard lost connection, then operator reported fixed

- Maya1 newly rebuilt Iran server IPv4: 94.184.4.38, management host IPv4: 5.10.248.50; user verified they are distinct.
- Before rebuild user reported read-only check: maya1 total=144 linked=116 unmatched=28 snapshot_saved=False. These are name-based checker results; Control Room approved mapping is separate. Never assume 141 historical mappings still match these exact counts.
- Broken state diagnostic: broker + direct API SSL WRONG_VERSION_NUMBER; the old saved Maya1 URL was HTTPS to port 2095 but newly installed X-UI panel used HTTP with a different custom base path.
- Operator successfully ran scripts/bootstrap_maya_ssh_tunnel.sh maya1 94.184.4.38 2095 and got SUCCESS: RESTRICTED SSH TUNNEL KEY VERIFIED. Actual Maya1 console SSH ED25519 fingerprint matched verified remote key. The user later said "ok shod" after secure reconnection steps.
- This does NOT prove legacy fixed-roster exporter/cron or control.sock was reinstalled on Maya1. It does not prove exact 144 linked/unmatched numbers after rebuild. Probe both paths independently before any further changes. Preserve approved_links.json, maya1_sync/mapping.json and historical usage data.
- Read-only helper: scripts/diagnose_maya1_after_rebuild_v1.sh; if it is only in current Git checkout, run it from that checkout, not assume /opt/vpn-control-center/scripts includes it.

## E. Known limits and next validation priorities

1. Verify the recent Maya1 reconnection using **current X-UI** read-only checker and live broker, not old HTTPS URL. Confirm new panel config loaded from root protected config. If the user already says working, do not gratuitously reconfigure.
2. If Maya1 shows stale daily usage/legacy Control Room sections, check /etc/cron.d/hesab-maya1-sync, maya1_sync timestamps, remote SSH forced commands and old fixed-roster size checks. Never regenerate approved 145-person mapping blindly.
3. New user payment restoring a disabled X-UI client without manual intervention has not been shown after V3; evaluate with a deliberate, narrowly scoped test and logs, not broad mass toggles.
4. Verify any current billing migration status before changing dues or expiries; welcome text alone is not data evidence.
5. Verify SMS app runtime/manual confirmation separately from API source; no automatic WhatsApp or SMS action by assertion.
6. Changes to VPN tunnels are a **separate frp-tunnel GitHub repository**, not dashboard code. Maya4 can run a dedicated Naive-lite stack rather than the triple Trust/Mieru/Naive lane3 menu; discover actual installed host services first.

## F. Provenance of recent GitHub work

- Branch documentation is based on repository commits through 2026-10-26.
- V2 restore code/installer/tests: a87e0906, f2897e1b, 8f84ef3f.
- V3 live lifespan worker code/installer/tests: aacee592, 1bcb5740, 04039835.
- Maya1 secure rebuild diagnosis/bootstrap/tests: a5ce4710, 3532562f, 43813caa.
- Portal notice Azar: e7039ba6, 8d659245, cd8b2521, 09a9f626.
- Exact current state must be checked with current GitHub branch and runtime, not these pinned hashes alone.

## G. Safe read-only intake for a live issue

~~~bash
cd /opt/vpn-control-center
docker compose -f docker-compose.yml -f docker-compose.sms.yml ps
sudo systemctl is-active hesab-maya-live.service
sudo python3 /opt/vpn-control-center/scripts/maya_multi_panel_sync.py check maya1
sudo python3 /opt/vpn-control-center/scripts/maya_multi_panel_sync.py check maya-s3
sudo python3 /opt/vpn-control-center/scripts/maya_multi_panel_sync.py check maya4
~~~

Only run checks pertinent to the user's request. Avoid outputting the root config, private bundles, usernames/passwords, tokens or phone numbers. The root GitHub checkout branch is a separate directory; prefer explicit safe installer paths with backup and rollback after source verification.

## H. Non-negotiable rules for the continuing assistant

- Speak Persian unless the user switches languages. Give copy/paste commands appropriate to **management host vs Iran host vs foreign host**, label which server must run them.
- Inspect the repo/history first; don't ask user to repeat details already in this handoff. Resolve actual current state read-only rather than guessing.
- **Never run install.sh on production, docker compose down -v, reset volumes, drop DB, replay payments, force-send SMS or toggle unrelated X-UI users.**
- Never make unrequested edits to main dashboard when user asks only for Control Room. Do not mix with Darma.
- Distinguish reviewed code / CI success / operator-run installer / live verified outcome / operator-reported result.
- Make minimal incremental changes on manual-sms-batch-operator-open; back up production files and DB when warranted, validate code and health, restart only necessary service, provide commands and expected output, and retain rollback.
- Document each meaningful future change in this README and docs/PROJECT_HISTORY_2026-10-26.md (or a dated successor). Append what actually happened, including tests and remaining uncertainties.

## I. Copy/paste prompt for a NEW chat

I am continuing the long-running Hesab VPN project (GitHub aliiitavazoeiii-afk/vpn-managrer, branch manual-sms-batch-operator-open). Before doing ANY work read docs/00_NEW_CHAT_READ_FIRST.md, docs/PROJECT_HISTORY_2026-10-26.md, and the historical root PROJECT_HANDOFF.md; then check recent Git commits, Dockerfile/Compose files and effective runtime patch order. The management server is 5.10.248.50 with deployment /opt/vpn-control-center; the admin panel is hesab.filmjadiid.ir, customer portal usersmanager.ir. This is the existing live finance/subscription platform, not a new installation. It manages billing, Ayria payments, followups, manual messaging and live X-UI Control Room for maya1, maya-s3 and maya4. Preserve all PostgreSQL customers/payments, audited manual approvals, X-UI identities, and server-specific data. Never execute root install.sh, down -v, destructive SQL or broad user toggles. V2 paid-only manual-cutoff auto-restoration plus V3 FastAPI lifespan worker were installed and executed, with old cases 382/242 reconciled; a fresh fully unattended payment-to-activation test is still unverified. Maya1 was rebuilt and its HTTPS mismatch fixed via secure SSH forward to HTTP X-UI; operator said fixed, but old cron/snapshot and post-rebuild count are not confirmed. The portal modal says first of Azar, which is a text-only change and not automatic account date migration. Maya network tunnels are in a different frp-tunnel repo. Work only on what I request, review the current branch first, use careful diagnostics and guarded, reversible deployment. Start by telling me briefly which components, latest verified state and known uncertainties you found, then help with my next task without restarting from scratch.


## J. Customer services UI V2 (added 2026-10-26 evening, NOT YET CONFIRMED LIVE)

- Owner requested existing white/black Vazirmatn theme and colorful illustrated large panels: subscription summary, current server state, Cloudflare browser speed test, official Iran Radar link, and large support card containing ONLY WhatsApp and phone. Code: customer_portal/services_home_v2.py, services_ui_v2.html/css/js and customer_portal/Dockerfile; compose optional HESAB_SUPPORT_WHATSAPP/HESAB_SUPPORT_PHONE.
- The original financial dashboard and existing Ayria payment route remain at /?view=payments. New payment history view /payments/history is authenticated and read-only, based on stored payments by matching phone. Multi-account home shows earliest expiry with aggregate existing debt.
- Maya tunnel health is UNKNOWN until separately implemented with owner-supplied rules; Radar card opens the official external page, not an integrated authenticated API. Cloudflare Speedtest runs in browser and needs in-country browser/CDN/CORS checks; report can only be copied for manual sending, not automatically submitted to admin.
- Support numbers were not provided: missing configuration produces disabled actions rather than bogus WhatsApp/tel links.
- Scoped installer: scripts/install_customer_services_v2.sh SOURCE_CHECKOUT with rollback option --rollback BACKUP_DIR. Installer only targets customer-portal, backs up source/compose, checks health, does not touch DB, app, X-UI or Caddy. Git source and CI workflow are not proof of production deployment.
- Full context and risks are in docs/PROJECT_HISTORY_2026-10-26.md, section "Customer services dashboard V2".
