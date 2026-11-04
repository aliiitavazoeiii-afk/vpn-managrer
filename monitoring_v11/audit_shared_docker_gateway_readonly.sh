#!/usr/bin/env bash
# HESAB_V11_SHARED_DOCKER_GATEWAY_AUDIT — read-only, no external probes.
# Never prints Caddyfile lines, upstream IPs, credentials or environment.
set -Eeuo pipefail
umask 077
echo "=== HESAB V11 SHARED DOCKER GATEWAY AUDIT (READ ONLY) ==="
python3 - <<'PY'
import ipaddress,json,re,subprocess
from pathlib import Path

def inspect(name):
    try:
        p=subprocess.run(["docker","inspect",name],capture_output=True,text=True,timeout=8)
        if p.returncode:
            return None
        return json.loads(p.stdout)[0]
    except (OSError,ValueError,IndexError,subprocess.TimeoutExpired):
        return None

names=("darma-general-caddy-1","vpn-control-center-app-1")
items={n:inspect(n) for n in names}
networks={}
for name,item in items.items():
    if not item:
        print("CONTAINER",name,"NOT_FOUND_OR_UNREADABLE")
        networks[name]=set()
        continue
    memberships=set((item.get("NetworkSettings") or {}).get("Networks") or {})
    networks[name]=memberships
    print("CONTAINER",name,"RUNNING",bool((item.get("State") or {}).get("Running")))
    print("CONTAINER_NETWORK_NAMES",name,",".join(sorted(memberships)) or "NONE")
    if name=="darma-general-caddy-1":
        mounts=item.get("Mounts") or []
        target=[m for m in mounts if m.get("Destination")=="/etc/caddy/Caddyfile"]
        print("CADDYFILE_BIND_MOUNT_PRESENT",bool(target))
        print("CADDYFILE_MOUNT_READONLY",bool(target and not target[0].get("RW",True)))
common=networks[names[0]] & networks[names[1]]
print("EXISTING_SHARED_NETWORKS",",".join(sorted(common)) or "NONE")
path=Path("/opt/darma-general/Caddyfile")
print("LIVE_CADDYFILE_PRESENT",path.is_file())
if path.is_file():
    try:
        raw=path.read_text(encoding="utf-8")
        print("LIVE_CADDYFILE_BYTES",path.stat().st_size)
        headers=list(re.finditer(r'(?m)^[ \t]*([^#\n{}]+?)\s*\{',raw))
        matches=[m for m in headers if re.search(r'\bhesab\b',m.group(1),re.IGNORECASE)]
        print("HESAB_SITE_BLOCK_CANDIDATES",len(matches))
        for i,m in enumerate(matches[:5],1):
            # Only inspect route to the matching closing brace; do not print contents.
            depth=1
            j=m.end()
            while j<len(raw) and depth>0:
                if raw[j]=="{":depth+=1
                if raw[j]=="}":depth-=1
                j+=1
            body=raw[m.end():max(m.end(),j-1)]
            targets=re.findall(r'(?m)^\s*reverse_proxy\s+([^\s{]+)',body)
            if not targets:
                print("HESAB_BLOCK",i,"NO_SIMPLE_REVERSE_PROXY_DIRECTIVE")
            for value in targets[:8]:
                v=value.removeprefix("http://").removeprefix("https://")
                h=v.split("/",1)[0].rsplit(":",1)[0]
                portmatch=re.search(r':(\d{1,5})(?:/|$)',v)
                port=portmatch.group(1) if portmatch else "unknown"
                low=h.lower().strip("[]")
                if low in ("127.0.0.1","localhost","::1"):
                    kind="LOOPBACK_INSIDE_CADDY_CONTAINER"
                elif low in ("host.docker.internal","gateway.docker.internal"):
                    kind="HOST_GATEWAY_NAME"
                else:
                    try:
                        ipaddress.ip_address(low)
                        kind="IP_LITERAL_REDACTED"
                    except ValueError:
                        kind="DOCKER_SERVICE_NAME_OR_HOSTNAME_REDACTED"
                print("HESAB_UPSTREAM",i,"kind",kind,"port",port)
    except (OSError,UnicodeError):
        print("LIVE_CADDYFILE_UNREADABLE")
try:
    p=subprocess.run(["git","-C","/opt/darma-general","status","--porcelain","--","Caddyfile"],
                     capture_output=True,text=True,timeout=8)
    print("CADDYFILE_GIT_LOCAL_MODIFIED",bool(p.stdout.strip()) if p.returncode==0 else "GIT_UNAVAILABLE")
except (OSError,subprocess.TimeoutExpired):
    print("CADDYFILE_GIT_LOCAL_MODIFIED","UNKNOWN")
print("AUDIT_COMPLETE_NO_CONFIG_OR_SERVICE_CHANGES")
PY
