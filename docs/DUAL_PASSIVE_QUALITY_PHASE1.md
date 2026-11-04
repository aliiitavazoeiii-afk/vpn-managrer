# Dual HA — Passive Traffic Quality, stage 1 (Hesab only)

**Scope:** Management server `/opt/vpn-control-center` only. This branch does not change any Iran or foreign node, HAProxy, Xray/REALITY, Backhaul, Mieru, Mita, system Health Controller, routing, weights, user data, payments, or Caddy.

## Actual capabilities of the current source

The existing forced-command key `/root/.ssh/hesab_dual_hourly_v1` only executes `NO_COLOR=1 /usr/local/bin/dual status`. The existing collector `maya_dual_hourly_collect_v1.py` serializes only foreign IP, small HTTPS health result (3 probes), average HTTPS response time, and freshness. **It does not serialize HAProxy session counts, bytes in/out, error counters, per-backend transfer performance, or transfer-test results.**

This stage therefore adds six separate Backhaul/Mieru *quality* cards, but reports **"کیفیت انتقال اندازه‌گیری نشده"** for each path until reliable counters are genuinely supplied by a separately reviewed, scoped future source. Keeping the existing HEALTHY label in the Connectivity section is NOT evidence of throughput health.

## Passive-only collection

`maya_dual_passive_quality_v1.py` reads *only* the local `maya_extra_sync/dual_hourly_v1.json`. The new local account-side `hesab-dual-quality-passive-v1.timer` runs this processor every 30 seconds; repeated identical source snapshots are deduplicated. No network connection or new foreign request is created by the processor. It maintains bounded, locked, atomic status/history files under `maya_extra_sync/dual_quality_v1/`, which is already available read-only inside the admin app's `/srv/maya-live` mount.

This does **not** turn a 1-hour source sample into a 5-minute network-quality measurement. The manual refresh button still obtains `dual status` through its original restricted key, and its status is independent of traffic quality.

The protected endpoint `GET /control-room/dual-quality/status` requires the existing admin CSRF session. Rendering is text-only DOM (not untrusted HTML); the cards display no invented counter values, graphs, errors, or transfer-test timestamps. Stale data over 75 minutes cannot appear healthy.

## Optional future per-backend counters: strict contract, NOT in current V1

Only if a **reviewed** future snapshot includes `paths[role].haproxy_counters` for a specific backend with all of:
- `source: haproxy_stats_readonly`
- `scope: backend`
- `epoch`: nonempty backend-process/reset identity
- nonnegative, monotonic integer `bytes_in`, `bytes_out`, `sessions_total`, `connection_errors_total`, `response_errors_total`
- nonnegative integer gauge `sessions_current`

may the passive analyzer compute per-window deltas. The source must explicitly document byte direction from **HAProxy's perspective**; bytes-out is not necessarily directly equivalent to a user's download. Epoch or counter reset, foreign IP replacement, missing samples, and gaps greater than 75 minutes invalidate that window. New sessions are delta(`sessions_total`); active sessions are a gauge, not a delta.

A **suspected degradation** signal needs at least five comparable historical baseline windows, three consecutive low windows, >=20 active and >=20 new connections in each low window, a baseline outgoing throughput >=64 KiB/s, and each recent window below 10% of that baseline. Confidence remains *medium* and no automatic failover occurs. Low traffic or near-equal active connections alone never prove failure. This conservative algorithm is already regression-tested, but **its counters are currently absent**, so such an alert cannot be emitted from V1 data.

## Real incident regression fixture

`fixtures/maya3_mieru_degraded_20261104.json` contains the user's observed Maya3 Mieru incident, including:
- Backhaul: 524288/524288 bytes, 0.50s, HTTP 200, exit 0.
- Mieru: HTTP 200 but 30118/524288 bytes in 25s, exit 28 (timeout).
- HAProxy proxy route: 42373/524288 bytes in 25s, exit 28.
- Backhaul vs Mieru per-backend counts: 201/204 active, 93/84 new connections, 11.31/0.35 MB, zero recorded errors.
- Replacement Mieru: complete 524288 bytes in 0.98s, exit 0.

These IPs are **test fixtures only**. They are never inserted into source selection or production logic. The offline test demonstrates that HTTP 200 and HAProxy UP do not imply successful bulk data transfer; a single low-throughput/imbalanced counter window is *not* a fault alert.

## Stage 2: Proposed controlled transfer test — NOT DEPLOYED

A *future*, separately approved test could fetch exactly 512 KiB from a trusted immutable HTTPS test object through each of the three explicitly chosen SOCKS paths: 21001 Backhaul, 21002 Mieru, 18080 HAProxy. Planned measured fields: HTTP status, bytes requested/received, elapsed time, time to first byte, throughput, timeout/exit status, timestamp and path identity. An HTTP 200 with incomplete body and exit 28 is **failure**.

Before any production test, separately agree on the HTTPS host/path, TLS verification, destination IP validation, total budget (max 512 KiB per path per invocation plus protocol overhead), connect timeout, total timeout <=25s, retry policy (none), manual operator confirmation, no schedule, maximum concurrency (one), bounded local privileges, and privacy risks. For now there is **no production transfer endpoint, no downloader, no scheduled download probe, no new privileged remote SSH command, and no new Iran-side agent**.

The current limited SSH key and `dual status` format are preserved, as are the original hourly collector and instant refresh.

## Guarded deployment and rollback

`scripts/install_dual_passive_quality_v1.sh` validates the live V10+Dual V1+manual V2 dashboard, compares the exact currently installed V2 addon with the reviewed GitHub reference, compiles/preflights the new admin addon, backs up the mounted admin overlay, Compose definitions, old app image ID and **a PostgreSQL custom-format dump** before any mutation, installs only the **account-server-side** passive processor/timer and additive read-only admin endpoint, restarts only the admin `app` container, and validates the protected endpoint and 3x3 cards. If a step fails after mutations, it restores the pre-install overlay/files and recreates only the old admin app.

No database migration or provider/tunnel-state write is performed. An installer `SUCCESS` is only proof of successful deployment of **passive UI**; it is not proof of active traffic-quality detection.
