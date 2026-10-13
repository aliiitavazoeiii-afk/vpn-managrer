# Hesab VPN — Project Handoff (2026-10-11)

> **Source of truth for code:** `aliiitavazoeiii-afk/vpn-managrer`, branch **`sms-app`** (NOT `main`). The branch was at commit `352421c1e71249ed7a72098c9f510ddb63edf319` when this handoff was written. Future commits may advance the branch.
>
> **Source of truth for live data:** production PostgreSQL on the server. **GitHub is not a database backup and commits do not imply deployment.**

## Important safety warnings

- **NEVER run `install.sh` on the existing production server.** It executes `docker compose down -v`, removes `/opt/vpn-control-center`, and re-seeds the app. The old `README.md` documents that initial-install path, not safe incremental deployment.
- Never run `docker compose down -v`, delete volumes, or `rm -rf /opt/vpn-control-center`.
- Do not expose or commit `.env`, payment gateway credentials, login keys, customer data, seed keys, or DB dumps. Do not `source .env` in chat scripts.
- Back up the database before any migration or bulk financial update. Avoid speculative or destructive SQL.
- Production has server-only `customer_portal/logo.png`, which is a Compose bind mount; it is intentionally absent from GitHub. Don't overwrite/delete it.
- Shared Caddy is associated with another project. Do not replace unrelated Caddy configuration; use the safe combined-config strategy where appropriate.
- The older `AYRIA_INTEGRATION.md` says automatic reconciliation is absent. **This is stale:** `customer_portal/billing_sync.py` now implements provider verification and automatic sync. Read current code, not the stale claim.

## Architecture and deployed paths

- Server: `root@5.10.248.50` (historical known management server); working folder: `/opt/vpn-control-center`.
- Main admin: `https://hesab.filmjadiid.ir`; Compose service `app`.
- Customer self-service: `https://moshtarakin.filmjadiid.ir`, newer alias `https://usersmanager.ir`; Compose service `customer-portal`.
- SMS gateway: Compose service `sms-gateway`, Android gateway app in `android-sms-gateway/`.
- PostgreSQL: Compose service `db`, persistent `pgdata` volume.
- Use both Compose files: `docker-compose.yml` and `docker-compose.sms.yml`.
- `deploy/Caddyfile.hesab.sms` contains portal/admin gateway routes. The server's shared Caddy environment may differ; inspect it before changes.

## Code layout and boot order

- Main admin app source is assembled at Docker build from `packed/main.*` plus a sequential list of `patches/*.py` specified explicitly in the **root `Dockerfile`**. CSS is assembled from `packed/css.*` plus sequential CSS patches. Ordering is important: later route/template overrides win.
- `docker-compose.sms.yml` also appends `patches/sms_admin.py` and `patches/billing_anchor.py` at container startup through read-only bind mounts. Editing these patches on disk requires an `app` recreate; editing files baked into the image requires a rebuild as well.
- Main dashboard: `patches/reference_ui.py` defines active counts and income; `patches/dashboard_focus.py` defines focus layout; `patches/workspace_refresh.py` injects income/active user KPI. Styles in `patches/workspace_refresh.css`; latest refinement commit `352421c1`. **Visual QA and deployment of this last CSS refinement are not confirmed.**
- The active account count equals `len([subscription for subscription in subscriptions if latest followup state != 'cut'])`. "Waiting" accounts remain counted; archived `cut` accounts are excluded. It counts accounts, not distinct phone numbers.
- The administrative "delete user" endpoints are overridden at the end of the image by `patches/user_lifecycle.py`: new deletions archive via latest `followup_cut` events, preserving subscription and payment rows. `/removed` is searchable; `/user-status` shows status-aware global search; prefilled "add again" creates a **new subscription ID** rather than erasing the archive. Confirm latest deployment before relying on this behavior.
- **Before this fix**, `patches/user_manage.py` physically deleted subscriptions and related payment rows. For these historical deletions, only remaining `audit_events.kind='user_delete'` messages may be searchable, and deleted financial details cannot be recreated from them.
- Waiting/debt flows: `patches/followup.py`, `patches/waiting_compact.py`, `patches/waiting_group_pay.py`, `patches/waiting_partial_pay.py`, `patches/waiting_prepay.py`, `patches/billing_anchor.py`, `patches/debt_adjust_bidirectional.py`; CSS row cleanup in `patches/waiting_partial_pay.css` (commit `cb235e2c`). `waiting_prepay.py` overrides `/followups/pay-amount`; `billing_anchor.py` overrides certain full-payment routes. Review overrides/order before changes.
- Customer portal: source `customer_portal/server.py`; `customer_portal/Dockerfile` appends `v2.py` and `billing_sync.py` at image build; includes template and CSS assets. Ayria automatic verified synchronization and cancellation-safe retries reside in `customer_portal/billing_sync.py`; portal green "verified payment" status in `v2.py`, `dashboard_v2.html`, `v2_polish.css`.
- Core DB tables include `subscriptions`, `payments`, `audit_events`, `billing_anchor`, `ayria_payment_requests` and `ayria_payment_allocations`. Always inspect actual schema before changing.

