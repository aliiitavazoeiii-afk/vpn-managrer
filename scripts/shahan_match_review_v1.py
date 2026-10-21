#!/usr/bin/env python3
"""SHAHAN_MATCH_REVIEW_V1
Local-only, read-only matching Shahan SSH roster to live Hesab financial IDs.
No accounts are enabled/disabled, no DB tables updated, no panel HTTP load.
Run on Hesab management server after WinSCP uploads /root/shahan_users_review.tsv.
"""
import csv,difflib,os,sys,unicodedata
from collections import defaultdict
from pathlib import Path
sys.path.insert(0,"/opt/vpn-control-center/scripts")
import maya_multi_panel_sync as source
SRC=Path("/root/shahan_users_review.tsv")
OUT=Path("/root/shahan_match_review.tsv")
def normalize(value):
    return "".join(unicodedata.normalize("NFKC",str(value or "")).casefold().split())
def main():
    if os.geteuid()!=0:raise ValueError("Root required")
    if not SRC.is_file() or SRC.is_symlink() or SRC.stat().st_size>200000:
        raise ValueError("Upload the small protected Shahan TSV via WinSCP to /root")
    with SRC.open(encoding="utf8",newline="") as f:
        r=csv.DictReader(f,delimiter="\t")
        if not r.fieldnames or "ssh_username" not in r.fieldnames:
            raise ValueError("Unexpected Shahan user export")
        shahan=list(r)
    if not 1<=len(shahan)<=2000:raise ValueError("Unexpected roster size")
    if len(set(x["ssh_username"].casefold() for x in shahan))!=len(shahan):
        raise ValueError("Duplicate SSH usernames; stop")
    accounts=source.dashboard()
    index=defaultdict(list)
    for a in accounts:
        index[normalize(a["display_name"])].append(a)
    suggestions={normalize(x["display_name"]):x for x in accounts}
    output=[]
    counts=defaultdict(int)
    for item in shahan:
        ssh=item["ssh_username"]
        matches=index.get(normalize(ssh),[])
        if len(matches)==1:
            candidate=matches[0]
            if candidate["state"]!="removed":
                sid=int(candidate["id"]);name=candidate["display_name"];category="EXACT_ACTIVE_NAME"
            else:
                sid="";name=candidate["display_name"];category="ARCHIVED_NAME_REVIEW"
        elif len(matches)>1:
            sid="";name="";category="DUPLICATE_NAME_REVIEW"
        else:
            sid="";name="";category="MANUAL_REVIEW"
        counts[category]+=1
        fuzzy=difflib.get_close_matches(normalize(ssh),list(suggestions),n=4,cutoff=.45)
        possible=" | ".join(str(suggestions[k]["id"])+":"+suggestions[k]["display_name"] for k in fuzzy)
        output.append({
          "ssh_username":ssh,
          "shahan_user_id":item.get("shahan_user_id",""),
          "shahan_state_raw":item.get("shahan_state_raw",""),
          "account_exists":item.get("linux_account_exists",""),
          "candidate_hesab_sid":sid,"candidate_name":name,
          "status":category,"other_options":possible,"operator_confirmed_sid":"",
        })
    if OUT.exists():raise ValueError("Existing report at /root/shahan_match_review.tsv; please rename before rerun")
    fd=os.open(OUT,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,"w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(output[0]),delimiter="\t")
        w.writeheader();w.writerows(output)
    print("SHAHAN TOTAL:",len(shahan),"HESAB TOTAL:",len(accounts))
    for key in ("EXACT_ACTIVE_NAME","ARCHIVED_NAME_REVIEW","DUPLICATE_NAME_REVIEW","MANUAL_REVIEW"):
        print(key+":",counts[key])
    print("NEEDS REVIEW:")
    for o in output:
        if o["status"]!="EXACT_ACTIVE_NAME":
            print(" ",o["ssh_username"],"|",o["status"],"|",o["other_options"][:220])
    print("READ-ONLY REPORT:",OUT,"MODE: 0600")
    print("NO connections activated or disabled; NO changes in Shahan or Hesab.")
if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("SHAHAN_MATCH_STOP:",type(exc).__name__,str(exc)[:180],file=sys.stderr)
        sys.exit(1)
