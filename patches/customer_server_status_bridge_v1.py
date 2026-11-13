# HESAB_CUSTOMER_SERVER_STATUS_BRIDGE_V1
# READ-ONLY bridge: only approved subscription->Maya links and existing cached
# monitoring outputs. No SSH, no sockets, no downloads, no tunnel changes.
# Must be appended to the already deployed admin maya1_control.py AFTER mapping,
# control room and manual-path-test addons.
import hashlib as _cssb_hashlib
import hmac as _cssb_hmac
import json as _cssb_json
import re as _cssb_re
import stat as _cssb_stat
import threading as _cssb_threading
import time as _cssb_time
from pathlib import Path as _cssb_Path
from fastapi import Request as _cssb_Request
from fastapi.responses import JSONResponse as _cssb_JSON

_CSSB_SECRET=_cssb_Path("/run/hesab-customer-status-v1.key")
_CSSB_DUAL=_cssb_Path("/srv/maya-live/dual_hourly_v1.json")
_CSSB_TRANSFER=_cssb_Path("/srv/maya-live/path_transfer_v1/status.json")
_CSSB_APPROVED=_cssb_Path("/srv/maya-live/approved_links.json")
_CSSB_LEGACY=_cssb_Path("/srv/maya1-sync/mapping.json")
_CSSB_NAMES=("maya1","maya-s3","maya4")
_CSSB_ROLES=("backhaul","mieru","haproxy")
_CSSB_LABELS={"maya1":"مایا ۱","maya-s3":"مایا ۳","maya4":"مایا ۴"}
_CSSB_DUAL_MAX_AGE=4500
_CSSB_TRANSFER_MAX_AGE=1800
_CSSB_RATE_LOCK=_cssb_threading.Lock()
_CSSB_RATE={}   # local process; no active probe and always bounded
_CSSB_REPORT_LOCK=_cssb_threading.Lock()
_CSSB_REPORT_CACHE={}  # one shared central report per physical Maya, 30s TTL
_CSSB_MAX_BRIDGE_CALLS=90 # 90/min across entire process
_CSSB_SECRET_MIN=32

def _cssb_read(path,max_size):
    """Read-only protected snapshot. No remote calls or user-supplied paths."""
    try:
        if not path.is_file() or path.is_symlink():
            return None
        st=path.stat()
        if not 0<st.st_size<=max_size:
            return None
        value=_cssb_json.loads(path.read_text(encoding="utf8"))
        return value if type(value) is dict else None
    except (OSError,ValueError,UnicodeError,TypeError):
        return None

def _cssb_secret():
    try:
        if _CSSB_SECRET.is_symlink() or not _CSSB_SECRET.is_file():
            return None
        mode=_CSSB_SECRET.stat().st_mode
        if mode & (_cssb_stat.S_IRWXG | _cssb_stat.S_IRWXO):
            return None
        data=_CSSB_SECRET.read_bytes().strip()
        return data if 32<=len(data)<=128 else None
    except OSError:
        return None

def _cssb_verify(sid,stamp,signature,now=None):
    if type(sid) is not int or sid<1 or sid>2147483647:
        return False
    if not isinstance(stamp,str) or not _cssb_re.fullmatch(r"\d{10}",stamp):
        return False
    if not isinstance(signature,str) or not _cssb_re.fullmatch(r"[0-9a-f]{64}",signature):
        return False
    moment=int(_cssb_time.time() if now is None else now)
    if abs(moment-int(stamp))>30:
        return False
    secret=_cssb_secret()
    if not secret:return False
    digest=_cssb_hmac.new(secret,f"v1:{stamp}:{sid}".encode(),
                    _cssb_hashlib.sha256).hexdigest()
    return _cssb_hmac.compare_digest(digest,signature)

def _cssb_approved():
    """Only explicit approved sid links. No matching based on customer names."""
    if not callable(globals().get("_ma_approved")):
        return None
    try:
        return _ma_approved()   # existing root-only validated mapping
    except (ValueError,TypeError,OSError,KeyError,PermissionError):
        return None

def _cssb_legacy():
    """Maya1 legacy map: only root-protected confirmed records, never guesses."""
    try:
        st=_CSSB_LEGACY.stat()
        # maya1_readonly_sync.py writes root-owned 0640 JSON atomically.
        # Read-only group access is acceptable; group write/any other denied.
        if (_CSSB_LEGACY.is_symlink() or st.st_uid!=0 or
            st.st_mode&(_cssb_stat.S_IWGRP|_cssb_stat.S_IRWXO)):
            return {}
    except OSError:
        return {}
    doc=_cssb_read(_CSSB_LEGACY,200000)
    if (not doc or doc.get("format")!="MAYA1_CONTROL_MAPPING_V1" or
        doc.get("expected_sha")!=globals().get("_ML_APPROVAL_SHA") or
        type(doc.get("mapping")) is not dict):
        return {}
    mapping={}
    for email,item in doc["mapping"].items():
        if (isinstance(email,str) and type(item) is dict and
            item.get("reason") in ("confirmed","exact_approved") and
            type(item.get("id")) is int and item["id"]>0):
            mapping[email.casefold()]=item["id"]
    return mapping

