# HESAB_CONTROL_ROOM_NIC_LIVE_V5
# Read-only measured RX/TX in existing V4/V2 cards WITHOUT billing direction.
# Does not modify XUI, payment, user controls, state or provider-quota baseline.
import json as _n5_json
import time as _n5_time
from pathlib import Path as _n5_Path
from fastapi import Request as _n5_Request
from fastapi.responses import JSONResponse as _n5_JSON
from jinja2 import Environment as _n5_Environment

_N5_PATH=_n5_Path("/srv/maya-live/phase1/status.json")
_N5_NAMES=("maya1","maya-s3","maya4")
def _n5_read(request:_n5_Request):
    output={name:{"state":"not_configured"} for name in _N5_NAMES}
    try:
        if _N5_PATH.is_file() and _N5_PATH.stat().st_size<65536:
            d=_n5_json.loads(_N5_PATH.read_text(encoding="utf-8"))
            if d.get("format")!="HESAB_PHASE1_V1":
                raise ValueError("unexpected meter format")
            collected=d.get("collected_at")
            now=_n5_time.time()
            if type(collected) not in (int,float) or not 0<=now-collected<=180:
                output={name:{"state":"stale"} for name in _N5_NAMES}
            else:
                for name in _N5_NAMES:
                    raw=(d.get("servers") or {}).get(name)
                    if not isinstance(raw,dict):continue
                    state=raw.get("state")
                    if state not in ("ok","unavailable","not_configured"):
                        state="invalid"
                    result={"state":state}
                    if state=="ok":
                        for key in ("rx_period_gb","tx_period_gb"):
                            val=raw.get(key)
                            if type(val) in (int,float) and 0<=val<=1e9:
                                result[key]=round(float(val),3)
                        rawstate=raw.get("traffic_state")
                        if rawstate in ("direction_unconfirmed","estimated",
                                        "verified","uncertain_reset","not_configured"):
                            result["traffic_state"]=rawstate
                        source=raw.get("traffic_source")
                        if source in ("NIC_RX","NIC_TX","physical_nic"):
                            result["traffic_source"]=source
                    output[name]=result
    except (OSError,ValueError,TypeError,KeyError):
        output={name:{"state":"invalid"} for name in _N5_NAMES}
    return _n5_JSON({"ok":True,"servers":output},
                    headers={"Cache-Control":"private,no-store"})
app.add_api_route("/control-room/v5/nic-traffic",_n5_read,methods=["GET"])

_N5_TEMPLATE=TEMPLATES.get("control_room.html","")
_N5_ANCHOR='const c4Host={};'
_N5_RENDER='''const host=c4Host[id]||{},quota=c4Quota[id]||{};'''
_N5_VALUES='''c4CardLabel("ترافیک باقی‌مانده",remaining,values);'''
_N5_FETCH='''refresh();c4FetchMetrics();setInterval(refresh,20000);'''
for anchor in (_N5_ANCHOR,_N5_RENDER,_N5_VALUES,_N5_FETCH,
               'id="c4-shell"','id="m2-style"','id="c3-mode"'):
    if _N5_TEMPLATE.count(anchor)!=1:
        raise RuntimeError("Unexpected V4+M2 control-room template layout: "+anchor)
if "n5-net-traffic" in _N5_TEMPLATE:
    raise RuntimeError("NIC V5 display already present")

