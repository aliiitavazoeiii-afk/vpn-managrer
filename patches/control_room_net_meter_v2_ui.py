# HESAB_CONTROL_ROOM_NET_METER_V2_UI
# Only add verified/estimated physical-NIC quota readouts to existing V4 card.
# Never invent a billed traffic direction, issue network actions or alter finance.
from jinja2 import Environment as _m2_Environment

_M2_TPL=TEMPLATES.get("control_room.html","")
_M2_TARGET='''c4CardLabel("ترافیک باقی‌مانده",remaining,values);
   c4CardLabel("حساب‌های فعال در X-UI",online?count(report.enabled):"—",values);'''
_M2_REPLACEMENT='''c4CardLabel("ترافیک باقی‌مانده",remaining,values);
   c4CardLabel("مصرف مبنای سهمیه",quotaUsable?
     c4Str(quota.traffic_used_gb," GB")+" · "+(quota.traffic_source==="NIC_RX"?"RX":"TX"):"—",values);
   c4CardLabel("حساب‌های فعال در X-UI",online?count(report.enabled):"—",values);'''
_M2_FOOT='''create("div",online?
      "تطبیق‌شده "+count(report.linked)+" · نیازمند بررسی "+count(report.unmatched):
      "اطلاعات زنده X-UI در دسترس نیست",btn,"c4-card-foot");'''
_M2_FOOT_NEW=_M2_FOOT+'''
   if(quota.state==="ok"&&quota.traffic_state==="uncertain_reset"){
     create("div","شمارنده شبکه ریست شده؛ باقیمانده سهمیه تا تطبیق با دیتاسنتر نامطمئن است.",
       btn,"m2-warning");
   }else if(quotaUsable&&Number(quota.remaining_gb)<=10){
     create("div","هشدار: برآورد ترافیک باقیمانده ۱۰ گیگ یا کمتر است؛ با پنل دیتاسنتر بررسی کن.",
       btn,"m2-warning");
   }else if(quota.state==="ok"&&quota.traffic_state==="direction_unconfirmed"){
     create("div","RX/TX مستقل ثبت می‌شود؛ جهت قابل‌صورتحساب و سهمیه هنوز تنظیم نشده‌اند.",
       btn,"m2-info");
   }'''
assert _M2_TPL.count(_M2_TARGET)==1,"Unexpected V4 quota slots"
assert _M2_TPL.count(_M2_FOOT)==1,"Unexpected V4 card foot"
_M2_CSS=r'''
<style id="m2-style">
#c2-root .c4-card-foot{margin-top:12px}
#c2-root .m2-warning{padding:10px;margin:10px 0 0;border-radius:10px;
 color:#ffe0a3;border:1px solid #9a6f3488;background:#a7631d23;
 font-size:11px;line-height:1.8}
#c2-root .m2-info{padding:9px;margin:9px 0 0;border-radius:10px;
 color:#a7b7da;border:1px solid #6177a344;background:#5269ad11;
 font-size:10px;line-height:1.8}
</style>
'''
_M2_TPL=_M2_TPL.replace(_M2_TARGET,_M2_REPLACEMENT,1)
_M2_TPL=_M2_TPL.replace(_M2_FOOT,_M2_FOOT_NEW,1)
_M2_TPL=_M2_TPL.replace("{% block content %}","{% block content %}"+_M2_CSS,1)
assert "{#" not in _M2_TPL
_m2_Environment().parse(_M2_TPL)
TEMPLATES["control_room.html"]=_M2_TPL
if hasattr(env.loader,"mapping"):env.loader.mapping.update(TEMPLATES)
