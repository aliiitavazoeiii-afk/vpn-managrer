#!/usr/bin/env python3
"""HESAB_PATH_TEST_MANUAL_BROKER_V1 - management host only.
A local Unix broker accepts exactly 'start'. It launches at most one bounded
3-host transfer test when an authenticated admin clicks 'تست مسیر'.
No schedule, no tunnel mutations, no arbitrary host/port/path/URL arguments.
"""
import concurrent.futures
import fcntl
import json
import os
from pathlib import Path
import secrets
import socketserver
import subprocess
import sys
import tempfile
import threading
import time

ROOT=Path("/opt/vpn-control-center")
CFG=Path("/root/.config/hesab-dual-hourly-v1.json")
KEY=Path("/root/.ssh/hesab_transfer_test_v1")
SOCK=ROOT/"maya_extra_sync/path_transfer_v1.sock"
DIR=ROOT/"maya_extra_sync/path_transfer_v1"
STATUS=DIR/"status.json"
LOCK=DIR/"run.lock"
FORMAT="HESAB_PATH_TEST_ACCOUNT_V1"
REMOTE_FORMAT="HESAB_PATH_TRANSFER_V1"
HOSTS={"maya1":"94.184.4.38","maya-s3":"185.215.230.221",
       "maya4":"5.10.249.206"}
ROLES=("backhaul","mieru","haproxy")
COOLDOWN=120
IN_MEMORY_LOCK=threading.Lock()
RUNNING=False
LAST_STARTED=0.0

def current_config():
    if not CFG.is_file() or CFG.is_symlink() or CFG.stat().st_mode & 0o077:
        raise ValueError("Dual host config missing or insecure")
    config=json.loads(CFG.read_text(encoding="utf8"))
    mapping=config.get("servers")
    if not isinstance(mapping,dict):
        raise ValueError("Invalid host map")
    return {name:mapping[name] for name in HOSTS
            if name in mapping and mapping[name].get("host")==HOSTS[name]}

def run_ssh(name,requested,timeout):
    if not KEY.is_file() or KEY.is_symlink() or KEY.stat().st_mode & 0o077:
        raise PermissionError("Dedicated path-test SSH key missing or insecure")
    cfg=current_config()
    if name not in cfg:
        raise ValueError("Verified Maya mapping unavailable")
    item=cfg[name]
    port=str(int(item.get("ssh_port",22)))
    cmd=["/usr/bin/ssh","-F","/dev/null","-n","-T",
         "-i",str(KEY),"-p",port,
         "-o","IdentitiesOnly=yes","-o","BatchMode=yes",
         "-o","PreferredAuthentications=publickey",
         "-o","StrictHostKeyChecking=yes",
         "-o","UserKnownHostsFile=/root/.ssh/known_hosts",
         "-o","ConnectTimeout=7","-o","ConnectionAttempts=1",
         "-o","ForwardAgent=no","-o","ClearAllForwardings=yes",
         "-o","ControlMaster=no","-o","LogLevel=ERROR",
         "root@"+HOSTS[name],requested]
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout,
                          stdin=subprocess.DEVNULL)
    if result.returncode!=0 or len(result.stdout)>10000:
        raise RuntimeError("Restricted SSH probe failed")
    data=json.loads(result.stdout)
    if not isinstance(data,dict) or data.get("format")!=REMOTE_FORMAT:
        raise ValueError("Unrecognized probe response")
    return data

def preflight():
    results={}
    for name in HOSTS:
        try:
            d=run_ssh(name,"hesab-path-test-preflight",14)
            results[name]=(d.get("mode")=="preflight" and d.get("ready") is True)
        except (OSError,ValueError,PermissionError,RuntimeError,
                subprocess.TimeoutExpired,json.JSONDecodeError):
            results[name]=False
    return results

def warning_all(reason):
    return {"state":"unavailable","reason":reason,
            "paths":{role:{"state":"warning"} for role in ROLES}}

def fetch_one(name):
    try:
        data=run_ssh(name,"hesab-path-test-v1",100)
        if data.get("state")!="completed":
            return warning_all("remote_unavailable")
        paths=data.get("paths")
        if not isinstance(paths,dict) or set(paths)!=set(ROLES):
            raise ValueError("Invalid remote roles")
        safe={}
        for role in ROLES:
            item=paths[role]
            if not isinstance(item,dict) or item.get("state") not in ("healthy","warning"):
                raise ValueError("Bad role state")
            status=item.get("http_status")
            got=item.get("received_bytes")
            required=item.get("requested_bytes")
            code=item.get("exit_code")
            elapsed=item.get("duration_ms")
            ttfb=item.get("ttfb_ms")
            if (type(status) is not int or type(got) is not int or
                type(required) is not int or type(code) is not int or
                required!=524288 or not 0<=got<=required or
                not 0<=status<=599 or not 0<=code<=255 or
                (elapsed is not None and (type(elapsed) is not int or not 0<=elapsed<=29000)) or
                (ttfb is not None and (type(ttfb) is not int or not 0<=ttfb<=29000))):
                raise ValueError("Invalid measured values")
            verified=(code==0 and status==200 and got==required and
                      elapsed is not None and elapsed<=12000)
            safe[role]={"state":"healthy" if verified else "warning",
                        "http_status":status,"requested_bytes":required,
                        "received_bytes":got,"exit_code":code,
                        "duration_ms":elapsed,"ttfb_ms":ttfb,
                        "reason":str(item.get("reason",""))[:40]}
        return {"state":"completed","paths":safe}
    except (OSError,ValueError,RuntimeError,PermissionError,
            subprocess.TimeoutExpired,json.JSONDecodeError):
        return warning_all("unavailable_or_invalid")

