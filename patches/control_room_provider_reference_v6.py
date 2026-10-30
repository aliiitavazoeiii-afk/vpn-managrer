# HESAB_CONTROL_ROOM_PROVIDER_REFERENCE_V6
# Display operator-reported DC remaining balance, clearly labeled as a NON-LIVE
# reference until physical NIC billing direction/period is confirmed.
# No XUI, payment, NIC metering state, or billing events are modified.
import json as _b6_json
import time as _b6_time
from pathlib import Path as _b6_Path
from fastapi import Request as _b6_Request
from fastapi.responses import JSONResponse as _b6_JSON
from jinja2 import Environment as _b6_Environment

_B6_REF_PATH=_b6_Path("/srv/maya-live/phase1/provider_balance_reference_v1.json")
_B6_SERVERS=("maya1","maya-s3","maya4")

def _b6_status(request:_b6_Request):
    result={name:{"state":"not_recorded"} for name in _B6_SERVERS}
    try:
        if _B6_REF_PATH.is_file() and _B6_REF_PATH.stat().st_size<=12000:
            doc=_b6_json.loads(_B6_REF_PATH.read_text(encoding="utf-8"))
            if doc.get("format")!="HESAB_PROVIDER_BALANCE_REFERENCE_V1":
                raise ValueError("invalid format")
            recorded=doc.get("recorded_at")
            if type(recorded) is not int or not 0<=_b6_time.time()-recorded<86400*366:
                raise ValueError("invalid recording time")
            if doc.get("provider_observed_at_known") is not False:
                raise ValueError("observed time incorrectly claimed")
            data=doc.get("servers")
            if not isinstance(data,dict):raise ValueError("invalid servers")
            for server in _B6_SERVERS:
                item=data.get(server)
                if not isinstance(item,dict):continue
                value=item.get("remaining_gb")
                if type(value) in (int,float) and 0<=value<=1e9:
                    result[server]={
                        "state":"reported_not_live",
                        "remaining_gb":round(float(value),3),
                        "recorded_at":recorded,
                        "source":"operator_report",
                        "provider_observed_at_known":False
                    }
    except (ValueError,TypeError,OSError,OverflowError):
        result={name:{"state":"invalid"} for name in _B6_SERVERS}
    return _b6_JSON({"ok":True,"servers":result},
                    headers={"Cache-Control":"private,no-store"})

app.add_api_route("/control-room/v6/provider-reference",_b6_status,methods=["GET"])

_B6_TEMPLATE=TEMPLATES.get("control_room.html","")
_B6_HELPER_ANCHOR='const c4Host={};'
_B6_REFRESH='refresh();c4FetchMetrics();setInterval(refresh,20000);'
_B6_REMAIN='''const remaining=quotaUsable?
     (quota.traffic_state==="estimated"?"حدودی ":"")+c4Str(quota.remaining_gb," GB"):"—";
   c4CardLabel("ترافیک باقی‌مانده",remaining,values);'''
_B6_CLICK='   btn.onclick=()=>{'
for marker in (_B6_HELPER_ANCHOR,_B6_REFRESH,_B6_REMAIN,_B6_CLICK,
               'id="c4-shell"','id="c3-mode"','id="m2-style"'):
    if _B6_TEMPLATE.count(marker)!=1:
        raise RuntimeError("V6 expected original Control Room V4/M2 template, missing/duplicate: "+marker)
if "b6-reference-style" in _B6_TEMPLATE:
    raise RuntimeError("V6 reference already present")

_B6_JS=r'''
const b6Provider={};
async function b6FetchReference(){
 try {
   const response=await fetch("/control-room/v6/provider-reference",{
      credentials:"same-origin",cache:"no-store"});
   if(!response.ok)throw Error("Reference API");
   const data=await response.json();
   if(data.ok!==true||!data.servers)throw Error("Reference format");
   for(const id of ["maya1","maya-s3","maya4"])
     b6Provider[id]=data.servers[id]||{state:"not_recorded"};
 } catch(e) {
   for(const id of ["maya1","maya-s3","maya4"])
      b6Provider[id]={state:"unavailable"};
 }
 renderCards();
}
'''
_B6_REMAIN_NEW='''const provider=b6Provider[id]||{};
   const hasProviderReference=provider.state==="reported_not_live"&&
       typeof provider.remaining_gb==="number"&&
       Number.isFinite(provider.remaining_gb)&&provider.remaining_gb>=0;
   const remaining=quotaUsable?
       (quota.traffic_state==="estimated"?"حدودی ":"")+c4Str(quota.remaining_gb," GB"):
       hasProviderReference?c4Str(provider.remaining_gb," GB"):"—";
   c4CardLabel(quotaUsable?"مانده تخمینی از سنسور":
      hasProviderReference?"آخرین مانده اعلامی دیتاسنتر":"مانده ترافیک دیتاسنتر",
      remaining,values);'''
_B6_NOTE='''   if(!quotaUsable&&hasProviderReference){
     create("div","آخرین مانده اعلامی دیتاسنتر؛ مقدار زنده نیست و ممکن است از زمان گزارش کمتر شده باشد. هنوز در محاسبه خودکار یا هشدار ۱۰ گیگ استفاده نمی‌شود.",
       btn,"b6-provider-reference-note");
   }'''
_B6_CSS=r'''
<style id="b6-reference-style">
#c2-root .b6-provider-reference-note{
 background:rgba(137,111,248,.07);
 border:1px solid rgba(158,134,242,.24);border-radius:11px;
 font-size:11px;line-height:1.85;color:#c7c1e7;
 padding:10px 12px;margin-top:10px;text-align:right
}
#c2-root .c4-values small{line-height:1.65}
</style>
'''
_B6_TEMPLATE=_B6_TEMPLATE.replace('{% block content %}',
                                  '{% block content %}'+_B6_CSS,1)
_B6_TEMPLATE=_B6_TEMPLATE.replace(_B6_HELPER_ANCHOR,
                                   _B6_JS+"\n"+_B6_HELPER_ANCHOR,1)
_B6_TEMPLATE=_B6_TEMPLATE.replace(_B6_REMAIN,_B6_REMAIN_NEW,1)
_B6_TEMPLATE=_B6_TEMPLATE.replace(_B6_CLICK,_B6_NOTE+"\n"+_B6_CLICK,1)
_B6_TEMPLATE=_B6_TEMPLATE.replace(_B6_REFRESH,
            _B6_REFRESH+'b6FetchReference();setInterval(()=>{if(!document.hidden)b6FetchReference();},60000);',1)
if "{#" in _B6_TEMPLATE:raise RuntimeError("Jinja comment opener")
_b6_Environment().parse(_B6_TEMPLATE)
TEMPLATES["control_room.html"]=_B6_TEMPLATE
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)
