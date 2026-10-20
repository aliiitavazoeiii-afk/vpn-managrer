#!/usr/bin/env python3
"""Read-only audit: XUI clients of three Maya servers vs financial subscription IDs.
Never updates any XUI account, dashboard record, or approval mapping.
Produces /root/... TSV files and sanitized console summary for user review.
"""
import csv,difflib,io,json,os,socket,sys,unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path
sys.path.insert(0,"/opt/vpn-control-center/scripts")
import maya_multi_panel_sync as connector

SOCK="/opt/vpn-control-center/maya_extra_sync/live.sock"
OLD=Path("/opt/vpn-control-center/maya1_sync/mapping.json")
APPROVED=Path("/opt/vpn-control-center/maya_extra_sync/approved_links.json")
OLD_SHA="8e1509674cf0c06d1e8015064c8c3b69b76931311bce4489b1bbda49d50f37fb"
SERVERS=("maya1","maya-s3","maya4")

def norm(s):
    val=unicodedata.normalize("NFKC",str(s or "")).casefold()
    return "".join(val.split())  # Same normalization as live control-room linking

def read_old():
    if not OLD.is_file():return {}
    raw=json.loads(OLD.read_text())
    if (raw.get("format")!="MAYA1_CONTROL_MAPPING_V1"
       or raw.get("expected_sha")!=OLD_SHA):return {}
    return raw.get("mapping",{})

def approved_links():
    if not APPROVED.exists():return {}
    if APPROVED.stat().st_mode&0o077:
        raise RuntimeError("Manual approval file must have permissions 600")
    raw=json.loads(APPROVED.read_text())
    if raw.get("format")!="HESAB_MAYA_APPROVALS_V1":raise RuntimeError("Invalid manual approval file")
    return raw.get("servers",{})

def snapshot(server):
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(75)
        s.connect(SOCK)
        s.sendall((json.dumps({"op":"snapshot","server":server})+"\n").encode())
        s.shutdown(socket.SHUT_WR)
        data=bytearray()
        while not data.endswith(b"\n"):
            part=s.recv(65536)
            if not part:break
            data.extend(part)
            if len(data)>3000000:raise RuntimeError("Oversized socket reply")
    if not data.endswith(b"\n"):raise RuntimeError("Incomplete socket reply")
    doc=json.loads(data)
    if doc.get("ok") is not True:raise RuntimeError(str(doc.get("error") or "No live response"))
    snap=doc["snapshot"]
    if snap.get("server")!=server:raise RuntimeError("Server identity mismatch")
    clients=snap.get("clients")
    if not isinstance(clients,list) or not clients:raise RuntimeError("Empty server roster")
    return clients

def main():
    rows=connector.dashboard()  # read-only SQL SELECT
    active={int(r["id"]):r for r in rows if r["state"]!="removed"}
    labels=defaultdict(list)
    for r in active.values():labels[norm(r["display_name"])].append(r)
    old=read_old()
    manual=approved_links()
    output=[]
    unresolved=[]
    stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
    for server in SERVERS:
        clients=snapshot(server)
        used=set()
        count=defaultdict(int)
        for c in sorted(clients,key=lambda x:str(x.get("email") or "").casefold()):
            email=str(c.get("email") or "").strip()
            if not email:continue
            key=email.casefold()
            source="UNMATCHED";sid=None;reason=""
            explicit=(manual.get(server) or {}).get(key)
            if explicit is not None:
                if isinstance(explicit,dict) and explicit.get("exclude") is True:
                    source="EXCLUDED_APPROVED"
                elif isinstance(explicit,dict) and type(explicit.get("sid")) is int:
                    sid=explicit["sid"];source="MANUAL_APPROVED"
                else:
                    source="MANUAL_INVALID";reason="Approval data invalid"
            elif server=="maya1" and key in old:
                ref=old[key]
                if ref.get("reason") in ("confirmed","exact_approved") and ref.get("id") is not None:
                    sid=int(ref["id"]);source="MAYA1_LEGACY_APPROVED"
                elif ref.get("id") is None:
                    source="EXCLUDED_LEGACY"
            if sid is None and source=="UNMATCHED":
                hits=labels.get(norm(email),[])
                if len(hits)==1:
                    sid=int(hits[0]["id"]);source="EXACT_NAME"
                elif len(hits)>1:
                    source="DUPLICATE_NAMES"
            if sid is not None and sid not in active:
                reason="Dashboard account archived or missing";source="REVIEW_MISSING_SID";sid=None
            if sid is not None and sid in used:
                reason="Two XUI clients resolve to one dashboard ID";source="REVIEW_DUPLICATE_ID";sid=None
            if sid is not None:used.add(sid)
            hit=active.get(sid) if sid else None
            candidate_names=difflib.get_close_matches(norm(email),list(labels),n=3,cutoff=.48)
            choices=[]
            for name in candidate_names:
                for cand in labels[name][:2]:
                    if int(cand["id"])!=sid:
                        choices.append(str(cand["id"])+":"+cand["display_name"])
            row={
             "server":server,"xui_email":email,"current_sid":sid or "",
             "dashboard_name":hit["display_name"] if hit else "",
             "status":source,"suggested_dashboard_ids_names":" | ".join(choices[:4]),
             "notes":reason
            }
            output.append(row)
            count[source]+=1
            if sid is None:unresolved.append(row)
        print(f"{server}: total={len(clients)} matched={len(used)} needs_review={sum(v for k,v in count.items() if k not in ('EXACT_NAME','MANUAL_APPROVED','MAYA1_LEGACY_APPROVED'))}")
        print("  breakdown:",", ".join(f"{k}={v}" for k,v in sorted(count.items())))
    cols=list(output[0])
    for kind,items in (("unmatched",unresolved),("all",output)):
        dest=Path(f"/root/maya_review_{kind}_{stamp}.tsv")
        with dest.open("w",encoding="utf-8",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=cols,delimiter="\t")
            writer.writeheader();writer.writerows(items)
        os.chmod(dest,0o600)
        print(f"REPORT_{kind.upper()}={dest}")
    print("\n== ACCOUNTS TO REVIEW (XUI --> SUGGESTED DASHBOARD IDs; NOT CONFIRMED) ==")
    for r in unresolved:
        print(f'{r["server"]} | {r["xui_email"]} | {r["status"]} | {r["suggested_dashboard_ids_names"] or "-"}')
    print(f'\nREVIEW_TOTAL={len(unresolved)}. No data or account states modified.')

if __name__=="__main__":
    try:main()
    except Exception as ex:
        print("MAYA_AUDIT_STOP:",type(ex).__name__,str(ex)[:200],file=sys.stderr)
        sys.exit(1)