def write_status(doc):
    DIR.mkdir(parents=True,mode=0o750,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix=".path-check-",dir=DIR)
    try:
        os.fchmod(fd,0o640)
        with os.fdopen(fd,"w",encoding="utf8") as f:
            json.dump(doc,f,ensure_ascii=False,separators=(",",":"))
            f.flush();os.fsync(f.fileno())
        os.replace(temp,STATUS)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def read_status():
    if not STATUS.is_file() or STATUS.is_symlink() or STATUS.stat().st_size>20000:
        return None
    try:
        result=json.loads(STATUS.read_text(encoding="utf8"))
        if result.get("format")==FORMAT:
            return result
    except (OSError,ValueError):
        pass
    return None

def worker(run_id,started):
    global RUNNING
    try:
        # 1 active HTTP download per Maya. 3 server tests may run concurrently.
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures={pool.submit(fetch_one,name):name for name in HOSTS}
            results={name:warning_all("no_result") for name in HOSTS}
            for future,name in futures.items():
                try:results[name]=future.result(timeout=110)
                except Exception:results[name]=warning_all("no_response")
        summary="healthy" if all(
            server["state"]=="completed" and all(
                server["paths"][role]["state"]=="healthy" for role in ROLES)
            for server in results.values()) else "warning"
        write_status({"format":FORMAT,"run_id":run_id,"state":"completed",
                      "summary":summary,"started_at":started,
                      "completed_at":int(time.time()),"servers":results})
    except Exception:
        write_status({"format":FORMAT,"run_id":run_id,"state":"failed",
                      "summary":"warning","started_at":started,
                      "completed_at":int(time.time()),"servers":{}})
    finally:
        with IN_MEMORY_LOCK:
            RUNNING=False

def handle(request):
    global RUNNING,LAST_STARTED
    if request!={"op":"start"}:
        return {"ok":False,"error":"Unsupported operation"}
    with IN_MEMORY_LOCK:
        if RUNNING:
            prior=read_status()
            return {"ok":True,"accepted":True,"run_id":prior.get("run_id","") if prior else ""}
        monotonic=time.monotonic()
        if LAST_STARTED and monotonic-LAST_STARTED<COOLDOWN:
            return {"ok":False,"error":"cooldown"}
        if set(current_config())!=set(HOSTS):
            return {"ok":False,"error":"invalid_hosts"}
        if not KEY.is_file() or KEY.is_symlink() or KEY.stat().st_mode & 0o077:
            return {"ok":False,"error":"probe_key_unavailable"}
        run_id=secrets.token_hex(12)
        now=int(time.time())
        LAST_STARTED=monotonic
        RUNNING=True
        write_status({"format":FORMAT,"run_id":run_id,"state":"running",
                      "summary":"unknown","started_at":now,"servers":{}})
        thread=threading.Thread(target=worker,args=(run_id,now),daemon=True)
        thread.start()
        return {"ok":True,"accepted":True,"run_id":run_id}

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            line=self.rfile.readline(200)
            if len(line)>180 or not line.endswith(b"\n"):
                raise ValueError("Invalid command")
            response=handle(json.loads(line))
        except Exception:
            response={"ok":False,"error":"invalid_or_unavailable"}
        self.wfile.write(json.dumps(response,separators=(",",":")).encode()+b"\n")

class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
    daemon_threads=True

def main():
    if len(sys.argv)==2 and sys.argv[1]=="--preflight":
        result=preflight()
        for name,ok in result.items():
            print("PATH_TEST_PREFLIGHT",name,"PASS" if ok else "FAILED")
        print("ACTIVE_DOWNLOADS_EXECUTED=NO")
        return 0 if all(result.values()) else 3
    if os.geteuid()!=0:
        raise PermissionError("Host root required")
    SOCK.parent.mkdir(parents=True,mode=0o750,exist_ok=True)
    if os.path.lexists(str(SOCK)):
        if not SOCK.is_socket():
            raise RuntimeError("Refusing to remove non-socket")
        SOCK.unlink()
    with Server(str(SOCK),Handler) as server:
        os.chmod(SOCK,0o660)
        print("MANUAL_TRANSFER_BROKER=READY_NO_TEST_STARTED",flush=True)
        try:server.serve_forever(poll_interval=0.2)
        finally:
            try:SOCK.unlink()
            except FileNotFoundError:pass
    return 0

if __name__=="__main__":
    try:sys.exit(main())
    except (OSError,ValueError,PermissionError,RuntimeError) as exc:
        print("PATH_TEST_BROKER_STOP",type(exc).__name__)
        sys.exit(1)
