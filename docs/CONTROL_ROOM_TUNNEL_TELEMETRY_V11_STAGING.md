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

## 5. STAGING: receiver on existing shared Docker network (NO LIVE DEPLOY)

Read-only audit on Nov 3 confirmed:
- `darma-general-caddy-1` uses `darma-general_default` AND
  `vpn-control-center_default` networks.
- `vpn-control-center-app-1` is already on `vpn-control-center_default`.
- The live Hesab Caddy site has TWO upstream ports (8090 and 8000),
  but the routing/matcher rules have NOT been confirmed.
- The live `/opt/darma-general/Caddyfile` is locally modified from Git;
  preserve it exactly. It is bind-mounted read-only into Caddy.

**Invalid earlier assumption:** a listener at host 127.0.0.1:8199
is not reachable from the Caddy container via its own loopback.
Do not install the old host systemd receiver or the old Caddy target.

Prepared, NOT INSTALLED:
- `monitoring_v11/docker-compose.telemetry-v11.yml` adds an isolated
  `telemetry-receiver-v11` container to the EXISTING VPN Compose network,
  implicitly reachable by Docker service DNS on that bridge.
- No host `ports:` publication whatsoever; no new Iran inbound ports.
- Receiver binds `0.0.0.0:8199` INSIDE that isolated container ONLY when
  `HESAB_RECEIVER_DEPLOYMENT=docker-internal` is explicitly supplied.
  The default receiver mode remains loopback-only.
- Receiver checks that the immediate peer is a Docker/private address,
  rejects unauthorized HMAC, replay, stale timestamp, invalid JSON/body
  and unknown/disabled server IDs. A private peer alone is NEVER enough.
- Container configuration includes readonly filesystem, dropped Linux
  capabilities, disabled privilege escalation, 128MB memory and CPU limit,
  no docker.sock and no host network mode.
- Independent telemetry SQLite volume is mounted RW to receiver only;
  the app sees it via existing `/srv/maya-live:ro` mount.

Strict prerequisites before any container creation:
1. Verify live Caddyfile routing structure, exact matcher ordering and
   existing Hesab upstream behavior using ONLY a sanitized read-only audit.
2. Confirm the management-host running overlay hash vs approved source.
3. Verify backup, independent PostgreSQL restore and rollback.
4. Verify test network DNS/alias resolution in STAGING, not on Maya1.
5. Prepare root-owned 0600 configuration at
   `/etc/hesab-telemetry-v11/receiver.json`, with independently generated
   32-byte random HMAC keys for maya1/maya-s3/maya4. Never paste keys into
   chats or commit them to Git.
6. Audit the effective Compose configuration to ensure no host port map.
7. Add an exact HTTPS POST-only matcher for
   `/api/control-room/v11/heartbeat` in a reviewed COPY of the current
   Caddyfile. Proposed internal upstream: `telemetry-receiver-v11:8199`.
   Preserve all other handlers for Hesab portal/admin, Darma and Kharj.
8. Validate a staging reverse proxy and signed request first. Caddy must
   provide the correct HTTPS forwarded scheme. NEVER proxy `/healthz`.
9. Only after explicit owner approval, apply a verified one-service
   Compose change and a reversible Caddy reload. No automatic deployment.

Example private receiver JSON layout (DO NOT commit real keys):

    {
      "database_path": "/opt/vpn-control-center/maya_extra_sync/telemetry_v11/telemetry.sqlite3",
      "servers": {
        "maya1": {"enabled": true, "key_hex": "FIRST_SECRET_64_HEX"},
        "maya-s3": {"enabled": true, "key_hex": "SECOND_SECRET_64_HEX"},
        "maya4": {"enabled": true, "key_hex": "THIRD_SECRET_64_HEX"}
      }
    }

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

## 10. Production edge discovery, 2026-11-03 — IMPORTANT BLOCKER

- Operator read-only inventory confirms ports 80/443 are published by
  `darma-general-caddy-1` (Caddy running in a Docker container), whereas
  Hesab admin app publishes its port 8080 on host loopback.
- In the Darma-General repository, `compose.yml` mounts its Caddyfile
  read-only at `/etc/caddy/Caddyfile`. The tracked public Caddyfile contains
  only Gozaresh and Kharj sites; the live operator checkout shows the
  Caddyfile MODIFIED and may contain additional bespoke Hesab routing.
- Thus **do not edit/replace `/opt/darma-general/Caddyfile` from GitHub**.
  Back up and inspect the actual live Caddyfile and full Docker networks
  on both containers. Do not `git checkout`/`git reset` this file.
