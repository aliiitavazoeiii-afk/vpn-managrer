# Customer-specific VPN server status — V1

**Status: development branch only; NOT deployed to Production.**

## Why cached-only and fail-closed?

The existing user portal `/login` issues a 30-day signed cookie after only checking that the entered phone number exists. There is no proof that the visitor controls the phone/SIM. Therefore the new customer status API refuses access until the separate **`customer_status_verified_phone_v1(request)`** function is supplied by an independently reviewed, possession-verified login flow. **Do not implement this hook by returning `_v2_session_phone(request)`; that is not verification.** The existing login, payment and account controls remain unchanged by this feature.

Without the verification hook:

- `GET /api/my-server-status/accounts` responds 403;
- `POST /api/my-server-status/check` responds 403;
- the new status card tells the user that phone verification is necessary.

This deliberately prioritizes privacy over claiming a functional production feature prematurely.

## Data flow

1. Signed user session **and** independently verified phone identity are checked by customer-portal backend.
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

Do not run `--install` until independent OTP/phone verification for status views is available and security-reviewed, and the user explicitly approves deployment. The CI tests do not include an end-to-end authenticated Production browser session or live network conditions.
