# HESAB_CONTROL_ROOM_LIVE_VISUAL_V4
# Visual reuse of the original dashboard control-room cards.
# STRICT SCOPE: /control-room template + read-only host metrics API.
# Existing 3 XUI live snapshots, exact-client toggles, manual links and V3 filters untouched.
import json as _c4_json
import time as _c4_time
from pathlib import Path as _c4_Path
from fastapi import Request as _c4_Request
from fastapi.responses import JSONResponse as _c4_JSON
from jinja2 import Environment as _c4_Environment

_C4_REPORT = _c4_Path("/srv/maya-live/phase1/xui_status_v1.json")
_C4_SERVERS = ("maya1","maya-s3","maya4")

def _c4_status(request:_c4_Request):
    outcome={k:{"state":"not_configured"} for k in _C4_SERVERS}
    try:
        if _C4_REPORT.is_file() and _C4_REPORT.stat().st_size<30000:
            document=_c4_json.loads(_C4_REPORT.read_text(encoding="utf-8"))
            if document.get("format")!="HESAB_MAYA_XUI_METRICS_V1":
                raise ValueError("invalid format")
            age=_c4_time.time()-float(document.get("collected_at",0))
            if age<0 or age>300:
                outcome={k:{"state":"stale"} for k in _C4_SERVERS}
            else:
                for key in _C4_SERVERS:
                    item=(document.get("servers") or {}).get(key)
                    if not isinstance(item,dict):continue
                    state=item.get("state","unavailable")
                    if state not in ("ok","unavailable","not_configured"):state="unavailable"
                    output={"state":state}
                    if state=="ok":
                        sampled=item.get("sampled_at")
                        if type(sampled) not in (int,float) or not 0<=_c4_time.time()-sampled<=300:
                            output={"state":"stale"}
                        else:
                            for metric in ("cpu_pct","ram_pct"):
                                val=item.get(metric)
                                if type(val) in (int,float) and 0<=val<=100:
                                    output[metric]=round(float(val),1)
                            proc=item.get("xray_process")
                            if proc in ("running","stopped","unknown"):
                                output["xray_process"]=proc
                    outcome[key]=output
    except (ValueError,TypeError,OSError,OverflowError,KeyError):
        outcome={k:{"state":"invalid"} for k in _C4_SERVERS}
    return _c4_JSON({"ok":True,"servers":outcome},
        headers={"Cache-Control":"private,no-store"})

app.add_api_route("/control-room/v4/host-metrics",_c4_status,methods=["GET"])

_C4_TEMPLATE=TEMPLATES.get("control_room.html","")
_C4_HEAD='<header class="c2-head"><h1>اتاق کنترل</h1><span id="c2-time" class="c2-time"></span></header>'
_C4_CARDS='<div id="c2-cards" class="c2-cards"></div>'
_C4_START='function renderCards(){'
_C4_END='\nfunction renderRank('
if not all(x in _C4_TEMPLATE for x in (
    _C4_HEAD,_C4_CARDS,_C4_START,_C4_END,
    'id="p1-monitor"','id="c3-mode"',
    'id="c2-users"','mdl2-toolbar',
    'const state={active:null,latest:{},query:"",queries:{},modes:{},loading:false,mutating:false};')):
    raise RuntimeError("Live visual V4 requires Phase1 + V3 control-room source")
if "id=\"c4-shell\"" in _C4_TEMPLATE:
    raise RuntimeError("V4 live visual already present")

