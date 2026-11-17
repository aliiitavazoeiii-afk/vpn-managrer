# HESAB_CONTROL_ROOM_TRAFFIC_ANALYTICS_V11
# Only add read-only traffic page / summary and make existing "daily traffic" clickable.
# No purchase controls, no changes to provider balances, no XUI/SMS/tunnels.
import json as _th11_json
import time as _th11_time
import secrets as _th11_secrets
from pathlib import Path as _th11_Path
from fastapi import Request as _th11_Request
from fastapi.responses import JSONResponse as _th11_JSON
from jinja2 import Environment as _th11_Jinja

_TH11_PATH = _th11_Path("/srv/maya-live/phase1/traffic_history_v11.json")
_TH11_NAMES = {"maya1": "مایا ۱", "maya-s3": "مایا ۳", "maya4": "مایا ۴"}


def _th11_load():
    if (_TH11_PATH.is_symlink() or not _TH11_PATH.is_file() or
            not 0 < _TH11_PATH.stat().st_size < 750000):
        return None
    doc = _th11_json.loads(_TH11_PATH.read_text(encoding="utf-8"))
    if doc.get("format") != "MAYA_NIC_TRAFFIC_HISTORY_V11":
        return None
    at = doc.get("generated_at")
    if type(at) is not int or not 0 <= _th11_time.time() - at <= 190:
        return None
    return doc


def _th11_token(request):
    token = request.session.get("maya1_control_csrf")
    if not isinstance(token, str) or len(token) < 30:
        token = _th11_secrets.token_urlsafe(32)
        request.session["maya1_control_csrf"] = token
    return token


def _th11_json_auth(request):
    token = request.session.get("maya1_control_csrf")
    header = request.headers.get("x-control-csrf", "")
    return (isinstance(token, str) and len(token) >= 30 and
            _th11_secrets.compare_digest(token, header) and
            request.headers.get("sec-fetch-site") in (None, "same-origin"))


def _th11_summary(request: _th11_Request):
    # Same-origin CSRF is supplied by the V10 page template.
    if not _th11_json_auth(request):
        return _th11_JSON({"ok": False}, status_code=403)
    try:
        doc = _th11_load()
    except (ValueError, OSError, TypeError, OverflowError):
        doc = None
    servers = {}
    for name in _TH11_NAMES:
        item = (doc or {}).get("servers", {}).get(name, {})
        if item.get("state") == "ok" and type(item.get("rx_today_gb")) in (int, float):
            servers[name] = {
                "state": "ok", "rx_today_gb": item["rx_today_gb"],
                "partial_day": item.get("partial_day") is True,
                "coverage_today_pct": item.get("coverage_today_pct", 0)}
        else:
            servers[name] = {"state": "unavailable" if doc else "stale"}
    return _th11_JSON({"ok": True, "servers": servers},
                      headers={"Cache-Control": "private,no-store"})


def _th11_data(request: _th11_Request, server: str):
    if not _th11_json_auth(request):
        return _th11_JSON({"ok": False}, status_code=403)
    if server not in _TH11_NAMES:
        return _th11_JSON({"ok": False, "error": "not_found"}, status_code=404)
    try:
        doc = _th11_load()
    except (ValueError, OSError, TypeError, OverflowError):
        doc = None
    if not doc:
        return _th11_JSON({"ok": False, "error": "stale"}, status_code=503,
                          headers={"Cache-Control": "private,no-store"})
    data = doc.get("servers", {}).get(server)
    if not isinstance(data, dict) or data.get("name") != server:
        return _th11_JSON({"ok": False, "error": "not_found"}, status_code=503)
    return _th11_JSON({"ok": True, "server": data, "generated_at": doc["generated_at"]},
                      headers={"Cache-Control": "private,no-store"})


def _th11_page(request: _th11_Request, server: str):
    if server not in _TH11_NAMES:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)
    return render("control_room_traffic_v11.html", request,
                  traffic_server_id=server,
                  traffic_server_label=_TH11_NAMES[server],
                  ctrl_csrf=_th11_token(request))


