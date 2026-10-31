# HESAB_MAYA_PROVISIONAL_REMAINING_V7
# Operator-reported balance minus ACTUAL physical NIC RX recorded AFTER
# controlled baseline activation. Not a verified datacenter quota.
# No XUI/user/payments writes; warning 10GB remains disabled for this estimate.
import json as _e7_json
import time as _e7_time
from pathlib import Path as _e7_Path
from fastapi import Request as _e7_Request
from fastapi.responses import JSONResponse as _e7_JSON
from jinja2 import Environment as _e7_Environment

_E7_ROOT=_e7_Path("/srv/maya-live/phase1")
_E7_BASE=_E7_ROOT/"provisional_meter_baseline_v7.json"
_E7_METER=_E7_ROOT/"status.json"
_E7_NAMES=("maya1","maya-s3","maya4")

def _e7_read(request:_e7_Request):
    result={n:{"state":"not_initialized"} for n in _E7_NAMES}
    try:
        if not (_E7_BASE.is_file() and _E7_METER.is_file()):
            return _e7_JSON({"ok":True,"servers":result},
                            headers={"Cache-Control":"private,no-store"})
        if _E7_BASE.stat().st_size>24000 or _E7_METER.stat().st_size>64000:
            raise ValueError("oversized telemetry")
        base=_e7_json.loads(_E7_BASE.read_text(encoding="utf8"))
        sample=_e7_json.loads(_E7_METER.read_text(encoding="utf8"))
        if (base.get("format")!="HESAB_MAYA_PROVISIONAL_BASELINE_V7" or
            sample.get("format")!="HESAB_PHASE1_V1" or
            base.get("direction_assumption")!="rx" or
            base.get("provider_observation_time_known") is not False or
            base.get("alert_eligible") is not False):
            raise ValueError("incorrect prototype meter format")
        now=_e7_time.time()
        collected=sample.get("collected_at")
        started=base.get("created_at")
        if type(started) is not int or started>now+60:
            raise ValueError("invalid baseline time")
        if type(collected) not in (int,float) or not 0<=now-collected<=180:
            return _e7_JSON({"ok":True,"servers":
                {n:{"state":"stale"} for n in _E7_NAMES}},
                headers={"Cache-Control":"private,no-store"})
        if collected < started-180:
            raise ValueError("sample older than baseline")
        for name in _E7_NAMES:
            reference=base.get("servers",{}).get(name,{})
            meter=sample.get("servers",{}).get(name,{})
            item={"state":"unavailable"}
            if meter.get("state")!="ok":
                result[name]=item;continue
            if meter.get("counter_uncertain") is not False:
                result[name]={"state":"uncertain_counter"};continue
            if meter.get("traffic_state")!="direction_unconfirmed":
                result[name]={"state":"calibration_changed"};continue
            incoming=meter.get("rx_period_gb")
            initial=reference.get("rx_baseline_gb")
            reported=reference.get("starting_reported_remaining_gb")
            if any(type(x) not in (int,float) or not 0<=x<=1e9
                   for x in (incoming,initial,reported)):
                result[name]={"state":"invalid"};continue
            if incoming < initial-0.002:
                result[name]={"state":"meter_reset"};continue
            delta=max(0,float(incoming)-float(initial))
            item={"state":"provisional","direction":"rx",
                  "after_baseline_rx_gb":round(delta,3),
                  "estimate_remaining_gb":round(max(0,float(reported)-delta),3),
                  "old_provider_report_gb":round(float(reported),3),
                  "started_at":started,"provider_observed_at_known":False,
                  "alert_eligible":False}
            result[name]=item
    except (OSError,ValueError,TypeError,KeyError,OverflowError):
        result={n:{"state":"invalid"} for n in _E7_NAMES}
    return _e7_JSON({"ok":True,"servers":result},
                    headers={"Cache-Control":"private,no-store"})

app.add_api_route("/control-room/v7/provisional-remaining",_e7_read,methods=["GET"])

_E7_TEMPLATE=TEMPLATES.get("control_room.html","")
_E7_A='const c4Host={};'
_E7_REMAIN='''const provider=b6Provider[id]||{};
   const hasProviderReference=provider.state==="reported_not_live"&&
       typeof provider.remaining_gb==="number"&&
       Number.isFinite(provider.remaining_gb)&&provider.remaining_gb>=0;
   const remaining=quotaUsable?
       (quota.traffic_state==="estimated"?"حدودی ":"")+c4Str(quota.remaining_gb," GB"):
       hasProviderReference?c4Str(provider.remaining_gb," GB"):"—";
   c4CardLabel(quotaUsable?"مانده تخمینی از سنسور":
      hasProviderReference?"آخرین مانده اعلامی دیتاسنتر":"مانده ترافیک دیتاسنتر",
      remaining,values);'''
