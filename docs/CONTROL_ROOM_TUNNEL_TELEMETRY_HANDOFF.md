# Hesab VPN Control Room — Tunnel HA and SMS Integration Handoff
Date: 2026-10-27
Repository: aliitavazoeiii-afk/vpn-managrer
Tunnel repository: aliiitavazoeiii-afk/frp-tunnel, branch naive-mieru-live-safe-v1

## STATUS / READ FIRST
This is an IMPLEMENTATION HANDOFF, not a claim the panel UI or SMS hookup is deployed.
The user wants to register several Iran VPN servers in the Persian RTL اتاق کنترل and receive phone SMS when either Naive or Mieru becomes unavailable, is auto-restarted, or quarantined. After sustained recovery, tunnel returns to approximately 50/50 new connections. The Iran agent and interface are independent: the tunnel must fail over locally even if panel/SMS/network is inaccessible.

**CRITICAL DATA WARNING**: Current vpn-managrer/install.sh destroys the live Docker database volume using docker compose down -v, deletes /opt/vpn-control-center and regenerates credentials. NEVER execute this installer on production. The production panel contains customer subscriptions, debt/payment history and may have uncommitted live customizations (including SMS); do not reset, reseed or overwrite them.

## CURRENT PROJECT FACTS REVIEWED
- The existing main repo contains Dockerfile, docker-compose.yml, encrypted seed, packed/main.* (base64/gzip Python) and additive patches/*.py.
- Dockerfile reconstructs app/main.py from packed/main.* and appends many patches. It does NOT contain a straightforward standalone main.py in GitHub. Read and reconstruct current implementation before changing.
- Control Room route /control-room and placeholder template originate in patches/core_workspace.py. Nav item already exists, placeholder says room ready but no features.
- Existing production may be ahead of GitHub. Reconcile against live source/containers before deployment.
- User reports an existing SMS application; code/provider and operational credentials were NOT verified from inspected repository files. Inspect deployed SMS feature and integrate with it; do not invent a provider.
- Current server maya11: x-ui VLESS REALITY :443 -> Mihomo dispatcher SOCKS :7990 -> Naive :7991 XUDP-TCP / :7993 direct, Mieru :7992 XUDP-TCP / :7994 direct.
- Current foreign IPv4s Naive 141.11.181.50 and Mieru 141.11.181.51. These are currently observed values only; never hardcode them as permanent inventory.

## HA AGENT SOURCE OF TRUTH
GitHub repository: aliiitavazoeiii-afk/frp-tunnel, branch naive-mieru-live-safe-v1
Read complete:
- dual-trust-mieru/nm-ha-agent.py
- dual-trust-mieru/nm-ha-install.sh
- dual-trust-mieru/nm-ha-telemetry.py
- dual-trust-mieru/nm-ha-test.py
- dual-trust-mieru/nm-helper.sh
- dual-trust-mieru/nm-live-audit.py

Iran HA locally tests 3 independent application probes for each lane (direct HTTP204, split HTTP204, Telegram via split), every systemd timer cycle. It marks a lane DOWN only if all 3 probes fail; 2 consecutive DOWN cycles + peer healthy cause exactly one role-local carrier restart per incident and immediate re-probe. If still bad, Selector group DUAL is set to healthy peer using authenticated Mihomo PUT /proxies/DUAL (no dispatcher restart at the moment of failover). When BOTH healthy for 3 cycles, it resumes DUAL-AUTO 50/50 round-robin; if both bad, never blindly rotate between failed carriers. Temporary partial errors stay DEGRADED, avoiding false bans. This is best-effort protection, NOT a guarantee no interrupted sessions or proof of censorship.

Important: original dispatcher has DUAL type load-balance and cannot be selected by PUT /proxies/DUAL. One-time explicit bootstrap creates DUAL-AUTO load-balance and DUAL selector [DUAL-AUTO,XUDP-TRUST,XUDP-MIERU]. The initial /configs reload MAY interrupt connections. Bootstrap refuses when there are active dispatcher flows unless operator explicitly enables one-time live reload. Later selection changes use only PUT /proxies/DUAL. The panel MUST NOT access the local Controller (127.0.0.1:19090) or its secret.

Root-only state files on Iran:
- /var/lib/dual-trust-mieru/naive-mieru/ha/status.json
- /var/lib/dual-trust-mieru/naive-mieru/ha/state.json
- /var/lib/dual-trust-mieru/naive-mieru/ha/events.jsonl
- /etc/dual-trust-mieru/ha-telemetry.json: generated config and secret, never commit.

## TELEMETRY SECURITY CONTRACT (one-way Iran -> Panel HTTPS)
After registering an Iran server in the panel, panel creates unique stable server_id and secure random >=32-character per-server shared secret (encrypted at rest, never in frontend JS except one-time reveal at registration). Put config on Iran with chmod 0600:

    {
      "endpoint": "https://hesab.filmjadiid.ir/api/control-room/heartbeat",
      "server_id": "maya11",
      "secret": "UNIQUE_RANDOM_SECRET_FROM_PANEL_NOT_THIS_STRING"
    }

Iran agent sends POST application/json JSON body from status.json, but replaces payload.server_id with configured identity. Request headers:
- X-NM-Server-ID: <id>
- X-NM-Timestamp: <UnixEpochSeconds>
- X-NM-Signature: sha256=<lowercase hex HMAC-SHA256(secret, ASCII(timestamp) + '.' + raw HTTP BODY bytes)>
- Content-Type: application/json

On panel:
- TLS required; one registered record per server_id, constant-time HMAC comparison on RAW body (before JSON decode), timestamp tolerance <=300s, size <=128KiB, per-server rate limits and optional IP restrictions. Reject unknown/revoked server and replay or stale requests. Authorize UI to admin only.
- Persist snapshots/events transactionally with immutable unique (server_id, event_seq). Sender includes last_event_seq and recent_events, so retries must be idempotent and yield no duplicate alerts.
- Payload status schema version 1: top-level schema, server_id, updated_at, policy, automatic_failover, pool_selection, roles.naive and roles.mieru, last_event_seq, recent_events. Each role includes status, health, foreign_ip, failed_cycles, healthy_cycles, last_restart_at, probes.direct/split/telegram {ok,ms,code}, incident.
- Status examples: HEALTHY, DEGRADED, SUSPECT, QUARANTINED, RECOVERING, MONITOR_ONLY; distinguish STALE if no heartbeat >3 minutes. Do NOT label filtered categorically solely from failed HTTP probes.
- Pool: DUAL-AUTO = split selection, XUDP-TRUST = Naive only, XUDP-MIERU = Mieru only. If status.policy != ARMED, show read-only monitor only, not automated failover.
- Browser should only fetch backend Control Room API every 10-20 seconds or SSE; never call Mihomo Controller directly.
- Outbound telemetry failing MUST NOT change local HA behavior; handle retry on next systemd timer tick.

## DATABASE/CONTROL ROOM RECOMMENDATIONS
Use additive tables or models, **no changes to existing accounting/payment/subscription semantics**:
- control_room_servers (server_id UNIQUE, name, public_ip optional, encrypted_secret, enabled, last_seen_at, created_at, updated_at)
- control_room_role_status (server_fk, role, status, health, foreign_ip, latency, last_restart, selected_route, last_update)
- control_room_events (server_fk, event_seq UNIQUE per server, at, event_type, role, detail)
- control_room_alerts (incident/event key UNIQUE, server_fk, state, attempts, last_attempt, sent_at, SMS provider id)
- alert_settings (SMS recipients, severity, dedupe windows, quiet hours policy)

Persian RTL UI /control-room: aggregate counters for online/degraded/stale Iran servers; separate responsive cards for each Iran server with current Naive and Mieru lanes, IPs, last probe response times, status badges, pool mode, last restart and incident timeline; server register/revoke/rotate-secret flow; SMS test button (explicit action only), notification preferences, stale state and last refresh. Do not put red FILTERED when only health probes failed; use قطع مسیر / نیاز به بررسی. Allow many Iran servers registered and shown at once.

## SMS INTEGRATION REQUIREMENTS
Reuse actual existing SMS app/provider/auth, which MUST be inspected (not guessed). Notify:
- confirmed QUARANTINED or POOL_SELECTION_CHANGED to peer -> one SMS with Iran name + failed lane + active lane + time;
- BOTH lanes unresponsive -> critical SMS (including no fallback), only after confirmation;
- recovery to DUAL-AUTO -> one recovery SMS;
- 3 minutes without heartbeat -> separate STALE telemetry warning (not necessarily VPN outage).
Deduplicate by server_id + incident/event key, persist delivery state transactionally, apply cooldown/retry/backoff, never send each health tick. Alert via existing app's SMS integration; SMS transport can be unavailable independently from tunneling.

## SAFE PANEL DEPLOYMENT PLAN FOR ANOTHER CHAT
1. Read this document AND complete existing repo (Dockerfile, packed/main.*, patches/core_workspace.py, auth, SMS app). Query production version and currently running Compose. Reconcile if main branch is stale.
2. Take tested PostgreSQL backup (pg_dump), env config backup, rollback image; check migration tooling.
3. Implement additive API/router/models and UI patch on a separate branch. Test HMAC signature, bad/late/replayed signatures, concurrent/deduped events, unknown server_id, stale heartbeat, SMS dedup, auth and rate limiting; test accounting regressions.
4. Stage on a separate environment with a fake signed heartbeat + fake SMS recipient. Confirm paid users, debts, portal and payment history unchanged.
5. Deploy app service only after validation; NEVER run root install.sh or docker compose down -v. Never delete seed/database.
6. Register maya11 in panel, create unique secret, copy its telemetry JSON as 0600 into Iran (via secret channel), enable nm-ha-telemetry.timer, test one heartbeat, THEN enable SMS alerts.
7. To onboard future Iran servers, install same agent + unique sender keys, register in Control Room.
8. No direct SSH, restart, IP blocking or remote controlling routing from web UI in this milestone. Local HA stays authoritative.

## VERIFIED PRODUCTION FIELD EVENT (maya11, 2026-10-27 UTC; user terminal logs)
This event occurred AFTER the first production bootstrap/HA timer activation and is operational evidence, not a synthetic simulation.
- Iran bootstrap confirmed DUAL Selector -> DUAL-AUTO; `nm-ha.timer` enabled and active; status.policy=ARMED.
- 15:15:32 UTC: Naive HEALTHY -> SUSPECT.
- 15:16:17 UTC: agent event `RESTARTING_CARRIER` role=naive, detail `2 consecutive full-path failures; peer healthy`.
- 15:16:22 UTC: `CARRIER_RECOVERED_AFTER_RESTART` role=naive. No selector-quarantine event, as local restart solved probe failure.
- 15:17:53 UTC: `ROLE_RECOVERED`, Naive RECOVERING -> HEALTHY.
- 15:20:12 and 15:27:52 UTC: further isolated Naive SUSPECT transitions, returning HEALTHY after one timer cycle. Mieru stayed HEALTHY throughout shown HA logs.
- 60-second flow audit afterward: 349 Naive + 351 Mieru newly observed flows (49.9/50.1%); sampled byte deltas Naive 19.94 MiB (19.2%), Mieru 84.02 MiB (80.8%). Connection count vs bytes diverged considerably; MUST render separately and NOT claim byte-balanced.
- Synthetic HTTP204 tests after incident: Naive :7991 6/6 pass avg 409ms, Mieru :7992 6/6 pass avg 635ms. Successful small synthetic probes don't prove sustained application quality.
- Status at 15:30:59 UTC: DUAL-AUTO, both HEALTHY; Naive incident=1, last_restart_at=2026-10-27T15:16:17+00:00. HA showed 22 total event sequence count including repeated short SUSPECT transitions.
- The logs prove *automatic role-local restart* worked once, but DO NOT prove a failed-restart -> quarantine -> Mieru-only transition, and do NOT validate SMS integration (not yet connected).
- Design Control Room to distinguish HEALTHY (currently passing probes), intermittently unstable / recurring SUSPECT, and QUARANTINED. Add alert rules for repeated flapping within an hour without duplicate SMS spam. Alert for actual role restart event if useful; never label every transient SUSPECT as proven filtering.

## DIRECT PROMPT TO PASTE INTO NEXT CHAT
Continue Hesab VPN panel in aliiitavazoeiii-afk/vpn-managrer. Before ANY modification, completely read docs/CONTROL_ROOM_TUNNEL_TELEMETRY_HANDOFF.md plus the current real production panel and SMS app. Implement a non-destructive multi-Iran Control Room using the signed heartbeat contract, live Naive/Mieru status, persisted events and deduped SMS notifications via the existing provider. Read the latest HA implementation in frp-tunnel branch naive-mieru-live-safe-v1. NEVER run install.sh or reset customer/payment DB. Verify with staging and backups before deployment.
