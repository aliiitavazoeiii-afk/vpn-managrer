# HESAB_CONTROL_ROOM_PHASE1_V1 — READ-ONLY UI & trusted local telemetry.
# Appended AFTER all existing Control Room overlays in the mounted maya1_control.py.
# Existing /control-room GET, /control-room/v2/data and guarded user toggle stay untouched.
import json as _p1_json
import time as _p1_time
from pathlib import Path as _p1_Path
from fastapi import Request as _p1_Request
from fastapi.responses import JSONResponse as _p1_JSON

_P1_TELEMETRY = _p1_Path("/srv/maya-live/phase1/status.json")
_P1_SERVERS = ("maya1","maya-s3","maya4")

def _p1_status(request:_p1_Request):
    result={name:{"role":"unknown","state":"not_configured"} for name in _P1_SERVERS}
    if _P1_TELEMETRY.is_file() and _P1_TELEMETRY.stat().st_size <= 64000:
        try:
            doc=_p1_json.loads(_P1_TELEMETRY.read_text(encoding="utf-8"))
            if doc.get("format")!="HESAB_PHASE1_V1":raise ValueError("unknown format")
            for name in _P1_SERVERS:
                candidate=(doc.get("servers") or {}).get(name)
                if not isinstance(candidate,dict):continue
                safe={}
                for k in ("role","state","traffic_state","probe_state","traffic_source"):
                    val=candidate.get(k)
                    if isinstance(val,str):
                        safe[k]=val[:60]
                for k in ("cpu_pct","ram_pct","remaining_gb","traffic_used_gb","traffic_quota_gb","sample_age_s"):
                    v=candidate.get(k)
                    if isinstance(v,(int,float)) and not isinstance(v,bool) and 0<=v<1e15:
                        safe[k]=round(float(v),2)
                if candidate.get("role")=="iran":
                    safe["role"]="iran"
                else:
                    for k in ("cpu_pct","ram_pct","remaining_gb","traffic_used_gb","traffic_quota_gb"):
                        safe.pop(k,None)
                result[name]=safe
            collected=doc.get("collected_at")
            if not isinstance(collected,(int,float)) or not 0<=_p1_time.time()-collected<360:
                for name in _P1_SERVERS:result[name]["state"]="stale"
        except (ValueError,TypeError,OSError,KeyError):
            for name in _P1_SERVERS:result[name]["state"]="invalid"
    return _p1_JSON({"ok":True,"servers":result},headers={"Cache-Control":"private,no-store"})

app.add_api_route("/control-room/phase1/status",_p1_status,methods=["GET"])

_p1_template=TEMPLATES.get("control_room.html","")
if not all(x in _p1_template for x in (
        '<div id="c2-cards" class="c2-cards"></div>',
        '<div class="c2-table-wrap" id="c2-scroll">',
        '<tbody id="c2-users"></tbody>',
        "{% endblock %}")):
    raise RuntimeError("Phase1 expected Control Room V2 template not present")
if "p1-ops-root" in _p1_template:
    raise RuntimeError("Phase1 already loaded; refuse duplicate UI")
