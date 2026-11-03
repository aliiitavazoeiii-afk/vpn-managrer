#!/usr/bin/env python3
"""Conservative, non-disclosing alpha-equivalence audit for Caddy V11.

Reads live Caddyfile; invokes two in-memory caddy adapt evaluations through
the existing Docker container. NEVER calls admin API, reloads, writes
configuration, contacts a VPN or emits any configuration values.
Verifies exactly one new POST-only route and bijective relabeling of generated
group names, while preserving original route ordering and group membership.
NOT deployment approval.
"""
import hashlib
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "audit_caddy_offline_regression_v11.py"
SPEC = importlib.util.spec_from_file_location("v11_caddy_regression_alpha", SOURCE)
REG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REG)

def group_alpha_equivalent(old, candidate):
    """Require exact old JSON equality under one-to-one group renaming."""
    old_to_new = {}
    new_to_old = {}
    differences = 0

    def compare(a, b):
        nonlocal differences
        if type(a) is not type(b):
            return False
        if isinstance(a, dict):
            if set(a) != set(b):
                return False
            for key in sorted(a):
                x, y = a[key], b[key]
                if key == "group" and isinstance(x, str) and isinstance(y, str):
                    if x in old_to_new and old_to_new[x] != y:
                        return False
                    if y in new_to_old and new_to_old[y] != x:
                        return False
                    old_to_new[x], new_to_old[y] = y, x
                    if x != y:
                        differences += 1
                elif not compare(x, y):
                    return False
            return True
        if isinstance(a, list):
            return len(a) == len(b) and all(compare(x, y) for x, y in zip(a, b))
        return a == b

    return compare(old, candidate), len(old_to_new), differences

def find_heartbeat_routes(obj):
    """Identify exact-match route nodes without exposing any values."""
    found = []
    def visit(x):
        if isinstance(x, dict):
            if "match" in x and REG.exact_heartbeat_match(x):
                found.append(x)
            for key, value in x.items():
                if key != "upstreams":
                    visit(value)
        elif isinstance(x, list):
            for el in x:
                visit(el)
    visit(obj)
    return found

def evaluate(old, new):
    if REG.has_upstream(old):
        return {"pass":False, "reason":"BASELINE_HAS_RECEIVER"}
    routes = find_heartbeat_routes(new)
    if len(routes) != 1:
        return {"pass":False, "reason":"HEARTBEAT_MATCH_COUNT_UNEXPECTED"}
    if not REG.has_upstream(routes[0]):
        return {"pass":False, "reason":"HEARTBEAT_UPSTREAM_WRONG"}
    if REG.compare(old,new) not in ("UNCHANGED_EXCEPT_NEW_POST_ROUTE",
                                     "NOT_IDENTICAL_AFTER_STRIP"):
        return {"pass":False, "reason":"STRICT_ROUTE_GATE_BLOCKED"}
    reduced, count = REG.strip_one_heartbeat_route(new)
    if count != 1:
        return {"pass":False, "reason":"HEARTBEAT_REMOVAL_NOT_UNIQUE"}
    is_equal, groups, diffs = group_alpha_equivalent(old,reduced)
    if not is_equal:
        return {"pass":False, "reason":"NON_GROUP_OR_MEMBERSHIP_DIFFERENCE"}
    return {"pass":True,"reason":"UNCHANGED_EXCEPT_EXACT_POST_AND_GROUP_RENAMES",
            "old_group_count":groups,"group_values_changed":diffs}

def main():
    print("HESAB_V11_CADDY_GROUP_EQUIVALENCE_AUDIT")
    f = REG.candidate_module.CADDYFILE
    if not f.is_file():
        print("CADDYFILE=UNAVAILABLE")
        return 2
    raw = f.read_bytes()
    print("LIVE_CADDY_SHA256",hashlib.sha256(raw).hexdigest())
    try:
        text = raw.decode("utf-8")
        proposed = REG.candidate_module.candidate(text)
        old = REG.candidate_module.adapt(text)
        new = REG.candidate_module.adapt(proposed)
        result = evaluate(old,new)
    except (OSError,ValueError,UnicodeError,RuntimeError):
        print("OFFLINE_ADAPT_OR_REVIEW=BLOCKED")
        print("DEPLOYMENT_ALLOWED=NO")
        return 3
    print("BASELINE_ADAPT=PASS")
    print("CANDIDATE_ADAPT=PASS")
    print("STRUCTURAL_EQUIVALENCE",result["reason"])
    if result["pass"]:
        print("ORIGINAL_GROUP_MEMBERSHIP_PRESERVED=YES")
        print("ORIGINAL_ROUTE_ORDER_AND_HANDLERS_PRESERVED=YES")
        print("ORIGINAL_GROUP_IDS",result["old_group_count"])
        print("GROUP_LABEL_OCCURRENCES_CHANGED",result["group_values_changed"])
    else:
        print("ORIGINAL_GROUP_MEMBERSHIP_PRESERVED=UNVERIFIED")
        print("ORIGINAL_ROUTE_ORDER_AND_HANDLERS_PRESERVED=UNVERIFIED")
    print("NO_CADDY_CONFIG_EDIT_OR_RELOAD")
    print("NO_VPN_NETWORK_PROBES")
    print("DEPLOYMENT_ALLOWED=NO")
    return 0 if result["pass"] else 4

if __name__ == "__main__":
    raise SystemExit(main())