_N5_SCRIPT=r'''
const n5Traffic={};
async function n5FetchTraffic(){
 try{
   const response=await fetch("/control-room/v5/nic-traffic",{
      credentials:"same-origin",cache:"no-store"});
   if(!response.ok)throw Error("NIC API "+response.status);
   const data=await response.json();
   if(data.ok!==true || !data.servers)throw Error("NIC API format");
   for(const id of ["maya1","maya-s3","maya4"])
      n5Traffic[id]=data.servers[id]||{state:"not_configured"};
 }catch(e){
   for(const id of ["maya1","maya-s3","maya4"])n5Traffic[id]={state:"unavailable"};
 }
 renderCards();
}
function n5Format(value){
 return typeof value==="number"&&Number.isFinite(value)?
    value.toLocaleString("fa-IR",{maximumFractionDigits:3})+" GB":"—";
}
'''
_N5_RENDER_NEW='''const host=c4Host[id]||{},quota=c4Quota[id]||{},net=n5Traffic[id]||{};'''
_N5_VALUES_NEW='''c4CardLabel("ترافیک باقی‌مانده",remaining,values);
   c4CardLabel("RX اندازه‌گیری‌شده",net.state==="ok"?n5Format(net.rx_period_gb):"—",values);
   c4CardLabel("TX اندازه‌گیری‌شده",net.state==="ok"?n5Format(net.tx_period_gb):"—",values);'''
_N5_CSS=r'''
<style id="n5-net-traffic">
#c2-root .c4-values{gap:7px}
#c2-root .c4-values>div{padding:9px 11px}
#c2-root .c4-values strong{font-size:14px!important}
#c2-root .c4-server-card{min-height:365px!important;height:auto!important}
#c2-root .n5-meter-note{font-size:10px;color:#a4b2d8;line-height:1.8;
 border:1px solid #64739c45;border-radius:9px;padding:9px 10px;margin-top:9px;
 background:#7392c30b;display:block}
#c2-root .n5-meter-note[data-state="error"]{color:#f4b2ad;border-color:#bd6a6a66}
</style>
'''
_N5_NOTICE='''   const n5Note=create("div",undefined,btn,"n5-meter-note");
   const n5Current=net.state==="ok"&&
       typeof net.rx_period_gb==="number"&&typeof net.tx_period_gb==="number";
   const n5Text=n5Current?
       (net.traffic_state==="direction_unconfirmed"?
       "RX و TX از شروع پایش ثبت می‌شوند؛ جهت قابل‌صورتحساب هنوز تأیید نشده است.":
       net.traffic_state==="uncertain_reset"?
       "ترافیک شبکه ثبت می‌شود؛ ریست شمارنده نیازمند تطبیق با دیتاسنتر است.":
       "RX/TX شمارنده واقعی کارت شبکه‌اند و مستقل از مصرف X-UI هستند.")
       :net.state==="stale"?
       "آخرین نمونه سنسور قدیمی است؛ تازگی جمع‌آوری را بررسی کن.":
       "اطلاعات شمارنده شبکه در دسترس نیست؛ سرویس جمع‌آوری را بررسی کن.";
   n5Note.textContent=n5Text;
   if(!n5Current)n5Note.dataset.state="error";
'''
_N5_TEMPLATE=_N5_TEMPLATE.replace('{% block content %}',
                                   '{% block content %}'+_N5_CSS,1)
_N5_TEMPLATE=_N5_TEMPLATE.replace(_N5_ANCHOR,
                                   _N5_SCRIPT+"\n"+_N5_ANCHOR,1)
_N5_TEMPLATE=_N5_TEMPLATE.replace(_N5_RENDER,_N5_RENDER_NEW,1)
_N5_TEMPLATE=_N5_TEMPLATE.replace(_N5_VALUES,_N5_VALUES_NEW,1)
_N5_TEMPLATE=_N5_TEMPLATE.replace(_N5_FETCH,
                                   _N5_FETCH+'n5FetchTraffic();setInterval(()=>{if(!document.hidden)n5FetchTraffic();},60000);',1)
# Insert note after existing V2 meter notice, and before btn click event.
_N5_CLICK="   btn.onclick=()=>{"
if _N5_TEMPLATE.count(_N5_CLICK)!=1:
    raise RuntimeError("Card click handler not unique")
_N5_TEMPLATE=_N5_TEMPLATE.replace(_N5_CLICK,_N5_NOTICE+_N5_CLICK,1)
if "{#" in _N5_TEMPLATE:raise RuntimeError("Jinja comment opener")
_n5_Environment().parse(_N5_TEMPLATE)
TEMPLATES["control_room.html"]=_N5_TEMPLATE
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)
