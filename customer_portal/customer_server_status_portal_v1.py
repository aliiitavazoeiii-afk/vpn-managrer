# HESAB_CUSTOMER_SERVER_STATUS_PORTAL_V1
# Customer-only read of existing shared central status. NO active probes,
# network scanning, SSH or private XUI access. All access fails CLOSED until
# a separately VERIFIED ownership mechanism is wired into the auth hook.
import hashlib as _cssp_hashlib
import hmac as _cssp_hmac
import json as _cssp_json
import re as _cssp_re
import stat as _cssp_stat
import threading as _cssp_threading
import time as _cssp_time
import urllib.error as _cssp_urlerr
import urllib.request as _cssp_urlreq
from pathlib import Path as _cssp_Path
from fastapi import Request as _cssp_Request
from fastapi.responses import JSONResponse as _cssp_JSON

_CSSP_SECRET=_cssp_Path("/run/hesab-customer-status-v1.key")
_CSSP_URL="http://app:8000/internal/customer-server-status/v1"
_CSSP_RATE_LOCK=_cssp_threading.Lock()
_CSSP_RATE={}
_CSSP_CACHE={}
_CSSP_FLIGHTS={}
_CSSP_CACHE_SECONDS=30
_CSSP_MAX_CACHE=2048

def _cssp_verified_phone(request):
    """Integration contract: callable must verify SIM/OTP, NOT just signed
    30-day cookie or a phone the visitor supplied. Missing hook => deny.
    This is intentionally NOT wired to existing insecure phone-only login.
    """
    phone=_v2_session_phone(request)
    if not phone:return None
    hook=globals().get("customer_status_verified_phone_v1")
    if not callable(hook):return None
    try:
        verified=hook(request)
        return phone if isinstance(verified,str) and (
            normalize_phone(verified)==phone) else None
    except (ValueError,TypeError,KeyError,AttributeError):
        return None

def _cssp_response(payload,code=200):
    return _cssp_JSON(payload,status_code=code,headers={
        "Cache-Control":"private,no-store,max-age=0","Pragma":"no-cache",
        "X-Content-Type-Options":"nosniff","X-Robots-Tag":"noindex, nofollow"})

def _cssp_accounts(phone):
    with db_conn() as conn:
        accounts=active_subscriptions(conn,phone)
    return [{"id":int(a["id"]),"label":str(a["display_name"] or "اشتراک")[:90]}
            for a in accounts if type(a.get("id")) is int and int(a["id"])>0]

def _cssp_allow(phone,sid,now):
    """Token bucket equivalents per authenticated phone, subscription and global.
    Cheap admission; status never triggers a live test even on cache misses.
    """
    with _CSSP_RATE_LOCK:
        if len(_CSSP_RATE)>2048:
            _CSSP_RATE.update({k:v for k,v in list(_CSSP_RATE.items()) if now-v[0]<60})
            for k,v in list(_CSSP_RATE.items()):
                if now-v[0]>=60:_CSSP_RATE.pop(k,None)
        keys=(("phone",phone,6),("sub",sid,12),("global",0,120))
        updated=[]
        for kind,value,limit in keys:
            key=(kind,value)
            start,count=_CSSP_RATE.get(key,(now,0))
            if now-start>=60:start,count=now,0
            if count>=limit:return False
            updated.append((key,start,count+1))
        for key,start,count in updated:
            _CSSP_RATE[key]=(start,count)
        return True

def _cssp_secret():
    try:
        if _CSSP_SECRET.is_symlink() or not _CSSP_SECRET.is_file():
            return None
        if _CSSP_SECRET.stat().st_mode&(_cssp_stat.S_IRWXG|_cssp_stat.S_IRWXO):
            return None
        key=_CSSP_SECRET.read_bytes().strip()
        return key if 32<=len(key)<=128 else None
    except OSError:return None

