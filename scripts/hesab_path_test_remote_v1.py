#!/usr/bin/env python3
"""HESAB_PATH_TRANSFER_REMOTE_V1: explicitly operator-triggered bounded transfer.
Installed separately on each Iran host. It never changes tunnel/HAProxy/XUI.
An SSH public key is forced to this file; no general shell or arbitrary commands.

Preflight: SSH_ORIGINAL_COMMAND=hesab-path-test-preflight (NO network test)
Active:    SSH_ORIGINAL_COMMAND=hesab-path-test-v1 (3 sequential 512-KiB requests)
"""
import fcntl
import json
import math
import os
from pathlib import Path
import subprocess
import time

VERSION="HESAB_PATH_TRANSFER_V1"
URL="https://speed.cloudflare.com/__down?bytes=524288"
BYTES=524288
MAX_SECONDS=25
SLOW_SECONDS=12.0
PATHS={"backhaul":21001,"mieru":21002,"haproxy":18080}
STATE=Path("/var/lib/hesab-path-test-v1")
LOCK=STATE/"probe.lock"
LAST=STATE/"last_started"
COOLDOWN=120

def output(value):
    print(json.dumps(value,ensure_ascii=False,separators=(",",":")),flush=True)

def test_one(role,port):
    # Curl resolves the host through the SOCKS proxy. No env proxies,
    # redirects, insecure TLS flags, dynamic user hosts, or retries.
    command=[
        "/usr/bin/curl","-q","--silent","--output","/dev/null",
        "--socks5-hostname","127.0.0.1:"+str(port),
        "--noproxy","","--connect-timeout","6",
        "--max-time",str(MAX_SECONDS),"--retry","0",
        "--max-redirs","0","--max-filesize",str(BYTES),
        "--proto","=https","--http1.1",
        "--write-out","%{http_code} %{size_download} %{time_total} %{time_starttransfer}",
        URL,
    ]
    result={"state":"warning","http_status":0,
            "requested_bytes":BYTES,"received_bytes":0,
            "duration_ms":None,"ttfb_ms":None,"exit_code":255,
            "reason":"measurement_failed"}
    try:
        proc=subprocess.run(command,stdin=subprocess.DEVNULL,
             stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
             text=True,timeout=MAX_SECONDS+4,
             env={"PATH":"/usr/bin:/bin","HOME":"/","LANG":"C"})
        result["exit_code"]=proc.returncode
        parts=proc.stdout.strip().split()
        if len(parts)!=4:
            result["reason"]="missing_curl_metrics"
            return result
        http=int(parts[0])
        received=float(parts[1])
        duration=float(parts[2])
        ttfb=float(parts[3])
        if (not 0<=http<=599 or not math.isfinite(received) or
            not 0<=received<=BYTES or not math.isfinite(duration) or
            not 0<=duration<=MAX_SECONDS+4 or
            not math.isfinite(ttfb) or not 0<=ttfb<=MAX_SECONDS+4):
            result["reason"]="invalid_curl_metrics"
            return result
        result.update({"http_status":http,"received_bytes":int(received),
                       "duration_ms":int(duration*1000),
                       "ttfb_ms":int(ttfb*1000)})
        if proc.returncode==0 and http==200 and int(received)==BYTES and duration<=SLOW_SECONDS:
            result["state"]="healthy"
            result["reason"]="complete"
        elif proc.returncode==28:
            result["reason"]="timeout"
        elif proc.returncode!=0:
            result["reason"]="transport_failure"
        elif http!=200:
            result["reason"]="http_status"
        elif received<BYTES:
            result["reason"]="incomplete"
        else:
            result["reason"]="slow_completion"
    except (OSError,ValueError,subprocess.TimeoutExpired):
        result["reason"]="probe_execution_failed"
    return result

def run():
    original=os.environ.get("SSH_ORIGINAL_COMMAND","")
    if original=="hesab-path-test-preflight":
        output({"format":VERSION,"mode":"preflight","ready":
                Path("/usr/bin/curl").is_file() and os.geteuid()==0})
        return
    if original!="hesab-path-test-v1":
        output({"format":VERSION,"state":"denied"})
        return
    if os.geteuid()!=0:
        output({"format":VERSION,"state":"denied"})
        return
    STATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    with LOCK.open("a+") as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        now=int(time.time())
        last=0
        if LAST.is_file() and LAST.stat().st_size<100:
            try:last=int(LAST.read_text().strip())
            except ValueError:pass
        if 0<=now-last<COOLDOWN:
            output({"format":VERSION,"state":"rate_limited"})
            return
        LAST.write_text(str(now),encoding="ascii")
        os.chmod(LAST,0o600)
        values={name:test_one(name,port) for name,port in PATHS.items()}
        output({"format":VERSION,"state":"completed","sampled_at":int(time.time()),
                "destination":"speed.cloudflare.com",
                "paths":values})

if __name__=="__main__":
    try:run()
    except (OSError,BlockingIOError):
        output({"format":VERSION,"state":"busy_or_unavailable"})