_C4_CSS = r'''
<style id="c4-style">
/* Reuse the main dashboard's deep navy palette and three-part card structure. */
#c2-root{max-width:1680px!important}
#c2-root #p1-ops-root,#c2-root #p1-monitor{display:none!important}
#c2-root .c4-heading{display:flex;justify-content:space-between;align-items:center;
 gap:15px;margin:4px 0 30px;flex-wrap:wrap}
#c2-root .c4-heading-main{display:flex;align-items:center;gap:15px}
#c2-root .c4-logo{display:grid;place-items:center;width:52px;height:52px;
 border-radius:15px;color:#c3b5ff;background:linear-gradient(145deg,#28215d,#151b43);
 border:1px solid #54459b;font-size:25px;flex:none}
#c2-root .c4-heading h1{font-size:clamp(21px,2vw,28px)!important;
 font-weight:850!important;color:#fafaff!important;margin:0!important}
#c2-root .c4-heading p{font-size:12px!important;color:#858fb4!important;
 margin:5px 0 0!important;line-height:1.8}
#c2-root .c4-return{padding:12px 15px;min-height:43px;display:inline-flex;
 align-items:center;justify-content:center;gap:7px;color:#cfbdff;text-decoration:none!important;
 border-radius:12px;border:1px solid #3f376f;background:rgba(104,80,219,.11);font-size:12px;font-weight:800}
#c2-root #c4-shell{padding:18px 22px 20px;border-radius:22px;border:1px solid #322a6f;
 background:linear-gradient(150deg,rgba(20,20,58,.72),rgba(11,13,39,.85));
 box-shadow:0 20px 50px rgba(0,0,0,.2)}
#c2-root .c4-section-head{display:flex;align-items:center;justify-content:space-between;
 gap:10px;padding:8px 2px 17px;margin-bottom:13px;border-bottom:1px solid #ffffff12}
#c2-root .c4-section-label{display:flex;align-items:center;gap:10px}
#c2-root .c4-section-icon{font-size:25px}
#c2-root .c4-section-head h2{font-size:18px!important;font-weight:850!important;
 margin:0!important;color:#f4f4ff!important}
#c2-root .c4-section-head p{font-size:11px!important;margin:4px 0 0!important;color:#838cb0!important}
#c2-root .c4-total{padding:8px 13px;border-radius:999px;background:#251c52;
 border:1px solid #4c398d;color:#c5afff;font-size:11px;white-space:nowrap}
#c2-root #c2-cards.c2-cards{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;
 gap:14px!important;margin:0!important}
#c2-root #c2-cards .c4-server-card{display:block!important;min-width:0;width:100%;
 min-height:305px!important;padding:20px!important;text-align:right!important;
 border-radius:20px!important;box-shadow:0 14px 36px rgba(0,0,0,.16)!important;
 border:1px solid rgba(144,131,243,.18)!important;
 background:linear-gradient(145deg,rgba(23,25,65,.88),rgba(13,16,45,.96))!important;
 color:#eff1ff!important;position:relative;overflow:hidden;cursor:pointer;
 transition:transform .18s,border-color .18s!important}
#c2-root #c2-cards .c4-server-card:hover{transform:translateY(-3px)!important;
 border-color:rgba(168,140,255,.5)!important}
#c2-root #c2-cards .c4-server-card[aria-expanded="true"]{
 border-color:#8d77ed!important;box-shadow:0 0 0 1px #654ebc55,0 20px 40px #0005!important}
#c2-root .c4-card-top{display:flex;justify-content:space-between;align-items:start;gap:8px}
#c2-root .c4-card-name{display:flex;align-items:center;gap:9px}
#c2-root .c4-mini-logo{font-size:20px;flex:none;opacity:.8}
#c2-root .c4-card-name b{font-size:17px!important;line-height:1.2;color:#fff!important}
#c2-root .c4-card-name small{display:block;font-size:11px!important;color:#8f96bb!important;margin-top:8px}
#c2-root .c4-reach{font-size:10px;color:#adb3d0;display:flex;align-items:center;gap:6px}
#c2-root .c4-dot{width:8px;height:8px;border-radius:100%;display:inline-block;background:#676b87}
#c2-root .c4-reach.is-ok .c4-dot{background:#60e7ae;box-shadow:0 0 11px #60e7ae80}
#c2-root .c4-reach.is-error .c4-dot{background:#ff8c9d}
#c2-root .c4-center{display:grid;grid-template-columns:125px minmax(0,1fr);
 gap:14px;align-items:center;margin:23px 0 16px}
#c2-root .c4-ring{width:120px;height:120px;border-radius:50%;padding:8px;
 background:conic-gradient(#9279fc calc(var(--c4-p)*1%),rgba(255,255,255,.075) 0);
 box-shadow:0 0 25px #7454fc19}
#c2-root .c4-ring-core{width:100%;height:100%;border-radius:50%;background:#121631;
 border:1px solid #ffffff13;display:flex;flex-direction:column;align-items:center;justify-content:center}
#c2-root .c4-ring strong{font-size:24px!important;font-weight:850;color:#fff}
#c2-root .c4-ring small{font-size:10px!important;color:#9197b7!important;margin-top:7px}
#c2-root .c4-values{display:grid;gap:11px;min-width:0}
#c2-root .c4-values>div{padding:12px;border-radius:11px;background:#ffffff08;border:1px solid #ffffff0a}
#c2-root .c4-values small{font-size:10px;color:#929bb9;display:block}
#c2-root .c4-values strong{font-size:17px!important;color:#f4f5ff!important;
 display:block;margin-top:7px!important;overflow-wrap:anywhere}
#c2-root .c4-bottom{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}
#c2-root .c4-bottom>div{min-width:0;padding:11px 8px;background:#ffffff07;
 border:1px solid #ffffff0b;border-radius:9px}
#c2-root .c4-bottom small{display:block;color:#858eaf;font-size:10px!important}
#c2-root .c4-bottom b{display:block;color:#e4e6fb;font-size:13px!important;margin-top:7px!important}
#c2-root .c4-card-foot{display:block;font-size:10px;color:#9fa9c6;line-height:1.6;
 min-height:25px;margin-top:13px}
#c2-root .c4-open-hint{font-size:11px;color:#8a93b5;margin:16px 3px 0}
#c2-root .c4-open-hint strong{color:#e2d9ff}
#c2-root .c2-panel{margin-top:18px!important}
@media(max-width:1100px){ #c2-root #c2-cards.c2-cards{grid-template-columns:repeat(2,minmax(0,1fr))!important}}
@media(max-width:720px){
 #c2-root #c4-shell{padding:13px 10px}
 #c2-root #c2-cards.c2-cards{grid-template-columns:1fr!important;gap:10px!important}
 #c2-root #c2-cards .c4-server-card{min-height:275px!important;padding:15px!important}
 #c2-root .c4-heading{margin-bottom:18px}
 #c2-root .c4-heading p{font-size:10px!important}
 #c2-root .c4-center{grid-template-columns:108px minmax(0,1fr);gap:10px}
 #c2-root .c4-ring{height:105px;width:105px}
 #c2-root .c4-ring strong{font-size:20px!important}
 #c2-root .c4-section-head h2{font-size:16px!important}
}
</style>
'''
_C4_HEADER=r'''
<header class="c4-heading">
  <div class="c4-heading-main">
    <span class="c4-logo" aria-hidden="true">⌘</span>
    <div><h1>اتاق کنترل</h1>
      <p>نمای زنده سه سرور مایا؛ مدیریت کاربران و پایش منابع 3x-ui</p></div>
  </div>
  <div>
    <span id="c2-time" class="c2-time" style="margin-inline-end:12px"></span>
    <a class="c4-return" href="/">← بازگشت به داشبورد</a>
  </div>
</header>
'''
_C4_SECTION=r'''
<section id="c4-shell" aria-label="سرورهای متصل مایا">
 <div class="c4-section-head">
   <div class="c4-section-label"><span class="c4-section-icon" aria-hidden="true">🖥️</span>
     <div><h2>سرورهای تحت مدیریت</h2>
      <p>مایا ۱، مایا ۳ و مایا ۴ · وضعیت پنل X-UI، نه تست قطعی اینترنت</p></div></div>
   <span class="c4-total">۳ سرور</span>
 </div>
 <div id="c2-cards" class="c2-cards"></div>
 <p class="c4-open-hint">برای مشاهده <strong>جدول کاربران، جست‌وجو، فیلترها و جزئیات</strong> روی کارت هر سرور بزن.</p>
</section>
'''

