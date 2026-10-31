# HESAB_CONTROL_ROOM_TRAFFIC_TOPUP_V9
# One-click 100/200/500GB operator purchases, audited and idempotent in
# isolated PostgreSQL table. Independent of XUI, financial subscription ledgers.
# V7 provisional RX estimate + sum of topups, with honestly provisional alerts.
import json as _t9_json
import secrets as _t9_secrets
from pathlib import Path as _t9_Path
import re as _t9_re
from fastapi import Request as _t9_Request,Depends as _t9_Depends,HTTPException as _t9_Error,Form as _t9_Form
from fastapi.responses import JSONResponse as _t9_JSON
from sqlalchemy.orm import Session as _t9_Session
from sqlalchemy import text as _t9_text
from sqlalchemy.exc import IntegrityError as _t9_Integrity
from jinja2 import Environment as _t9_Environment

_T9_NAMES=("maya1","maya-s3","maya4")
_T9_AMOUNTS=(100,200,500)
_T9_TABLE="hesab_maya_traffic_topups_v9"
_T9_DDL="""
CREATE TABLE IF NOT EXISTS hesab_maya_traffic_topups_v9 (
 id BIGSERIAL PRIMARY KEY,
 server_id VARCHAR(16) NOT NULL CHECK(server_id IN ('maya1','maya-s3','maya4')),
 gb INTEGER NOT NULL CHECK(gb IN (100,200,500)),
 request_key VARCHAR(64) NOT NULL UNIQUE,
 meter_epoch VARCHAR(100) NOT NULL,
 origin VARCHAR(32) NOT NULL CHECK(origin IN ('operator_ui','initial_operator_purchase')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

_T9_BASELINE=_t9_Path("/srv/maya-live/phase1/provisional_meter_baseline_v7.json")
def _t9_epochs():
    try:
        raw=_t9_json.loads(_T9_BASELINE.read_text(encoding="utf8"))
        if (raw.get("format")!="HESAB_MAYA_PROVISIONAL_BASELINE_V7" or
            raw.get("direction_assumption")!="rx" or
            raw.get("alert_eligible") is not False):
            raise ValueError("Unexpected meter baseline")
        result={}
        for name in _T9_NAMES:
            b=raw["servers"][name]
            epoch=f'{raw["created_at"]}|{b["rx_baseline_gb"]}'
            if not _t9_re.fullmatch(r"[0-9.]{2,100}\|[0-9.]{1,40}",epoch):
                raise ValueError("Invalid meter epoch")
            result[name]=epoch
        return result
    except (OSError,ValueError,TypeError,KeyError):
        return {}

def _t9_get_data(db):
    rows=db.execute(_t9_text(
       "SELECT id,server_id,gb,origin,created_at FROM "+_T9_TABLE+
       " ORDER BY id DESC LIMIT 100")).all()
    epochs=_t9_epochs()
    sums={k:0 for k in _T9_NAMES}
    recent=[]
    # Last 100 for UI; total MUST be query over all rows, never last 100.
    for row in rows:
        recent.append({"id":int(row.id),"server":row.server_id,
                       "gb":int(row.gb),"origin":row.origin,
                       "at":row.created_at.isoformat()})
    # Only credit purchases recorded AFTER the CURRENT V7 RX baseline.
    # A future V8 rebaseline already includes earlier purchases in the new
    # provider reference; old ledger rows must not be credited twice.
    for row in db.execute(_t9_text(
        "SELECT server_id,meter_epoch,COALESCE(SUM(gb),0) AS total FROM "+
        _T9_TABLE+" GROUP BY server_id,meter_epoch")).all():
        if row.server_id in sums and epochs.get(row.server_id)==row.meter_epoch:
            sums[row.server_id]=int(row.total)
    return sums,recent

def _t9_status(request:_t9_Request,db:_t9_Session=_t9_Depends(get_db)):
    try:
        sums,recent=_t9_get_data(db)
    except Exception:
        db.rollback()
        raise _t9_Error(status_code=503,detail="Traffic purchase journal unavailable")
    try:
        provisional=_t9_json.loads(_e7_read(None).body)["servers"]
    except Exception:
        provisional={}
    calculated={}
    for name in _T9_NAMES:
        s=provisional.get(name,{})
        result={"state":s.get("state","unavailable"),"topup_gb":sums[name],
                "alert_threshold_gb":10}
        if (s.get("state")=="provisional" and
            type(s.get("estimate_remaining_gb")) in (float,int) and
            type(s.get("after_baseline_rx_gb")) in (float,int)):
            total=max(0,round(float(s["estimate_remaining_gb"])+sums[name],3))
            result.update({
                "state":"provisional","estimated_remaining_gb":total,
                "low_estimate":total<=10,
                "alert_is_estimate_only":True,
                "actual_provider_remaining_verified":False,
                "rx_after_baseline_gb":s["after_baseline_rx_gb"]
            })
        calculated[name]=result
    return _t9_JSON({"ok":True,"servers":calculated,"history":recent,
                     "alert_scope":"web_app_when_open_and_permission_granted",
                     "alerts_are_provisional":True},
                    headers={"Cache-Control":"private,no-store"})

def _t9_add(request:_t9_Request,
            server:str=_t9_Form(""),
            amount:int=_t9_Form(0),
            request_key:str=_t9_Form(""),
            csrf:str=_t9_Form(""),
            db:_t9_Session=_t9_Depends(get_db)):
    if (request.headers.get("origin")!="https://hesab.filmjadiid.ir" or
        request.headers.get("sec-fetch-site") not in (None,"same-origin")):
        raise _t9_Error(status_code=403,detail="Origin denied")
    expected=request.session.get("maya1_control_csrf")
    if (not isinstance(expected,str) or len(expected)<30 or
        not _t9_secrets.compare_digest(expected,csrf)):
        raise _t9_Error(status_code=403,detail="CSRF token invalid")
    if (server not in _T9_NAMES or amount not in _T9_AMOUNTS or
        not _t9_re.fullmatch(r"[A-Za-z0-9_-]{20,64}",request_key)):
        raise _t9_Error(status_code=422,detail="Invalid server, amount or request identifier")
    epochs=_t9_epochs()
    if server not in epochs:
        raise _t9_Error(status_code=409,detail="Meter baseline not configured; cannot apply credit safely")
    try:
        inserted=db.execute(_t9_text("""
