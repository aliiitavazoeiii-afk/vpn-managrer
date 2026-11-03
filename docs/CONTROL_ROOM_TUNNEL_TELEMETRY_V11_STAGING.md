# Control Room Tunnel Telemetry V11 — audit and staging runbook
Date: 2026-11-03. STATUS: DEVELOPMENT BRANCH ONLY. NOT DEPLOYED.

GitHub repository: aliiitavazoeiii-afk/vpn-managrer
Base: manual-sms-batch-operator-open
Feature: feat/control-room-tunnel-telemetry-v11
Active tunnel source: aliiitavazoeiii-afk/frp-tunnel
Branch: dual-backhaul-mieru-ha
Tunnel files are under dual-backhaul-mieru-ha/v2/.

## 1. Repository and production audit

- The default main branch of vpn-managrer is an older, small source tree.
  The live-work branch manual-sms-batch-operator-open contains Control Room
  V2–V10, approved XUI mappings, host metrics, provisional traffic meter,
  traffic topup ledger, and the V10 daily NIC display.
  DO NOT replace production with main or run the legacy destructive install.sh.
- Current real production differences and uncommitted server patches are
  NOT independently inspected. First run the supplied read-only preflight
  and compare all mounted overlays before making a deployment decision.
- From operator terminal reports, the three XUI destinations as of
  2026-11-03 were:
  maya1, maya-s3, and maya4 are the IDs. IP inventory is private and
  must not be copied into the public Git repository.
  XUI API success does NOT prove true VPN egress and does not prove that
  all three hosts use the new dual tunnel architecture.
- Existing admin routes and customer finance/payment routes must remain.
  Old approved_links and Maya snapshots must never be regenerated blindly.
- Older doc docs/CONTROL_ROOM_TUNNEL_TELEMETRY_HANDOFF.md was read
  from vpn-managrer main because it is absent from the active branch.
  It describes old Naive+Mieru: security reference only, NOT live state.

## 2. Verified dual HA v2 data contract

The actual controller.py writes /run/dual-ha-v2/health.json as:
  updated_utc: ISO8601 UTC
  paths.backhaul / paths.mieru:
    available (bool)
    passed_probes (int), total_probes (int)
    latency_average_s (seconds or null)
    consecutive_success, consecutive_fail
    haproxy_before_action

The controller tests 3 real HTTPS destinations every 8 seconds, requires
2 successful probes per path, disables after 3 failures and re-enables
after 5 successes. The Agent DOES NOT call this controller or alter its
choices. V11 reads only its output.

Actual HAProxy: backend dual_egress, policy leastconn, local SOCKS
21001 / 21002, frontend 127.0.0.1:18080 and stats socket
/run/dual-ha-v2/haproxy.sock. The Agent reads show stat over the
existing Unix socket: scur, stot, bin, bout, status, chkfail.
Those counters reset on restart and do not represent daily billing.
Connection share and byte share are separate percentages; never claim
they are 50/50 or infer UDP from TCP/HTTPS tests.

Foreign IP addresses are optional private metadata in the root-owned
Agent JSON (foreign_ips). Agent does not read private Backhaul/Mieru
bundles. Unconfigured foreign addresses are UNKNOWN.

## 3. V11 feature contents and limitations

monitoring_v11/iran_agent.py:
  Standalone Python standard-library Agent. CPU, RAM, root filesystem disk,
  uptime, NIC RX/TX, fixed allowlisted service states, controller health,
  HAProxy statistics and configured foreign IP; no UUID, credentials,
  REALITY private key, payment information or users exported.
  Does not restart/disable/enable any tunnel or XUI process.
  HTTPS POST to the privately configured verified panel domain, one key per server.

