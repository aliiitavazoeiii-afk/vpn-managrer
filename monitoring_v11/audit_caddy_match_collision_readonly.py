#!/usr/bin/env python3
"""Read-only, non-disclosing Caddy v2 route collision audit.

NO network, Docker, subprocess, configuration edits or runtime probes.
Emit only categorical results about a proposed new exact POST heartbeat.
If an existing matcher isn't a simple path expression, return UNKNOWN.
"""
import re
from pathlib import Path

CADDY = Path("/opt/darma-general/Caddyfile")
TARGET = "/api/control-room/v11/heartbeat"

def test_pattern(pattern, target=TARGET):
    """Conservative subset of Caddy path matching; unknown must block deploy."""
    if pattern == "*" or pattern == "/*":
        return "OVERLAP"
    if not re.fullmatch(r"/[A-Za-z0-9_.*~/-]+", pattern or ""):
        return "UNKNOWN"
    if pattern.count("*") == 0:
        return "OVERLAP" if pattern == target else "CLEAR"
    # Only simple trailing glob is modeled; Caddy other pattern syntax => unknown.
    if pattern.count("*") == 1 and pattern.endswith("*"):
        return "OVERLAP" if target.startswith(pattern[:-1]) else "CLEAR"
    return "UNKNOWN"

def evaluate(contents):
    sections=[]
    depth=0
    current=None
    for line in contents.splitlines():
        stripped=line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if depth == 0 and stripped.endswith("{"):
            current={"is_hesab":bool(re.search(r"\bhesab\b",stripped,re.I)),
                     "directives":[]}
            sections.append(current)
        elif depth == 1 and current and current["is_hesab"] and stripped != "}":
            current["directives"].append(stripped)
        depth += line.count("{")-line.count("}")
        if depth == 0:
            current=None
        elif depth < 0:
            return {"structure":"INVALID_BRACES","handle_path":"UNKNOWN",
                    "redirect":"UNKNOWN","ready":False}
    sites=[s for s in sections if s["is_hesab"]]
    if len(sites)!=1 or depth!=0:
        return {"structure":"UNEXPECTED_SITE_LAYOUT","handle_path":"UNKNOWN",
                "redirect":"UNKNOWN","ready":False}
    commands=sites[0]["directives"]
    # The audited 2026-11-03 production topology: exactly one path handler,
    # one catchall handler, and one named redirect. Unknown => no rollout.
    hp=[x for x in commands if re.match(r"^handle_path\s",x)]
    hd=[x for x in commands if re.match(r"^handle(?:\s|\{)",x)]
    redirect=[x for x in commands if re.match(r"^redir(?:\s|$)",x)]
    if len(hp)!=1 or len(hd)!=1 or len(redirect)!=1:
        return {"structure":"UNEXPECTED_HANDLER_COUNT",
                "handle_path":"UNKNOWN","redirect":"UNKNOWN","ready":False}
    tokens=hp[0].replace("{"," ").split()
    handler_match=test_pattern(tokens[1]) if len(tokens)>=2 else "UNKNOWN"
    # Redirect with a named matcher: parse only simple oneline '@name path /foo/*'
    # Other match types (header, regexp, expression) require a human review.
    rd=redirect[0].split()
    if len(rd)>=2 and rd[1].startswith("@"):
        label=rd[1]
        matcher=[x for x in commands if x.startswith(label+" ")]
        if len(matcher)!=1:
            redirect_state="UNKNOWN"
        else:
            mt=matcher[0].split()
            if len(mt)==3 and mt[1]=="path":
                redirect_state=test_pattern(mt[2])
            else:
                redirect_state="UNKNOWN"
    elif len(rd)>=2 and rd[1].startswith("/"):
        redirect_state=test_pattern(rd[1])
    else:
        redirect_state="UNKNOWN"
    # The parser does not claim readiness when it could not identify a
    # named matcher or when the generic Caddyfile adapter hasn't been checked.
    return {"structure":"EXPECTED_SHAPE","handle_path":handler_match,
            "redirect":redirect_state,
            "ready":handler_match=="CLEAR" and redirect_state=="CLEAR"}

def main():
    if not CADDY.is_file():
        print("AUDIT_RESULT CADDYFILE_MISSING")
        raise SystemExit(2)
    document=CADDY.read_text(encoding="utf8")
    outcome=evaluate(document)
    print("CADDYFILE_MATCH_COLLISION_V11")
    print("EXPECTED_ROUTE_METHOD POST")
    print("EXPECTED_ROUTE_TYPE EXACT")
    print("CADDY_LAYOUT",outcome["structure"])
    print("EXISTING_HANDLE_PATH_OVERLAP",outcome["handle_path"])
    print("EXISTING_REDIRECT_OVERLAP",outcome["redirect"])
    print("AUTOMATIC_ROUTING_PROOF","POSSIBLE_FURTHER_VALIDATION" if outcome["ready"]
          else "BLOCKED_REQUIRE_REVIEW")
    print("NO_CADDY_CHANGES_NO_NETWORK_REQUESTS")
    # Deliberately EXIT 0 for UNKNOWN: distinguish diagnostic from deployment guard.
if __name__=="__main__":
    main()