def _cssb_server_for_sid(sid):
    """Reject all conflicting cross-server approvals and unverified/removed IDs."""
    if type(sid) is not int or sid<=0:return None
    approved=_cssb_approved()
    if approved is None:return None
    owners=set()
    for server in _CSSB_NAMES:
        data=approved.get(server,{})
        if type(data) is not dict:return None
        if any(type(v) is dict and type(v.get("sid")) is int
               and v["sid"]==sid for v in data.values()):
            owners.add(server)
    # Existing Maya1 approvals are superseded by explicit entry per XUI key.
    manual_maya1=approved.get("maya1",{})
    for email,legacy_sid in _cssb_legacy().items():
        if email in manual_maya1:continue
        if legacy_sid==sid:owners.add("maya1")
    return next(iter(owners)) if len(owners)==1 else None

def _cssb_fresh(epoch,max_age,now):
    return type(epoch) is int and -30<=now-epoch<=max_age

def _cssb_connection(dual,server,role,now):
    if role=="haproxy":
        return ("unknown",None)
    if not dual or dual.get("format")!="HESAB_DUAL_HOURLY_V1":
        return ("unknown",None)
    collected=dual.get("collected_at")
    if not _cssb_fresh(collected,_CSSB_DUAL_MAX_AGE,now):
        return ("unknown",None)
    servers=dual.get("servers")
    info=servers.get(server) if type(servers) is dict else None
    if type(info) is not dict or info.get("state")!="ok" or (
        not _cssb_fresh(info.get("sampled_at"),_CSSB_DUAL_MAX_AGE,now)
    ) or type(info.get("controller_age_s")) is not int or not 0<=info["controller_age_s"]<=30:
        return ("unknown",None)
    paths=info.get("paths")
    item=paths.get(role) if type(paths) is dict else None
    if type(item) is not dict:return ("unknown",None)
    state=item.get("state")
    if state=="healthy" and item.get("https_total")==3 and (
        type(item.get("https_passed")) is int and item["https_passed"]>=2
    ):
        return ("connected",collected)
    if state=="down":return ("down",collected)
    return ("unknown",None)

def _cssb_transfer(transfer,server,role,now):
    if not transfer or transfer.get("format")!="HESAB_PATH_TEST_ACCOUNT_V1":
        return ("unknown",None)
    started,completed=transfer.get("started_at"),transfer.get("completed_at")
    if (transfer.get("state")!="completed" or
        not _cssb_fresh(completed,_CSSB_TRANSFER_MAX_AGE,now) or
        type(started) is not int or started>completed or
        completed-started>400 or
        not isinstance(transfer.get("run_id"),str) or
        not _cssb_re.fullmatch(r"[0-9a-f]{24}",transfer["run_id"])):
        return ("unknown",None)
    servers=transfer.get("servers")
    record=servers.get(server) if type(servers) is dict else None
    if type(record) is not dict or record.get("state")!="completed":
        return ("unknown",None)
    paths=record.get("paths")
    metrics=paths.get(role) if type(paths) is dict else None
    if type(metrics) is not dict:return ("unknown",None)
    total=metrics.get("requested_bytes")
    got=metrics.get("received_bytes")
    http=metrics.get("http_status")
    code=metrics.get("exit_code")
    elapsed=metrics.get("duration_ms")
    if (type(total) is not int or total!=524288 or
        type(got) is not int or not 0<=got<=total or
        type(http) is not int or not 0<=http<=599 or
        type(code) is not int or not 0<=code<=255 or
        (elapsed is not None and (type(elapsed) is not int or not 0<=elapsed<=29000))):
        return ("unknown",None)
    reason=metrics.get("reason")
    if code==28 or reason=="timeout":return ("timeout",completed)
    if got<total and (got>0 or reason=="incomplete"):
        return ("incomplete",completed)
    if code==0 and http==200 and got==total and elapsed is not None:
        return ("healthy" if elapsed<=12000 else "slow",completed)
    if code!=0 or http!=200:return ("disrupted",completed)
    return ("unknown",None)