monitoring_v11/receiver.py:
  Dedicated localhost-only HTTP server 127.0.0.1:8199 with HMAC-SHA256
  on timestamp + period + exact request body, signed nonce, 120s clock
  tolerance, per-server nonce uniqueness, 64KB limit, 10-second minimum
  interval, fixed known server IDs and constant-time signature check.
  Stores six ADDITIVE tables in independent SQLite, not existing PG:
  replays, server_state, samples, counters, events, alerts.
  A status transition requires two matching messages. Stale >120s
  never appears healthy. HAProxy counter resets create an epoch event.
  Incident alerts are unique, have 10-minute cooldown, and remain
  pending_review: NO automatic SMS is sent.

monitoring_v11/control_room_overlay.py:
  Three GET-only admin endpoints /control-room/v11/status,
  /control-room/v11/events and /control-room/v11/samples.
  Require the existing admin session CSRF token header and inherit
  the existing site-wide authentication. Existing V10 cards, approved
  XUI controls, topup/usage views and finance APIs are preserved.
  The UI displays 3 server cards, real CPU/RAM/disk, uptime,
  tunnel HTTPS health, active and cumulative connections, bytes,
  separate HAProxy shares, real CPU chart and event timeline in
  Iran time. Manual refresh and 30-second refresh provided.
  Never display confirmed filtering from a failed HTTPS probe.

IMPORTANT NOT IMPLEMENTED YET:
  - Provider-verified remaining quota / 10GB and 20GB alerts:
    provider API or a verified synchronized quota source required.
    Historical V6/V7 provisional traffic must not be promoted to fact.
  - Genuine XUI concurrent-online user counts: separate validated
    XUI source is required. Existing client counts are not concurrency.
  - UDP/XUDP probe: UNKNOWN, not proof of success or failure.
  - Independent end-to-end VPN client health and live remote egress IP.
  - Automatic SMS or push delivery: existing native SMS app is
    manual/queue-driven, not an approved verified auto-alert provider.
    Alert candidates are stored for later explicit integration.

## 4. Mandatory discovery / backups before deployment

Run ON THE MANAGEMENT HOST from a separate reviewed feature checkout:
    bash monitoring_v11/preflight_production_readonly.sh

For EACH IRAN HOST, use its provider console / verified SSH host:
    for x in x-ui dual-ha-v2-gateway dual-ha-v2-health dual-ha-mieru dual-ha-backhaul dual-ha-router dual-ha-tls; do
      echo "$x"; systemctl is-active "$x" 2>/dev/null || true
    done
    ip -br link
    test -f /run/dual-ha-v2/health.json && echo V2_HEALTH_PRESENT
    test -S /run/dual-ha-v2/haproxy.sock && echo V2_STATS_PRESENT

If HA v2 isn't installed, the Agent must report unidentified/unknown,
not manufacture Backhaul/Mieru health. A different agent adapter requires
its own code review and tests; do not read any arbitrary private config.

Compare live current patch overlays, effective Docker Compose mounts,
runtime route names, image IDs and SHA256 against the reviewed GitHub
checkout; check for uncommitted production modifications.

Before applying:
  1. A real protected PostgreSQL custom-format pg_dump -Fc.
  2. pg_restore -l archive check, AND RESTORE INTO A SEPARATE STAGING DB.
  3. Compare subscription count, total debt, payment count/sum pre/post.
  4. Back up .env, Docker Compose, all mounted overlays,
     approved Maya mapping, XUI connection config, and original
     reverse-proxy config. Do not publish secrets.
  5. Verify rollback to prior app overlay and image is practical.
  6. Confirm authenticated page and signed-out API authorization.

Never run root install.sh, docker compose down -v, git reset --hard
or database seed/import on this financial application.

## 5. STAGING setup: independent receiver

Create directories privately on the management host:
    install -d -o root -g root -m 0700 /etc/hesab-telemetry-v11
    install -d -o root -g root -m 0700 /opt/vpn-control-center/maya_extra_sync/telemetry_v11

Install from reviewed feature checkout:
    install -m 0755 monitoring_v11/receiver.py /usr/local/sbin/hesab-v11-receiver

