# HESAB_CONTROL_ROOM_COMPACT_V10
# UI-only redesign: preserve XUI user table, V9 topup ledger + CSRF endpoints,
# existing V7 provisional balance and browser alerts. No financial writes here.
import re as _t10_re
import json as _t10_json
import time as _t10_time
from datetime import datetime as _t10_datetime
from zoneinfo import ZoneInfo as _t10_ZoneInfo
from pathlib import Path as _t10_Path
from fastapi import Request as _t10_Request
from fastapi.responses import JSONResponse as _t10_JSON
from jinja2 import Environment as _t10_Environment

_T10_PATH=_t10_Path("/srv/maya-live/phase1/daily_nic_v10.json")
_T10_NAMES=("maya1","maya-s3","maya4")
def _t10_daily(request:_t10_Request):
    entries={name:{"state":"unavailable"} for name in _T10_NAMES}
    try:
        if _T10_PATH.is_file() and 0<_T10_PATH.stat().st_size<=20000:
            doc=_t10_json.loads(_T10_PATH.read_text(encoding="utf8"))
            collected=doc.get("collected_at")
            today=_t10_datetime.now(_t10_ZoneInfo("Asia/Tehran")).date().isoformat()
            if doc.get("format")!="HESAB_MAYA_DAILY_NIC_V10":
                raise ValueError("format")
            if (type(collected) not in (int,float) or
                not 0<=_t10_time.time()-collected<=190 or doc.get("day")!=today):
                entries={name:{"state":"stale"} for name in _T10_NAMES}
            else:
                for name in _T10_NAMES:
                    r=doc.get("servers",{}).get(name,{})
                    if r.get("state")=="ok" and type(r.get("rx_today_gb")) in (float,int):
                        value=float(r["rx_today_gb"])
                        if 0<=value<=1e9:
                            entries[name]={"state":"ok","rx_today_gb":round(value,3),
                                           "partial_day":r.get("partial_day") is True}
    except (OSError,ValueError,KeyError,TypeError,OverflowError):
        entries={name:{"state":"invalid"} for name in _T10_NAMES}
    return _t10_JSON({"ok":True,"servers":entries},
                     headers={"Cache-Control":"private,no-store"})
app.add_api_route("/control-room/v10/daily",_t10_daily,methods=["GET"])

_T10_TEMPLATE=TEMPLATES.get("control_room.html","")
for item in ("id=\"t9-topup-panel\"","id=\"c2-cards\"","function renderCards(){",
             "\nfunction renderRank(","const t9State={};",
             "setInterval(t9Refresh,60000);","id=\"c4-shell\"","id=\"p1-monitor\"",
             "id=\"c3-mode\"","id=\"t9-notify-enable\""):
    if _T10_TEMPLATE.count(item)!=1:
        raise RuntimeError("V10 expected original active V9 layout: "+item)
if "t10-compact-css" in _T10_TEMPLATE:
    raise RuntimeError("V10 compact UI already installed")