- IMPORTANT: a reverse proxy running in a different container CANNOT
  reach the host's `127.0.0.1:8199` via its own loopback. The earlier
  illustrative Caddy snippet targeting `127.0.0.1:8199` is NOT valid
  for this known deployment; DO NOT APPLY IT.
- The receiver deployment is blocked until a vetted Docker-internal-only
  route or a safe Unix socket / explicitly approved non-public gateway
  is designed and tested. No host-wide port 8199 exposure.
- Do not reload Caddy merely to test telemetry. Existing Darma-General,
  Expense and Hesab HTTPS services share this reverse proxy.
- `darma-general-caddy-1` and `vpn-control-center-app-1` container network
  memberships, their exact existing Hesab upstream mapping, and current
  Caddyfile changes must be inspected using *read-only* commands before
  any receiver or agent installation.
- Operator's unrelated V134 Darma-General production deployment completed
  with its own backup and web restart. Do not roll it back or alter it
  as part of VPN telemetry work.

## 11. Live Caddy route topology verified; collision guard still pending

On 2026-11-03 the operator's redacted read-only audit reported:
- Exactly one Hesab site block in the active locally modified Caddyfile.
- One named matcher/redirect at the site level.
- One handle_path with upstream port 8090.
- One default handle with upstream port 8000.
- Balanced braces. No content from the Caddyfile was printed.

The next non-mutating step is the conservative script:
`python3 monitoring_v11/audit_caddy_match_collision_readonly.py`
which reads the REAL live Caddyfile and reports only whether the
existing handle_path and redirect match the proposed POST
`/api/control-room/v11/heartbeat`. The script never prints
upstream hostnames, route matcher values or credentials.

Results `OVERLAP` OR `UNKNOWN` must block automatic Caddy editing.
Even if it reports `CLEAR` on both, do not immediately reload Caddy:
inspect an offline candidate and the actual Caddy adapter ordering in
staging, back up the local production-only Caddyfile, and retain a
verified rollback for shared Darma, Kharj and Hesab services.

Implementation proposal ONLY (not installed): an exact POST-only Caddy
named matcher and `handle` proxy to the new Docker service DNS name
`telemetry-receiver-v11:8199`, declared ahead of the catchall handle.
HTTPS terminates in Caddy; receiver checks timestamped HMAC message.
No Caddy data-plane or tunnel path changes are permitted in this step.

## 12. November 3 redirect cleared; next gate: in-memory Caddy adapter check

Operator's latest read-only Caddy redirect result:
- SITE FOUND, ROUTE_SHAPE EXPECTED, REDIRECT_MATCHER_CLASS PATH.
- REDIRECT_POST_HEARTBEAT_OVERLAP CLEAR, REVIEW_GATE PASS_MATCHER_ONLY.
- Earlier handle_path collision check was CLEAR.

These results eliminate the known matcher overlap concern but DO NOT
prove that Caddy will parse the new block or that other routes are
unaffected. No changes have been deployed.

Before any config modification, run ONLY the offline candidate checker
`monitoring_v11/audit_caddy_offline_candidate_v11.py` on the management
host. It passes current and in-memory candidate Caddyfile content over
stdin to a separate `caddy adapt` CLI process via Docker exec. It does
not print config or adapted JSON, does not reload/start Caddy, does not
write temp/prod files, and requires the existing Caddy container.

Passing results: BASELINE_ADAPT=PASS, CANDIDATE_ADAPT=PASS and
SIGNED_HEARTBEAT_ROUTE=EXACT_POST_ROUTE_PRESENT.
OTHER_EXISTING_ROUTES_REGRESSION=NOT_TESTED remains a blocker for rollout.
The final proxy must be reviewed as an offline candidate and obtain
explicit approval and a tested backup/rollback. Do not touch Maya hosts.


## 13. Offline Caddy regression diff gate (2026-11-03)

Read-only operator audit results:
- BASELINE_ADAPT=PASS; CANDIDATE_ADAPT=PASS.
- SIGNED_HEARTBEAT_ROUTE=EXACT_POST_ROUTE_PRESENT.
- LIVE_CADDYFILE_EDITED=NO; CADDY_RELOAD_OR_RESTART=NO.