_TH11_TEMPLATE = r'''{% extends "base.html" %}
{% block title %}تحلیل ترافیک {{ traffic_server_label }}{% endblock %}
{% block heading %}{% endblock %}
{% block subheading %}{% endblock %}
{% block content %}
<div id="th11" dir="rtl" class="th11-page">
<style>
#th11{--line:#ffffff1b;--muted:#acb5d3;--violet:#a88aff;--cyan:#4ed7d9;
 color:#f4f3ff;max-width:1230px;margin:0 auto;padding:12px 12px 35px;
 font-family:inherit;line-height:1.8}
#th11 *{box-sizing:border-box}
#th11 .th11-head{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-bottom:18px}
#th11 .th11-head h1{font-size:23px;font-weight:900;margin:0}
#th11 .th11-head p{font-size:12px;color:var(--muted);margin:3px 0 0}
#th11 .th11-back{text-decoration:none;border:1px solid #6f6590;border-radius:11px;
 padding:8px 13px;color:#eeeaff;font-size:12px;background:#232743}
#th11 .th11-status{font-size:11px;color:#c0d4ec;margin:0 0 12px}
#th11 .th11-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:14px}
#th11 .th11-box{background:linear-gradient(145deg,#1e2548,#171c35);
 border:1px solid var(--line);border-radius:17px;padding:15px 17px;min-width:0}
#th11 .th11-kpi small{font-size:12px;color:var(--muted);display:block}
#th11 .th11-kpi strong{font-size:24px;direction:ltr;display:block;text-align:right;
 font-variant-numeric:tabular-nums;margin:3px 0}
#th11 .th11-kpi em{font-style:normal;color:#bbc4e0;font-size:10px}
#th11 h2{font-size:17px;font-weight:850;margin:0}
#th11 .th11-heading{display:flex;justify-content:space-between;align-items:center;
 gap:10px;flex-wrap:wrap;margin-bottom:10px}
#th11 .th11-caption{font-size:11px;color:var(--muted)}
#th11 .th11-section{margin-top:14px}
#th11 .th11-legend{display:flex;gap:18px;font-size:11px;color:#dae0f2;align-items:center;flex-wrap:wrap}
#th11 .th11-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-left:5px}
#th11 .th11-dot.rx{background:var(--violet)}
#th11 .th11-dot.tx{background:var(--cyan)}
#th11 .th11-chart-wrap{overflow-x:auto;overscroll-behavior-x:contain}
#th11 svg{display:block;min-height:235px}
#th11 .th11-grid{stroke:#ffffff20;stroke-width:1}
#th11 .th11-axis{font-family:inherit;fill:#aeb9d7;font-size:11px}
#th11 .th11-daybar{cursor:pointer}
#th11 .th11-daybar:focus{outline:2px solid #fff;outline-offset:2px}
#th11 .th11-info{color:#b7c4e4;font-size:11px;margin:12px 0 0;line-height:2}
#th11 .th11-info strong{color:#e4d7ff}
#th11 .th11-insights{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:15px}
#th11 .th11-insights strong{display:block;color:#f4edff;font-size:19px}
#th11 .th11-insights small{color:var(--muted);font-size:11px}
#th11 .th11-nodata{padding:15px 0;color:#c2c4dd;font-size:13px}
@media(max-width:850px){#th11 .th11-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
 #th11 .th11-insights{grid-template-columns:1fr}}
@media(max-width:450px){#th11 .th11-kpis{gap:8px}
 #th11 .th11-box{padding:11px}#th11 .th11-kpi strong{font-size:21px}
 #th11 .th11-head h1{font-size:20px}}
</style>
<div class="th11-head">
 <div><h1>ترافیک {{ traffic_server_label }}</h1>
 <p>مصرف واقعی کارت شبکه سرور · ثبت ساعتی و روزانه · ساعت ایران</p></div>
 <a class="th11-back" href="/control-room">بازگشت به اتاق کنترل</a>
</div>
<p id="th11-status" class="th11-status">در حال خواندن آمار ثبت‌شده…</p>
<div class="th11-kpis">
 <div class="th11-box th11-kpi"><small>دریافت امروز (RX)</small><strong id="th11-today">—</strong><em>گیگابایت، از بخش اندازه‌گیری‌شده روز</em></div>
 <div class="th11-box th11-kpi"><small>ارسال امروز (TX)</small><strong id="th11-tx">—</strong><em>گیگابایت، از بخش اندازه‌گیری‌شده روز</em></div>
 <div class="th11-box th11-kpi"><small>RX ثبت‌شده در ۳۰ روز</small><strong id="th11-month">—</strong><em>در روزهای بدون داده، مصرف حدس زده نمی‌شود</em></div>
 <div class="th11-box th11-kpi"><small>میانگین روزانه RX</small><strong id="th11-average">—</strong><em>فقط روزهای با پوشش حداقل ۷۵٪، هفت روز اخیر</em></div>
</div>
<section class="th11-box th11-section">
 <div class="th11-heading"><h2>روند روزانه · ۳۰ روز</h2><div class="th11-legend">
 <span><i class="th11-dot rx"></i>دریافت RX</span><span><i class="th11-dot tx"></i>ارسال TX</span></div></div>
 <div class="th11-chart-wrap" id="th11-daily"></div>
 <p class="th11-info">روی هر روز بزن تا جزئیات ۲۴ ساعت همان روز را ببینی. فاصله‌های ثبت‌نشده خالی می‌مانند؛ صفر فرض نمی‌شوند.</p>
</section>
<section class="th11-box th11-section">
 <div class="th11-heading"><h2 id="th11-hour-title">ترافیک ساعتی امروز</h2>
 <span class="th11-caption" id="th11-hour-coverage">—</span></div>
 <div class="th11-chart-wrap" id="th11-hourly"></div>
 <p class="th11-info" id="th11-day-note"></p>
</section>
<div class="th11-insights">
 <div class="th11-box"><small>پرترافیک‌ترین ساعت ثبت‌شده · ۷ روز</small><strong id="th11-peak">—</strong><small id="th11-peak-detail">فقط ساعات با پوشش کافی</small></div>
 <div class="th11-box"><small>کم‌ترافیک‌ترین ساعت ثبت‌شده · ۷ روز</small><strong id="th11-quiet">—</strong><small id="th11-quiet-detail">فقط ساعات با پوشش کافی</small></div>
 <div class="th11-box"><small>پوشش اندازه‌گیری امروز</small><strong id="th11-coverage">—</strong><small>از ابتدای امروز تا آخرین به‌روزرسانی</small></div>
</div>
<p class="th11-info">مبنای نمودار RX/TX رابط شبکه فیزیکی سرور است، نه مصرف اکانت‌ها در X-UI و نه لزوماً میزان قابل‌صورتحساب دیتاسنتر. تاریخچه از زمان فعال‌شدن این ثبت‌کننده ساخته می‌شود و قابل بازسازی حدسی نیست. مقادیر با GB ده‌دهی نمایش داده شده‌اند.</p>
</div>
<script id="th11-script">
(function(){
"use strict";
const sid={{ traffic_server_id | tojson }};
const csrf={{ ctrl_csrf | tojson }};
const ns="http://www.w3.org/2000/svg";
const el=id=>document.getElementById(id);
let current=null,selected=null;
const fmt=x=>x===null||x===undefined?"—":Number(x).toLocaleString("fa-IR",{maximumFractionDigits:3});
const gb=x=>x===null||x===undefined?"—":fmt(x)+" GB";
const dateLabel=x=>x?new Intl.DateTimeFormat("fa-IR",{month:"short",day:"numeric"}).format(new Date(x+"T12:00:00+03:30")):"—";
const clock=h=>String(h).padStart(2,"0")+":۰۰";
function svg(tag,parent,attrs,text){
 const e=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs||{}))e.setAttribute(k,v);
 if(text!==undefined)e.textContent=text;if(parent)parent.appendChild(e);return e;
}
function draw(where,data,isDay){
 where.replaceChildren();
 const W=isDay?940:850,H=245,L=53,R=12,T=13,B=43;
 const usableW=W-L-R,usableH=H-T-B,n=data.length;
 const max=Math.max(.01,...data.flatMap(x=>[x.rx_gb||0,x.tx_gb||0]))*1.15;
 const view=svg("svg",where,{viewBox:"0 0 "+W+" "+H,width:isDay?"940":"850",height:"245",
   role:"img","aria-label":isDay?"نمودار مصرف روزانه RX و TX":"نمودار مصرف ساعتی RX و TX"});
 for(let j=0;j<=4;j++){
   const y=T+usableH*(1-j/4),value=max*j/4;
   svg("line",view,{x1:L,y1:y,x2:W-R,y2:y,class:"th11-grid"});
   svg("text",view,{x:L-7,y:y+4,"text-anchor":"end",class:"th11-axis"},fmt(value));
 }
 const space=usableW/n,bar=Math.max(3,space*.27),hasData=data.some(x=>x.rx_gb!==null||x.tx_gb!==null);
 data.forEach((d,i)=>{
   const xc=L+(i+.5)*space;
   if(isDay&&d.day===selected){
     svg("rect",view,{x:L+i*space+1,y:T,width:space-2,height:usableH,rx:4,fill:"#a58aff18"});
   }
   for(const [j,key,color] of [[0,"rx_gb","#a88aff"],[1,"tx_gb","#4ed7d9"]]){
     if(d[key]===null)continue;
     const height=Math.max(.8,d[key]/max*usableH);
     const rect=svg("rect",view,{x:xc+(j-.98)*bar,y:T+usableH-height,
       width:bar,height:height,rx:2,fill:color,class:isDay?"th11-daybar":""});
     svg("title",rect,{},(isDay?d.day:clock(d.hour))+" · "+(j?"TX: ":"RX: ")+gb(d[key]));
     if(isDay){
       const activate=()=>{selected=d.day;draw(el("th11-daily"),current.days,true);renderHours();};
       rect.addEventListener("click",activate);
       rect.setAttribute("tabindex","0");
       rect.setAttribute("role","button");
       rect.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();activate();}});
     }
   }
   const shouldLabel=isDay?(i%4===0||i===n-1):(i%2===0);
   if(shouldLabel){
     svg("text",view,{x:xc,y:H-B+17,"text-anchor":"middle",class:"th11-axis"},
       isDay?dateLabel(d.day):String(d.hour).padStart(2,"0"));
   }
 });
 if(!hasData)svg("text",view,{x:W/2,y:H/2,"text-anchor":"middle",fill:"#ccd0ea",
  "font-size":15},"هنوز داده ثبت‌شده‌ای وجود ندارد");
}
function renderHours(){
 const day=current.days.find(d=>d.day===selected)||current.days.at(-1);
 selected=day.day;
 el("th11-hour-title").textContent="ترافیک ساعتی · "+dateLabel(day.day);
 el("th11-hour-coverage").textContent="پوشش نمونه‌برداری: "+fmt(day.coverage_pct)+"٪";
 draw(el("th11-hourly"),day.hours,false);
 let note=day.unallocated_rx_gb>0?
  "بخشی از RX امروز ("+gb(day.unallocated_rx_gb)+") از شمارنده معتبر قبلی منتقل شده و ساعت دقیق آن قابل بازیابی نیست. ":"";
 note+=day.coverage_pct<99?"این روز داده ناقص دارد؛ نمودار فقط بازه‌های واقعاً مشاهده‌شده را نشان می‌دهد.":"پوشش نمونه‌های این روز تقریباً کامل است.";
 el("th11-day-note").textContent=note;
}
function render(data,generated){
 current=data;
 if(!selected||!data.days.some(x=>x.day===selected))selected=data.days.at(-1).day;
 const age=Math.max(0,Math.floor(Date.now()/1000-generated));
 el("th11-status").textContent=(data.state==="ok"?"ثبت ترافیک فعال است":data.state==="warming_up"?
 "ثبت‌کننده تازه مبناگذاری شده":"نمونه تازه در دسترس نیست")+
 " · آخرین داده سرور: "+(data.sampled_at?new Date(data.sampled_at*1000).toLocaleString("fa-IR"):"ناموجود")+
 " · زمان تولید گزارش: "+fmt(Math.floor(age/60))+" دقیقه پیش";
 el("th11-today").textContent=gb(data.rx_today_gb);
 el("th11-tx").textContent=gb(data.tx_today_gb);
 el("th11-month").textContent=gb(data.last30_observed_rx_gb);
 el("th11-average").textContent=gb(data.last7_daily_average_rx_gb);
 el("th11-coverage").textContent=fmt(data.coverage_today_pct)+"٪";
 el("th11-peak").textContent=data.peak_hour===null?"داده کافی نیست":clock(data.peak_hour);
 el("th11-quiet").textContent=data.quiet_hour===null?"داده کافی نیست":clock(data.quiet_hour);
 el("th11-peak-detail").textContent=data.peak_avg_rx_gb===null?
 "ساعت‌های فاقد اندازه‌گیری رتبه‌بندی نمی‌شوند":"متوسط RX: "+gb(data.peak_avg_rx_gb)+"/ساعت";
 el("th11-quiet-detail").textContent=data.quiet_avg_rx_gb===null?
 "ساعت‌های فاقد اندازه‌گیری رتبه‌بندی نمی‌شوند":"متوسط RX: "+gb(data.quiet_avg_rx_gb)+"/ساعت";
 draw(el("th11-daily"),data.days,true);renderHours();
}
async function refresh(){
 try{
   const r=await fetch("/control-room/traffic/data/"+encodeURIComponent(sid),{
     credentials:"same-origin",cache:"no-store",headers:{"X-Control-CSRF":csrf}});
   const body=await r.json();
   if(!r.ok||body.ok!==true)throw Error(body.error||"unavailable");
   render(body.server,body.generated_at);
 }catch(e){
   el("th11-status").textContent="آمار تازه در دسترس نیست؛ وضعیت سنسور و سرویس جمع‌آوری باید بررسی شود.";
 }
}
refresh();setInterval(refresh,60000);
})();
</script>
{% endblock %}
'''
_th11_Jinja().parse(_TH11_TEMPLATE)
TEMPLATES["control_room_traffic_v11.html"] = _TH11_TEMPLATE
if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)

