# HESAB_MAYA_CONTROL_ROOM_V2
# ONLY /control-room template and GET route are replaced. All other pages unchanged.
# Traffic reports read /srv/maya-live/usage_v1.sqlite3 (local sampling, no finance writes).
import json as _cr2_json
import secrets as _cr2_secrets
import sqlite3 as _cr2_sqlite
from datetime import datetime as _cr2_datetime,timedelta as _cr2_timedelta
from pathlib import Path as _cr2_Path
from zoneinfo import ZoneInfo as _cr2_ZoneInfo
from fastapi import Request as _cr2_Request,Depends as _cr2_Depends
from fastapi.responses import JSONResponse as _cr2_JSON
from sqlalchemy.orm import Session as _cr2_Session

_CR2_DB=_cr2_Path("/srv/maya-live/usage_v1.sqlite3")
_CR2_TZ=_cr2_ZoneInfo("Asia/Tehran")

def _cr2_usage(server,records):
    empty={"today":0,"last30":0,"rate":None,"sampled":False}
    output={str(x["email"]).strip().casefold():dict(empty) for x in records}
    if not _CR2_DB.is_file():return output
    today=_cr2_datetime.now(_CR2_TZ).date()
    first=(today-_cr2_timedelta(days=29)).isoformat()
    try:
        with _cr2_sqlite.connect("file:"+str(_CR2_DB)+"?mode=ro",uri=True,timeout=3) as conn:
            for email,day,up,down,samples in conn.execute("""
                SELECT email,local_day,up,down,sample_count FROM daily_usage
                WHERE server=? AND local_day>=? AND local_day<=?
                """,(server,first,today.isoformat())):
                key=str(email or "").casefold()
                if key not in output:continue
                value=max(0,int(up or 0))+max(0,int(down or 0))
                output[key]["last30"]+=value
                output[key]["sampled"]=True
                if day==today.isoformat():output[key]["today"]+=value
            now=int(_cr2_datetime.now(_CR2_TZ).timestamp())
            for email,rate,measured in conn.execute(
                "SELECT email,rate_bps,measured_at FROM client_state WHERE server=?",(server,)):
                key=str(email or "").casefold()
                if key in output and 0<=now-int(measured)<=900:
                    output[key]["rate"]=max(0,float(rate or 0))
    except (_cr2_sqlite.Error,ValueError,OSError):
        # Missing reports must NEVER be silently represented as precise zero.
        return {key:dict(empty) for key in output}
    return output

def _cr2_one(server,db):
    report=_ml_one(server,db)
    sample=_cr2_usage(server,report["rows"])
    for row in report["rows"]:
        usage=sample.get(str(row["email"]).casefold(),{})
        row.update({
         "today_bytes":usage.get("today",0),
         "last30_bytes":usage.get("last30",0),
         "rate_bps":usage.get("rate"),
         "usage_sampled":usage.get("sampled",False)
        })
    report["today_total"]=sum(r["today_bytes"] for r in report["rows"])
    report["last30_total"]=sum(r["last30_bytes"] for r in report["rows"])
    report["sampled"]=any(r["usage_sampled"] for r in report["rows"])
    report["top_today"]=[
      {"email":r["email"],"name":r["name"],"bytes":r["today_bytes"]}
      for r in sorted(report["rows"],key=lambda x:(-x["today_bytes"],x["email"].casefold()))
      if r["today_bytes"]>0
    ][:10]
    report["top_30"]=[
      {"email":r["email"],"name":r["name"],"bytes":r["last30_bytes"]}
      for r in sorted(report["rows"],key=lambda x:(-x["last30_bytes"],x["email"].casefold()))
      if r["last30_bytes"]>0
    ][:10]
    return report

def _cr2_data(request:_cr2_Request,db:_cr2_Session=_cr2_Depends(get_db)):
    reports=[]
    for server in _ML_SERVERS:
        try:reports.append(_cr2_one(server,db))
        except Exception as exc:
            print("MAYA_C2_DATA_ERROR",server,type(exc).__name__,str(exc)[:90])
            reports.append({"server":server,"ok":False,"message":"ارتباط ناموفق"})
    return _cr2_JSON({"ok":True,"servers":reports},headers={"Cache-Control":"private, no-store"})