def _cssp_fetch(sid,now=None):
    secret=_cssp_secret()
    if secret is None:raise ValueError("Private bridge unavailable")
    now=int(_cssp_time.time() if now is None else now)
    stamp=str(now)
    sig=_cssp_hmac.new(secret,f"v1:{stamp}:{sid}".encode(),
                      _cssp_hashlib.sha256).hexdigest()
    req=_cssp_urlreq.Request(
         _CSSP_URL+"?sid="+str(sid),
         headers={"X-Hesab-Status-At":stamp,
                  "X-Hesab-Status-Signature":sig,
                  "Accept":"application/json",
                  "User-Agent":"Hesab-Customer-Status-ReadOnly/1"})
    # Hardcoded Docker service address; no redirections, URLs or IPs from user.
    class NoRedirect(_cssp_urlreq.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            return None
    opener=_cssp_urlreq.build_opener(NoRedirect())
    with opener.open(req,timeout=3) as result:
        if result.status!=200 or result.headers.get("content-type","").split(";")[0]!="application/json":
            raise ValueError("Unexpected private status response")
        body=result.read(5500)
        if len(body)>5000:raise ValueError("Oversized private response")
    data=_cssp_json.loads(body.decode("utf8"))
    if type(data) is not dict or data.get("ok") is not True:
        raise ValueError("Unverified central report")
    report=data.get("report")
    if type(report) is not dict:raise ValueError("Missing central report")
    if report.get("server") not in (None,"maya1","maya-s3","maya4"):
        raise ValueError("Unknown central server")
    if report.get("summary") not in (
        "healthy","slow","disrupted","connection_only","unknown"):
        raise ValueError("Unknown report state")
    roles=report.get("paths")
    if type(roles) is not dict or any(k not in ("backhaul","mieru","haproxy") for k in roles):
        raise ValueError("Invalid role set")
    for role,item in roles.items():
        if type(item) is not dict or item.get("state") not in (
                "healthy","slow","timeout","incomplete","disrupted",
                "connection_only","unknown"):
            raise ValueError("Invalid role status")
    # Explicit output allowlist; never forward hidden internal future fields.
    clean={}
    for role in ("backhaul","mieru","haproxy"):
        value=roles.get(role,{})
        clean[role]={
            "state":value.get("state","unknown"),
            "connection":value.get("connection") if value.get("connection") in ("connected","down","unknown") else "unknown",
            "transfer":value.get("transfer") if value.get("transfer") in (
                "healthy","slow","timeout","incomplete","disrupted","unknown") else "unknown",
            "connection_at":value.get("connection_at") if type(value.get("connection_at")) is int else None,
            "transfer_at":value.get("transfer_at") if type(value.get("transfer_at")) is int else None}
    return {"server":report.get("server"),
            "server_label":report.get("server_label") if
                 report.get("server_label") in ("مایا ۱","مایا ۳","مایا ۴") else "نامشخص",
            "summary":report["summary"],"paths":clean,
            "last_checked_at":report.get("last_checked_at") if
                  type(report.get("last_checked_at")) is int else None,
            "method":"central_cached_only"}

def _cssp_cached(sid,now):
    with _CSSP_RATE_LOCK:
        row=_CSSP_CACHE.get(sid)
        if row and now-row[0]>=0 and now-row[0]<_CSSP_CACHE_SECONDS:
            return row[1]
        in_progress=_CSSP_FLIGHTS.get(sid)
        if in_progress is None:
            ev=_cssp_threading.Event()
            _CSSP_FLIGHTS[sid]=ev
            owner=True
        else:
            ev=in_progress
            owner=False
    if not owner:
        if not ev.wait(timeout=4):
            raise ValueError("Shared request is taking too long")
        with _CSSP_RATE_LOCK:
            row=_CSSP_CACHE.get(sid)
            if row and now-row[0]>=0 and now-row[0]<_CSSP_CACHE_SECONDS:
                return row[1]
        raise ValueError("Shared central report unavailable")
    try:
        result=_cssp_fetch(sid,now=now)
        with _CSSP_RATE_LOCK:
            if len(_CSSP_CACHE)>_CSSP_MAX_CACHE:
                _CSSP_CACHE.clear()
            _CSSP_CACHE[sid]=(now,result)
        return result
    finally:
        with _CSSP_RATE_LOCK:
            if _CSSP_FLIGHTS.get(sid) is ev:
                del _CSSP_FLIGHTS[sid]
            ev.set()

def _cssp_accounts_endpoint(request:_cssp_Request):
    phone=_cssp_verified_phone(request)
    if not phone:return _cssp_response({"ok":False,
        "message":"برای بررسی وضعیت، ابتدا باید شماره شما تأیید شود."},403)
    try:
        accounts=_cssp_accounts(phone)
        return _cssp_response({"ok":True,"accounts":accounts,
                        "csrf":csrf_for(phone)})
    except (OSError,ValueError,TypeError,KeyError):
        return _cssp_response({"ok":False,"message":"دریافت اشتراک‌ها ممکن نیست."},503)

async def _cssp_check_endpoint(request:_cssp_Request):
    phone=_cssp_verified_phone(request)
    if not phone:return _cssp_response({"ok":False,
       "message":"برای بررسی وضعیت، ابتدا باید شماره شما تأیید شود."},403)
    if request.headers.get("origin")!="https://usermanager.ir" or (
        request.headers.get("sec-fetch-site") not in (None,"same-origin")):
        return _cssp_response({"ok":False,"message":"درخواست معتبر نیست."},403)
    if not verify_csrf(phone,request.headers.get("x-customer-status-csrf","")):
        return _cssp_response({"ok":False,"message":"درخواست معتبر نیست."},403)
    if request.headers.get("content-type","").split(";")[0].strip().lower()!="application/json":
        return _cssp_response({"ok":False},415)
    length=request.headers.get("content-length","0")
    if not length.isascii() or not length.isdecimal():
        return _cssp_response({"ok":False},400)
    if int(length)>256:
        return _cssp_response({"ok":False},413)
    try:
        payload=await request.body()
        if len(payload)>256:return _cssp_response({"ok":False},413)
        data=_cssp_json.loads(payload)
    except (ValueError,TypeError,UnicodeError):
        return _cssp_response({"ok":False},400)
    if type(data) is not dict or set(data)!={"subscription_id"} or (
        type(data["subscription_id"]) is not int or not 1<=data["subscription_id"]<=2147483647):
        return _cssp_response({"ok":False,"message":"اشتراک نامعتبر است."},400)
    sid=data["subscription_id"]
    try:
        owned={v["id"] for v in _cssp_accounts(phone)}
        if sid not in owned:
            return _cssp_response({"ok":False,"message":"اشتراک انتخاب‌شده مجاز نیست."},403)
        now=int(_cssp_time.time())
        if not _cssp_allow(phone,sid,now):
            return _cssp_response({"ok":False,
                      "message":"تعداد درخواست‌ها زیاد است؛ کمی بعد بررسی کن."},429)
        report=_cssp_cached(sid,now)
        return _cssp_response({"ok":True,"report":report,
            "message":"نتیجه از آخرین پایش مرکزی خوانده شد؛ تست دانلود جدید اجرا نشد."})
    except (_cssp_urlerr.URLError,OSError,ValueError,TypeError,
            _cssp_json.JSONDecodeError):
        return _cssp_response({"ok":False,
                    "message":"گزارش معتبر در دسترس نیست. کمی بعد دوباره بررسی کن."},503)

for _cssp_route in ("/api/my-server-status/accounts",
                    "/api/my-server-status/check"):
    if any(getattr(r,"path",None)==_cssp_route for r in app.router.routes):
        raise RuntimeError("CUSTOMER_STATUS_PORTAL_ROUTE_COLLISION")
app.add_api_route("/api/my-server-status/accounts",_cssp_accounts_endpoint,
                  methods=["GET"],include_in_schema=False)
app.add_api_route("/api/my-server-status/check",_cssp_check_endpoint,
                  methods=["POST"],include_in_schema=False)

_CSSP_CARD=r'''
<div class="sv-cstatus" id="sv-cstatus" aria-label="تست وضعیت سرور من">
  <div class="sv-cstatus-title">وضعیت سرور من</div>
  <p>آخرین اطلاعات پایش اختصاصی اشتراک شما؛ بدون دانلود آزمایشی جدید.</p>
  <label class="sv-cstatus-label" for="sv-cstatus-account" id="sv-cstatus-label" hidden>انتخاب اشتراک</label>
  <select id="sv-cstatus-account" hidden></select>
  <button type="button" id="sv-cstatus-check">تست وضعیت سرور من</button>
  <div class="sv-cstatus-message" id="sv-cstatus-message" role="status" aria-live="polite"></div>
  <div class="sv-cstatus-results" id="sv-cstatus-results" hidden></div>
</div>
'''
_CSSP_STYLE=r'''
<style id="cssp-style">
.sv-cstatus{margin:14px 0 12px;padding:15px;border:1px solid #e1e5ee;
 border-radius:17px;background:#f9faff;color:#252b39;min-width:0}
.sv-cstatus-title{font-size:16px;font-weight:900;color:#182039;line-height:1.6}
.sv-cstatus p{margin:5px 0 12px;color:#78839b;font-size:11px;line-height:1.9}
.sv-cstatus-label{display:block;font-size:12px;font-weight:700;margin:8px 0}
.sv-cstatus select{width:100%;min-height:44px;font:inherit;font-size:14px;
 background:#fff;border:1px solid #d6ddeb;border-radius:11px;
 color:#1c263a;padding:8px}
.sv-cstatus button{min-height:46px;width:100%;border:0;border-radius:12px;
 background:#252d54;color:#fff;font:inherit;font-size:13px;font-weight:850;
 cursor:pointer;margin-top:8px}
.sv-cstatus button:disabled{opacity:.55;cursor:wait}
.sv-cstatus-message{font-size:12px;line-height:1.9;margin-top:10px;color:#59637b}
.sv-cstatus-results{margin-top:13px;padding:11px;background:white;
 border:1px solid #e3e8f1;border-radius:13px;min-width:0}
.sv-cstatus-results>div{font-size:12px;line-height:1.9}
.sv-cstatus-row{display:flex;align-items:center;justify-content:space-between;
 flex-wrap:wrap;gap:9px;border-top:1px solid #eef0f5;padding:9px 0}
.sv-cstatus-row b{color:#344263}
.sv-cstatus-pill{border-radius:9px;background:#f0f2f7;padding:4px 10px;
 color:#434e68;font-weight:800}
.sv-cstatus-pill.ok{background:#e4f6ec;color:#16683f}
.sv-cstatus-pill.warn{background:#fff0e0;color:#965b19}
.sv-cstatus-pill.bad{background:#fff0f1;color:#ac3e48}
.sv-cstatus-meta{font-size:11px!important;color:#748095!important;
 overflow-wrap:anywhere}
.sv-cstatus-results[hidden],.sv-cstatus label[hidden],
.sv-cstatus select[hidden]{display:none!important}
@media(max-width:640px){
 .sv-cstatus{padding:12px;border-radius:14px}
 .sv-cstatus-title{font-size:15px}
 .sv-cstatus-row{font-size:12px}
}
</style>
'''
_CSSP_JS=r'''
<script id="cssp-js">
(function(){
"use strict";
const el=document.getElementById("sv-cstatus");
if(!el)return;
const button=document.getElementById("sv-cstatus-check");
const select=document.getElementById("sv-cstatus-account");
const label=document.getElementById("sv-cstatus-label");
const message=document.getElementById("sv-cstatus-message");
const results=document.getElementById("sv-cstatus-results");
let csrf="",loaded=false,busy=false;
const states={
 healthy:["سالم","ok"],
 slow:["کند","warn"],
 disrupted:["دارای اختلال","bad"],
 timeout:["زمان پاسخ تمام شد","bad"],
 incomplete:["دریافت ناقص","bad"],
 connection_only:["اتصال برقرار؛ کیفیت اندازه‌گیری نشده","warn"],
 unknown:["نامشخص",""]
};
function mk(parent,tag,value,cls){
 const n=document.createElement(tag);
 if(cls)n.className=cls;
 if(value!=null)n.textContent=String(value);
 parent.append(n);
 return n;
}
function date(stamp){
 if(!Number.isInteger(stamp)||stamp<1)return "نامشخص";
 try{
  return new Intl.DateTimeFormat("fa-IR",{dateStyle:"short",timeStyle:"short",
    timeZone:"Asia/Tehran"}).format(new Date(stamp*1000));
 }catch(_){return "نامشخص"}
}
function render(report){
 results.replaceChildren();results.hidden=false;
 mk(results,"div","سرور: "+(report.server_label||"نامشخص"));
 for(const [key,title] of [["backhaul","Backhaul"],
                           ["mieru","Mieru"],["haproxy","HAProxy"]]){
  const entry=(report.paths||{})[key]||{};
  const val=states[entry.state]||states.unknown;
  const row=mk(results,"div",null,"sv-cstatus-row");
  mk(row,"b",title);
  mk(row,"span",val[0],"sv-cstatus-pill "+val[1]);
  let evidence="نوع بررسی: اطلاعات معتبر موجود نیست";
  if(entry.transfer&&entry.transfer!=="unknown"&&entry.transfer_at){
     evidence="آزمایش واقعی انتقال: "+date(entry.transfer_at);
  }else if(entry.connection&&entry.connection!=="unknown"&&entry.connection_at){
     evidence="بررسی اتصال: "+date(entry.connection_at)+" · سرعت اندازه‌گیری نشده";
  }
  mk(results,"div",title+" · "+evidence,"sv-cstatus-meta");
 }
 const final=states[report.summary]||states.unknown;
 mk(results,"div","وضعیت کلی: "+final[0],"sv-cstatus-meta");
 mk(results,"div","آخرین بررسی: "+date(report.last_checked_at),"sv-cstatus-meta");
 const hasTransfer=Object.values(report.paths||{}).some(
    p=>p.transfer&&p.transfer!=="unknown"&&p.transfer_at);
 mk(results,"div",hasTransfer?"نوع شواهد: آخرین تست واقعی مرکزی + پایش اتصال":
   "نوع شواهد: پایش اتصال؛ کیفیت انتقال اندازه‌گیری نشده",
   "sv-cstatus-meta");
 mk(results,"div","این نتیجه از گزارش مشترک خوانده شده؛ تست جدیدی اجرا نشده است.",
    "sv-cstatus-meta");
}
async function getJSON(path,options){
 const r=await fetch(path,{credentials:"same-origin",cache:"no-store",...options});
 const data=await r.json();
 if(!r.ok||data.ok!==true)throw Error(data.message||"گزارش در دسترس نیست.");
 return data;
}
button.addEventListener("click",async()=>{
 if(busy)return;busy=true;button.disabled=true;
 message.textContent="در حال خواندن آخرین گزارش مرکزی...";
 try{
  if(!loaded){
   const data=await getJSON("/api/my-server-status/accounts");
   csrf=data.csrf;
   select.replaceChildren();
   for(const account of data.accounts){
    const option=document.createElement("option");
    option.value=String(account.id);
    option.textContent=account.label+" · #"+account.id;
    select.appendChild(option);
   }
   loaded=true;
   if(data.accounts.length===0)throw Error("اشتراک فعالی برای بررسی وجود ندارد.");
   if(data.accounts.length>1){
      select.hidden=false;label.hidden=false;
      button.textContent="بررسی اشتراک انتخاب‌شده";
      message.textContent="اشتراک خود را انتخاب کن، سپس دوباره دکمه را بزن.";
      return;
   }
  }
  const sid=Number(select.value);
  if(!Number.isSafeInteger(sid)||sid<1)throw Error("اشتراک معتبری انتخاب نشده.");
  const data=await getJSON("/api/my-server-status/check",{
    method:"POST",headers:{"Content-Type":"application/json",
       "X-Customer-Status-CSRF":csrf},
    body:JSON.stringify({subscription_id:sid})
  });
  render(data.report);
  message.textContent="گزارش مرکزی دریافت شد.";
 }catch(error){
  results.hidden=true;
  message.textContent=error.message||"بررسی وضعیت ممکن نیست.";
 }finally{busy=false;button.disabled=false}
});
})();
</script>
'''
if "_SV2_HTML" not in globals() or type(_SV2_HTML) is not str:
    raise RuntimeError("CUSTOMER_STATUS_SERVICES_TEMPLATE_MISSING")
if (_SV2_HTML.count('<div class="sv-server-footer">')!=1 or
    _SV2_HTML.count("</body>")!=1 or
    'id="sv-cstatus"' in _SV2_HTML):
    raise RuntimeError("CUSTOMER_STATUS_CARD_ANCHOR_MISMATCH")
_SV2_HTML=_SV2_HTML.replace('<div class="sv-server-footer">',
       _CSSP_CARD+'<div class="sv-server-footer">',1)
_SV2_HTML=_SV2_HTML.replace("</body>",_CSSP_STYLE+_CSSP_JS+"</body>",1)
