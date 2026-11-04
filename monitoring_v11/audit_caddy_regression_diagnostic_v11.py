#!/usr/bin/env python3
"""Strict redacted diagnosis of a Caddy adapt regression mismatch (read-only).

Runs the SAME in-memory baseline/candidate adaptation, then reports only
structural-difference categories and paths containing allowlisted field names.
Never outputs config values, upstreams, hostnames, domain names, IPs, secrets,
or the adapted JSON. No modifications, reloads, restarts, or network probes.
"""
from collections import Counter
import copy
import hashlib
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE / "audit_caddy_offline_regression_v11.py"
SPEC = importlib.util.spec_from_file_location("caddy_regression_v11", ORIGINAL)
REG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REG)

SAFE = {
    "apps","http","servers","routes","handle","handler","match",
    "group","terminal","upstreams","dial","path","method","host",
    "tls","automatic_https","encode","encodings","request_body",
    "headers","request_headers","response_headers","status_code",
    "errors","logs","log","listener_wrappers","listen","subroute",
}
MAX_REPORT = 14

def canonical_group_ids(document):
    """Rename opaque group IDs by first occurrence; preserve membership."""
    result = copy.deepcopy(document)
    groups = {}
    def visit(value):
        if isinstance(value, dict):
            # Sorting keys makes renumbering independent of serialized key order.
            for key in sorted(value):
                item = value[key]
                if key == "group" and isinstance(item, str):
                    if item not in groups:
                        groups[item] = "G" + str(len(groups))
                    value[key] = groups[item]
                else:
                    visit(item)
        elif isinstance(value, list):
            for v in value:
                visit(v)
    visit(result)
    return result

def structural_differences(left, right, limit=MAX_REPORT):
    """Opaque categories/paths only; never print user content."""
    result = []
    totals = Counter()
    def rec(a,b,path):
        if len(result) >= limit:
            return
        if type(a) is not type(b):
            typ = "TYPE_CHANGED"
            totals[typ] += 1
            result.append((path,typ))
            return
        if isinstance(a, dict):
            for key in sorted(set(a)|set(b)):
                shown = key if key in SAFE else "<redacted_key>"
                child = path + "/" + shown
                if key not in a or key not in b:
                    typ = "FIELD_ADDED_OR_REMOVED"
                    totals[typ] += 1
                    result.append((child, typ))
                else:
                    rec(a[key],b[key],child)
                if len(result) >= limit:
                    break
        elif isinstance(a,list):
            if len(a)!=len(b):
                typ="ARRAY_LENGTH_CHANGED"
                totals[typ]+=1
                result.append((path,typ))
            for i in range(min(len(a),len(b))):
                rec(a[i],b[i],path+"["+str(i)+"]")
                if len(result)>=limit:
                    break
        elif a != b:
            typ = "OPAQUE_GROUP_ID_CHANGED" if path.endswith("/group") else "VALUE_CHANGED"
            totals[typ]+=1
            result.append((path,typ))
    rec(left,right,"ROOT")
    return result,totals

def analyze(old, new):
    if REG.has_upstream(old):
        return {"verdict":"INVALID_BASELINE","removed":0,"only_groups":False,
                "diffs":[]}
    status = REG.compare(old,new)
    clean, removed = REG.strip_one_heartbeat_route(new)
    if removed!=1:
        return {"verdict":status,"removed":removed,"only_groups":False,
                "diffs":[]}
    only_groups = (clean != old and
                   canonical_group_ids(clean) == canonical_group_ids(old))
    diffs,totals = structural_differences(old,clean)
    return {"verdict":status,"removed":removed,"only_groups":only_groups,
            "diffs":diffs,"totals":totals}

def main():
    print("CADDY_V11_STRUCTURAL_REGRESSION_DIAGNOSTIC")
    f = REG.candidate_module.CADDYFILE
    if not f.is_file():
        print("BASELINE_CONFIG=UNAVAILABLE")
        return 2
    original_bytes=f.read_bytes()
    print("LIVE_CADDY_SHA256", hashlib.sha256(original_bytes).hexdigest())
    try:
        original=original_bytes.decode("utf8")
        proposed=REG.candidate_module.candidate(original)
        before=REG.candidate_module.adapt(original)
        after=REG.candidate_module.adapt(proposed)
        result=analyze(before,after)
    except (UnicodeError,OSError,ValueError,RuntimeError):
        print("ADAPT_OR_COMPARE=BLOCKED")
        print("DEPLOYMENT_ALLOWED=NO")
        return 3
    print("BASELINE_AND_CANDIDATE_ADAPT=PASS")
    print("INITIAL_STRICT_COMPARISON",result["verdict"])
    print("CANDIDATE_ROUTES_REMOVED",result["removed"])
    print("DIFF_ONLY_OPAQUE_GROUP_IDENTIFIERS",
          "YES" if result["only_groups"] else "NO")
    print("STRUCTURAL_DIFFERENCES_SHOWN",len(result["diffs"]))
    for n,(path,category) in enumerate(result["diffs"],1):
        # Path is built ONLY from allowed keys or redacted placeholders.
        print("DIFF_"+str(n),category,path)
    print("NO_CONFIG_CHANGES_NO_CADDY_RELOAD_NO_VPN_PROBES")
    print("DEPLOYMENT_ALLOWED=NO")
    # Diagnostic only. Even group-only differences require human review.
    return 0

if __name__=="__main__":
    raise SystemExit(main())