_P1_CSS = r'''
<style id="p1-ops-styles">
#p1-ops-root{direction:rtl;margin:0 0 15px}
#p1-ops-root .p1-head{display:flex;align-items:flex-end;justify-content:space-between;flex-wrap:wrap;gap:10px;margin-bottom:12px}
#p1-ops-root h2{font-size:17px!important;color:var(--c2-txt,#fff)!important;margin:0!important;font-weight:850}
#p1-ops-root p{color:var(--c2-muted,#aab);font-size:12px;margin:5px 0 0;line-height:1.8}
#p1-ops-root .p1-pill{padding:6px 10px;border:1px solid #526080;border-radius:999px;font-size:11px;color:#ccd7ed}
#c2-root .c2-cards{margin-top:6px!important}
#c2-root .c2-card{min-height:124px}
#p1-monitor{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:16px 0}
#p1-monitor .p1-server{padding:15px;border:1px solid var(--c2-line,#31385b);border-radius:17px;
 background:linear-gradient(145deg,rgba(36,46,82,.8),rgba(18,23,42,.8));min-width:0;color:#f2f3ff}
#p1-monitor .p1-top{display:flex;justify-content:space-between;align-items:center;gap:8px;font-weight:850;font-size:13px}
#p1-monitor .p1-state{font-size:10px;color:#b9bedb;font-weight:650}
#p1-monitor .p1-values{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}
#p1-monitor .p1-metric{background:rgba(255,255,255,.045);border-radius:11px;padding:11px;min-width:0}
#p1-monitor .p1-metric small{display:block;color:#afb9d6;font-size:10px}
#p1-monitor .p1-metric b{display:block;font-size:16px;margin-top:7px;font-weight:800;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
#p1-monitor .p1-note{font-size:10px;color:#b6bfd9;line-height:1.7;margin-top:10px}
#c2-root .c2-table-wrap{overflow:visible!important;max-height:none!important;border:0!important;border-radius:0!important}
#c2-root .c2-table-wrap table{display:block!important;min-width:0!important;width:100%!important;border-collapse:separate!important}
#c2-root .c2-table-wrap thead{display:none!important}
#c2-root .c2-table-wrap tbody{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
#c2-root .c2-table-wrap tbody tr{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;
 padding:13px;border:1px solid var(--c2-line,#31385b);border-radius:16px;
 background:rgba(20,25,50,.58);box-shadow:0 8px 20px #0002;min-width:0}
#c2-root .c2-table-wrap tbody td{display:flex!important;min-width:0!important;
 flex-direction:column;gap:4px;padding:6px 8px!important;border:0!important;
 text-align:right!important;white-space:normal!important;overflow-wrap:anywhere!important;font-size:12px!important}
#c2-root .c2-table-wrap tbody td::before{font-size:10px!important;color:#abaed0!important;line-height:1.7}
#c2-root .c2-table-wrap tbody td:nth-child(1){grid-column:1/-1;font-weight:850;font-size:15px!important}
#c2-root .c2-table-wrap tbody td:nth-child(1)::before{content:"اکانت X-UI"}
#c2-root .c2-table-wrap tbody td:nth-child(2){grid-column:1/-1}
#c2-root .c2-table-wrap tbody td:nth-child(2)::before{content:"حساب VPN"}
#c2-root .c2-table-wrap tbody td:nth-child(3)::before{content:"وضعیت"}
#c2-root .c2-table-wrap tbody td:nth-child(4)::before{content:"مصرف کل X-UI"}
#c2-root .c2-table-wrap tbody td:nth-child(5)::before{content:"مصرف امروز"}
#c2-root .c2-table-wrap tbody td:nth-child(6)::before{content:"مصرف ۳۰ روز"}
#c2-root .c2-table-wrap tbody td:nth-child(7)::before{content:"نرخ لحظه‌ای"}
#c2-root .c2-table-wrap tbody td:nth-child(8)::before{content:"آخرین اتصال"}
#c2-root .c2-table-wrap tbody td:nth-child(9){grid-column:1/-1;padding-top:10px!important;border-top:1px solid #42466a!important}
#c2-root .c2-table-wrap tbody td:nth-child(9)::before{content:"کنترل اکانت"}
#c2-root .c2-table-wrap tbody td:nth-child(9) button{width:100%;min-height:42px}
#c2-root .c2-table-wrap tbody tr:has(td[colspan]){display:block!important}
#c2-root .c2-table-wrap tbody tr:has(td[colspan]) td:before{display:none}
@media(max-width:950px){#p1-monitor{grid-template-columns:1fr}}
@media(max-width:800px){#c2-root .c2-table-wrap tbody{grid-template-columns:1fr}}
</style>
'''
_P1_HEADER = r'''
<section id="p1-ops-root" aria-label="نمای اصلی پایش سرورها">
  <div class="p1-head"><div><h2>مرکز پایش سه سرور</h2>
  <p>اطلاعات X-UI زنده است؛ CPU، RAM و سهمیه خریداری‌شده فقط بعد از اتصال پایش میزبان ایران نمایش داده می‌شوند.</p>
  </div><span class="p1-pill">پایش فاز یک · فقط‌خواندنی</span></div>
</section>
'''
_P1_METRICS = '<section id="p1-monitor" aria-label="منابع و سهمیه سرورها"></section>'
_p1_template=_p1_template.replace('{% block content %}','{% block content %}'+_P1_CSS,1)
_p1_template=_p1_template.replace('<div id="c2-cards" class="c2-cards"></div>',
                                  _P1_HEADER+'<div id="c2-cards" class="c2-cards"></div>'+_P1_METRICS,1)
