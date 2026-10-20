#!/usr/bin/env python3
"""HESAB_MAYA_EXTRA_RO_V1. Read-only 3x-ui API: Maya S3, Maya4. No client writes."""
import csv,getpass,io,json,os,subprocess,sys,tempfile,urllib.parse,urllib.request,urllib.error,http.cookiejar,ipaddress,socket,time
from contextlib import contextmanager
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
def panel_base(raw_url):
 # Operators often copy the dashboard URL ending in /panel/.
 # 3x-ui login is at BASE/login and its inbound API at BASE/panel/api.
 # Strip ONLY the exact trailing UI segment; never mutate hostname/TLS.
 value=str(raw_url or "").strip().rstrip("/")
 parsed=urllib.parse.urlsplit(value)
 if (parsed.scheme!="https" or not parsed.netloc or parsed.username or
     parsed.password or parsed.query or parsed.fragment):
  stop("Valid HTTPS 3x-ui panel URL required")
 if parsed.path.endswith("/panel"):
  value=value[:-len("/panel")]
 return value.rstrip("/")
@contextmanager
def panel_connection(details):
 # For public HTTPS, enforce certificate verification (urllib default).
 # For plain HTTP x-ui, credentials travel ONLY through a verified SSH tunnel
 # to its loopback port. Never connect directly to public HTTP.
 mode=details.get("transport","https")
 process=None
 if mode=="https":
  base=panel_base(details["url"])+"/"
 elif mode=="ssh":
  host=str(details["ssh_host"])
  ipaddress.ip_address(host)
  remote_port=int(details["remote_port"])
  ssh_port=int(details.get("ssh_port",22))
  if not (1<=remote_port<=65535 and 1<=ssh_port<=65535):
   stop("Invalid SSH/X-UI port")
  path=str(details["panel_path"])
  if not path.startswith("/") or "//" in path or ".." in path or len(path)>190:
   stop("Invalid x-ui panel base path")
  key="/root/.ssh/hesab_"+str(details["server"]).replace("-","_")+"_tunnel"
  if not os.path.isfile(key):stop("SSH key missing: "+key+"; run SSH tunnel bootstrap first")
  port_socket=socket.socket()
  port_socket.bind(("127.0.0.1",0))
  local_port=port_socket.getsockname()[1]
  port_socket.close()
  args=["ssh","-N","-T","-i",key,"-o","IdentitiesOnly=yes","-o","BatchMode=yes",
        "-o","StrictHostKeyChecking=yes","-o","ExitOnForwardFailure=yes",
        "-o","ConnectTimeout=8","-o","ServerAliveInterval=5","-o","ServerAliveCountMax=2",
        "-p",str(ssh_port),"-L",f"127.0.0.1:{local_port}:127.0.0.1:{remote_port}",
        str(details.get("ssh_user") or "root")+"@"+host]
  process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
  for i in range(35):
   if process.poll() is not None:stop("SSH tunnel failed; check key, host fingerprint and remote SSH")
   with socket.socket() as test:
    test.settimeout(.2)
    if test.connect_ex(("127.0.0.1",local_port))==0:break
   time.sleep(.15)
  else:stop("SSH tunnel local forward did not open")
  base="http://127.0.0.1:"+str(local_port)+"/"+path.strip("/")+"/"
 else:stop("Unsupported panel transport")
 try:
  jar=http.cookiejar.CookieJar()
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),
          urllib.request.HTTPCookieProcessor(jar),NoRedirect)
  if details.get("mode")=="login":
   data=urllib.parse.urlencode({
    "username":details["username"],"password":details["password"]}).encode("utf8")
   req=urllib.request.Request(base+"login",data=data,headers={
      "Accept":"application/json","Content-Type":"application/x-www-form-urlencoded"})
   try:
    with opener.open(req,timeout=15) as r:
     answer=json.loads(r.read(65536))
    if not isinstance(answer,dict) or answer.get("success") is not True:
     stop("Panel rejected login")
   except (urllib.error.HTTPError,ValueError):
    request_json(opener,base+"login",{
     "username":details["username"],"password":details["password"]})
   if not list(jar):stop("Panel did not set session cookie")
   headers={}
  elif details.get("mode") in ("token",None):
   headers={"Authorization":"Bearer "+details["token"]}
  else:stop("Invalid panel authentication mode")
  yield opener,base,headers
 finally:
  if process is not None:
   process.terminate()
   try:process.wait(timeout=5)
   except subprocess.TimeoutExpired:
    process.kill()
    process.wait(timeout=5)

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
 with panel_connection(details) as (opener,base,headers):
  doc=request_json(opener,base+"panel/api/inbounds/list",headers=headers)
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
  raw_url=input("3x-ui panel URL (HTTPS or HTTP over SSH): ").strip().rstrip("/")
  parsed=urllib.parse.urlsplit(raw_url)
  if parsed.scheme=="https":
   url=panel_base(raw_url)
   entry={"url":url,"transport":"https","server":name}
   print("HTTPS panel connection with verified TLS.")
  elif parsed.scheme=="http":
   if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
       or parsed.port is None):
    stop("Valid HTTP panel host and port required for SSH tunneling")
   ipaddress.ip_address(parsed.hostname)
   path=parsed.path.rstrip("/")
   if path.endswith("/panel"):path=path[:-6]
   if not path.startswith("/") or ".." in path or "//" in path:
    stop("Invalid X-UI panel path")
   print("HTTP panel detected: SSH encryption is REQUIRED; direct plaintext login prohibited.")
   entry={"server":name,"transport":"ssh","ssh_host":parsed.hostname,
          "ssh_port":22,"ssh_user":"root","remote_port":parsed.port,
          "panel_path":path}
  else:stop("HTTPS or SSH-wrapped HTTP required")
  auth=input("Auth: [L] panel username/password or [T] API bearer token? ").strip().lower() or "l"
  if auth=="l":
   username=input("Panel username: ").strip()
   password=getpass.getpass("Panel password (hidden): ")
   if not username or not password:stop("Missing panel credentials")
   entry.update({"mode":"login","username":username,"password":password})
  elif auth=="t":
   token=getpass.getpass("3x-ui bearer API token (hidden): ").strip()
   if len(token)<8:stop("Missing bearer token")
   entry.update({"mode":"token","token":token})
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