Generate THREE independent secrets privately, with no chat/log exposure:
    umask 077
    openssl rand -hex 32

Create /etc/hesab-telemetry-v11/receiver.json, chmod 0600, owner root.
Example structure (replace ALL placeholder secrets with different values):

    {
      "database_path": "/opt/vpn-control-center/maya_extra_sync/telemetry_v11/telemetry.sqlite3",
      "servers": {
        "maya1": {"enabled": true, "key_hex": "MAYA1_64_HEX"},
        "maya-s3": {"enabled": true, "key_hex": "MAYA3_DIFFERENT_64_HEX"},
        "maya4": {"enabled": true, "key_hex": "MAYA4_DIFFERENT_64_HEX"}
      }
    }

Create /etc/systemd/system/hesab-telemetry-v11.service:
    [Unit]
    Description=Hesab V11 signed telemetry receiver (localhost)
    After=network-online.target
    [Service]
    Type=simple
    User=root
    ExecStart=/usr/bin/python3 /usr/local/sbin/hesab-v11-receiver
    Restart=on-failure
    RestartSec=5
    ProtectHome=yes
    ProtectSystem=strict
    ReadWritePaths=/opt/vpn-control-center/maya_extra_sync/telemetry_v11
    NoNewPrivileges=yes
    [Install]
    WantedBy=multi-user.target

Start in staging only and confirm listening on 127.0.0.1:8199,
NEVER on a public interface.

Reverse proxy: inspect the actual current Caddy/nginx config first.
Only the POST endpoint /api/control-room/v11/heartbeat should proxy
to 127.0.0.1:8199 and forward X-Forwarded-Proto=https, with valid TLS.
The receiver refuses direct public clients or non-HTTPS proxy headers.
Do not replace the full production reverse proxy configuration blindly.
Do not expose /healthz externally. Browser calls admin app APIs only.

Illustrative Caddy matcher INSIDE the existing site (not a complete file):
    @hesabV11Heartbeat {
      path /api/control-room/v11/heartbeat
      method POST
    }
    handle @hesabV11Heartbeat {
      reverse_proxy 127.0.0.1:8199 {
        header_up X-Forwarded-Proto https
      }
    }

Before any reload: caddy validate, backup config, verify no route
regression and retain previous working config for rollback.

## 6. STAGING setup: independent Agent on each Iran host

Determine real NIC with ip -br link and real tunnel type first.
Install ONLY the reviewed agent; never paste keys into GitHub/chat:
    install -d -o root -g root -m 0700 /etc/hesab-telemetry-v11
    install -m 0755 monitoring_v11/iran_agent.py /usr/local/sbin/hesab-v11-agent

Root-owned /etc/hesab-telemetry-v11/agent.json, chmod 0600:
    {
      "server_id": "maya1",
      "endpoint": "https://<PRIVATE_VERIFIED_PANEL_DOMAIN>/api/control-room/v11/heartbeat",
      "key_hex": "SAME_MAYA1_SECRET_AS_RECEIVER",
      "interface": "CONFIRMED_REAL_INTERFACE"
    }

Use maya-s3 (NOT maya3) on Maya3. Perform a single manual heartbeat:
    /usr/bin/python3 /usr/local/sbin/hesab-v11-agent

Accepted result prints server ID and controller state, no secrets.

After endpoint TLS, HMAC and receiver tests succeed, install a separate
systemd oneshot service with ExecStart=/usr/bin/python3
/usr/local/sbin/hesab-v11-agent, then a systemd timer:
    [Unit]
    Description=Signed Hesab telemetry every 30 seconds
    [Timer]
    OnBootSec=30s
    OnUnitInactiveSec=30s
    AccuracySec=5s
    RandomizedDelaySec=2s
    [Install]
    WantedBy=timers.target

Observe one host first; do not deploy three simultaneously until
each host/transport is verified. Agent failure must have NO effect on
local failover or Xray.

