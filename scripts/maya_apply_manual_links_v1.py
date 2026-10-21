#!/usr/bin/env python3
"""Validate user-approved Maya XUI->Hesab ID links; --apply changes ONLY local mapping JSON.

No changes to PostgreSQL, financial accounting, XUI clients, or scheduled controls.
Never print full customer database. Plan is provided locally on production host.
"""
import argparse,json,os,socket,stat,sys,tempfile
from pathlib import Path
sys.path.insert(0,"/opt/vpn-control-center/scripts")
import maya_multi_panel_sync as source

DEST=Path("/opt/vpn-control-center/maya_extra_sync/approved_links.json")
SOCK=Path("/opt/vpn-control-center/maya_extra_sync/live.sock")
SERVERS=set(source.SERVERS)
def stop(reason):raise ValueError(reason)

def check_plan(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size>120000:
        stop("Missing, linked, or oversized approval plan file")
    obj=json.loads(path.read_text(encoding="utf-8"))
    if obj.get("format")!="HESAB_MAYA_APPROVALS_V1":
        stop("Unexpected approval format")
    servers=obj.get("servers")
    if not isinstance(servers,dict) or not servers or set(servers)-SERVERS:
        stop("Unrecognized Maya server")
    for server,links in servers.items():
        if not isinstance(links,dict):stop("Invalid server approval data")
        used=set()
        for email,val in links.items():
            if not isinstance(email,str) or not email or email!=email.strip().casefold():
                stop("All XUI labels must be lowercase and trimmed")
            if type(val) is not dict:stop("Approval entry must be an object")
            if set(val)=={"sid"}:
                sid=val["sid"]
                if type(sid) is not int or sid<1:stop("Invalid ID")
                if sid in used:stop("Two accounts share the same approved ID on "+server)
                used.add(sid)
            elif set(val)=={"exclude"} and val["exclude"] is True:
                pass
            else:stop("Specify exactly a positive sid or exclude:true")
    return servers

def read_snapshot(server):
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(70)
        s.connect(str(SOCK))
        s.sendall((json.dumps({"op":"snapshot","server":server})+"\n").encode())
        s.shutdown(socket.SHUT_WR)
        body=bytearray()
        while not body.endswith(b"\n"):
            block=s.recv(65536)
            if not block:break
            body.extend(block)
            if len(body)>3000000:stop("Oversize XUI response")
    if not body.endswith(b"\n"):stop("Incomplete XUI response")
    result=json.loads(body)
    if not result.get("ok") or result["snapshot"].get("server")!=server:
        stop("Live XUI snapshot not confirmed")
    return {str(c.get("email") or "").casefold() for c in result["snapshot"]["clients"]}

def get_existing():
    if not DEST.is_file():return {}
    if DEST.is_symlink() or DEST.stat().st_mode&0o077:stop("Unsafe existing approval permissions")
    obj=json.loads(DEST.read_text(encoding="utf8"))
    if obj.get("format")!="HESAB_MAYA_APPROVALS_V1":stop("Existing approval file has unexpected format")
    data=obj.get("servers")
    if not isinstance(data,dict):stop("Corrupted saved approval file")
    return data

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--file",required=True,type=Path)
    parser.add_argument("--apply",action="store_true")
    args=parser.parse_args()
    if os.geteuid()!=0:stop("Run with sudo/root")
    new=check_plan(args.file)
    old=get_existing()
    merged={server:dict(items) for server,items in old.items()}
    for server,items in new.items():
        merged.setdefault(server,{})
        merged[server].update(items)
    # Validate merged config, not only new entries.
    parent=args.file.parent
    with tempfile.NamedTemporaryFile(mode="w",encoding="utf8",dir=parent,delete=False) as tmp:
        tmp_path=Path(tmp.name)
        json.dump({"format":"HESAB_MAYA_APPROVALS_V1","servers":merged},tmp)
    try:check_plan(tmp_path)
    finally:tmp_path.unlink(missing_ok=True)
    rows=source.dashboard()
    accounts={int(r["id"]):r for r in rows}
    statuses=[]
    for server,links in new.items():
        present=read_snapshot(server)
        for email,item in links.items():
            if email not in present:
                status="XUI_MISSING"
            elif "exclude" in item:
                status="EXCLUDED"
            elif item["sid"] not in accounts:
                status="ACCOUNT_MISSING"
            elif accounts[item["sid"]]["state"]=="removed":
                status="ACCOUNT_ARCHIVED"
            else:
                status="READY"
            statuses.append((server,email,item,status))
    for server,email,item,status in statuses:
        val=("#"+str(item["sid"])) if "sid" in item else "EXCLUDED"
        print(f"{server:7} | {email:29} -> {val:10} | {status}")
    ready=sum(x[3]=="READY" for x in statuses)
    excluded=sum(x[3]=="EXCLUDED" for x in statuses)
    blocked=len(statuses)-ready-excluded
    print(f"SUMMARY ready={ready} excluded={excluded} pending={blocked}")
    if not args.apply:
        print("CHECK ONLY: nothing saved.")
        return
    # Never write a bogus record that would silently auto-map another ID.
    # Pending entries remain fail-closed in live resolver until confirmed active.
    DEST.parent.mkdir(parents=True,exist_ok=True,mode=0o750)
    if DEST.parent.is_symlink():stop("Unexpected linked config folder")
    fd,tmp=tempfile.mkstemp(prefix=".maya-approval-",dir=DEST.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf8") as f:
            json.dump({"format":"HESAB_MAYA_APPROVALS_V1","servers":merged},
                      f,ensure_ascii=False,indent=2)
            f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o600)
        if DEST.exists():
            bak=DEST.parent/("approved_links.backup.json")
            if bak.exists():stop("Old approval backup exists; refusing overwrite")
            # hardlink preserves previous bytes securely, atomic replace is below
            os.link(DEST,bak)
            os.chmod(bak,0o600)
        os.replace(tmp,DEST)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    print("SAVED root-only approval mapping:",str(DEST))
    print("No finance records changed, no user toggled, no automation enabled.")

if __name__=="__main__":
    try:main()
    except Exception as e:
        print("APPROVAL_STOP:",type(e).__name__,str(e)[:170],file=sys.stderr)
        sys.exit(1)