_C4_JS = r'''
const c4Host={};
const c4Quota={};
const c4HostLabel={
 maya1:"مایا ۱", "maya-s3":"مایا ۳", maya4:"مایا ۴"
};
const c4Str=(v,suffix="")=>v===null||v===undefined?"—":
  Number(v).toLocaleString("fa-IR",{maximumFractionDigits:1})+suffix;
const c4Pct=(v)=>Number.isFinite(v)?Math.min(100,Math.max(0,v)):null;
async function c4FetchMetrics(){
  const result=await Promise.allSettled([
    fetch("/control-room/v4/host-metrics",{credentials:"same-origin",cache:"no-store"}),
    fetch("/control-room/phase1/status",{credentials:"same-origin",cache:"no-store"})
  ]);
  try{
    if(result[0].status==="fulfilled"&&result[0].value.ok){
      const d=await result[0].value.json();
      if(d.ok)for(const key of ["maya1","maya-s3","maya4"])c4Host[key]=d.servers?.[key]||{};
    }
  }catch(e){}
  try{
    if(result[1].status==="fulfilled"&&result[1].value.ok){
      const d=await result[1].value.json();
      if(d.ok)for(const key of ["maya1","maya-s3","maya4"])c4Quota[key]=d.servers?.[key]||{};
    }
  }catch(e){}
  renderCards();
}
function c4CardLabel(label,value,container){
 const panel=create("div",undefined,container);
 create("small",label,panel);create("strong",value,panel);
}
'''
_C4_CARDS_JS = r'''function renderCards(){
 cardBox.replaceChildren();
 for(const id of ["maya1","maya-s3","maya4"]){
   const report=state.latest[id]||{};
   const online=report.ok===true;
   const host=c4Host[id]||{},quota=c4Quota[id]||{};
   const quotaUsable=quota.state==="ok"&&
      ["verified","estimated"].includes(quota.traffic_state)&&
      Number.isFinite(Number(quota.traffic_quota_gb))&&
      Number(quota.traffic_quota_gb)>0&&
      Number.isFinite(Number(quota.traffic_used_gb))&&
      Number.isFinite(Number(quota.remaining_gb));
   const percent=quotaUsable?
     c4Pct(100*Number(quota.traffic_used_gb)/Number(quota.traffic_quota_gb)):null;
   const selected=state.active===id;
   const btn=create("button",undefined,cardBox,"c2-card c4-server-card");
   btn.type="button";btn.setAttribute("aria-expanded",selected?"true":"false");
   btn.setAttribute("aria-label",c4HostLabel[id]+"؛ نمایش کاربران و کنترل‌ها");
   const top=create("div",undefined,btn,"c4-card-top");
   const identity=create("div",undefined,top,"c4-card-name");
   create("span","⌘",identity,"c4-mini-logo");
   const titles=create("div",undefined,identity);
   create("b",c4HostLabel[id],titles);
   create("small","3x-ui · "+(online?"پاسخگو":"وضعیت نامشخص"),titles);
   const reach=create("div",undefined,top,"c4-reach "+(online?"is-ok":report.ok===false?"is-error":""));
   create("span","",reach,"c4-dot");
   create("span",online?"پنل متصل":report.ok===false?"عدم دسترسی":"در حال بررسی",reach);
   const center=create("div",undefined,btn,"c4-center");
   const ring=create("div",undefined,center,"c4-ring");
   ring.style.setProperty("--c4-p",String(percent??0));
   const ringCore=create("div",undefined,ring,"c4-ring-core");
   create("strong",percent===null?"—":c4Str(percent,"٪"),ringCore);
   create("small","سهمیه ترافیک",ringCore);
   const values=create("div",undefined,center,"c4-values");
   const remaining=quotaUsable?
     (quota.traffic_state==="estimated"?"حدودی ":"")+c4Str(quota.remaining_gb," GB"):"—";
   c4CardLabel("ترافیک باقی‌مانده",remaining,values);
   c4CardLabel("حساب‌های فعال در X-UI",online?count(report.enabled):"—",values);
   const metrics=create("div",undefined,btn,"c4-bottom");
   const cpu=host.state==="ok"?c4Str(host.cpu_pct,"٪"):"—";
   const ram=host.state==="ok"?c4Str(host.ram_pct,"٪"):"—";
   for(const [label,val] of [
      ["CPU",cpu],["RAM",ram],["کل اکانت‌ها",online?count(report.total):"—"]
   ]){
      const item=create("div",undefined,metrics);
      create("small",label,item);create("b",val,item);
   }
   create("div",online?
      "تطبیق‌شده "+count(report.linked)+" · نیازمند بررسی "+count(report.unmatched):
      "اطلاعات زنده X-UI در دسترس نیست",btn,"c4-card-foot");
   btn.onclick=()=>{
     state.active=state.active===id?null:id;
     state.query=state.queries[id]||"";
     search.value=state.query;
     c3Mode.value=state.modes[id]||"normal";
     notice.textContent="";
     renderCards();renderDetails();
     if(state.active)detail.scrollIntoView({behavior:"smooth",block:"start"});
   };
 }
}
'''
_C4_TEMPLATE=_C4_TEMPLATE.replace("{% block content %}","{% block content %}"+_C4_CSS,1)
assert _C4_TEMPLATE.count(_C4_HEAD)==1
assert _C4_TEMPLATE.count(_C4_CARDS)==1
_C4_TEMPLATE=_C4_TEMPLATE.replace(_C4_HEAD,_C4_HEADER,1)
_C4_TEMPLATE=_C4_TEMPLATE.replace(_C4_CARDS,_C4_SECTION,1)

