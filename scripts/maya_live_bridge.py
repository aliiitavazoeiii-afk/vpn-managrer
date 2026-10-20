#!/usr/bin/env python3
"""HESAB_MAYA_LIVE_BRIDGE_V1: local root-only session broker, no public TCP port.
Read live 3x-ui snapshots, optionally set ONE client enable bit with read-back.
Never deletes/adds clients, changes expiration, or touches financial records.
"""
import copy,http.cookiejar,json,os,re,socketserver,sys,threading,time,urllib.parse,urllib.request,urllib.error
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,"/opt/vpn-control-center/scripts")
import maya_multi_panel_sync as maya

ROOT=Path("/opt/vpn-control-center/maya_extra_sync")
SOCK=ROOT/"live.sock"
AUDIT=ROOT/"live-actions.jsonl"
MAX_REQUEST=4096
LOCKS={name:threading.Lock() for name in maya.SERVERS}

def fail(message):
    raise ValueError(message)

def opener_for(details):
    url=details.get("url","").rstrip("/")+"/"
    if not url.startswith("https://"):fail("HTTPS panel required")
    jar=http.cookiejar.CookieJar()
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),maya.NoRedirect)
    if details.get("mode")=="login":
        # Classic 3x-ui login uses urlencoded form; new installations also
        # commonly accept JSON. Only try JSON if the first response is rejected.
        form=urllib.parse.urlencode({
            "username":details["username"],"password":details["password"]}).encode("utf8")
        req=urllib.request.Request(url+"login",data=form,headers={
             "Accept":"application/json","Content-Type":"application/x-www-form-urlencoded"})
        try:
            with opener.open(req,timeout=12) as response:
                data=json.loads(response.read(65536))
            if not data.get("success"):raise ValueError("Login rejected")
        except (urllib.error.HTTPError,ValueError):
            maya.request_json(opener,url+"login",{
              "username":details["username"],"password":details["password"]})
        if not list(jar):fail("Login returned no session; check panel version")
        headers={}
    elif details.get("mode") in ("token",None):
        headers={"Authorization":"Bearer "+details["token"]}
    else:fail("Authentication configuration unsupported")
    return opener,url,headers

def snapshot(server,details):
    # Dynamic roster, no fixed count or fixed fingerprint.
    return maya.pull(server,details)

def legacy_vless_toggle(opener,base,headers,email,expected,target):
    """Old 3x-ui fallback only for ONE VLESS client; preserve complete fields.
    Based on the already established Maya1 verified updateClient procedure.
    Never serialize or update an entire inbound configuration.
    """
    source=maya.request_json(opener,base+"panel/api/inbounds/list",headers=headers)
    hits=[]
    for inbound in source.get("obj") or []:
        if str(inbound.get("protocol") or "").lower()!="vless":continue
        settings=inbound.get("settings") or {}
        if isinstance(settings,str):settings=json.loads(settings)
        if not isinstance(settings,dict):fail("Invalid old XUI inbound settings")
        for c in settings.get("clients",[]):
            if str(c.get("email") or "").strip().casefold()==email.casefold():
                hits.append((inbound,c))
    if len(hits)!=1:fail("Legacy XUI requires exactly one matching VLESS client")
    inbound,client=hits[0]
    if bool(client.get("enable",True)) is not expected:
        fail("Legacy XUI client changed before update")
    uuid=str(client.get("id") or "")
    if not re.fullmatch(r"[0-9a-fA-F-]{32,40}",uuid):
        fail("Unsupported VLESS UUID; refusing old API mutation")
    previous=copy.deepcopy(client)
    updated=copy.deepcopy(client)
    updated["enable"]=target
    payload={"id":int(inbound["id"]),
             "settings":json.dumps({"clients":[updated]},ensure_ascii=False,separators=(",",":"))}
    maya.request_json(opener,base+"panel/api/inbounds/updateClient/"+
                    urllib.parse.quote(uuid,safe=""),payload,headers=headers)
    # DO NOT assume POST means the client is changed; the outer caller will
    # read the state again and mark success only on fresh confirmation.
    return previous

