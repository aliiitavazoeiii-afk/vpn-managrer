#!/usr/bin/env python3
"""Offline strict regression guard for a Caddy telemetry route.

Reads the actual live Caddyfile, adapts both versions IN MEMORY through a
separate caddy adapt CLI, then removes exactly one candidate route and compares
the complete remaining adapted document with the baseline. Does not print any
Caddyfile, JSON, domain, IP, upstream, redirect destination or secrets.
Does not edit any config, contact endpoints, or reload Caddy. Fail closed.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

source = Path(__file__).with_name("audit_caddy_offline_candidate_v11.py")
spec = importlib.util.spec_from_file_location("hesab_v11_candidate",source)
candidate_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate_module)


def has_upstream(node):
    if isinstance(node, dict):
        if node.get("handler") == "reverse_proxy":
            for u in node.get("upstreams", []):
                if isinstance(u, dict) and u.get("dial") == candidate_module.INTERNAL_UPSTREAM:
                    return True
        return any(has_upstream(v) for k,v in node.items() if k not in ("upstreams",))
    if isinstance(node, list):
        return any(has_upstream(v) for v in node)
    return False


def exact_heartbeat_match(route):
    items = route.get("match")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        return False
    m = items[0]
    return (m.get("path") == [candidate_module.HEARTBEAT_PATH]
            and m.get("method") == ["POST"]
            and set(m) == {"path", "method"})


def strip_one_heartbeat_route(document):
    """Return (remaining_document, matched_route_count). Never change input."""
    clone = copy.deepcopy(document)
    removed = 0

    def traverse(value):
        nonlocal removed
        if isinstance(value, dict):
            for k, v in list(value.items()):
                if k == "routes" and isinstance(v, list):
                    kept = []
                    for route in v:
                        if (isinstance(route, dict) and
                            exact_heartbeat_match(route) and has_upstream(route)):
                            removed += 1
                        else:
                            traverse(route)
                            kept.append(route)
                    value[k] = kept
                else:
                    traverse(v)
        elif isinstance(value, list):
            for item in value:
                traverse(item)

    traverse(clone)
    return clone, removed


def compare(old, new):
    # Explicit same upstream count, no duplicates. Preserve non-candidate config.
    if has_upstream(old):
        return "BASELINE_ALREADY_CONTAINS_RECEIVER"
    okay, _ = candidate_module.normalize_routes(new)
    if not okay:
        return "NEW_ROUTE_NOT_EXACT_POST"
    remaining, removed = strip_one_heartbeat_route(new)
    if removed != 1:
        return "CANDIDATE_ROUTE_COUNT_NOT_ONE"
    if remaining == old:
        return "UNCHANGED_EXCEPT_NEW_POST_ROUTE"
    return "NOT_IDENTICAL_AFTER_STRIP"


def main():
    print("HESAB_V11_OFFLINE_CADDY_REGRESSION")
    f = candidate_module.CADDYFILE
    if not f.is_file():
        print("CADDYFILE=NOT_FOUND")
        return 2
    raw = f.read_bytes()
    print("LIVE_CADDY_SHA256", hashlib.sha256(raw).hexdigest())
    try:
        original = raw.decode("utf8")
        proposed = candidate_module.candidate(original)
        old = candidate_module.adapt(original)
        newer = candidate_module.adapt(proposed)
    except (UnicodeError, OSError, ValueError, RuntimeError):
        print("ADAPT=BLOCKED")
        print("DEPLOYMENT_ALLOWED=NO")
        return 3
    print("BASELINE_ADAPT=PASS")
    print("CANDIDATE_ADAPT=PASS")
    verdict = compare(old, newer)
    print("REGRESSION_COMPARISON", verdict)
    print("NO_CADDY_CONFIG_EDIT_OR_RELOAD")
    print("NO_VPN_NETWORK_PROBES")
    print("DEPLOYMENT_ALLOWED=NO")
    # Exit 0 for a definitive structural check; NOT installation approval.
    return 0 if verdict == "UNCHANGED_EXCEPT_NEW_POST_ROUTE" else 4

if __name__ == "__main__":
    raise SystemExit(main())
