#!/usr/bin/env python3
"""HESAB_MAYA_EXTRA_RO_V1. Read-only 3x-ui API: Maya S3, Maya4. No client writes."""
import csv,getpass,io,json,os,subprocess,sys,tempfile,urllib.parse,urllib.request,urllib.error,http.cookiejar
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
BASE=Path("/opt/vpn-control-center")
CFG=Path("/root/.config/hesab-maya-extra.json")
OUT=BASE/"maya_extra_sync"/"public"
SERVERS=("maya1","maya-s3","maya4")
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
def request_json(opener,url,payload=None,headers=None):
 # HTTPS only, don't follow a redirect carrying a session or secret.
 h={"Accept":"application/json",**(headers or {})}
 body=json.dumps(payload).encode("utf8") if payload is not None else None
 if body is not None:h["Content-Type"]="application/json"
 req=urllib.request.Request(url,headers=h,data=body,method="POST" if body is not None else "GET")
 try:
  with opener.open(req,timeout=15) as r:
   if r.status!=200:stop("Unexpected panel HTTP status")
   content=r.read(6000001)
 except urllib.error.HTTPError as ex:
  stop("X-UI API returned HTTP "+str(ex.code)+" (verify panel path and authentication)")
 except (urllib.error.URLError,TimeoutError) as ex:
  stop("X-UI API connection failed ("+type(ex).__name__+")")
 if len(content)>6000000:stop("Panel response oversized")
 try:doc=json.loads(content)
 except ValueError:stop("Panel returned a non-JSON response")
 if not isinstance(doc,dict) or doc.get("success") is not True:
  stop("X-UI rejected API request")
 return doc
def pull(name,details):
 url=details["url"]
 if not url.startswith("https://"):stop("TLS/HTTPS required")
 base=url.rstrip("/")+"/"
 endpoint=base+"panel/api/inbounds/list"
 cookiejar=http.cookiejar.CookieJar()
 opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookiejar),NoRedirect)
 if details.get("mode")=="login":
  # Legacy 3x-ui uses form body, newer builds may accept JSON.
  # Only send credentials to the configured HTTPS panel, with redirects blocked.
  form=urllib.parse.urlencode({"username":details["username"],"password":details["password"]}).encode("utf8")
  req=urllib.request.Request(base+"login",data=form,headers={
   "Accept":"application/json","Content-Type":"application/x-www-form-urlencoded"})
  try:
   with opener.open(req,timeout=15) as response:
    result=json.loads(response.read(65536))
   if not isinstance(result,dict) or result.get("success") is not True:
    raise ValueError("Panel rejected login")
  except (urllib.error.HTTPError,ValueError):
   request_json(opener,base+"login",{
    "username":details["username"],"password":details["password"]})
  if not any(True for _ in cookiejar):stop("Panel login returned no session cookie")
  headers={}
 elif details.get("mode") in (None,"token"):
  headers={"Authorization":"Bearer "+details["token"]}
 else:stop("Unrecognized authentication mode")
 doc=request_json(opener,endpoint,headers=headers)
 if not isinstance(doc.get("obj"),list):stop("Unrecognized panel/API result")
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
   if not key:stop("Empty X-UI email")
   t=stats.get(key,{})
   def num(x):
    try:return int(x or 0)
    except(ValueError,TypeError):return 0
   entry={"email":email,
      "client_enabled":bool(c.get("enable",True)),
      "inbound_enabled":bool(inbound.get("enable",True)),
      "enabled":bool(inbound.get("enable",True)) and bool(c.get("enable",True)) and bool(t.get("enable",True)),
      "up_bytes":num(t.get("up")),"down_bytes":num(t.get("down")),
      "quota_bytes":num(t.get("total")),
      "traffic_expiry_ms":num(t.get("expiryTime")),
      "last_online_ms":num(t.get("lastOnline") or t.get("last_online")),
      "control_ambiguous":False,"multi_inbound":False}
   if key in users:
    # A current 3x-ui client can be attached to multiple inbounds.
    # Collapse by email; fail closed for toggle if enable flags disagree.
    prev=users[key]
    prev["multi_inbound"]=True
    if prev["client_enabled"] != entry["client_enabled"]:
     prev["control_ambiguous"]=True
    prev["client_enabled"]=prev["client_enabled"] or entry["client_enabled"]
    prev["enabled"]=prev["enabled"] or entry["enabled"]
    prev["inbound_enabled"]=prev["inbound_enabled"] or entry["inbound_enabled"]
    for field in ("up_bytes","down_bytes","quota_bytes","traffic_expiry_ms","last_online_ms"):
     prev[field]=max(prev[field],entry[field])
   else:users[key]=entry
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
 if len(sys.argv)<2:stop("Usage: configure maya1|maya-s3|maya4 OR check|sync|status")
 action=sys.argv[1];name=sys.argv[2] if len(sys.argv)>2 else None
 if action=="configure":
  if name not in SERVERS:stop("Specify maya1, maya-s3 or maya4")
  url=input("HTTPS 3x-ui panel base URL (include custom web path): ").strip().rstrip("/")
  p=urllib.parse.urlsplit(url)
  if p.scheme!="https" or not p.netloc or p.username or p.password or p.query or p.fragment:
   stop("Valid HTTPS URL without credentials required")
  auth=input("Auth: [L] panel username/password or [T] API bearer token? ").strip().lower() or "l"
  if auth=="l":
   username=input("Panel username: ").strip()
   password=getpass.getpass("Panel password (hidden): ")
   if not username or not password:stop("Missing panel credentials")
   entry={"url":url,"mode":"login","username":username,"password":password}
  elif auth=="t":
   token=getpass.getpass("3x-ui bearer API token (hidden): ").strip()
   if len(token)<8:stop("Missing bearer token")
   entry={"url":url,"mode":"token","token":token}
  else:stop("Choose login or token")
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
