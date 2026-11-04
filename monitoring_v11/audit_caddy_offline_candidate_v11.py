#!/usr/bin/env python3
"""Offline V11 Caddy candidate adaptation. No live config edits or reloads.

Read the actual locally-modified Caddyfile and pass BOTH old config and
in-memory augmented candidate over stdin to 'caddy adapt' INSIDE the existing
Caddy container. Never prints Caddyfile, hostnames, IPs, upstreams, secrets,
raw Caddy errors, or adapted JSON. Never calls Caddy admin API.
"""
import json
from pathlib import Path
import re
import subprocess

CADDYFILE = Path("/opt/darma-general/Caddyfile")
CONTAINER = "darma-general-caddy-1"
HEARTBEAT_PATH = "/api/control-room/v11/heartbeat"
INTERNAL_UPSTREAM = "telemetry-receiver-v11:8199"
BLOCK = (
    "\n    @tv11SignedHeartbeat {\n"
    "        path /api/control-room/v11/heartbeat\n"
    "        method POST\n"
    "    }\n"
    "    handle @tv11SignedHeartbeat {\n"
    "        reverse_proxy telemetry-receiver-v11:8199\n"
    "    }\n"
)

def candidate(original):
    if "@tv11SignedHeartbeat" in original or INTERNAL_UPSTREAM in original:
        raise ValueError("V11 matcher already exists")
    found = list(re.finditer(r"(?m)^hesab\.[^\s{}]+\s*\{[ \t]*$", original))
    if len(found) != 1:
        raise ValueError("expected exactly one Hesab site")
    pos = found[0].end()
    return original[:pos] + BLOCK + original[pos:]

def adapt(source):
    # Parse in a separate, brief Caddy CLI process. No load/reload/admin API.
    cmd = ["docker", "exec", "-i", CONTAINER, "caddy", "adapt",
           "--config", "-", "--adapter", "caddyfile"]
    try:
        p = subprocess.run(cmd, input=source, text=True, capture_output=True,
                           timeout=18, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(type(exc).__name__) from None
    if p.returncode != 0:
        raise RuntimeError("caddy_adapt_exit_"+str(p.returncode))
    try:
        return json.loads(p.stdout)
    except ValueError:
        raise RuntimeError("invalid_adapter_json") from None

def normalize_routes(document):
    """Check exact POST-only reverse proxy in adapted JSON without disclosure."""
    matches = []
    def walk(node, inherited=()):
        if isinstance(node, dict):
            matcher = node.get("match")
            route_path = inherited
            if isinstance(matcher, list):
                route_path = inherited + tuple(x for x in matcher if isinstance(x, dict))
            if node.get("handler") == "reverse_proxy":
                for entry in node.get("upstreams", []):
                    if isinstance(entry, dict) and entry.get("dial") == INTERNAL_UPSTREAM:
                        matches.append(route_path)
            for key, value in node.items():
                if key not in ("match", "upstreams"):
                    walk(value, route_path)
        elif isinstance(node, list):
            for item in node:
                walk(item, inherited)
    walk(document)
    if len(matches) != 1:
        return False, "MISSING_OR_DUPLICATE_BACKEND"
    ancestor = matches[0]
    found_path = any(x.get("path") == [HEARTBEAT_PATH] for x in ancestor)
    found_method = any(x.get("method") == ["POST"] for x in ancestor)
    if not found_path or not found_method:
        return False, "MATCH_NOT_EXACT_POST"
    return True, "EXACT_POST_ROUTE_PRESENT"

def main():
    print("HESAB_V11_OFFLINE_CADDY_CANDIDATE_AUDIT")
    if not CADDYFILE.is_file():
        print("SOURCE=UNAVAILABLE")
        return 2
    source = CADDYFILE.read_text(encoding="utf-8")
    try:
        proposed = candidate(source)
    except ValueError:
        print("CANDIDATE_BUILD=BLOCKED")
        return 3
    print("LIVE_CADDYFILE_EDITED=NO")
    print("CADDY_RELOAD_OR_RESTART=NO")
    print("NETWORK_REQUESTS_TO_VPN=NONE")
    try:
        before = adapt(source)
        print("BASELINE_ADAPT=PASS")
        after = adapt(proposed)
        print("CANDIDATE_ADAPT=PASS")
    except RuntimeError:
        print("ADAPT=FAIL_OR_UNAVAILABLE")
        return 4
    ok, verdict = normalize_routes(after)
    print("SIGNED_HEARTBEAT_ROUTE="+verdict)
    print("OTHER_EXISTING_ROUTES_REGRESSION=NOT_TESTED")
    print("DEPLOYMENT_ALLOWED=NO")
    return 0 if ok else 5

if __name__ == "__main__":
    raise SystemExit(main())