_TH11_MAIN = TEMPLATES.get("control_room.html", "")
_TH11_OLD = 'fetch("/control-room/v10/daily",'
_TH11_CARD = '''c4CardLabel("ترافیک روز",today,values);
   if(day.partial_day===true){'''
_TH11_NEW_CARD = '''c4CardLabel("ترافیک روز",today,values);
   const trafficLine=values.lastElementChild;
   trafficLine.classList.add("th11-traffic-link");
   trafficLine.setAttribute("role","link");
   trafficLine.setAttribute("aria-label","نمودار ترافیک "+t10Names[id]);
   trafficLine.setAttribute("tabindex","0");
   const openTraffic=e=>{
      e.stopPropagation();e.preventDefault();
      window.location.assign("/control-room/traffic/"+encodeURIComponent(id));
   };
   trafficLine.addEventListener("click",openTraffic);
   trafficLine.addEventListener("keydown",e=>{
      if(e.key==="Enter"||e.key===" "){openTraffic(e);}
   });
   if(day.partial_day===true){'''
if (_TH11_MAIN.count(_TH11_OLD) != 1 or
        _TH11_MAIN.count(_TH11_CARD) != 1 or
        "t10-compact-css" not in _TH11_MAIN or
        "th11-traffic-link" in _TH11_MAIN):
    raise RuntimeError("V11 requires the unique live V10 daily card")
