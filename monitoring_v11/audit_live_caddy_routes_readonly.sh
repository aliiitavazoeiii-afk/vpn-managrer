#!/usr/bin/env bash
# HESAB_V11_CADDY_ROUTE_STRUCTURE_AUDIT — read-only, local only, secret-safe.
# Prints only directive TYPES, nesting, and port numbers. Never route text.
set -Eeuo pipefail
python3 - <<'PY'
from pathlib import Path
import re
path=Path("/opt/darma-general/Caddyfile")
if not path.is_file():
    print("CADDYFILE_NOT_FOUND")
    raise SystemExit(1)
raw=path.read_text(encoding="utf-8")
print("CADDYFILE_BYTES",len(raw.encode()))
print("NOTE: hostnames, matchers, tokens and upstream addresses REDACTED")
depth=0
site="NONE"
sites=0
for lineno,line in enumerate(raw.splitlines(),1):
    value=line.strip()
    if not value or value.startswith("#"):
        continue
    if depth==0 and value.endswith("{"):
        site="HESAB" if re.search(r"\bhesab\b",value,re.IGNORECASE) else "OTHER"
        sites+=1
        print("SITE_BLOCK",sites,site)
    elif site=="HESAB":
        keywords=("handle_path","handle","route","reverse_proxy","@","path",
                  "method","uri","rewrite","redir","respond","header","tls","import")
        first=value.split(maxsplit=1)[0]
        if first.startswith("@"):
            typ="NAMED_MATCHER_DECLARATION"
        elif first in keywords:
            typ=first.upper()
        else:
            typ="OTHER_DIRECTIVE"
        if value=="}":
            typ="END_BLOCK"
        if typ=="REVERSE_PROXY":
            ports=re.findall(r":([0-9]{2,5})(?=\W|$)",value)
            extra="upstream_ports="+(",".join(ports) if ports else "not_explicit")
        elif typ in ("HANDLE","HANDLE_PATH","ROUTE"):
            extra="matcher="+("specified" if len(value.split())>2 else "default_or_unnamed")
        else:
            extra="values=REDACTED"
        print(f"LINE {lineno} nesting={depth} {typ} {extra}")
    depth+=line.count("{")-line.count("}")
    if depth<0:
        print("INVALID_CADDY_BRACES")
        break
    if depth==0:
        site="NONE"
print("FINAL_BRACE_DEPTH",depth)
print("READONLY_CADDY_STRUCTURE_AUDIT_COMPLETE")
PY