## 7. Admin overlay: LAST, only after approved backup gate

    sudo bash monitoring_v11/install_admin_ui_v11.sh /ABSOLUTE/PATH/TO/SEPARATE/V11_CHECKOUT --apply

The installer preflights the active V10 template and guarded prior
routes. It backs up mounted UI source, Compose and real PostgreSQL
custom-format dump; confirms TOC readability; appends only the V11 UI
overlay to the existing mounted patches/maya1_control.py, then recreates
ONLY the admin app without image build or DB restart. It checks expected
routes and fails/rolls back if source isn't compatible.

Manual UI rollback using exact installer BACKUP path:
    cd /opt/vpn-control-center
    cp -a /EXACT/BACKUP/maya1_control.py patches/maya1_control.py
    docker compose -f docker-compose.yml -f docker-compose.sms.yml up -d --no-deps --no-build --force-recreate app

Receiver rollback: disable receiver service and remove only its new proxy
route after restoring backed-up proxy config. Iran rollback: disable
independent Agent timer. Preserve telemetry SQLite for audit history.

## 8. Test and release criteria

Feature-branch CI path:
.github/workflows/test-control-room-telemetry-v11.yml

- Positive HMAC, bad HMAC, unknown sender, stale timestamp, tampered raw
  body, bad payload/false quota, nonce replay, and early rate limit.
- Two observed bad states before event; two good states before recovery.
  Alert cooldown and persistent dedupe, counter reset epoch, stale flag.
- Admin API with no session/CSRF returns 403 or login, never raw data.
- No agent-host tunnel restart, XUI toggle, HAProxy set or finance write.
- Jinja, JavaScript, browser desktop/mobile and real sample history.
- Verify actual Caddy proxy, real signed heartbeat, no proxy secrets.
- Verify PostgreSQL financial counts and payment ledger unchanged.
- Verify old XUI controls, mappings, V9 topups and V10 daily data survive.
- Do not simulate outage on Production without separate explicit approval.

No V11 deployment or actual Production backup verification was performed
by the assistant. A successful feature commit is not a live acceptance test.

## 9. Maya1 stability-first non-interference policy

- No new HTTPS health probe, no loopback TCP port-443 connect, no network
  test to a foreign IP, and no new tunnel controller requests are allowed.
- The agent uses only pre-existing health.json, local read-only show stat
  on the HAProxy Unix socket, /proc and /sys counters, filesystem usage,
  read-only systemd is-active checks, and its own private 0600 config.
- The port 443 indication comes from /proc/net/tcp and /proc/net/tcp6
  LISTEN entries only. This is not proof of remote client reachability.
- Optional foreign IPs come solely from private Agent config metadata.
  It never reads the existing Mieru or Backhaul credential bundles.
- Sender makes one outbound HTTPS POST per approved run to a configured
  management FQDN. HTTPS validates TLS; redirects and environment proxies
  are disabled. No new inbound Iran-host port is used.
- Local HAProxy socket connection only sends the fixed show stat command.
  HAProxy still has an admin-capable Unix socket, so permission hardening
  matters. The reader makes no enable, disable, set, reload or restart call.
- Each run is single-shot. Proposed 30-second systemd timer is optional
  and must only be installed after separate explicit owner authorization.
- An outbound telemetry POST creates some additional management traffic.
  Thus absolute zero detection risk cannot be promised; verify normal
  host policy routes, resource overhead and independent failure behavior
  on a non-Maya1 host before running it on Maya1.
- The GitHub repos are public and earlier history contains real IPs,
  including earlier V11 feature commits. This revision removes explicit
  current IPs and the panel FQDN from feature source, but Git history still
  exposes prior values. Do not rewrite Git history or change visibility
  without explicit owner approval.
- Rollout order: offline audit -> receiver staging -> non-Maya1 dry run
  -> approval -> Maya1 sender trial. Do not change existing tunnel services.
