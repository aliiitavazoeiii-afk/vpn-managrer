#!/usr/bin/env python3
"""Build read-only SSH Shahan status snapshot from operator-transferred local TSV.

No Shahan login, polling, daemon, cron, SSH account changes, DB writes, or XUI
changes. Requires the signed-off six overrides; removed amirkhanisis ignored.
"""
import csv,json,os,sys,tempfile,time,unicodedata
from collections import defaultdict
from pathlib import Path
sys.path.insert(0,"/opt/vpn-control-center/scripts")
import maya_multi_panel_sync as source

ROOT=Path("/opt/vpn-control-center/maya_extra_sync")
SRC=Path("/root/shahan_users_review.tsv")
DEST=ROOT/"shahan_waiting_status_v1.json"
OVERRIDE={"farajisis":33,"hadihoda":2,"hodapedar":151,
          "taherpoor":269,"moshefi":139,"khademitv":336}
SKIP={"amirkhanisis"}
def norm(x):return "".join(unicodedata.normalize("NFKC",str(x or "")).casefold().split())
def main():
    if os.geteuid()!=0:raise ValueError("sudo/root required")
    if not SRC.is_file() or SRC.is_symlink() or SRC.stat().st_size>200000:
        raise ValueError("Missing Shahan TSV; WinSCP transfer it to /root")
    with SRC.open(encoding="utf8",newline="") as f:
        r=csv.DictReader(f,delimiter="\t")
        required={"ssh_username","shahan_state_raw","linux_account_exists"}
        if not r.fieldnames or not required.issubset(r.fieldnames):
            raise ValueError("Unrecognized Shahan probe file")
        clients=list(r)
    if not clients or len(clients)>2000:raise ValueError("Shahan export count invalid")
    accounts=source.dashboard()
    by_name=defaultdict(list)
    active={int(x["id"]):x for x in accounts if x["state"]!="removed"}
    for a in active.values():by_name[norm(a["display_name"])].append(a)
    used=set()
    mapped=[]
    skipped=[]
    for c in clients:
        ssh=str(c["ssh_username"]).strip()
        key=ssh.casefold()
        if not ssh or len(ssh)>128:continue
        if key in SKIP:
            skipped.append(key);continue
        sid=OVERRIDE.get(key)
        if sid is None:
            hits=by_name.get(norm(ssh),[])
            if len(hits)!=1:continue
            sid=int(hits[0]["id"])
        if sid not in active or sid in used:
            # Never guess a replacement or duplicate two SSH users onto one customer.
            continue
        used.add(sid)
        flag=str(c["shahan_state_raw"]).strip().lower()
        exists=str(c["linux_account_exists"]).strip().lower()
        if exists=="false":
            status="not_present"
        elif flag in ("true","1","yes","on","enabled","active"):
            status="enabled_reported"
        elif flag in ("false","0","no","off","disabled","inactive"):
            status="disabled_reported"
        else:
            status="unknown"
        mapped.append({"sid":sid,"ssh":ssh,"reported_state":status})
    document={"format":"SHAHAN_WAITING_STATUS_V1",
              "imported_at":int(time.time()),
              "source_note":"operator-imported TSV, capture time unverified, not live",
              "mapped":mapped}
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o750)
    if ROOT.is_symlink():raise ValueError("Unsafe target directory")
    fd,temp=tempfile.mkstemp(prefix=".shahan-waiting-",dir=ROOT)
    try:
        with os.fdopen(fd,"w",encoding="utf8") as f:
            json.dump(document,f,ensure_ascii=False,separators=(",",":"))
            f.flush();os.fsync(f.fileno())
        os.chmod(temp,0o600)
        os.replace(temp,DEST)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    print("SHAHAN IMPORTED:",len(clients),"APPROVED_SSH_LINKS:",len(mapped))
    print("EXCLUDED:",",".join(skipped) or "NONE")
    print("SAVED:",DEST)
    print("NOTE: status from manually supplied report, NOT live. Refresh by importing a new probe.")
    print("NO SHA HAN SERVICE OR USER ACTION, NO FINANCIAL MUTATION")
if __name__=="__main__":
    try:main()
    except Exception as e:
        print("SHAHAN_WAITING_STOP:",type(e).__name__,str(e)[:170],file=sys.stderr)
        sys.exit(1)
