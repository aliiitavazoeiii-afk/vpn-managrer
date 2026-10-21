#!/usr/bin/env python3
"""HESAB_MAYA_DAVARI_AFROGH_LINK_FIX_V1
Root-only protected approval delta for two explicitly confirmed accounts.
Never touches billing, expiries, client states, or payment workflows.
Requires preinstalled archived-read-only overlay in the running web app.
"""
import json,os,subprocess,sys,socket
from pathlib import Path
BASE=Path("/opt/vpn-control-center")
EXISTING=BASE/"maya_extra_sync/approved_links.json"
PATCH=BASE/"patches/maya1_control.py"
SCRIPT=BASE/"scripts/maya_apply_manual_links_v1.py"
OUTPUT=Path("/root/maya_approved_davari_afrogh_delta.json")
DELTA={"format":"HESAB_MAYA_APPROVALS_V1","servers":{
    "maya1":{"afrogh hooman":{"sid":24}},
    "maya-s3":{"davari khodesh":{"sid":235}}
}}

def stop(reason):raise RuntimeError(reason)

def main():
    if os.geteuid()!=0:stop("Must run as root")
    if not EXISTING.is_file() or EXISTING.is_symlink():
        stop("Previously approved 20 links missing")
    if "HESAB_MAYA_ARCHIVED_LINK_READONLY_V1" not in PATCH.read_text():
        stop("Archived read-only overlay has not been installed")
    current=json.loads(EXISTING.read_text(encoding="utf8"))
    if current.get("format")!="HESAB_MAYA_APPROVALS_V1":
        stop("Unexpected existing mapping schema")
    items=current["servers"]
    if items.get("maya1",{}).get("afrogh hooman")!={"exclude":True}:
        stop("Maya1 #24 approval state changed; manual review needed")
    if items.get("maya-s3",{}).get("davari khodesh")!={"sid":234}:
        stop("Maya3 Davari old #234 has changed; manual review needed")
    for email,v in items["maya-s3"].items():
        if email!="davari khodesh" and v.get("sid")==235:
            stop("Maya3 #235 is already manually assigned to another client")
    fd=os.open(OUTPUT,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,"w",encoding="utf8") as f:
        json.dump(DELTA,f,ensure_ascii=False,indent=2);f.write("\n")
    p=subprocess.run([sys.executable,str(SCRIPT),"--file",str(OUTPUT)],
                     cwd=BASE,text=True,capture_output=True,timeout=250)
    print(p.stdout,flush=True)
    if p.returncode:stop("Read-only XUI/finance preflight failed: "+p.stderr[-220:])
    status={}
    for row in p.stdout.splitlines():
        if "davari khodesh" in row:status["davari"]=row
        if "afrogh hooman" in row:status["afrogh"]=row
    if not (status.get("davari","").endswith("READY") and
            status.get("afrogh","").endswith("ACCOUNT_ARCHIVED")):
        stop("Unexpected live account statuses; no mapping saved")
    # Only approval JSON is modified, importer backs up existing file.
    p=subprocess.run([sys.executable,str(SCRIPT),"--file",str(OUTPUT),"--apply"],
                     cwd=BASE,text=True,capture_output=True,timeout=250)
    print(p.stdout,flush=True)
    if p.returncode:stop("Approval mapping update failed: "+p.stderr[-300:])
    if "SAVED root-only approval mapping:" not in p.stdout:
        stop("No saving confirmation")
    print("SAVED: Davari #235; archived Afrogh #24 READ ONLY",flush=True)
    # The last verification runs the installed _ml_one code from the app.
    program='''from app.main import _ml_one,get_db
gen=get_db();db=next(gen)
try:
    for server,email,expected in [
        ("maya-s3","davari khodesh",235),
        ("maya1","afrogh hooman",24)]:
        out=_ml_one(server,db)
        found=[r for r in out["rows"] if r["email"].casefold()==email]
        assert len(found)==1,(server,email,"not found")
        r=found[0]
        assert r["sid"]==expected,(server,email,r["sid"])
        if server=="maya1":
            assert r["finance_state"]=="cut" and r["control_ambiguous"] is True
        print(server,email,"sid",r["sid"],"reason",r["reason"],"control_blocked",r["control_ambiguous"])
finally:
    gen.close()
print("SUCCESS: BOTH CORRECTED LINKS VISIBLE IN RUNNING WEB APP")
'''
    cmd=["docker","compose","-f","docker-compose.yml","-f","docker-compose.sms.yml",
         "exec","-T","app","python","-c",program]
    p=subprocess.run(cmd,cwd=BASE,text=True,capture_output=True,timeout=180)
    print(p.stdout,flush=True)
    if p.returncode:stop("Site readback failed: "+p.stderr[-350:])
    print("No XUI toggles / DB writes / scheduled activation.",flush=True)

if __name__=="__main__":
    try:main()
    except Exception as e:
        print("MAYA_DAVARI_AFROGH_STOP:",type(e).__name__,str(e)[:280],file=sys.stderr)
        sys.exit(1)