The previous tool did not compare the OTHER routes. Next use
`monitoring_v11/audit_caddy_offline_regression_v11.py` together with its
sibling `audit_caddy_offline_candidate_v11.py` (both in same directory).
It adapts original and candidate Caddyfiles entirely IN MEMORY, locates
one candidate reverse_proxy guarded by exact `method POST` and exact
`path /api/control-room/v11/heartbeat`, removes only that route from a
copy of candidate adapted JSON, then requires the remaining adapted
JSON document to equal the original adapted JSON document exactly.
It prints verdicts only, never the Caddyfile or adapted JSON, and never
applies/reloads live Caddy. Unrecognized route structures or any difference
are BLOCKED / NOT_IDENTICAL_AFTER_STRIP. A passing result is
`REGRESSION_COMPARISON UNCHANGED_EXCEPT_NEW_POST_ROUTE`.

A passing *structural* diff is necessary but NOT sufficient for rollout:
real reverse-proxy startup, authenticated admin/session isolation,
existing payment flows, Docker DNS to new service, staging signed
heartbeat, DB restore, and rollback remain unverified. No Production
changes or Maya1 Agent deployment are authorized.

## 14. V11 adapted Caddy strict diff did not pass (operator 2026-11-03)

Observed from live read-only dry run:
- BASELINE_ADAPT=PASS and CANDIDATE_ADAPT=PASS.
- REGRESSION_COMPARISON=NOT_IDENTICAL_AFTER_STRIP.
- LIVE_CADDY_SHA256 was recorded separately for operator verification.
- No live Caddyfile editing/reload, no VPN probes, DEPLOYMENT_ALLOWED=NO.

This is NOT proof of a route collision or downtime. A possible cause is
Caddy's opaque route-group renumbering or nested route restructuring,
but this has NOT been established on live adapted JSON.

Next run the non-disclosing script
`monitoring_v11/audit_caddy_regression_diagnostic_v11.py`
next to existing `audit_caddy_offline_regression_v11.py` and
`audit_caddy_offline_candidate_v11.py`. It returns only safe structural
paths and categorical differences; no hostnames, upstreams or values.
It also reports whether existing routes differ only by an injective
renaming of opaque group IDs (`DIFF_ONLY_OPAQUE_GROUP_IDENTIFIERS=YES`).
Even that diagnostic does not authorize a Caddy reload: perform human
review of preserved grouping and order, backup and rollback first.

## 15. Verified root cause of the strict Caddy structural diff (operator)

2026-11-03 live, read-only diagnostic on the actual Caddyfile:
- BASELINE_AND_CANDIDATE_ADAPT=PASS.
- CANDIDATE_ROUTES_REMOVED=1.
- DIFF_ONLY_OPAQUE_GROUP_IDENTIFIERS=YES.
- Exactly two existing group label occurrences changed in the adapted JSON.
- No hostnames, credentials, route values or adapted JSON were printed.
- NO_CONFIG_CHANGES_NO_CADDY_RELOAD_NO_VPN_PROBES.

Next audited script: audit_caddy_group_equivalence_v11.py alongside
the previously audited audit_caddy_offline_regression_v11.py and
audit_caddy_offline_candidate_v11.py, all sharing one local directory.
This script requires a *bijective* old-to-new generated group ID map
(preserves group membership), preserves all other adapted JSON objects
and array/route order EXACTLY, requires one POST-only heartbeat route,
and confirms it shares the existing exclusive Caddy handle group.
Any conflict fails closed, and even PASS does NOT permit deployment.

## 16. Operator 2026-11-03: Caddy V11 structural-equivalence gate PASS

The real production, unmodified Caddyfile adaptation produced:
- BASELINE_ADAPT=PASS / CANDIDATE_ADAPT=PASS.
- STRUCTURAL_EQUIVALENCE UNCHANGED_EXCEPT_EXACT_POST_AND_GROUP_RENAMES.
- ORIGINAL_GROUP_MEMBERSHIP_PRESERVED=YES.
- ORIGINAL_ROUTE_ORDER_AND_HANDLERS_PRESERVED=YES.
- ORIGINAL_GROUP_IDS=1, GROUP_LABEL_OCCURRENCES_CHANGED=2.
- NO_CADDY_CONFIG_EDIT_OR_RELOAD; NO_VPN_NETWORK_PROBES.

**Next step, not deployment:** The temporary loopback HTTP integration
script `monitoring_v11/receiver_http_smoketest_v11.py` imports the reviewed
`receiver.py`, opens only an automatically assigned 127.0.0.1 port,
creates random HMAC key in memory and SQLite under tempfile, and
tests signed POST/duplicate/bad HMAC/forwarded scheme responses.
It shuts down its temporary HTTP server and deletes its test DB.
It makes ZERO contact to Maya hosts or the shared Docker Caddy.
GitHub Actions exercises the same isolated test. No real provider
quota, real VPN link, public TLS or Docker routing is verified by this.