INSERT INTO hesab_maya_traffic_topups_v9(server_id,gb,request_key,meter_epoch,origin)
VALUES(:server,:gb,:key,:epoch,'operator_ui')
ON CONFLICT(request_key) DO NOTHING RETURNING id
"""),{"server":server,"gb":amount,"key":request_key,"epoch":epochs[server]}).first()
        if inserted is None:
            existing=db.execute(_t9_text("""
SELECT server_id,gb FROM hesab_maya_traffic_topups_v9 WHERE request_key=:key
"""),{"key":request_key}).first()
            if not existing or existing.server_id!=server or existing.gb!=amount:
                db.rollback()
                raise _t9_Error(status_code=409,detail="Identifier already used with other purchase")
        db.commit()
    except _t9_Error:
        raise
    except Exception:
        db.rollback()
        raise _t9_Error(status_code=503,detail="Purchase could not be recorded; check history before retry")
    return _t9_JSON({"ok":True,"server":server,"added_gb":amount,
                     "already_recorded":inserted is None},
                    headers={"Cache-Control":"private,no-store"})

app.add_api_route("/control-room/v9/traffic",_t9_status,methods=["GET"])
app.add_api_route("/control-room/v9/topup",_t9_add,methods=["POST"])

_T9_TEMPLATE=TEMPLATES.get("control_room.html","")
_T9_RENDER='''hasEstimated?"≈ "+e7Gb(forecast.estimate_remaining_gb):'''
_T9_FETCH='''refresh();c4FetchMetrics();setInterval(refresh,20000);'''
_T9_START='''const c4Host={};'''
_T9_CARDS='''<div id="c2-cards" class="c2-cards"></div>'''
for needle in (_T9_RENDER,_T9_FETCH,_T9_START,_T9_CARDS,
               'id="e7-provisional-style"','id="c3-mode"'):
    if _T9_TEMPLATE.count(needle)!=1:
        raise RuntimeError("Expected Control Room V7 (V9 overlay mismatch): "+needle)
if "t9-topup-panel" in _T9_TEMPLATE:raise RuntimeError("Traffic topup already installed")

_T9_AREA=r'''
<section id="t9-topup-panel" aria-label="مدیریت خرید ترافیک">
 <div class="t9-heading"><div><strong>افزایش حجم سرورها</strong>
 <p>خرید انجام‌شده در دیتاسنتر را اینجا ثبت کن؛ ثبت در این قسمت خودش بسته‌ای از دیتاسنتر نمی‌خرد.</p></div>
 <button id="t9-notify-enable" type="button">فعال‌کردن اعلان مرورگر</button></div>
 <div class="t9-layout">
  <label>سرور<select id="t9-server">
   <option value="maya1">مایا ۱</option>
   <option value="maya-s3">مایا ۳</option>
   <option value="maya4">مایا ۴</option></select></label>
  <div class="t9-choice" role="group" aria-label="بسته خرید">
   <label><input type="radio" name="t9-amount" value="100">۱۰۰ گیگ</label>
   <label><input type="radio" name="t9-amount" value="200">۲۰۰ گیگ</label>
   <label><input type="radio" name="t9-amount" value="500" checked>۵۰۰ گیگ</label>
  </div>
  <button id="t9-topup-submit" type="button">ثبت خرید ترافیک</button>
 </div>
 <p class="t9-existing-seed">شارژ ۵۰۰ گیگ امروزِ مایا ۱ هنگام نصب فقط یک‌بار ثبت می‌شود؛ آن خرید را دوباره ثبت نکن.</p>
 <div id="t9-feedback" role="status" aria-live="polite"></div>
 <div id="t9-alerts" aria-live="polite"></div>
 <details><summary>سابقه خریدهای ثبت‌شده</summary><div id="t9-history"></div></details>
</section>
'''
_T9_CSS=r'''
<style id="t9-topup-style">
#t9-topup-panel{border:1px solid rgba(148,168,218,.22);border-radius:18px;
padding:18px;margin:12px 0 18px;background:linear-gradient(135deg,#1c294d,#111935);
color:#edf2ff;direction:rtl}
#t9-topup-panel *{box-sizing:border-box}
#t9-topup-panel .t9-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
#t9-topup-panel strong{font-size:16px;font-weight:850}
#t9-topup-panel p{font-size:11px;color:#b2bfdc;line-height:1.7;margin:6px 0 0}
#t9-topup-panel .t9-layout{display:flex;gap:11px;align-items:center;flex-wrap:wrap;margin:17px 0 10px}
#t9-topup-panel select{min-width:105px;background:#141d38;color:#fff;border:1px solid #626e98;border-radius:9px;padding:11px}
#t9-topup-panel .t9-choice{display:flex;gap:6px;flex-wrap:wrap}
#t9-topup-panel .t9-choice label{border:1px solid #5a668b;padding:10px 13px;border-radius:9px;cursor:pointer;font-size:12px}
#t9-topup-panel .t9-choice label:has(input:checked){border-color:#5ad4ad;background:#285b503b;color:#cbfff1}
#t9-topup-panel .t9-choice input{accent-color:#5ad4ad}
#t9-topup-panel button{border-radius:9px;padding:10px 14px;background:#347b66;border:1px solid #4da688;color:#fff;cursor:pointer;font:inherit;font-size:12px;font-weight:800}
#t9-topup-panel button:disabled{opacity:.55;cursor:wait}
#t9-topup-panel #t9-notify-enable{background:#273b62;border-color:#526c98}
#t9-topup-panel #t9-feedback{font-size:12px;line-height:1.8;min-height:1em;margin:10px 0;color:#a7f6d1}
#t9-topup-panel #t9-alerts:empty{display:none}
#t9-topup-panel .t9-alert{border:1px solid #c59150;background:#70502833;color:#f8d6a4;
border-radius:10px;padding:12px;margin:9px 0;font-size:12px;line-height:1.8}
#t9-topup-panel details{font-size:11px;color:#adbce0;border-top:1px solid #ffffff24;padding-top:10px;margin-top:10px}
#t9-topup-panel summary{cursor:pointer}
#t9-topup-panel .t9-history-item{padding:7px 0;border-bottom:1px solid #ffffff18}
@media(max-width:650px){
#t9-topup-panel{padding:13px}
#t9-topup-panel .t9-layout{align-items:stretch;flex-direction:column}
#t9-topup-panel .t9-choice label{flex:1;text-align:center}}
</style>
'''
_T9_JS=r'''
const t9State={};
const t9Label={"maya1":"مایا ۱","maya-s3":"مایا ۳","maya4":"مایا ۴"};
const t9Server=document.getElementById("t9-server");
const t9Submit=document.getElementById("t9-topup-submit");
const t9Feedback=document.getElementById("t9-feedback");
const t9Alerts=document.getElementById("t9-alerts");
const t9History=document.getElementById("t9-history");
const t9Notify=document.getElementById("t9-notify-enable");
const t9CSRF="{{ ctrl_csrf }}";
let t9Pending=null;
function t9Num(value){return Number(value).toLocaleString("fa-IR",{minimumFractionDigits:2,maximumFractionDigits:3});}
async function t9Refresh(){
 try{
  const response=await fetch("/control-room/v9/traffic",{credentials:"same-origin",cache:"no-store"});
  if(!response.ok)throw Error("HTTP "+response.status);
  const data=await response.json();
  if(!data.ok)throw Error("Invalid server response");
  for(const name of ["maya1","maya-s3","maya4"])
    t9State[name]=data.servers[name]||{state:"unavailable",topup_gb:0};
  t9History.replaceChildren();
  for(const item of data.history.slice(0,15)){
    const row=document.createElement("div");row.className="t9-history-item";
    row.textContent=t9Label[item.server]+" · +"+t9Num(item.gb)+" GB · "+new Date(item.at).toLocaleString("fa-IR");
    t9History.appendChild(row);
  }
  t9Alerts.replaceChildren();
  for(const name of ["maya1","maya-s3","maya4"]){
    const item=t9State[name]||{};
    if(item.state==="provisional"&&item.low_estimate===true){
       const alert=document.createElement("div");alert.className="t9-alert";
       alert.textContent="هشدار تخمینی: مانده "+t9Label[name]+" حدود "+t9Num(item.estimated_remaining_gb)+
         " گیگ شده؛ جهت RX هنوز با دیتاسنتر تأیید نشده است. فوراً موجودی پنل دیتاسنتر را بررسی کن.";
       t9Alerts.appendChild(alert);
       const key="t9-low-sent-"+name;
       let shown=false;try{shown=localStorage.getItem(key)==="1"}catch(e){}
       if(!shown&&"Notification" in window&&Notification.permission==="granted"){
         try{new Notification("هشدار تخمینی ترافیک "+t9Label[name],{body:alert.textContent,
               tag:"hesab-traffic-"+name});
           localStorage.setItem(key,"1");}catch(e){}
       }
    }else if(item.state==="provisional"&&item.low_estimate===false){
       try{localStorage.removeItem("t9-low-sent-"+name)}catch(e){}
    }
  }
  renderCards();
 }catch(err){t9Feedback.textContent="خواندن دفتر خرید ترافیک ناموفق است؛ اتصال سرور را بررسی کن.";}
}
t9Submit.addEventListener("click",async()=>{
 const server=t9Server.value;
 const amount=Number(document.querySelector('input[name="t9-amount"]:checked')?.value);
 if(!["maya1","maya-s3","maya4"].includes(server)||![100,200,500].includes(amount))return;
 if(!window.confirm("آیا واقعاً بسته "+amount+" گیگابایتی برای "+t9Label[server]+
    " را در دیتاسنتر خریداری کرده‌ای؟ ثبت مجدد همان خرید حجم را دوبار زیاد می‌کند."))return;
 if(!t9Pending||t9Pending.server!==server||t9Pending.amount!==amount)
   t9Pending={server,amount,key:crypto.randomUUID().replace(/-/g,"")};
 const payload=new URLSearchParams({server,amount:String(amount),
          request_key:t9Pending.key,csrf:t9CSRF});
 t9Submit.disabled=true;t9Feedback.textContent="در حال ثبت...";
 try{
  const response=await fetch("/control-room/v9/topup",{
    method:"POST",credentials:"same-origin",
    headers:{"Content-Type":"application/x-www-form-urlencoded"},
    body:payload.toString()});
  const result=await response.json();
  if(!response.ok||!result.ok)throw Error(result.detail||"ثبت ناموفق بود");
  t9Feedback.textContent="بسته "+t9Num(amount)+" گیگ "+t9Label[server]+
     (result.already_recorded?" قبلاً ثبت شده بود؛ تکرار نشد.":" ثبت شد.");
  t9Pending=null;
  await t9Refresh();
 }catch(err){t9Feedback.textContent="خطا: "+String(err.message).slice(0,160)+
  " — قبل از ثبت دوباره، سابقه را بررسی کن.";}
 finally{t9Submit.disabled=false;}
});
t9Notify.addEventListener("click",async()=>{
 if(!("Notification" in window)){t9Feedback.textContent="مرورگر اعلان سیستم را پشتیبانی نمی‌کند.";return;}
 const result=await Notification.requestPermission();
 t9Feedback.textContent=result==="granted"?
 "اعلان مرورگر فعال شد؛ فقط زمانی که پنل باز و در حال پایش باشد قابل ارسال است.":
 "دسترسی اعلان تأیید نشده است.";
});
t9Refresh();
setInterval(t9Refresh,60000);
'''
# One-click purchases affect displayed V7 provisional remaining, not underlying
# meter ledger (which must remain independent).
_T9_RENDER_NEW='''hasEstimated?"≈ "+e7Gb(forecast.estimate_remaining_gb+Number(t9State[id]?.topup_gb||0)):'''
_T9_TEMPLATE=_T9_TEMPLATE.replace("{% block content %}","{% block content %}"+_T9_CSS,1)
_T9_TEMPLATE=_T9_TEMPLATE.replace(_T9_CARDS,_T9_AREA+_T9_CARDS,1)
_T9_TEMPLATE=_T9_TEMPLATE.replace(_T9_START,_T9_JS+"\n"+_T9_START,1)
_T9_TEMPLATE=_T9_TEMPLATE.replace(_T9_RENDER,_T9_RENDER_NEW,1)
if "{#" in _T9_TEMPLATE:raise RuntimeError("Unsafe Jinja comment token")
_t9_Environment().parse(_T9_TEMPLATE)
TEMPLATES["control_room.html"]=_T9_TEMPLATE
if hasattr(env.loader,"mapping"):env.loader.mapping.update(TEMPLATES)