def send_enable(server,details,email,expected,target):
    before=snapshot(server,details)
    matches=[c for c in before["clients"] if c["email"].casefold()==email.casefold()]
    if len(matches)!=1:fail("Client missing or duplicate; no update")
    if matches[0].get("control_ambiguous"):
        fail("Different enabled flags across inbounds; manual X-UI review required")
    actual=bool(matches[0].get("client_enabled",matches[0]["enabled"]))
    if actual is not expected:fail("Client changed since operator display; refresh first")
    if expected is target:fail("Requested state already set")
    opener,base,headers=opener_for(details)
    # Modern 3x-ui exposes client-scoped bulk toggle. Strictly ONE email.
    # Older panels can upgrade or use a separate locally constrained agent.
    path="panel/api/clients/bulkEnable" if target else "panel/api/clients/bulkDisable"
    legacy_before=None
    try:
        reply=maya.request_json(opener,base+path,{"emails":[email]},headers=headers)
        value=reply.get("obj")
        if isinstance(value,dict) and (value.get("failed") or value.get("skipped")):
            fail("Panel reports incomplete client toggle")
    except (ValueError,RuntimeError) as ex:
        # Only an explicit 404 permits a second, *different* compatibility
        # path. No retry after timeout, connection drop, 403 or 5xx.
        if "returned HTTP 404" not in str(ex):
            raise
        legacy_before=legacy_vless_toggle(opener,base,headers,email,expected,target)
    after=snapshot(server,details)
    match=[c for c in after["clients"] if c["email"].casefold()==email.casefold()]
    if len(match)!=1 or match[0].get("control_ambiguous") or bool(match[0].get("client_enabled",match[0]["enabled"])) is not target:
        fail("Panel did not confirm requested state; inspect 3x-ui")
    if legacy_before is not None:
        # Verify every original client field survived the old updateClient call.
        fresh=maya.request_json(opener,base+"panel/api/inbounds/list",headers=headers)
        hits=[]
        for inbound in fresh.get("obj") or []:
            settings=inbound.get("settings") or {}
            if isinstance(settings,str):settings=json.loads(settings)
            if not isinstance(settings,dict):continue
            for c in settings.get("clients",[]):
                if str(c.get("email") or "").strip().casefold()==email.casefold():
                    hits.append(c)
        if len(hits)!=1 or any(hits[0].get(k)!=v for k,v in legacy_before.items() if k!="enable"):
            fail("Old panel update changed unexpected fields; inspect client immediately")
    return {"ok":True,"client_enabled":target,
            "confirmed_at":datetime.now(timezone.utc).isoformat()}

def append_audit(server,email,expected,target,result):
    obj={"at":datetime.now(timezone.utc).isoformat(),"server":server,
         "client_email":email,"expected":expected,"target":target,"result":result}
    fd=os.open(AUDIT,os.O_CREAT|os.O_APPEND|os.O_WRONLY,0o600)
    try:
        payload=json.dumps(obj,ensure_ascii=False,separators=(",",":")).encode()+b"\n"
        os.write(fd,payload);os.fsync(fd)
    finally:os.close(fd)

def handle(msg):
    if not isinstance(msg,dict):fail("Bad request")
    if msg.get("server") not in maya.SERVERS:fail("Unknown server")
    if set(msg) not in ({"op","server"},{"op","server","email","expected","target"}):
        fail("Unexpected fields")
    server=msg["server"];op=msg["op"]
    if op not in ("snapshot","toggle"):fail("Unknown operation")
    cfg=maya.config()
    if server not in cfg:fail("Server not configured; use configure on management host")
    with LOCKS[server]:
        if op=="snapshot":
            if set(msg)!={"op","server"}:fail("Unexpected snapshot fields")
            return {"ok":True,"snapshot":snapshot(server,cfg[server])}
        if set(msg)!={"op","server","email","expected","target"}:fail("Missing toggle fields")
        email=msg["email"]
        if not isinstance(email,str) or len(email)>160 or not email.strip():
            fail("Bad client label")
        exp,tgt=msg["expected"],msg["target"]
        if type(exp) is not bool or type(tgt) is not bool or exp is tgt:
            fail("Bad enable state transition")
        try:
            result=send_enable(server,cfg[server],email,exp,tgt)
        except Exception as ex:
            append_audit(server,email,exp,tgt,"unconfirmed")
            raise
        append_audit(server,email,exp,tgt,"confirmed")
        return result

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            line=self.rfile.readline(MAX_REQUEST+1)
            if not line or len(line)>MAX_REQUEST or not line.endswith(b"\n"):
                fail("Invalid request size")
            value=handle(json.loads(line))
        except Exception as ex:
            value={"ok":False,"error":str(ex)[:160]}
        data=json.dumps(value,ensure_ascii=False,separators=(",",":")).encode()+b"\n"
        self.wfile.write(data)

class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
    daemon_threads=True
    allow_reuse_address=True

def main():
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o750)
    if SOCK.exists():SOCK.unlink()
    with Server(str(SOCK),Handler) as server:
        os.chmod(SOCK,0o660)
        try:server.serve_forever()
        finally:
            try:SOCK.unlink()
            except FileNotFoundError:pass

if __name__=="__main__":
    main()