## Known financial context and unresolved production state

1. The business intends **two billing stages**: first register historic/manual customer payments using each customer's original individual due date, then later establish first-of-Jalali-month billing anchored to **1405/08/01** without double charging users for periods they paid.
2. As reported by the owner on 2026-10-11, query results for `billing_anchor` showed **294 pending, 2 scheduled, 1 paid**, with pending transition amount **53,662,127 toman** and scheduled amount **386,666 toman**. These are **reported historical query results**, not proof of live current state.
3. Prior assistant gave an optional SQL/Python script to temporarily pause `pending`/`scheduled` anchors and recalculate original due-date debt without changing expiry dates. **Owner has NOT confirmed running this script.** Inspect `billing_anchor.status`, current data, and existence of any pause snapshot before proceeding. Do not rerun blindly, and do not simply restore old `pending` values after manual payments: recompute anchor amounts from **updated** expiry/payment state.
4. A prior Ayria payment on subscription ID 345 failed to be applied because the `payments.paid_at` NOT NULL field was omitted in SQL INSERT. The `billing_sync.py` fix added `paid_at` and logging; payment status must be checked on production. Avoid asking customers to pay twice.
5. An additional fix handles canceled Ayria references: requery provider, mark canceled requests canceled, create a brand-new checkout/reference for canceled attempts; reconcile confirmed paid references before retrying; prevent uncertain duplicate charge.
6. Latest UI screenshot showed active-account count **317** and monthly total **67,860,000 toman**; these are **screenshot observations**, not independently verified database counts. New dashboard typography/card refinements exist in GitHub, but production visibility is not verified.

## Recommended safe working procedure for a new chat

1. Inspect **current branch `sms-app`**, latest commits, root `Dockerfile`, Compose files, affected `patches`, `customer_portal`, and relevant runtime overrides before proposing changes.
2. Compare production files against current GitHub versions. Production may contain uncommitted work and server-only assets; **do not `git reset --hard` or blindly overwrite the directory**.
3. Make small, reviewable GitHub commits to `sms-app`, not `main`. Use exact changed file deployment and back up originals. Confirm syntax/build before restarting only the affected service.
4. Use `docker compose -f docker-compose.yml -f docker-compose.sms.yml ...` to inspect and deploy. A GitHub commit never deploys by itself.
5. Before public launch: verify one real payment end-to-end (provider confirmation, a single `payments` row, expiry/debt update, audit and follow-up state, customer and admin success UI), canceled-link retry, manual historical payments, archive/re-add flows, and browser desktop/mobile layout.
6. Avoid financial edits until the owner confirms their existing backup, original-due-date pause status, and desired transition date.

### Read-only production checks (safe; no secrets displayed)

```bash
cd /opt/vpn-control-center
docker compose -f docker-compose.yml -f docker-compose.sms.yml ps
git status --short --branch || true
git log -1 --oneline || true
docker compose -f docker-compose.yml -f docker-compose.sms.yml logs --tail=40 app
docker compose -f docker-compose.yml -f docker-compose.sms.yml logs --tail=40 customer-portal
```

To check anchor states without modifying anything:

```bash
docker compose -f docker-compose.yml -f docker-compose.sms.yml exec -T db sh -lc \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT status, count(*) FROM billing_anchor GROUP BY status ORDER BY status"'
```

## External design material

A Figma design draft was created separately (not part of this code repository): `https://www.figma.com/design/0gSbV7ACIxSu4exm8XAhtN`. The authoritative deployed UI remains the Python templates and CSS in GitHub, not the Figma draft.

## Owners' near-term goal

Finalize the VPN accounting/customer portal, backfill already-paid users fairly, then share the public customer URL. **Do not claim launch readiness without production smoke tests and confirmation of billing state.**


## Maya1 x-ui read-only control-room integration (2026-10-13, prepared; NOT YET DEPLOYED)

