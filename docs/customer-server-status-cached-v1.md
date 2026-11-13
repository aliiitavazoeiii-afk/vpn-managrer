# Customer-specific VPN server status — V1

**Status: development branch only; NOT deployed to Production.** User requested existing login without a verification code.

## Existing customer login (no new OTP)

As requested, this feature **uses the existing signed `moshtarakin_customer` session** on `usermanager.ir` and checks subscription ownership against the session phone in the database on **every request**. It does **not** add an SMS code or any other login step.

**Existing security tradeoff:** the current phone-only login checks whether the phone is registered, not whether the visitor controls the SIM. A visitor who knows someone else's registered phone could obtain a valid login for that phone. The new status endpoint does not expose IP addresses or internal secrets, and it does not permit selecting unrelated subscription IDs, but it inherits that pre-existing risk. This cannot be described as verified SIM ownership.

Without an existing valid signed login cookie, both status endpoints return 403. The UI remains accessible to logged-in users after deployment.

## Data flow

1. The existing signed user session is checked by the customer-portal backend; **no additional OTP is required**.
2. The portal checks authorized, not-cut account IDs against `subscriptions` using the session phone (`active_subscriptions`). The browser may submit only `subscription_id`, not a Maya ID, host, URL or port.
3. A fixed Docker-internal request to `http://app:8000/internal/customer-server-status/v1?sid=<approved id>` carries a 30-second HMAC keyed from a root-only secret file mounted read-only into both web containers.
4. The administrative app resolves **only explicitly approved XUI ↔ subscription mappings** from `approved_links.json` and confirmed legacy Maya1 `mapping.json`. Unknown, conflicting and inferred name matches are **unknown**, never guessed.
5. The administrative app reads the existing **`dual_hourly_v1.json`** (connection check, fresh at most 75 minutes) and the existing **`path_transfer_v1/status.json`** (512-KiB real transfer, fresh at most 30 minutes). There is no SSH, SOCKS, curl, active download, new cron, new service, or call to the existing `/control-room/*` administrative endpoints.
6. Only the single resolved server’s sanitized three-role status leaves the internal bridge. Foreign IPs, path ports, remote hostnames, hashes and SSH information are never returned.
7. The portal applies a **30-second cache and single-flight per subscription**, six customer checks/minute, twelve per subscription/minute and 120 total/minute; the central bridge additionally limits 30 per Maya/minute and 90 total/minute (per process). Existing Compose launches one Uvicorn process for each service. These process-local limits must be replaced by shared-store limits if horizontally scaled.

## Result model

- `healthy`: the previous real test completed exactly 524288 bytes with HTTP 200, curl exit 0 and duration at most 12s within 30 minutes.
- `slow`: same verified full transfer but duration over 12s.
- `timeout`: curl exit 28 or validated timeout reason.
- `incomplete`: verified partial download or incomplete reason.
- `disrupted`: failed path or newer connection-down evidence.
- `connection_only`: recent 2/3 or 3/3 HTTPS checks but **no recent verified transfer**; **never** label transfer quality healthy.
- `unknown`: invalid, stale, missing or ambiguous data.

HAProxy has no independent HTTPS-only status source here; its quality is `unknown` until a valid central transfer test exists.

All last-observed timestamps are displayed in Persian as **Iran/Tehran**. No user click launches an active test. Readings can still be stale or incomplete even within TTL; this is not an end-to-end guarantee for an individual subscriber.

## Repository files

- `patches/customer_server_status_bridge_v1.py` — authenticated, HMAC-protected private status bridge on admin service.
- `customer_portal/customer_server_status_portal_v1.py` — scoped customer endpoints, rate limits, UI and CSRF.
- `scripts/test_customer_server_status_v1.py` — isolated unit/integration-style tests for allowed/denied subscribers, concurrency and stale data.
- `scripts/install_customer_server_status_v1.sh` — **`--check` is default**; `--install` is an explicit separate action requiring operator approval, protected secret and backups.
- `scripts/rollback_customer_server_status_v1.sh` — check exact deployed hashes before restoring.
- `.github/workflows/test-customer-server-status-v1.yml` — CI.

## Operational compatibility and deployment caveats

The exact Production file versions cannot be determined from GitHub alone. The guarded installer compares known markers, live bind mounts and the actual loaded app/customer portal templates before any mutation and stops if the installed shape differs. That is **not** a guarantee that its actual side effects are safe; perform a maintenance-window review of the Compose diff and secret permissions before running `--install`.

Default check-only command (not run by this development task):

```bash
bash scripts/install_customer_server_status_v1.sh --check
```

Run `--check` first and deploy with `--install` only after reviewing the live compatibility results; the user explicitly requested the current phone-only login with no extra verification. The CI tests do not include an end-to-end authenticated Production browser session or live network conditions.
