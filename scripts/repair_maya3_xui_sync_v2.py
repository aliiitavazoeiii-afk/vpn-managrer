#!/usr/bin/env python3
"""Safe Maya3 X-UI source repair. Read-only validate; migrate only a stale
SSH-tunnel host binding after verified SSH host fingerprint and 3x-ui API read.
Never changes clients, passwords, panel ports, provider meter or tunnel services.
"""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse

ROOT=Path("/opt/vpn-control-center")
sys.path.insert(0,str(ROOT/"scripts"))
import maya_multi_panel_sync as maya

MAYA3_IP="185.215.230.221"
MAYA4_IP="5.10.249.206"
FINGERPRINT="SHA256:rEJqkLeGc2iqzMTdv9dEmFt2pUs9bOrfNMEMWXvBsOw"
CFG=Path("/root/.config/hesab-maya-extra.json")
KH=Path("/root/.ssh/known_hosts")
SOCK=ROOT/"maya_extra_sync/live.sock"

def verify_rsa_host():
    record=subprocess.run(["ssh-keygen","-F",MAYA3_IP,"-f",str(KH)],
                          capture_output=True,text=True,timeout=5)
    if record.returncode:
        return False
    for row in record.stdout.splitlines():
        fields=row.split()
        if len(fields)>=3 and fields[1]=="ssh-rsa":
            fp=subprocess.run(["ssh-keygen","-lf","-","-E","sha256"],
                              input=row,capture_output=True,text=True,timeout=5)
            if fp.returncode==0 and FINGERPRINT in fp.stdout:
                return True
    return False

def live_result():
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
            s.settimeout(30)
            s.connect(str(SOCK))
            s.sendall(b'{"op":"snapshot","server":"maya-s3"}\n')
            s.shutdown(socket.SHUT_WR)
            data=b""
            while len(data)<2000000 and not data.endswith(b"\n"):
                chunk=s.recv(65536)
                if not chunk:break
                data+=chunk
        result=json.loads(data)
        if result.get("ok") is True and result.get("snapshot",{}).get("server")=="maya-s3":
            n=len(result["snapshot"]["clients"])
            print("MAYA3_XUI_LIVE_BRIDGE=CONNECTED","USERS",n)
            return True
    except Exception:
        pass
    print("MAYA3_XUI_LIVE_BRIDGE=UNAVAILABLE")
    return False

def atomic_update(data):
    if CFG.is_symlink() or not CFG.is_file() or CFG.stat().st_uid!=0 or CFG.stat().st_mode&0o077:
        raise PermissionError("Unsafe existing panel configuration")
    backup=CFG.with_name(CFG.name+".maya3-backup-"+time.strftime("%Y%m%d%H%M%S"))
    shutil.copy2(CFG,backup)
    fd,tmp=tempfile.mkstemp(prefix=".maya3-xui-",dir=str(CFG.parent))
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,"w",encoding="utf8") as stream:
            json.dump(data,stream,ensure_ascii=False,indent=2)
            stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,CFG)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    print("MAYA3_XUI_CONFIG_BACKUP=CREATED")
    print("MAYA3_XUI_SSH_HOST=CORRECTED")

def main():
    if os.geteuid()!=0:raise PermissionError("Root required")
    if not CFG.is_file() or CFG.is_symlink() or CFG.stat().st_mode&0o077:
        print("MAYA3_XUI=CONFIG_MISSING_OR_UNSAFE")
        return 0
    full=maya.config()
    entry=full.get("maya-s3")
    if not isinstance(entry,dict):
        print("MAYA3_XUI=NOT_CONFIGURED")
        return 0
    transport=entry.get("transport","https")
    print("MAYA3_XUI_TRANSPORT="+str(transport))
    if transport=="ssh":
        current=str(entry.get("ssh_host",""))
        print("MAYA3_XUI_CURRENT_TARGET="+(
          "MAYA3_CORRECT" if current==MAYA3_IP else
          "MAYA4_WRONG" if current==MAYA4_IP else "OTHER"))
        if current not in (MAYA3_IP,MAYA4_IP):
            print("MAYA3_XUI=OTHER_TARGET_NEEDS_REVIEW")
            return 0
        if not verify_rsa_host():
            print("MAYA3_XUI=HOST_IDENTITY_NOT_VERIFIED")
            return 0
        proposed=dict(entry)
        proposed["ssh_host"]=MAYA3_IP
        try:
            response=maya.pull("maya-s3",proposed)
            count=len(response["clients"])
            if not 1<=count<=5000:raise ValueError("Unexpected roster")
            print("MAYA3_XUI_PANEL_API=CONNECTED","USERS",count)
        except Exception as exc:
            print("MAYA3_XUI=NOT_REPAIRED")
            print("MAYA3_XUI_FAILURE_CLASS="+type(exc).__name__)
            print("MAYA3_XUI_HINT=CHECK_DEDICATED_XUI_TUNNEL_KEY_AND_PANEL_AUTH_ON_MAYA3")
            return 0
        if current!=MAYA3_IP:
            full["maya-s3"]=proposed
            atomic_update(full)
        else:
            print("MAYA3_XUI_CONFIG=ALREADY_CORRECT")
        live_result()
        return 0
    if transport=="https":
        parsed=urllib.parse.urlsplit(str(entry.get("url","")))
        if parsed.scheme!="https" or not parsed.hostname:
            print("MAYA3_XUI=INVALID_HTTPS_CONFIG")
            return 0
        try:
            ips={result[4][0] for result in socket.getaddrinfo(parsed.hostname,443,
                family=socket.AF_INET,type=socket.SOCK_STREAM)}
        except OSError:
            ips=set()
        label=("MAYA3_CORRECT" if MAYA3_IP in ips else
               "POINTS_TO_MAYA4" if MAYA4_IP in ips else
               "OTHER_OR_UNRESOLVED")
        print("MAYA3_XUI_HTTPS_DNS="+label)
        try:
            result=maya.pull("maya-s3",entry)
            print("MAYA3_XUI_PANEL_API=CONNECTED","USERS",len(result["clients"]))
            live_result()
        except Exception as exc:
            print("MAYA3_XUI_PANEL_API=UNAVAILABLE")
            print("MAYA3_XUI_FAILURE_CLASS="+type(exc).__name__)
        if label!="MAYA3_CORRECT":
            print("MAYA3_XUI=HTTPS_ENDPOINT_NEEDS_VERIFIED_URL_OR_DNS")
        return 0
    print("MAYA3_XUI=UNSUPPORTED_TRANSPORT")
    return 0

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (OSError,ValueError,RuntimeError,PermissionError) as exc:
        print("MAYA3_XUI_SAFE_REPAIR_STOP",type(exc).__name__)
        raise SystemExit(1)