After real host smoke test, proceed to a separate Docker staging
receiver test with no published host port, explicit resource limits
and a dedicated test DB; production Caddy remains unchanged until
approval and rollback/finance checks are verified.

## 17. Operator 2026-11-03: isolated real HTTP + Docker receiver smoke tests PASS

Operator-provided management-host terminal evidence, after commit bba523facdb56e9d87f113c5af267face36bc2e5:

1. Ran pinned receiver.py and receiver_http_smoketest_v11.py under
   /root/hesab-v11-offline-smoke on management host:
   LISTEN_INTERFACE=127.0.0.1_ONLY; VALID_SIGNED_POST=202;
   REPLAY=REJECTED; INVALID_SIGNATURE=401;
   NON_HTTPS_FORWARD_HEADER=403; EPHEMERAL_SQLITE_SAMPLES=1;
   SYNTHETIC_VPN_HEALTH=UNKNOWN.
2. Read-only Docker readiness: Docker 29.9.1; existing
   vpn-control-center_default network and both Compose files present;
   vpn-control-center app, customer-portal, sms-gateway and db healthy;
   shared darma-general-caddy-1 running; no host listener on :8199.
   python:3.12-slim was not cached, and was pulled for the next test.
3. Ran transient receiver on a DIFFERENT, newly created Docker
   --internal network, with no host port binding. Used an independent
   synthetic HMAC key and separate temporary SQLite; a second container
   sent the test traffic. Results:
   RECEIVER_HEALTH=202; HOST_PORT_PUBLICATION=NONE;
   DOCKER_INTERNAL_SIGNED_POST=202; DOCKER_REPLAY=REJECTED;
   DOCKER_INVALID_HMAC=401; SYNTHETIC_VPN_STATE=UNKNOWN;
   STAGING_SQLITE_SAMPLES=1; STAGING_SQLITE_REPLAYS=1;
   ISOLATED_DOCKER_TEST=PASS.
   Test shell used EXIT cleanup to remove the disposable receiver,
   isolated network and temporary directory; completed normally.

Evidence scope: these PASS results prove standalone HTTP HMAC behavior
and a cross-container private Docker network path only. They DO NOT
prove a shared production Docker-network route, actual TLS termination
through Caddy, existing finance/portal route non-regression, credentials
of real Maya hosts, provider quotas, or any operational VPN health.
The tests did not attach the new receiver to the live vpn-control-center
network or edit/reload production Caddy/finance/VPN services.

NEXT GATE: separately start ephemeral Caddy + receiver containers ONLY
on an isolated disposable Docker network, with a synthetic TLS site and
matching POST-only handle rule. Prove that TLS proxy forwards correct
scheme and exact-route requests while GET/other paths remain rejected.
Do not mount or edit the production Caddyfile, publish any host port,
or connect to Maya hosts. Before any shared-network/production rollout,
verify backup, independently restorable PostgreSQL archive, live UI
source drift, admin authorization and a reviewed rollback. No deploy approval.

## 18. Operator 2026-11-04: isolated Caddy HTTPS smoke test NOT READY

Operator ran pinned isolated test at commit 45aa66112341e806f5e1f42910c998489d409749.
Preparation passed: disposable internal Docker network created, no host ports,
existing local Caddy image selected, temporary HMAC key created.
The HTTPS readiness loop exhausted its attempts and raised
`RuntimeError: ISOLATED_CADDY_TLS_NOT_READY`. No signed test POST was
attempted and therefore real TLS-to-receiver behavior is NOT YET VERIFIED.
Prior independent HTTP and isolated cross-container Docker tests remain PASS.

The script's EXIT trap removed disposable resources; the first version
suppressed network error details and deleted the staging Caddy before logs
could be inspected. Do not attribute this failure to TLS, DNS, Caddy process,
resource limits or routing without diagnostic evidence.

Updated staging script at commit 6acd68d5320b27f8be1d16aeb777cef3c72d998b
prints categorized client readiness failure and isolated Caddy/receiver
container state plus synthetic-only Caddy startup log tail BEFORE cleanup.
Its Bash syntax CI is PASS, but successful real execution is still pending.
No live Caddyfile/reload, finance DB, Maya service, XUI or tunnel work approved.