- Owner audited maya1 x-ui: currently 145 distinct client email labels; 141 approved dashboard links and four excluded names (default `m0z2wrul`, personal `khodamm`, free `pedram tofigh` and `pedram tofigh hamsar`). No link is derived from fuzzy matching. The original user-reviewed mapping has digest `8e1509674cf0c06d1e8015064c8c3b69b76931311bce4489b1bbda49d50f37fb` and the sync script validates this exact digest and all 141 unique dashboard IDs against the live database. Changes to roster or names cause sync to fail closed, not guess.
- New branch files: `scripts/maya1_xui_export.py` (sanitized read-only SQLite export, no UUID/config), `scripts/maya1_readonly_sync.py` (SSH pull, live mapping verification, atomic JSON snapshots), `patches/maya1_control.py` (admin-only `/control-room` extension), `scripts/install_maya1_control.sh` (preflight, restricted-SSH pairing, rollback-ready app-only runtime patch and cron).
- Source maya1 SSH target `94.184.4.38`; DB `/etc/x-ui/x-ui.db`. Installation creates `/usr/local/sbin/maya1-xui-export` and an `authorized_keys` entry with OpenSSH `restrict,command=` limiting the dedicated key to the read-only inventory exporter. On management server the private key is `/root/.ssh/hesab_maya1_readonly`; never commit, display, or send it. First-pair may prompt for root password locally on the management terminal; never enter the root password into chat. Manually verify new SSH host fingerprint before accepting.
- Management source is `/opt/vpn-control-center/scripts/maya1_readonly_sync.py`; snapshots are `/opt/vpn-control-center/maya1_sync/{snapshot,mapping}.json`, mounted **read-only** into the `app` container. Five-minute refresh in `/etc/cron.d/hesab-maya1-sync`. Cron logs `/var/log/hesab-maya1-sync.log`. The admin patch is appended at startup from a read-only bind mount; the installer recreates **only** the `app` service and never rebuilds images, restarts x-ui, or writes to subscription/payment or x-ui SQLite databases. It does not touch shared Caddy.
- The owner confirmed dashboard IDs `28,49,109,291` exist and the status of 49 and 109 is normal, 28 and 291 waiting. The owner removed `abass negin amirhossein` from maya1 intentionally to host it on another server later. Never delete that person from dashboard during maya1 mapping.
- Do **not** claim production sync is active until the owner runs the installer and shares `SUCCESS: MAYA1 READ-ONLY CONTROL ROOM ACTIVE` plus verification that `/control-room` works with an authenticated admin session. Check that the portal and HTTPS are still healthy, given the unrelated past Caddy outage.


## Maya1 manual controls + per-day usage (2026-10-13, prepared; NOT YET DEPLOYED)

- The owner confirmed the original readonly Maya1 pairing and `/control-room` deployment is live. Maya1 has x-ui on TCP 2095, a custom base path and HTTPS, and the VLESS `/panel/api/inbounds/updateClient/:clientId` route exists in the installed binary. The owner-provided SSH ED25519 host fingerprint is `SHA256:wbtVoThIOcMgKp9jeoQCneTNX1YRXvwNfyFTCT8Bt3s`. Do not disclose the custom base path or credentials.
- New files: `scripts/maya1_xui_control.py` (installed only on Maya1, authenticates against local panel API, modifies exclusively the chosen VLESS client's `enable` via updateClient, re-reads API and SQLite), `scripts/maya1_control_gateway.py` (host Unix socket `maya1_sync/control.sock`, audited SSH forced-command calls, local `actions.jsonl`), `scripts/maya1_usage_daily.py` (Tehran-day deltas, baseline-only on first sample, midnight/gap/reset accounting).
- Updated `scripts/maya1_readonly_sync.py` to record daily history after **validated** successful readonly snapshots; updated `patches/maya1_control.py` to render top-10 per-day usage, individual usage, POST toggles with session CSRF + origin check + exact subscription mapping, and an operations audit history. Existing financial and customer routes remain unchanged. Excluded/default/personal/free 4 labels cannot be changed via this integration.
- The only installer is `scripts/install_maya1_controls.sh`; it requires the existing readonly integration. It pins the Maya1 SSH host-key fingerprint, installs a **separate forced-command SSH key**, deploys the control script on Maya1, and prompts locally on Maya1 for an x-ui login password OR bearer token (never send to chat or store on the management host). Setup tests login/list (no modifications). Only after that does it back up and update app patch/source, install the host-side gateway `hesab-maya1-controls.service`, and force-recreate the **app** container only. The script explicitly has app rollback; it never restarts x-ui/Caddy/customer portal, changes finance records, or updates the x-ui SQLite directly. It does not toggle any clients during install.
- Use strict name + ID mapping verified against 145 client roster / 141 mapped dashboard accounts. Management actions are only POSTed after an authenticated admin session CSRF check. The remote verifies that the client is in the 141-item allowlist and uniquely identified in both its read-only SQLite config and authenticated x-ui API, then updates only enable and checks the outcome. New/renamed client rosters fail closed.
- Daily usage is **observed since installation**, sampled every 5 minutes. It does not fabricate consumption before monitoring started, across midnight, or after a long monitoring gap; dashboard labels this limitation.
- DO NOT claim manual toggles installed or tested until the owner sends the installer success line `SUCCESS: MAYA1 MANUAL CONTROL + DAILY USAGE INSTALLED` and confirms a single deliberate low-risk test. On any uncertain write result, manually check x-ui before retrying.

- Resume after successful manual `--configure`: set `MAYA1_AUTH_ALREADY_CONFIGURED=1` when invoking `scripts/install_maya1_controls.sh` on the management server. Installer refreshes forced-command script and allowlist on maya1 and performs `--check` (saved local credentials + read-only inbounds API probe) rather than prompting for the x-ui password again. This is important when an original shell-heredoc invocation stalls at "Choose p or t:"; that invocation may have ended before any dashboard files were changed. Never repeat `--configure` unnecessarily.
