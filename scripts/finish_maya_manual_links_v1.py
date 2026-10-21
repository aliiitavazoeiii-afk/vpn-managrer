#!/usr/bin/env python3
"""HESAB_MAYA_FINISH_APPROVALS_V1

One-command, fail-closed promotion of the user's private Maya approval plan:
- preserve 20 user-confirmed, available financial SID links;
- temporarily exclude archived #24 (no forced reactivation);
- exclude XUI-only axkahe02 and jxhyjrxo as requested;
- commit ONLY root-owned manual mapping JSON, never mutate XUI or finance;
- verify that the currently running web app resolves links from the saved file.

The customer's mapping plan stays on the private management server, not Git.
"""
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BASE=Path("/opt/vpn-control-center")
SOURCE=Path("/root/maya_approval_plan.json")
OUTPUT=Path("/root/maya_approval_ready.json")
IMPORTER=BASE/"scripts/maya_apply_manual_links_v1.py"
SERVER_ORDER=("maya1","maya-s3","maya4")
EXPECTED_LINKS=20
EXPECTED_EXCLUSIONS=11

def fail(message):
    raise RuntimeError(message)

def run(cmd, *, input_text=None, timeout=250):
    p=subprocess.run(cmd, input=input_text,text=True,capture_output=True,
                     timeout=timeout, cwd=str(BASE))
    if p.stdout:
        print(p.stdout.rstrip(),flush=True)
    if p.returncode:
        print(p.stderr[-2000:],file=sys.stderr)
        fail("Step failed: "+cmd[-1])
    return p.stdout

def prepare():
    if os.geteuid()!=0:fail("Run as root")
    if not SOURCE.is_file() or SOURCE.is_symlink():
        fail("Missing /root/maya_approval_plan.json. Upload with WinSCP first.")
    if SOURCE.stat().st_size>120000:
        fail("Unexpected plan size")
    doc=json.loads(SOURCE.read_text(encoding="utf8"))
    if doc.get("format")!="HESAB_MAYA_APPROVALS_V1":
        fail("Unexpected manual approval format")
    servers=doc.get("servers")
    if not isinstance(servers,dict) or set(servers)!=set(SERVER_ORDER):
        fail("Incomplete approval plan")
    # Strong preflight against accidentally reading another private mapping file.
    if servers["maya1"].get("afrogh hooman")!={"sid":24}:
        fail("Expected archived Maya1 account #24 missing or changed")
    if servers["maya-s3"].get("abedi")!={"sid":115}:
        fail("Expected reviewed Maya3 #115 missing")
    if servers["maya-s3"].get("amanolahi bakhtiyari")!={"sid":375}:
        fail("New Maya3 #375 missing")
    if servers["maya-s3"].get("azadeh hoda")!={"sid":376}:
        fail("New Maya3 #376 missing")
    if servers["maya4"].get("haleh")!={"sid":373}:
        fail("New Maya4 #373 missing")
    if servers["maya4"].get("yalda ghazal")!={"sid":374}:
        fail("New Maya4 #374 missing")
    doc=copy.deepcopy(doc)
    servers=doc["servers"]
    # Archived account is not considered approved for operational linking.
    # A later explicit operator approval may replace this temporary exclusion.
    servers["maya1"]["afrogh hooman"]={"exclude":True}
    for server,email in (("maya-s3","axkahe02"),("maya4","jxhyjrxo")):
        if email in servers[server] and servers[server][email]!={"exclude":True}:
            fail("Refusing to override another approval for "+server+"/"+email)
        servers[server][email]={"exclude":True}
    links=sum("sid" in v for items in servers.values() for v in items.values())
    exclusions=sum(v.get("exclude") is True for items in servers.values() for v in items.values())
    if (links,exclusions)!=(EXPECTED_LINKS,EXPECTED_EXCLUSIONS):
        fail("Unexpected mapping totals: links="+str(links)+" excluded="+str(exclusions))
    fd,temp=tempfile.mkstemp(prefix=".maya-ready-",dir="/root")
    try:
        with os.fdopen(fd,"w",encoding="utf8") as f:
            json.dump(doc,f,ensure_ascii=False,indent=2)
            f.write("\n");f.flush();os.fsync(f.fileno())
        os.chmod(temp,0o600)
        os.replace(temp,OUTPUT)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    print("PLAN READY: 20 linked, 11 excluded (includes archived #24 and 2 ignored XUI entries).",flush=True)
    return doc

def main():
    plan=prepare()
    if not IMPORTER.is_file():
        fail("Approved mapping importer not installed")
    print("=== STEP 1: LIVE PREFLIGHT (read-only) ===",flush=True)
    cmd=[sys.executable,str(IMPORTER),"--file",str(OUTPUT)]
    report=run(cmd)
    if not re.search(r"^SUMMARY ready=20 excluded=11 pending=0$",report,re.M):
        fail("Not applying: live preflight has errors; inspect statuses above")
    print("=== STEP 2: SAVE PRIVATE APPROVED LINKS (no XUI writes) ===",flush=True)
    report=run(cmd+["--apply"])
    if not re.search(r"^SUMMARY ready=20 excluded=11 pending=0$",report,re.M):
        fail("Importer returned an unexpected status; verify before continuing")
    print("=== STEP 3: VERIFY LOADED WEB APP /control-room DATA ===",flush=True)
    verification=r'''import sys
from app.main import _ma_approved, _ml_one, get_db
import json
expected=json.loads(sys.stdin.read())
actual=_ma_approved()
for server,entries in expected.items():
    for email,item in entries.items():
        assert actual.get(server,{}).get(email)==item,(server,email,"mapping file differs")
print("APP FILE: approved links loaded and matching plan",flush=True)
gen=get_db()
db=next(gen)
try:
    for server,entries in expected.items():
        report=_ml_one(server,db)
        users={r["email"].casefold():r for r in report["rows"]}
        for email,item in entries.items():
            assert email in users,(server,email,"XUI entry vanished")
            sid=users[email]["sid"]
            if "sid" in item:
                assert sid==item["sid"],(server,email,"link did not resolve")
            else:
                assert sid is None,(server,email,"excluded XUI linked unexpectedly")
        print(server,"LIVE total",report["total"],"linked",report["linked"],
              "unmatched_including_excluded",report["unmatched"],flush=True)
finally:
    gen.close()
print("SUCCESS: VERIFIED ALL 20 LINKS AND 11 EXCLUSIONS IN RUNNING APP",flush=True)
'''
    # Combine program and plan on stdin using -c because python - consumes stdin as source.
    compose=["docker","compose","-f","docker-compose.yml",
             "-f","docker-compose.sms.yml","exec","-T","app",
             "python","-c",verification]
    run(compose,input_text=json.dumps(plan["servers"],ensure_ascii=False),timeout=250)
    print("FINISHED: No XUI, accounting, homepage or automation changes.",flush=True)

if __name__=="__main__":
    try:main()
    except Exception as e:
        print("MAYA_LINK_FINISH_STOP:",type(e).__name__,str(e)[:230],file=sys.stderr)
        sys.exit(1)
