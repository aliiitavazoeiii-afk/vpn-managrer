#!/usr/bin/env python3
"""Redacted, conservative Caddy matcher audit. READS ONLY local Caddyfile.

No imports/calls of Docker, socket, subprocess, requests; prints no hostnames,
redirect targets, matcher identifiers, IP addresses, secrets or raw line values.
UNCERTAIN results MUST NOT authorize a deployment.
"""
from pathlib import Path
import re

PATH = Path("/opt/darma-general/Caddyfile")
HEARTBEAT = "/api/control-room/v11/heartbeat"
METHOD = "POST"

def path_check(glob):
    if not isinstance(glob, str) or not re.fullmatch(r"/[a-zA-Z0-9._~/*-]+",glob):
        return "UNKNOWN"
    if glob in ("/*",):
        return "OVERLAP"
    if "*" not in glob:
        return "OVERLAP" if glob==HEARTBEAT else "CLEAR"
    if glob.count("*")==1 and glob.endswith("*"):
        return "OVERLAP" if HEARTBEAT.startswith(glob[:-1]) else "CLEAR"
    return "UNKNOWN"

def aggregate_or(states):
    return ("OVERLAP" if "OVERLAP" in states else
            "UNKNOWN" if "UNKNOWN" in states else "CLEAR") if states else "UNKNOWN"

def named_matcher_check(expr):
    """Only single-line path/method matchers get conclusive classification."""
    t=expr.strip().split()
    if not t: return "MISSING","UNKNOWN"
    # Caddy: @name path /foo/* /bar*; OR within path matcher.
    if t[0]=="path":
        return "PATH",aggregate_or([path_check(v) for v in t[1:]])
    if t[0]=="method":
        methods=[m.upper() for m in t[1:]]
        if not methods or not all(re.fullmatch("[A-Z]+",m) for m in methods):
            return "METHOD","UNKNOWN"
        return "METHOD","OVERLAP" if METHOD in methods else "CLEAR"
    if t[0]=="not":
        # Negation is only safe for one, exactly recognized atomic matcher.
        k,inner=named_matcher_check(" ".join(t[1:]))
        if inner=="UNKNOWN":return "NEGATED_"+k,"UNKNOWN"
        return "NEGATED_"+k,"CLEAR" if inner=="OVERLAP" else "OVERLAP"
    return ({"host":"HOST","header":"HEADER","path_regexp":"REGEXP",
             "expression":"EXPRESSION","protocol":"PROTOCOL",
             "remote_ip":"REMOTE_IP","client_ip":"CLIENT_IP"}.get(t[0],"OTHER"),"UNKNOWN")

def evaluate(raw):
    depth=0
    site=None
    hesabs=[]
    directives=[]
    for line in raw.splitlines():
        v=line.strip()
        if not v or v.startswith("#"):
            continue
        if depth==0 and v.endswith("{"):
            site="HESAB" if re.search(r"\bhesab\b",v,re.I) else "OTHER"
            if site=="HESAB":
                hesabs.append(True)
        elif site=="HESAB" and depth==1 and v!="}":
            directives.append(v)
        depth+=line.count("{")-line.count("}")
        if depth<0:return {"site":"INVALID","shape":"UNKNOWN","kind":"UNKNOWN","match":"UNKNOWN"}
        if depth==0:site=None
    if depth!=0 or len(hesabs)!=1:
        return {"site":"UNEXPECTED","shape":"UNKNOWN","kind":"UNKNOWN","match":"UNKNOWN"}

    # Validate topology before interpreting one matcher. Other nested
    # blocks/complex constructs are not silently treated as safe.
    handles=[x for x in directives if re.match(r"^handle(?:\s|\{)",x)]
    handlepaths=[x for x in directives if re.match(r"^handle_path\s",x)]
    redirects=[x for x in directives if re.match(r"^redir(?:\s|$)",x)]
    if len(handles)!=1 or len(handlepaths)!=1 or len(redirects)!=1:
        return {"site":"FOUND","shape":"UNEXPECTED","kind":"UNKNOWN","match":"UNKNOWN"}
    if not re.fullmatch(r"handle\s+\{\s*",handles[0]):
        return {"site":"FOUND","shape":"UNEXPECTED","kind":"UNKNOWN","match":"UNKNOWN"}
    rd=redirects[0].split()
    if len(rd)<2:
        return {"site":"FOUND","shape":"EXPECTED","kind":"MISSING","match":"UNKNOWN"}
    if rd[1].startswith("@"):
        name=rd[1]
        # A matcher block may begin with "@name {" — do not attempt to
        # infer semantics from nested/regex clauses.
        matches=[x for x in directives if x==name+" {" or x.startswith(name+" ")]
        if len(matches)!=1:
            return {"site":"FOUND","shape":"EXPECTED","kind":"MISSING_OR_DUPLICATE","match":"UNKNOWN"}
        expr=matches[0][len(name):].strip()
        if expr.startswith("{"):
            return {"site":"FOUND","shape":"EXPECTED","kind":"BLOCK","match":"UNKNOWN"}
        kind,match=named_matcher_check(expr)
        return {"site":"FOUND","shape":"EXPECTED","kind":kind,"match":match}
    if rd[1].startswith("/"):
        return {"site":"FOUND","shape":"EXPECTED","kind":"INLINE_PATH","match":path_check(rd[1])}
    return {"site":"FOUND","shape":"EXPECTED","kind":"UNNAMED_OR_COMPLEX","match":"UNKNOWN"}

def main():
    try:
        doc=PATH.read_text(encoding="utf8")
        result=evaluate(doc)
    except (OSError,UnicodeError,ValueError):
        result={"site":"UNREADABLE","shape":"UNKNOWN","kind":"UNKNOWN","match":"UNKNOWN"}
    print("HESAB_CADDY_REDIRECT_V11_AUDIT")
    print("SITE",result["site"])
    print("ROUTE_SHAPE",result["shape"])
    print("REDIRECT_MATCHER_CLASS",result["kind"])
    print("REDIRECT_POST_HEARTBEAT_OVERLAP",result["match"])
    print("REVIEW_GATE","PASS_MATCHER_ONLY" if result["match"]=="CLEAR" and result["shape"]=="EXPECTED"
          else "BLOCKED")
    print("LIVE_CONFIG_UNCHANGED; NO_CADDY_RELOAD; NO_NETWORK_PROBE")
if __name__=="__main__":
    main()