_TH11_STYLE = r'''
<style id="th11-control-style">
#c2-root .th11-traffic-link{cursor:pointer!important;border-color:#9c7fff99!important;
 transition:background .12s,border-color .12s!important}
#c2-root .th11-traffic-link:hover,#c2-root .th11-traffic-link:focus{
 background:#45356b77!important;border-color:#bda9ff!important;outline:2px solid #9580ff55}
</style>
'''
_TH11_MAIN = _TH11_MAIN.replace(_TH11_OLD,
    'fetch("/control-room/traffic/summary",', 1)
_TH11_MAIN = _TH11_MAIN.replace(_TH11_CARD, _TH11_NEW_CARD, 1)
_TH11_MAIN = _TH11_MAIN.replace("{% block content %}",
    "{% block content %}" + _TH11_STYLE, 1)
_th11_Jinja().parse(_TH11_MAIN)
TEMPLATES["control_room.html"] = _TH11_MAIN
if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)

for route in ("/control-room/traffic/summary",
              "/control-room/traffic/data/{server}",
              "/control-room/traffic/{server}"):
    if any(r.path == route for r in app.router.routes):
        raise RuntimeError("Duplicate Maya traffic history route: " + route)
app.add_api_route("/control-room/traffic/summary", _th11_summary, methods=["GET"])
app.add_api_route("/control-room/traffic/data/{server}", _th11_data, methods=["GET"])
app.add_api_route("/control-room/traffic/{server}", _th11_page, methods=["GET"])
