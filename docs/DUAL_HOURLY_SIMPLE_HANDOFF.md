# Simplified Dual HA hourly status in Hesab Control Room

Status: **SOURCE READY, CI PASS; NOT DEPLOYED OR LIVE TESTED.**
Branch: `feat/control-room-dual-hourly-simple-v1`, based on current V10
`manual-sms-batch-operator-open` (not V11 telemetry draft).

User scope is intentionally ONLY:
- Once per hour, read existing `sudo dual status` on Iran Maya servers
  (initially Maya1 and Maya3, canonical ID `maya-s3`).
- Show Backhaul / Mieru **foreign IP**, **HEALTHY / Down / unknown**,
  and existing HTTPS health-check average latency **in ms** in Control Room.
- Show stale/unavailable instead of fake green; Maya4 unconfigured by default.
- No extra connection check to foreign servers, no new Caddy route, no
  Receiver/HMAC/SQLite, no changes to tunnel, HA, Xray, provider balance,
  users, finance or automatic SMS.

## Why this is much simpler than V11
`frp-tunnel/dual-backhaul-mieru-ha/v2/dual.py status` reads root-only
configuration for the two IPs, the controller's already-maintained
`/run/dual-ha-v2/health.json`, and local HAProxy statistics.
It does not run `dual health` active probes or a tunnel cutover.
The user calls the printed `avg` "ping", but it is actually average
**HTTPS probe elapsed time**, not ICMP ping.

## Prepared code
- `scripts/maya_dual_hourly_collect_v1.py`: management host
  executes strictly `/usr/local/bin/dual status` via verified, batch-mode
  SSH, parses only two IPs / freshness / status / HTTPS latency, atomically
  writes /opt/vpn-control-center/maya_extra_sync/dual_hourly_v1.json.
- `scripts/prepare_maya_dual_hourly_v1.py`: safely tries to reuse
  the existing protected Maya SSH host metadata and currently configured
  identity from the XUI tunnel. Creates only NEW 0600
  /root/.config/hesab-dual-hourly-v1.json if absent; never alters SSH
  host keys, remote servers or existing credential config.
  Existing port-forward-only keys can reject command execution; that
  is expected, not permission to weaken restrictions.
- `patches/control_room_dual_hourly_v1.py`: appended AFTER V10 to
  mounted admin overlay only after approved deployment. Separate
  GET `/control-room/dual-hourly/status` requires current admin
  session CSRF token. Three small RTL server summaries below existing
  V10 cards; refreshes browser view every 60 sec from hourly snapshot.
  Data older than 75 minutes cannot display healthy.
- `scripts/test_maya_dual_hourly_v1.py`: synthetic parser/security tests.
- `.github/workflows/test-control-room-dual-hourly-v1.yml`: Python
  compilation, offline unit tests and JS syntax. CI PASS.

## Minimal next real-host check (no app restart)

On the management host, in a separate directory download pinned copies of
`scripts/maya_dual_hourly_collect_v1.py` and
`scripts/prepare_maya_dual_hourly_v1.py`. Run:
`python3 prepare_maya_dual_hourly_v1.py`

Expected per-server `DUAL_SSH_ACCESS=PASS`. If SSH is forced port-forward,
return `DUAL_SSH_ACCESS=NOT_YET_AVAILABLE`; do NOT change original XUI key.
A dedicated SSH key restricted to forced `/usr/local/bin/dual status`
can be added in a separate explicit one-time setup instead. Never put
raw config / private key / passwords into chat or GitHub.

## Deployment gate
The UI feature is **not** yet installed. After both Iran hosts can be read
safely, stage a backup and compare production mounted V10 overlay with Git,
then append only the new admin overlay and recreate only the admin app.
Install a management-host systemd oneshot+hourly timer to run collector.
No Caddy reload, no Maya changes beyond optional one-time restricted SSH.
Verify admin authorization and preexisting XUI/payment routes. Keep rollback.

## Previous abandoned V11 HTTPS test
Caddy synthetic test failed with `exec /usr/bin/caddy: operation not
permitted`, due to execution restriction on the disposable test
container. This is not evidence that the production Caddy or VPN broke.
Do not pursue V11 staging unless the user separately asks.
