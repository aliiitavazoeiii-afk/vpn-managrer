# Hesab Control Room — manual 512 KiB path test

## One purpose

Keep the existing **«بررسی وضعیت»** button unmodified. Add separate **«تست مسیر»** that performs actual, bounded single-stream HTTPS downloads through each local proxy on **Maya1**, **Maya3**, and **Maya4** and shows **only سالم / هشدار** for Backhaul, Mieru, and HAProxy.

The new button is manual only. There is **no Cron/systemd timer for downloading**, no automated response (no HAProxy weight changes), no active test during installation or app startup, and no access to the current `hesab_dual_hourly_v1` SSH key.

## Exact test and impact (9 fixed requests, no retries)

- Destination: Cloudflare-maintained `https://speed.cloudflare.com/__down?bytes=524288`
- Download: **512 KiB (524288 bytes) per route**; 3 routes × 3 Maya = **4,718,592 bytes (4.5 MiB)** of downloaded payload if all complete; additional TLS/HTTP overhead is possible.
- Protocol: HTTPS with standard certificate verification over SOCKS5h loopback; DNS for endpoint resolves through proxy.
- Routes: `127.0.0.1:21001` Backhaul, `127.0.0.1:21002` Mieru, `127.0.0.1:18080` HAProxy (assumed SOCKS5; protocol errors are warnings, never ignored).
- Requests: one per route; within each host sequential; across three hosts up to three at a time. **No redirects, retries, remote arbitrary URLs, or arbitrary commands.**
- Timeout: connect <=6 seconds; total <=25 seconds per path (with bounded Python process timeout); a run can take ~90 seconds in extreme failure conditions.
- Threshold: **سالم** iff curl exit code=0 AND HTTP 200 AND exact 524288 bytes received AND total <=12 seconds. Otherwise **هشدار** (includes timeout 28 despite HTTP 200; slow completion also produces a conservative warning). This status is for this specific 512KiB endpoint and is not guaranteed general tunnel health.
- At least 120 seconds between active runs at host level and management level.
- Measurements collected internally: HTTP status, requested and downloaded bytes, transfer duration, TTFB, tool exit code and reason, per-route outcome. **Only status labels** appear on the dashboard.
- DNS and TLS egress is to Cloudflare; this external provider can observe requests and process aggregate network-quality telemetry. Cloudflare documents its speed-test download API.

## Strictly scoped access

The root management host has a separate `/root/.ssh/hesab_transfer_test_v1` key; it is **not** the `/root/.ssh/hesab_dual_hourly_v1` key.

Each Iran host adds only one `authorized_keys` entry:

`restrict,command="/usr/bin/python3 /usr/local/libexec/hesab_path_test_remote_v1.py" ssh-ed25519 ...`

That entry forces a fixed-purpose Python script even if the connecting client asks for a different command. The script only responds to:
- `hesab-path-test-preflight`: prints version/availability, **no download**.
- `hesab-path-test-v1`: fixed nine? **three** transfers local to that one Maya, only from a dashboard-approved button click.

All other SSH commands return DENIED. Key forwarding, PTY, TCP forwarding and agent forwarding are disabled by the `restrict` option. The probe has no ability to touch HAProxy, Backhaul, Mieru, Xray, Reality, XUI, or routing configuration.

The management-side broker reads the existing protected Maya address map (`maya1=94.184.4.38`, `maya-s3=185.215.230.221`, `maya4=5.10.249.206`) and uses strict pinned existing SSH known-host verification. It accepts exactly the local socket request `{"op":"start"}`, passes no user-defined hosts/ports/commands, and writes an atomic status snapshot to:

`/opt/vpn-control-center/maya_extra_sync/path_transfer_v1/status.json`

Admin routes:
- `POST /control-room/path-test/start` requires same-origin, session CSRF, then starts.
- `GET /control-room/path-test/status` requires admin CSRF; returns only validated per-route labels, not arbitrary diagnostics.

## Staged, non-probing deployment

1. On the **account management host**, run `scripts/prepare_hesab_path_test_v1.py`. It prints a new **PUBLIC** key to copy; the private key stays in `/root/.ssh/`.
2. On **each of three Iranian Maya servers**, download the reviewed `hesab_path_test_remote_v1.py` and `install_hesab_path_test_remote_v1.py` into the same directory, then invoke the installer with the management host's public key as one quoted argument. Only `authorized_keys` and a new fixed helper file change. There is no restart.
3. On management host, run `scripts/install_hesab_manual_path_test_v1.sh`. It reads each remote **preflight only** using the separate key, creates an admin and DB backup, starts the **idle** root-only Unix-socket broker, adds the new button to the **admin app only**, and validates the dashboard. No active test runs as part of installation.
4. **Only after an admin actually clicks «تست مسیر»** does the remote code download through all nine routes, then the UI renders labels.

The original `sudo dual status` collector, hourly timer, active health controller, manual refresh, Caddy, production VPN services and financial DB are not changed.

## Rollback

The management installer backs up `patches/maya1_control.py` under `/root/hesab-manual-path-transfer-backup-.../`, its Compose definitions, app image ID and a Postgres dump. On installation failure it restores only admin code / local new broker service and recreates the admin app; it does not restore the finance DB (which was never modified).

To revoke access on the Iran hosts, **separately remove just the matching dedicated public-key line** from `/root/.ssh/authorized_keys`; never delete or alter the original Dual status monitoring key. Removal or uninstall should happen only with an explicit operator action.

## What “سالم” does not prove

A 512 KiB sample completed within 12 seconds proves only that the Cloudflare HTTPS object transferred on that path at that moment. It does not prove low latency everywhere, optimal throughput, streaming smoothness, or absence of deep packet inspection effects. The HAProxy path tests the **load-balanced route**, so it cannot independently identify the faulty backend: use direct Backhaul and Mieru outcomes to determine which fixed route is affected.

The 2026-11-04 Maya3 historical regression — HTTP 200 but 30118 bytes / 25 seconds / curl exit 28 on Mieru, versus complete 524288 bytes / 0.50s on Backhaul — is a mandatory offline test case; no historical foreign IP is hardcoded in operational probe logic.