def _cssb_report(server,now=None):
    """Only one server's sanitized evidence leaves the management service."""
    if server not in _CSSB_NAMES:return None
    now=int(_cssb_time.time() if now is None else now)
    dual=_cssb_read(_CSSB_DUAL,16000)
    transfer=_cssb_read(_CSSB_TRANSFER,20000)
    output={}
    for role in _CSSB_ROLES:
        conn,conn_time=_cssb_connection(dual,server,role,now)
        real,real_time=_cssb_transfer(transfer,server,role,now)
        # Current connectivity failure takes precedence if newer than transfer.
        if conn=="down" and (real_time is None or conn_time>=real_time):
            state="disrupted"
        elif real!="unknown":
            state=real
        elif conn=="down":
            state="disrupted"
        elif conn=="connected":
            state="connection_only"
        else:
            state="unknown"
        output[role]={"state":state,"connection":conn,"transfer":real,
                      "connection_at":conn_time,"transfer_at":real_time}
    values=[entry["state"] for entry in output.values()]
    if any(v in ("timeout","incomplete","disrupted") for v in values):
        summary="disrupted"
    elif "slow" in values:summary="slow"
    elif all(v=="healthy" for v in values):summary="healthy"
    elif "connection_only" in values:summary="connection_only"
    else:summary="unknown"
    observed=[x for path in output.values() for x in
              (path["connection_at"],path["transfer_at"]) if x is not None]
    return {"server":server,"server_label":_CSSB_LABELS[server],
            "summary":summary,"paths":output,
            "last_checked_at":max(observed) if observed else None,
            "method":"central_cached_only",
            "max_transfer_age_s":_CSSB_TRANSFER_MAX_AGE}

def _cssb_cached_report(server,now=None):
    """One cached report per Maya, shared by all approved subscriptions there.
    The lock also coalesces concurrent reads of the same central report.
    """
    if server not in _CSSB_NAMES:return None
    now=int(_cssb_time.time() if now is None else now)
    with _CSSB_REPORT_LOCK:
        current=_CSSB_REPORT_CACHE.get(server)
        if current and 0<=now-current[0]<30:
            return current[1]
        result=_cssb_report(server,now)
        _CSSB_REPORT_CACHE[server]=(now,result)
        return result

def _cssb_rate(now,server):
    # Limit both aggregate access and each physical Maya; no active probes.
    with _CSSB_RATE_LOCK:
        cutoff=now-60
        for key,value in list(_CSSB_RATE.items()):
            if value[0]<cutoff:_CSSB_RATE.pop(key,None)
        keys=[("all",_CSSB_MAX_BRIDGE_CALLS)]
        if server in _CSSB_NAMES:keys.append(("server:"+server,30))
        fresh=[]
        for key,limit in keys:
            start,count=_CSSB_RATE.get(key,(now,0))
            if now-start>=60:start,count=now,0
            if count>=limit:return False
            fresh.append((key,start,count+1))
        for key,start,count in fresh:_CSSB_RATE[key]=(start,count)
        return True

def _cssb_endpoint(request:_cssb_Request):
    # Internal endpoint is reachable through public proxy routes too.
    # Authentication is compulsory even when Docker network is private.
    raw_sid=request.query_params.get("sid")
    if raw_sid is None or not _cssb_re.fullmatch(r"[1-9]\d{0,9}",raw_sid):
        return _cssb_JSON({"ok":False},status_code=404)
    sid=int(raw_sid)
    stamp=request.headers.get("x-hesab-status-at","")
    signature=request.headers.get("x-hesab-status-signature","")
    if not _cssb_verify(sid,stamp,signature):
        return _cssb_JSON({"ok":False},status_code=403,
              headers={"Cache-Control":"no-store"})
    server=_cssb_server_for_sid(sid)
    if not _cssb_rate(int(_cssb_time.time()),server):
        return _cssb_JSON({"ok":False},status_code=429,
              headers={"Cache-Control":"no-store"})
    report=_cssb_cached_report(server) if server else None
    # Never send other Maya data, mappings, names, IPs or SSH status.
    if report is None:
        report={"server":None,"server_label":"نامشخص",
                "summary":"unknown","paths":{},
                "last_checked_at":None,"method":"central_cached_only"}
    return _cssb_JSON({"ok":True,"report":report},
           headers={"Cache-Control":"private,no-store",
                    "X-Content-Type-Options":"nosniff"})

if any(getattr(r,"path",None)=="/internal/customer-server-status/v1"
       for r in app.router.routes):
    raise RuntimeError("CUSTOMER_STATUS_INTERNAL_ROUTE_COLLISION")
app.add_api_route("/internal/customer-server-status/v1",
                  _cssb_endpoint,methods=["GET"],include_in_schema=False)