_CR2_TEMPLATE=r'''{% extends "base.html" %}
{% block title %}اتاق کنترل · حساب VPN{% endblock %}
{% block heading %}{% endblock %}
{% block subheading %}{% endblock %}
{% block content %}
<div class="ref-control-page c2-root" id="c2-root" dir="rtl">
<style>
#c2-root{
 --c2-glass:var(--ref-card,rgba(18,20,53,.72));
 --c2-dark:var(--ref-card2,rgba(12,14,39,.82));
 --c2-line:var(--ref-line,rgba(157,161,255,.14));
 --c2-accent:var(--ref-purple,#8c67ff);
 --c2-txt:var(--ref-text,#f4f5ff);
 --c2-muted:var(--ref-muted,#8f94bc);
 --c2-ok:var(--ref-green,#4de3a2);
 --c2-bad:var(--ref-red,#ff657f);
 --c2-sh:var(--ref-shadow,0 26px 70px rgba(0,0,0,.36));
 max-width:1680px;margin:0 auto;color:var(--c2-txt);
 font:inherit;font-family:inherit
}
#c2-root *{box-sizing:border-box}
#c2-root [hidden]{display:none!important}
#c2-root .c2-head{display:flex;align-items:center;justify-content:space-between;gap:14px;margin:6px 0 19px}
#c2-root .c2-head h1{font-size:clamp(22px,3vw,31px)!important;font-weight:850!important;margin:0!important;color:var(--c2-txt)!important}
#c2-root .c2-time{font-size:12px;color:var(--c2-muted)}
#c2-root .c2-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:15px}
#c2-root .c2-card{
 display:flex;align-items:center;justify-content:space-between;gap:10px;text-align:right;
 min-height:135px;width:100%;cursor:pointer;font:inherit;color:var(--c2-txt);
 padding:23px 24px;border:1px solid var(--c2-line);border-radius:21px;
 background:radial-gradient(circle at 5% 0%,rgba(133,92,255,.13),transparent 48%),linear-gradient(135deg,var(--c2-glass),var(--c2-dark));
 box-shadow:var(--c2-sh);transition:transform .18s,border-color .18s,background .18s
}
#c2-root .c2-card:hover{transform:translateY(-3px);border-color:rgba(156,127,255,.42)}
#c2-root .c2-card[aria-expanded="true"]{border-color:var(--c2-accent);background:linear-gradient(145deg,rgba(116,81,255,.22),var(--c2-dark))}
#c2-root .c2-card b{display:block;font-size:21px;font-weight:850}
#c2-root .c2-card small{display:block;font-size:12px;color:var(--c2-muted);margin-top:11px}
#c2-root .c2-card strong{font-size:32px;font-weight:850;line-height:1.25}
#c2-root .c2-card em{display:block;font-style:normal;font-size:11px;color:var(--c2-ok);margin-top:3px}
#c2-root .c2-panel{
 margin-top:17px;padding:20px;border:1px solid var(--c2-line);border-radius:22px;
 background:linear-gradient(135deg,var(--c2-glass),var(--c2-dark));box-shadow:var(--c2-sh)
}
#c2-root .c2-panel-top{display:flex;align-items:center;justify-content:space-between;gap:13px;flex-wrap:wrap;margin-bottom:15px}
#c2-root .c2-panel-top h2,#c2-root .c2-panel-title{font-size:19px!important;color:var(--c2-txt)!important;margin:0!important;font-weight:800}
#c2-root .c2-stat{font-size:12px;color:var(--c2-muted)}
#c2-root .c2-search{height:43px;width:min(340px,100%);border-radius:12px!important;
 border:1px solid var(--c2-line)!important;background:rgba(6,9,27,.56)!important;
 padding:0 15px!important;color:var(--c2-txt)!important;font:inherit!important;font-size:14px!important
}
#c2-root .c2-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin-bottom:16px}
#c2-root .c2-kpis div{padding:14px;border:1px solid var(--c2-line);border-radius:13px;background:rgba(124,103,255,.06)}
#c2-root .c2-kpis small{display:block;font-size:11px;color:var(--c2-muted)}
#c2-root .c2-kpis b{display:block;margin-top:6px;font-size:20px}
#c2-root .c2-table-wrap{overflow:auto;max-height:62vh;border:1px solid var(--c2-line);border-radius:14px}
#c2-root table{border-collapse:collapse;width:100%;min-width:930px}
#c2-root th,#c2-root td{padding:11px 12px;text-align:right;border-bottom:1px solid var(--c2-line);font-size:12px;vertical-align:middle}
#c2-root th{background:rgba(69,50,144,.19);color:#b2acdf;position:sticky;top:0;z-index:1;font-weight:750}
#c2-root td{color:var(--c2-txt)}#c2-root td small{display:block;color:var(--c2-muted);font-size:11px;margin-top:3px}
#c2-root td a{color:#b8a7ff;text-decoration:none}#c2-root td a:hover{text-decoration:underline}
#c2-root .c2-ltr{direction:ltr;text-align:right;font-variant-numeric:tabular-nums}
#c2-root .c2-ok{color:var(--c2-ok)}#c2-root .c2-bad{color:var(--c2-bad)}
#c2-root .c2-btn{
 padding:8px 13px;min-width:79px;border-radius:10px;font:inherit;font-size:12px;font-weight:750;cursor:pointer;
 border:1px solid rgba(146,117,255,.20);background:rgba(119,84,255,.14);color:var(--c2-txt)
}
#c2-root .c2-btn.c2-stop{color:#ffafb9;border-color:rgba(255,101,127,.26);background:rgba(255,101,127,.10)}
#c2-root .c2-btn.c2-start{color:#8bebbf;border-color:rgba(77,227,162,.23);background:rgba(77,227,162,.09)}
#c2-root .c2-btn:disabled{opacity:.45;cursor:wait}
#c2-root .c2-reports{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:16px}
#c2-root .c2-report{min-width:0;padding:17px;border:1px solid var(--c2-line);border-radius:17px;background:rgba(112,91,255,.045)}
#c2-root .c2-report h3{margin:0 0 13px!important;font-size:16px!important;color:var(--c2-txt)!important}
#c2-root .c2-rank-row{display:grid;grid-template-columns:30px minmax(0,1fr) auto;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid rgba(157,161,255,.07);font-size:12px}
#c2-root .c2-rank-row span{color:var(--c2-muted)}#c2-root .c2-rank-row b{font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#c2-root .c2-rank-row strong{font-size:12px;color:#bcaeff;direction:ltr}
#c2-root .c2-empty{font-size:12px;color:var(--c2-muted);padding:18px 0}
#c2-root .c2-notice{font-size:12px;min-height:23px;color:var(--c2-muted);margin-top:10px}
@media(max-width:900px){
 #c2-root .c2-cards{gap:8px}
 #c2-root .c2-card{padding:13px;min-height:105px;border-radius:16px}
 #c2-root .c2-card b{font-size:15px}#c2-root .c2-card strong{font-size:22px}
 #c2-root .c2-reports{grid-template-columns:1fr}
 #c2-root .c2-kpis{grid-template-columns:repeat(2,1fr)}
}
@media(max-width:520px){
 #c2-root .c2-card{min-height:95px;padding:10px 8px;display:block}
 #c2-root .c2-card b{font-size:13px}#c2-root .c2-card strong{font-size:22px;margin-top:6px;display:block}
 #c2-root .c2-card small{font-size:10px;margin-top:4px}
 #c2-root .c2-panel{padding:11px}
}
</style>
<header class="c2-head"><h1>اتاق کنترل</h1><span id="c2-time" class="c2-time"></span></header>
<div id="c2-cards" class="c2-cards"></div>
<section id="c2-panel" class="c2-panel" hidden>
 <div class="c2-panel-top">
  <div><h2 id="c2-name">—</h2><div id="c2-stat" class="c2-stat"></div></div>
  <input id="c2-search" class="c2-search" type="search" autocomplete="off" placeholder="جست‌وجوی کاربر، نام، شناسه">
 </div>
 <div id="c2-kpis" class="c2-kpis"></div>
 <div class="c2-table-wrap" id="c2-scroll">
  <table><thead><tr>
    <th>اکانت X-UI</th><th>حساب VPN</th><th>وضعیت</th>
    <th>مصرف کل</th><th>امروز</th><th>۳۰ روز</th>
    <th>نرخ اخیر</th><th>آخرین اتصال</th><th>کنترل</th>
  </tr></thead><tbody id="c2-users"></tbody></table>
 </div>
 <div class="c2-reports">
  <section class="c2-report"><h3>پرمصرف‌ترین‌های امروز</h3><div id="c2-top-today"></div></section>
  <section class="c2-report"><h3>پرمصرف‌ترین‌های ۳۰ روز ثبت‌شده</h3><div id="c2-top-30"></div></section>
 </div>
 <div id="c2-msg" class="c2-notice" role="status"></div>
</section>
<script>
(function(){
"use strict";
if(window.__HESAB_CONTROL_ROOM_V2)return;window.__HESAB_CONTROL_ROOM_V2=true;
const names={"maya1":"مایا ۱","maya-s3":"مایا ۳","maya4":"مایا ۴"};
const csrf="{{ ctrl_csrf }}";
const cardBox=document.getElementById("c2-cards");
const detail=document.getElementById("c2-panel");
const search=document.getElementById("c2-search");
const tbody=document.getElementById("c2-users");
const scroll=document.getElementById("c2-scroll");
const notice=document.getElementById("c2-msg");
const state={active:null,latest:{},query:"",loading:false,mutating:false};
const byId=id=>document.getElementById(id);
const create=(tag,txt,parent,cls)=>{
 const e=document.createElement(tag);if(txt!==undefined)e.textContent=String(txt);
 if(cls)e.className=cls;if(parent)parent.appendChild(e);return e;
};
const count=n=>Number(n||0).toLocaleString("fa-IR");
const bytes=n=>{
 if(n===null||n===undefined)return "—";
 const x=Number(n);if(!Number.isFinite(x))return "—";
 if(x>=1073741824)return (x/1073741824).toFixed(2)+" GB";
 if(x>=1048576)return (x/1048576).toFixed(1)+" MB";
 return (x/1024).toFixed(0)+" KB";
};
const rate=n=>n===null||n===undefined?"—":bytes(Number(n))+"/s";
const normal=x=>String(x||"").toLocaleLowerCase().replaceAll("ي","ی").replaceAll("ك","ک").replace(/\s+/g,"");
const last=x=>{
 let v=Number(x||0);if(!v)return "—";if(v<1e11)v*=1000;
 const d=new Date(v);
 return Number.isFinite(d.getTime())?d.toLocaleString("fa-IR",{timeZone:"Asia/Tehran"}):"—";
};
function renderCards(){
 cardBox.replaceChildren();
 for(const id of ["maya1","maya-s3","maya4"]){
  const data=state.latest[id],ok=data&&data.ok;
  const btn=create("button",undefined,cardBox,"c2-card");
  btn.type="button";btn.setAttribute("aria-expanded",state.active===id?"true":"false");
  const left=create("div",undefined,btn);
  create("b",names[id],left);
  create("small",!data?"...":ok?("فعال "+count(data.enabled)+" · تطبیق "+count(data.linked)):"ارتباط ناموفق",left);
  const right=create("div",undefined,btn);
  create("strong",ok?count(data.total):"—",right);
  create("em",ok?"● LIVE":"○",right);
  btn.onclick=()=>{
    state.active=state.active===id?null:id;
    notice.textContent="";
    renderCards();renderDetails();
  };
 }
}
function renderRank(target,list){
 const el=byId(target);el.replaceChildren();
 if(!list||!list.length){create("div","—",el,"c2-empty");return;}
 list.forEach((item,i)=>{
  const row=create("div",undefined,el,"c2-rank-row");
  create("span",count(i+1),row);
  const label=create("b",item.name||item.email,row);
  label.title=item.email;
  create("strong",bytes(item.bytes),row);
 });
}
function renderDetails(){
 const server=state.active;
 detail.hidden=!server;
 if(!server)return;
 const data=state.latest[server];
 byId("c2-name").textContent=names[server];
 byId("c2-stat").textContent=data&&data.ok?
    (count(data.total)+" اکانت · "+count(data.linked)+" تطبیق · "+count(data.unmatched)+" بدون تطبیق"):
    "دریافت اطلاعات ناموفق";
 const kpis=byId("c2-kpis");kpis.replaceChildren();
 if(!data||!data.ok){
   tbody.replaceChildren();renderRank("c2-top-today",[]);renderRank("c2-top-30",[]);return;
 }
 for(const [label,val] of [
   ["کل کاربران",count(data.total)],["فعال",count(data.enabled)],
   ["مصرف امروز",data.sampled?bytes(data.today_total):"—"],
   ["مصرف ۳۰ روز ثبت‌شده",data.sampled?bytes(data.last30_total):"—"]
 ]){
   const box=create("div",undefined,kpis);
   create("small",label,box);create("b",val,box);
 }
 const y=scroll.scrollTop;
 tbody.replaceChildren();
 const q=normal(state.query);
 for(const item of data.rows){
   if(!normal([item.email,item.name,item.sid||""].join(" ")).includes(q))continue;
   const tr=create("tr",undefined,tbody);
   const name=create("td",undefined,tr);
   create("b",item.email,name);
   const account=create("td",undefined,tr);
   if(item.sid){
      const a=create("a","#"+item.sid+" · "+item.name,account);
      a.href="/users/"+encodeURIComponent(item.sid);
   }else create("small","تطبیق نشده",account);
   const enabled=Boolean(item.client_enabled);
   create("td",enabled?"فعال":"غیرفعال",tr,enabled?"c2-ok":"c2-bad");
   create("td",bytes(item.up+item.down),tr,"c2-ltr");
   create("td",item.usage_sampled?bytes(item.today_bytes):"—",tr,"c2-ltr");
   create("td",item.usage_sampled?bytes(item.last30_bytes):"—",tr,"c2-ltr");
   create("td",rate(item.rate_bps),tr,"c2-ltr");
   create("td",last(item.last_online),tr);
   const controls=create("td",undefined,tr);
   if(item.sid&&!item.control_ambiguous){
     const btn=create("button",enabled?"قطع":"وصل",controls,
       "c2-btn "+(enabled?"c2-stop":"c2-start"));
     btn.type="button";btn.disabled=state.mutating;
     btn.onclick=()=>toggle(server,item,btn);
   }else create("small",item.control_ambiguous?"تعارض ورودی":"نیازمند تطبیق",controls);
 }
 if(!tbody.children.length){
   const tr=create("tr",undefined,tbody);
   const td=create("td","نتیجه‌ای پیدا نشد",tr);td.colSpan=9;
 }
 scroll.scrollTop=y;
 renderRank("c2-top-today",data.top_today);
 renderRank("c2-top-30",data.top_30);
}
async function toggle(server,item,button){
 if(state.mutating)return;
 if(!confirm((item.client_enabled?"قطع":"وصل")+" "+item.email+" در "+names[server]+"؟"))return;
 state.mutating=true;button.disabled=true;
 const form=new FormData();
 for(const [k,v] of Object.entries({
   server,email:item.email,sid:item.sid,
   expected:item.client_enabled?1:0,target:item.client_enabled?0:1,csrf
 }))form.append(k,String(v));
 try{
   const res=await fetch("/control-room/maya-live/toggle",{
     method:"POST",body:form,credentials:"same-origin",
     headers:{"X-Requested-With":"XMLHttpRequest"}});
   const data=await res.json();
   if(!res.ok||!data.ok)throw Error(data.error||"تأیید نشد");
   notice.textContent="وضعیت "+item.email+" در "+names[server]+" تأیید شد.";
 }catch(err){
   notice.textContent=String(err.message)+" · پیش از تلاش دوباره وضعیت پنل را بررسی کن";
 }finally{
   state.mutating=false;await refresh();
 }
}
async function refresh(){
 if(document.hidden||state.mutating||state.loading)return;
 state.loading=true;
 try{
  const response=await fetch("/control-room/v2/data",{
     credentials:"same-origin",cache:"no-store"});
  if(!response.ok)throw Error("API "+response.status);
  const data=await response.json();
  if(!data.ok||!Array.isArray(data.servers))throw Error("API format");
  for(const item of data.servers)state.latest[item.server]=item;
  byId("c2-time").textContent=new Date().toLocaleTimeString("fa-IR",{timeZone:"Asia/Tehran"});
  renderCards();renderDetails();
 }catch(err){
  byId("c2-time").textContent="اتصال ناموفق";
 }finally{state.loading=false;}
}
search.oninput=()=>{state.query=search.value;renderDetails();};
refresh();setInterval(refresh,20000);
})();
</script>
</div>
{% endblock %}
'''

def _cr2_page(request:_cr2_Request):
    csrf=request.session.get("maya1_control_csrf")
    if not isinstance(csrf,str) or len(csrf)<30:
        csrf=_cr2_secrets.token_urlsafe(32)
        request.session["maya1_control_csrf"]=csrf
    return render("control_room.html",request,ctrl_csrf=csrf)

TEMPLATES["control_room.html"]=_CR2_TEMPLATE
if hasattr(env.loader,"mapping"):env.loader.mapping.update(TEMPLATES)
# Replace ONLY this page and endpoint, NEVER the home dashboard or account flows.
app.router.routes[:]=[
  r for r in app.router.routes
  if not (getattr(r,"path",None)=="/control-room"
     and "GET" in (getattr(r,"methods",set()) or set()))
]
app.add_api_route("/control-room",_cr2_page,methods=["GET"])
app.add_api_route("/control-room/v2/data",_cr2_data,methods=["GET"])