_E7_NOTE='''if(!quotaUsable&&hasProviderReference){
     create("div","آخرین مانده اعلامی دیتاسنتر؛ مقدار زنده نیست و ممکن است از زمان گزارش کمتر شده باشد. هنوز در محاسبه خودکار یا هشدار ۱۰ گیگ استفاده نمی‌شود.",
       btn,"b6-provider-reference-note");
   }'''
_E7_FETCH='refresh();c4FetchMetrics();setInterval(refresh,20000);'
for needle in (_E7_A,_E7_REMAIN,_E7_NOTE,_E7_FETCH,
               'id="b6-reference-style"','id="c4-shell"'):
    if _E7_TEMPLATE.count(needle)!=1:
        raise RuntimeError("V7 requires V6 Control Room without conflicting UI: "+needle)
if "e7-provisional-style" in _E7_TEMPLATE:
    raise RuntimeError("V7 already present")
_E7_HELPERS=r'''
const e7Estimate={};
const e7Gb=(v)=>Number(v).toLocaleString("fa-IR",
    {minimumFractionDigits:2,maximumFractionDigits:3})+" GB";
async function e7Fetch(){
 try {
  const r=await fetch("/control-room/v7/provisional-remaining",
      {credentials:"same-origin",cache:"no-store"});
  if(!r.ok)throw Error("meter API unavailable");
  const d=await r.json();
  if(!d.ok || !d.servers)throw Error("meter payload invalid");
  for(const name of ["maya1","maya-s3","maya4"])
   e7Estimate[name]=d.servers[name]||{state:"unavailable"};
 }catch(err){
  for(const name of ["maya1","maya-s3","maya4"])
   e7Estimate[name]={state:"unavailable"};
 }
 renderCards();
}
'''
_E7_NEW_REMAIN='''const provider=b6Provider[id]||{},forecast=e7Estimate[id]||{};
   const hasProviderReference=provider.state==="reported_not_live"&&
       typeof provider.remaining_gb==="number"&&
       Number.isFinite(provider.remaining_gb)&&provider.remaining_gb>=0;
   const hasEstimated=forecast.state==="provisional"&&
       typeof forecast.estimate_remaining_gb==="number"&&
       Number.isFinite(forecast.estimate_remaining_gb);
   const remaining=quotaUsable?
       (quota.traffic_state==="estimated"?"حدودی ":"")+c4Str(quota.remaining_gb," GB"):
       hasEstimated?"≈ "+e7Gb(forecast.estimate_remaining_gb):
       hasProviderReference?c4Str(provider.remaining_gb," GB"):"—";
   c4CardLabel(quotaUsable?"مانده تخمینی از سنسور":
      hasEstimated?"برآورد موقت از مرجع قدیمی · RX":
      hasProviderReference?"آخرین مانده اعلامی دیتاسنتر":"مانده ترافیک دیتاسنتر",
      remaining,values);'''
_E7_NEW_NOTE='''if(!quotaUsable&&hasEstimated){
     create("div","برآورد آزمایشی: از مقدار اعلام‌شده قدیمی فقط RX ثبت‌شده از زمان فعال‌سازی کسر می‌شود. مصرف دیشب بازسازی نشده، جهت RX قطعی نیست و این عدد برای تصمیم قطع سرور یا هشدار ۱۰ گیگ معتبر نیست.",
       btn,"e7-provisional-note");
   }else if(!quotaUsable&&hasProviderReference){
     create("div","آخرین مانده اعلامی دیتاسنتر؛ مقدار زنده نیست و ممکن است از زمان گزارش کمتر شده باشد. هنوز در محاسبه خودکار یا هشدار ۱۰ گیگ استفاده نمی‌شود.",
       btn,"b6-provider-reference-note");
   }'''
_E7_STYLE=r'''
<style id="e7-provisional-style">
#c2-root .e7-provisional-note{background:#7c65311a;border:1px solid #b18b5277;
 padding:10px 12px;border-radius:10px;line-height:1.85;color:#e5c995;
 font-size:11px;margin-top:10px;text-align:right}
</style>
'''
_E7_TEMPLATE=_E7_TEMPLATE.replace("{% block content %}",
     "{% block content %}"+_E7_STYLE,1)
_E7_TEMPLATE=_E7_TEMPLATE.replace(_E7_A,_E7_HELPERS+"\n"+_E7_A,1)
_E7_TEMPLATE=_E7_TEMPLATE.replace(_E7_REMAIN,_E7_NEW_REMAIN,1)
_E7_TEMPLATE=_E7_TEMPLATE.replace(_E7_NOTE,_E7_NEW_NOTE,1)
_E7_TEMPLATE=_E7_TEMPLATE.replace(_E7_FETCH,
  _E7_FETCH+'e7Fetch();setInterval(()=>{if(!document.hidden)e7Fetch();},60000);',1)
if "{#" in _E7_TEMPLATE:raise RuntimeError("Jinja unsafe token")
_e7_Environment().parse(_E7_TEMPLATE)
TEMPLATES["control_room.html"]=_E7_TEMPLATE
if hasattr(env.loader,"mapping"):env.loader.mapping.update(TEMPLATES)
