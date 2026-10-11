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