_T10_CSS=r'''
<style id="t10-compact-css">
#c2-root #p1-monitor,#c2-root #p1-ops-root{display:none!important}
#c2-root #t9-topup-panel{display:none!important}
#c2-root #c2-cards.c2-cards{align-items:stretch!important}
#c2-root .t10-wrapper{min-width:0;display:flex;flex-direction:column;gap:8px}
#c2-root #c2-cards .t10-wrapper .c4-server-card{
 height:auto!important;min-height:300px!important;flex:1;
 margin:0!important}
#c2-root #c2-cards .t10-ring{width:120px;height:120px;padding:7px;
 border-radius:50%;background:linear-gradient(145deg,#745ff7,#4e419c);
 box-shadow:0 0 20px #7257e83a;display:flex}
#c2-root #c2-cards .t10-ring .c4-ring-core{width:100%;height:100%;
 background:#151934;display:flex;align-items:center;justify-content:center;
 border-radius:50%;flex-direction:column;text-align:center;gap:1px}
#c2-root #c2-cards .t10-ring .c4-ring-core strong{font-size:23px!important;
 direction:ltr;unicode-bidi:isolate;line-height:1.4;white-space:nowrap}
#c2-root #c2-cards .t10-ring .c4-ring-core small{font-size:10px!important;margin:0}
#c2-root #c2-cards .t10-wrapper .c4-values{grid-template-columns:1fr;gap:9px}
#c2-root #c2-cards .t10-wrapper .c4-values>div{padding:11px 13px}
#c2-root .t10-purchase{display:flex;gap:6px;align-items:center;flex-wrap:wrap;
 background:#151a3d;border:1px solid #5c568f55;border-radius:12px;
 padding:9px 10px;direction:rtl}
#c2-root .t10-purchase-label{font-size:10px;color:#c0c7e4;margin-left:auto;
 white-space:nowrap}
#c2-root .t10-purchase button{font:inherit;font-size:11px;font-weight:800;
 min-width:54px;padding:7px 8px;background:#242d55;
 border:1px solid #52649a;border-radius:8px;color:#e2e9ff;cursor:pointer;
 transition:background .15s,transform .15s}
#c2-root .t10-purchase button:hover{background:#344879}
#c2-root .t10-purchase button:disabled{opacity:.45;cursor:wait}
#c2-root .t10-purchase .t10-status{flex-basis:100%;color:#97dfbb;
 font-size:11px;text-align:right}
#c2-root .t10-head-tools{display:flex;align-items:center;gap:8px}
#c2-root #t10-notify{background:#292753;color:#e8e3ff;border:1px solid #615a9b;
 border-radius:9px;padding:7px 11px;font:inherit;font-size:11px;cursor:pointer}
#c2-root .t10-low{font-size:10px;color:#ffd1a2;margin-top:4px}
#c2-root .t10-ring.t10-low-ring{background:linear-gradient(145deg,#ffad57,#b26b34)}
#c2-root .t10-ring .c4-ring-core small{max-width:95px;line-height:1.4}
#c2-root .c4-server-card .m2-info,#c2-root .c4-server-card .m2-warning,
#c2-root .c4-server-card .n5-meter-note,#c2-root .c4-server-card .e7-provisional-note,
#c2-root .c4-server-card .b6-provider-reference-note{display:none!important}
@media(max-width:720px){
 #c2-root #c2-cards .t10-wrapper .c4-server-card{min-height:275px!important}
 #c2-root #c2-cards .t10-ring{width:105px;height:105px}
 #c2-root #c2-cards .t10-ring .c4-ring-core strong{font-size:20px!important}
 #c2-root .t10-purchase button{min-width:52px}
}
</style>
'''
_T10_JS=r'''
const t9State={};
const t10DailyState={};
const t10Names={"maya1":"مایا ۱","maya-s3":"مایا ۳","maya4":"مایا ۴"};
const t10Feedback={};
const t10Pending={};
const t10CSRF="{{ ctrl_csrf }}";
const t10Format=v=>Number(v).toLocaleString("fa-IR",
  {minimumFractionDigits:0,maximumFractionDigits:2});
const t10FormatGB=v=>t10Format(v)+" GB";
const t10NotifyKey=id=>"t10-low-notified-"+id;
async function t9Refresh(){
 try{
  const response=await fetch("/control-room/v9/traffic",
    {credentials:"same-origin",cache:"no-store"});
  if(!response.ok)throw Error("API");
  const data=await response.json();
  if(data.ok!==true||!data.servers)throw Error("payload");
  for(const id of ["maya1","maya-s3","maya4"]){
    t9State[id]=data.servers[id]||{state:"unavailable",topup_gb:0};
    const entry=t9State[id];
    if(entry.state==="provisional"&&entry.low_estimate===true){
      if("Notification" in window&&Notification.permission==="granted"){
        const key=t10NotifyKey(id);
        let sent=false;try{sent=localStorage.getItem(key)==="1"}catch(e){}
        if(!sent){
          try{
           new Notification("هشدار کمبود ترافیک "+t10Names[id],
              {body:"مانده تخمینی کمتر از ۱۰ گیگ است. موجودی دیتاسنتر را بررسی کن.",
               tag:"hesab-maya-low-"+id});
           localStorage.setItem(key,"1");
          }catch(e){}
        }
      }
    }else if(entry.state==="provisional"&&entry.low_estimate===false){
      try{localStorage.removeItem(t10NotifyKey(id));}catch(e){}
    }
  }
  renderCards();
 }catch(e){/* Retain the last successful reading; no invented quota. */}
}
async function t10FetchDaily(){
 try{
  const response=await fetch("/control-room/v10/daily",
    {credentials:"same-origin",cache:"no-store"});
  if(!response.ok)throw Error("API");
  const data=await response.json();
  if(data.ok!==true||!data.servers)throw Error("payload");
  for(const id of ["maya1","maya-s3","maya4"])
     t10DailyState[id]=data.servers[id]||{state:"unavailable"};
  renderCards();
 }catch(e){
  for(const id of ["maya1","maya-s3","maya4"])t10DailyState[id]={state:"unavailable"};
  renderCards();
 }
}
async function t10Topup(id,amount){
 if(!["maya1","maya-s3","maya4"].includes(id)||![100,200,500].includes(amount))return;
 if(t10Pending[id]?.busy)return;
 if(!confirm("بسته "+amount+" گیگ را برای "+t10Names[id]+
    " در دیتاسنتر خریده‌ای؟ با تأیید، به موجودی تخمینی اضافه می‌شود."))return;
 let pending=t10Pending[id];
 if(!pending||pending.amount!==amount)
    pending={amount,key:crypto.randomUUID().replace(/-/g,"")};
 t10Pending[id]={...pending,busy:true};
 t10Feedback[id]="در حال ثبت...";
 renderCards();
 try{
   const body=new URLSearchParams({server:id,amount:String(amount),
     request_key:pending.key,csrf:t10CSRF});
   const response=await fetch("/control-room/v9/topup",{
      method:"POST",credentials:"same-origin",
      headers:{"Content-Type":"application/x-www-form-urlencoded"},
      body:body.toString()});
   const result=await response.json();
   if(!response.ok||!result.ok)throw Error(result.detail||"ثبت ناموفق");
   t10Feedback[id]=result.already_recorded?
      "این خرید قبلاً ثبت شده است.":"+"+amount+" گیگ ثبت شد.";
   delete t10Pending[id];
   await t9Refresh();
 }catch(e){
   t10Pending[id]={...pending,busy:false};
   t10Feedback[id]="ثبت نامطمئن؛ قبل از تلاش دوباره سوابق خرید را بررسی کن.";
 }finally{
   if(t10Pending[id])t10Pending[id].busy=false;
   renderCards();
 }
}
async function t10Permission(){
 if(!("Notification" in window)){alert("این مرورگر اعلان سیستم ندارد.");return;}
 const value=await Notification.requestPermission();
 const button=document.getElementById("t10-notify");
 if(button)button.textContent=value==="granted"?"اعلان فعال است":"فعال‌سازی اعلان";
}
const t10Bell=document.getElementById("t10-notify");
if(t10Bell)t10Bell.addEventListener("click",t10Permission);
t9Refresh();t10FetchDaily();
setInterval(t9Refresh,60000);
setInterval(t10FetchDaily,60000);
'''
_T10_CARDS=r'''function renderCards(){
 cardBox.replaceChildren();
 for(const id of ["maya1","maya-s3","maya4"]){
   const report=state.latest[id]||{};
   const online=report.ok===true;
   const host=c4Host[id]||{},quota=c4Quota[id]||{},net=n5Traffic[id]||{};
   const estimate=t9State[id]||{};
   const day=t10DailyState[id]||{};
   const quotaUsable=quota.state==="ok"&&
      ["verified","estimated"].includes(quota.traffic_state)&&
      Number.isFinite(Number(quota.remaining_gb));
   const estimateOK=estimate.state==="provisional"&&
      typeof estimate.estimated_remaining_gb==="number"&&
      Number.isFinite(estimate.estimated_remaining_gb);
   const remaining=quotaUsable?Number(quota.remaining_gb):
      estimateOK?Number(estimate.estimated_remaining_gb):null;
   const low=remaining!==null&&remaining<=10;
   const selected=state.active===id;
   const wrap=create("div",undefined,cardBox,"t10-wrapper");
   const btn=create("button",undefined,wrap,"c2-card c4-server-card");
   btn.type="button";
   btn.setAttribute("aria-expanded",selected?"true":"false");
   btn.setAttribute("aria-label",c4HostLabel[id]+"؛ نمایش کاربران و کنترل‌ها");
   const top=create("div",undefined,btn,"c4-card-top");
   const identity=create("div",undefined,top,"c4-card-name");
   create("span","⌘",identity,"c4-mini-logo");
   const titles=create("div",undefined,identity);
   create("b",c4HostLabel[id],titles);
   create("small",online?"پنل متصل":"وضعیت اتصال نامشخص",titles);
   const reach=create("div",undefined,top,"c4-reach "+(online?"is-ok":report.ok===false?"is-error":""));
   create("span","",reach,"c4-dot");
   create("span",online?"اتصال برقرار":report.ok===false?"عدم دسترسی":"در حال بررسی",reach);
   const center=create("div",undefined,btn,"c4-center");
   const ring=create("div",undefined,center,"c4-ring t10-ring"+(low?" t10-low-ring":""));
   const ringCore=create("div",undefined,ring,"c4-ring-core");
   const strong=create("strong",remaining===null?"—":t10Format(remaining),ringCore);
   strong.title=estimateOK&&!quotaUsable?"مانده تخمینی از RX؛ هنوز تأییدشده دیتاسنتر نیست":"مانده ترافیک";
   create("small","گیگ مانده",ringCore);
   const values=create("div",undefined,center,"c4-values");
   const today=day.state==="ok"?t10FormatGB(day.rx_today_gb):"—";
   c4CardLabel("ترافیک روز",today,values);
   if(day.partial_day===true){
     values.lastElementChild.title="مصرف RX فقط از شروع ثبت در امروز است؛ کل روز نیست.";
   }else{
     values.lastElementChild.title="مصرف RX کارت شبکه در روز تهران";
   }
   c4CardLabel("اکانت‌های فعال",online?count(report.enabled):"—",values);
   const metrics=create("div",undefined,btn,"c4-bottom");
   const cpu=host.state==="ok"?c4Str(host.cpu_pct,"٪"):"—";
   const ram=host.state==="ok"?c4Str(host.ram_pct,"٪"):"—";
   for(const [label,val] of [["CPU",cpu],["RAM",ram],
            ["کل اکانت‌ها",online?count(report.total):"—"]]){
      const one=create("div",undefined,metrics);
      create("small",label,one);create("b",val,one);
   }
   if(low)create("div","کمتر از ۱۰ گیگ · تخمینی",btn,"t10-low");
   btn.onclick=()=>{
      state.active=state.active===id?null:id;
      state.query=state.queries[id]||"";
      search.value=state.query;
      c3Mode.value=state.modes[id]||"normal";
      notice.textContent="";
      renderCards();renderDetails();
      if(state.active)detail.scrollIntoView({behavior:"smooth",block:"start"});
   };
   const purchase=create("div",undefined,wrap,"t10-purchase");
   create("span","خرید ترافیک",purchase,"t10-purchase-label");
   for(const amount of [100,200,500]){
      const opt=create("button",amount+" GB",purchase);
      opt.type="button";
      opt.disabled=Boolean(t10Pending[id]?.busy);
      opt.onclick=(e)=>{e.stopPropagation();t10Topup(id,amount);};
   }
   if(t10Feedback[id])create("div",t10Feedback[id],purchase,"t10-status");
 }
}
'''
# Replacement of the V9 JS block avoids null dereferences caused by removing
# its large form/panel. Retains the backend and notification functionality.
_T10_SCRIPT_START="const t9State={};"
_T10_SCRIPT_END="setInterval(t9Refresh,60000);"
start=_T10_TEMPLATE.index(_T10_SCRIPT_START)
end=_T10_TEMPLATE.index(_T10_SCRIPT_END,start)+len(_T10_SCRIPT_END)
_T10_TEMPLATE=_T10_TEMPLATE[:start]+_T10_JS+_T10_TEMPLATE[end:]
# Discard *markup only*: journal/API remains intact and is not cleared.
_T10_TEMPLATE,n=_t10_re.subn(
   r'<section id="t9-topup-panel"[\s\S]*?</section>\s*','',
   _T10_TEMPLATE,count=1)