# Add V4 helpers before the closure's original renderCards and replace only its
# markup. V3's search, filter, details, exact controls and error logic are retained.
_first,_tail=_C4_TEMPLATE.split(_C4_START,1)
if _C4_END not in _tail:raise RuntimeError("V2 card renderer boundaries missing")
_old_cards,_rest=_tail.split(_C4_END,1)
if "btn.onclick=()=>" not in _old_cards or "renderDetails()" not in _old_cards:
    raise RuntimeError("V2 card selector changed unexpectedly")
_C4_TEMPLATE=_first+_C4_JS+"\n"+_C4_CARDS_JS+_C4_END+_rest

_C4_START_REFRESH="refresh();setInterval(refresh,20000);"
_C4_NEW_REFRESH=("refresh();c4FetchMetrics();setInterval(refresh,20000);"
                 "setInterval(()=>{if(!document.hidden)c4FetchMetrics();},60000);")
assert _C4_TEMPLATE.count(_C4_START_REFRESH)==1
_C4_TEMPLATE=_C4_TEMPLATE.replace(_C4_START_REFRESH,_C4_NEW_REFRESH,1)

if "{#" in _C4_TEMPLATE:
    raise RuntimeError("Unsafe Jinja comment token in V4 template")
_c4_Environment().parse(_C4_TEMPLATE)
TEMPLATES["control_room.html"]=_C4_TEMPLATE
if hasattr(env.loader,"mapping"):env.loader.mapping.update(TEMPLATES)