_P1_SCRIPT = r'''
<script>
(function(){
"use strict";
if(window.__HESAB_PHASE1_UI_V1)return;window.__HESAB_PHASE1_UI_V1=true;
const box=document.getElementById("p1-monitor");
if(!box)return;
const serverNames={"maya1":"مایا ۱","maya-s3":"مایا S3","maya4":"مایا ۴"};
const el=(tag,text,parent,cls)=>{const e=document.createElement(tag);
 if(text!==undefined)e.textContent=text;if(cls)e.className=cls;
 if(parent)parent.appendChild(e);return e;};
const fmt=v=>(v===null||v===undefined)?"—":Number(v).toLocaleString("fa-IR",{maximumFractionDigits:1});
const values={};
function render(){
 box.replaceChildren();
 for(const id of ["maya1","maya-s3","maya4"]){
  const d=values[id]||{}, card=el("article",undefined,box,"p1-server");
  const head=el("div",undefined,card,"p1-top");
  el("span",serverNames[id],head);
  let label=d.state==="ok"?"متصل":d.state==="stale"?"اطلاعات قدیمی":
    d.state==="not_configured"?"نیازمند اتصال":"در انتظار اطلاعات";
  el("span",label,head,"p1-state");
  const grid=el("div",undefined,card,"p1-values");
  const iran=d.role==="iran";
  function metric(name,value){const one=el("div",undefined,grid,"p1-metric");
   el("small",name,one);el("b",value,one);}
  metric("CPU سرور ایران",iran?fmt(d.cpu_pct)+"٪":"—");
  metric("RAM سرور ایران",iran?fmt(d.ram_pct)+"٪":"—");
  metric("حجم باقی‌مانده",iran&&["verified","estimated"].includes(d.traffic_state)?
    (d.traffic_state==="verified"?"":"حدودی: ")+fmt(d.remaining_gb)+" GB":"—");
  metric("وضعیت مسیر VPN",d.probe_state==="ok"?"تست موفق":
    d.probe_state==="failed"?"اختلال تأییدشده":"تست تنظیم نشده");
  el("div",!iran?"پایش منابع برای سرور خارج فعال نیست.":
    d.traffic_state==="estimated"&&d.remaining_gb<=10?"هشدار اولیه: برآورد کمتر از ۱۰ گیگ است؛ با پنل دیتاسنتر تطبیق بده.":
    d.traffic_state!=="verified"?"حجم باقی‌مانده هنوز با سهمیه واقعی دیتاسنتر تأیید نشده است.":
    "مقدار سهمیه طبق شمارنده پیکربندی‌شده میزبان.",card,"p1-note");
 }
}
async function refresh(){
 try{
  const r=await fetch("/control-room/phase1/status",{credentials:"same-origin",cache:"no-store"});
  if(!r.ok)throw Error("HTTP");
  const d=await r.json();
  if(!d.ok||!d.servers)throw Error("Malformed");
  for(const id of ["maya1","maya-s3","maya4"])values[id]=d.servers[id]||{};
 }catch(e){for(const id of ["maya1","maya-s3","maya4"])values[id]={state:"unavailable"};}
 render();
}
refresh();setInterval(()=>{if(!document.hidden)refresh();},60000);
})();
</script>
'''
_p1_start,_p1_end=_p1_template.rsplit("{% endblock %}",1)
_p1_template=_p1_start+_P1_SCRIPT+"\n{% endblock %}"+_p1_end
TEMPLATES["control_room.html"]=_p1_template
if hasattr(env.loader,"mapping"):env.loader.mapping.update(TEMPLATES)
