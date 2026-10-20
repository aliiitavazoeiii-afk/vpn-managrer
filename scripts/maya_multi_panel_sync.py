#!/usr/bin/env python3
"""HESAB_MAYA_EXTRA_RO_V1. Read-only 3x-ui API: Maya S3, Maya4. No client writes."""
import csv,getpass,io,json,os,subprocess,sys,tempfile,urllib.parse,urllib.request,urllib.error
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
BASE=Path("/opt/vpn-control-center")
CFG=Path("/root/.config/hesab-maya-extra.json")
OUT=BASE/"maya_extra_sync"/"public"
SERVERS=("maya-s3","maya4")
def stop(s):raise RuntimeError(s)
def write(path,obj,mode=0o640):
 path.parent.mkdir(mode=0o750,parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(dir=path.parent)
 try:
  with os.fdopen(fd,"w") as f:
   json.dump(obj,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
  os.chmod(tmp,mode);os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def config():
 if not CFG.exists():return {}
 if CFG.stat().st_mode&0o077:stop("chmod 600 "+str(CFG))
 return json.loads(CFG.read_text())
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*a,**kw):return None
def pull(name,details):
 url=details["url"]
 if not url.startswith("https://"):stop("TLS/HTTPS required")
 endpoint=url.rstrip("/")+"/panel/api/inbounds/list"
 req=urllib.request.Request(endpoint,headers={"Accept":"application/json","Authorization":"Bearer "+details["token"]})
 opener=urllib.request.build_opener(NoRedirect)
 try:
  with opener.open(req,timeout=15) as r:
   content=r.read(6000001)
 except Exception as ex:stop("Panel read failed: "+type(ex).__name__)
 if len(content)>6000000:stop("Panel response oversized")
 doc=json.loads(content)
 if doc.get("success") is not True or not isinstance(doc.get("obj"),list):stop("Unrecognized panel/API result")
 users={}
 for inbound in doc["obj"]:
  settings=inbound.get("settings") or {}
  if isinstance(settings,str):settings=json.loads(settings)
  if not isinstance(settings,dict):stop("Invalid inbound settings")
  stats={}
  for st in inbound.get("clientStats") or []:
   k=str(st.get("email") or "").strip().casefold()
   if k:stats[k]=st
  for c in settings.get("clients",[]):
   email=str(c.get("email") or "").strip()
   key=email.casefold()
   if not key or key in users:stop("Duplicate/invalid X-UI email")
   t=stats.get(key,{})
   def num(x):
    try:return int(x or 0)
    except(ValueError,TypeError):return 0
   users[key]={"email":email,"enabled":bool(inbound.get("enable",True)) and bool(c.get("enable",True)) and bool(t.get("enable",True)),
      "up_bytes":num(t.get("up")),"down_bytes":num(t.get("down")),
      "quota_bytes":num(t.get("total")),
      "traffic_expiry_ms":num(t.get("expiryTime")),
      "last_online_ms":num(t.get("lastOnline") or t.get("last_online"))}
 if len(users)<1 or len(users)>5000:stop("Unexpected client count")
 return {"format":"HESAB_MAYA_EXTRA_V1","server":name,"synced_at":datetime.now(timezone.utc).isoformat(),"clients":[users[k] for k in sorted(users)]}
def dashboard():
 query="""COPY (SELECT id,display_name,
 COALESCE((SELECT CASE kind WHEN 'followup_cut' THEN 'removed' WHEN 'followup_waiting' THEN 'waiting'
 ELSE 'normal' END FROM audit_events
 WHERE kind IN ('followup_cut','followup_waiting','followup_clear')
 AND message LIKE 'sid=' || s.id::text || ';%' ORDER BY id DESC LIMIT 1),'normal') AS state
 FROM subscriptions s) TO STDOUT WITH CSV HEADER;"""
 cmd=["docker","compose","-f","docker-compose.yml","-f","docker-compose.sms.yml","exec","-T","db",
 "sh","-c",'PGOPTIONS="-c default_transaction_read_only=on" PGPASSWORD="$POSTGRES_PASSWORD" psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"']
 p=subprocess.run(cmd,input=query,cwd=BASE,capture_output=True,text=True,timeout=40)
 if p.returncode:stop("Dashboard read-only query failed")
 data=list(csv.DictReader(io.StringIO(p.stdout)))
 if not data or set(data[0])!={"id","display_name","state"}:stop("Dashboard schema unknown")
 return data
def normalize(s):return "".join(str(s or "").casefold().split())
def sync(name,details,commit):
 snapshot=pull(name,details)
 rows=dashboard();idx=defaultdict(list)
 for r in rows:
  if r["state"]!="removed":idx[normalize(r["display_name"])].append(r)
 ids=set()
 for c in snapshot["clients"]:
  matches=idx[normalize(c["email"])]
  match=matches[0] if len(matches)==1 else None
  sid=int(match["id"]) if match else None
  if sid in ids:sid=None
  if sid:ids.add(sid)
  c.update({"sid":sid,"name":match["display_name"] if sid else "",
            "dashboard_state":match["state"] if sid else "",
            "reason":"exact_name" if sid else "unmatched_review"})
 snapshot["linked"]=len(ids);snapshot["unmatched"]=len(snapshot["clients"])-len(ids)
 if commit:write(OUT/(name+".json"),snapshot)
 print(name,"total=",len(snapshot["clients"]),"linked=",snapshot["linked"],
       "unmatched=",snapshot["unmatched"],"snapshot_saved=",commit)
def main():
 if len(sys.argv)<2:stop("Usage: configure maya-s3|maya4 OR check|sync|status")
 action=sys.argv[1];name=sys.argv[2] if len(sys.argv)>2 else None
 if action=="configure":
  if name not in SERVERS:stop("Specify maya-s3 or maya4")
  url=input("HTTPS 3x-ui panel base URL (include custom web path): ").strip().rstrip("/")
  p=urllib.parse.urlsplit(url)
  if p.scheme!="https" or not p.netloc or p.username or p.password or p.query or p.fragment:
   stop("Valid HTTPS URL without credentials required")
  token=getpass.getpass("3x-ui bearer API token (hidden): ").strip()
  if len(token)<8:stop("Missing bearer token")
  entry={"url":url,"token":token}
  sync(name,entry,False) # Validate before saving. Never write a client.
  found=config();found[name]=entry
  CFG.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
  write(CFG,found,0o600)
  print("Saved protected configuration for",name)
 elif action in ("sync","check"):
  found=config()
  for key in ([name] if name else SERVERS):
   if key not in found:print(key,"NOT_CONFIGURED");continue
   try:sync(key,found[key],action=="sync")
   except Exception as ex:
    print(key,"FAILED:",str(ex)[:160],file=sys.stderr)
    if name:raise
 elif action=="status":
  for key in SERVERS:
   p=OUT/(key+".json")
   if p.exists():
    o=json.loads(p.read_text())
    print(key,o.get("synced_at"),"linked",o.get("linked"),"unmatched",o.get("unmatched"))
   else:print(key,"NOT_SYNCED")
 else:stop("Unknown action")
if __name__=="__main__":
 try:main()
 except Exception as ex:
  print("MAYA_EXTRA_STOP:",str(ex)[:180],file=sys.stderr);sys.exit(1)