if n!=1:raise RuntimeError("Could not remove large topup form")
a=_T10_TEMPLATE.index("function renderCards(){")
b=_T10_TEMPLATE.index("\nfunction renderRank(",a)
_T10_TEMPLATE=_T10_TEMPLATE[:a]+_T10_CARDS+_T10_TEMPLATE[b:]
_T10_TEMPLATE=_T10_TEMPLATE.replace("{% block content %}",
                                     "{% block content %}"+_T10_CSS,1)
# Put the small notification opt-in in the current section head; no extra panel.
_T10_HEADING='<span class="c4-total">۳ سرور</span>'
_T10_HEADING_NEW='<span class="t10-head-tools"><button type="button" id="t10-notify">فعال‌سازی اعلان</button><span class="c4-total">۳ سرور</span></span>'
if _T10_TEMPLATE.count(_T10_HEADING)!=1:
    raise RuntimeError("Server section heading changed")
_T10_TEMPLATE=_T10_TEMPLATE.replace(_T10_HEADING,_T10_HEADING_NEW,1)
_T10_TEMPLATE=_T10_TEMPLATE.replace('t9-topup-style','t9-topup-style-retained-but-unmounted',1)
if "{#" in _T10_TEMPLATE:raise RuntimeError("Jinja unsafe token")
_t10_Environment().parse(_T10_TEMPLATE)
TEMPLATES["control_room.html"]=_T10_TEMPLATE
if hasattr(env.loader,"mapping"):env.loader.mapping.update(TEMPLATES)
