# HESAB_CONTROL_ROOM_TUNNEL_TELEMETRY_V11
# Append-only admin read API and UI overlay. Preserves V10 cards, XUI controls,
# topups, historical finance, user mapping and authenticated existing routes.
import json as _tv11_json
import secrets as _tv11_secrets
import sqlite3 as _tv11_sqlite
import time as _tv11_time
from pathlib import Path as _tv11_Path
from fastapi import Request as _tv11_Request
from fastapi.responses import JSONResponse as _tv11_JSON
from jinja2 import Environment as _tv11_Jinja

_TV11_DB = _tv11_Path("/srv/maya-live/telemetry_v11/telemetry.sqlite3")
_TV11_NAMES = ("maya1", "maya-s3", "maya4")
_TV11_LABELS = {"maya1": "مایا ۱", "maya-s3": "مایا ۳", "maya4": "مایا ۴"}

def _tv11_authorized(request):
    token = request.session.get("maya1_control_csrf")
    header = request.headers.get("x-control-csrf","")
    if (not isinstance(token,str) or len(token)<30
        or not _tv11_secrets.compare_digest(token,header)
        or request.headers.get("sec-fetch-site") not in (None,"same-origin")):
        return False
    return True

def _tv11_db_open():
    if not _TV11_DB.is_file():
        return None
    # Defensive: telemetry is a separate, independent, read-only SQLite store.
    return _tv11_sqlite.connect(
        "file:" + str(_TV11_DB) + "?mode=ro",uri=True,timeout=2
    )

def _tv11_data(request:_tv11_Request):
    if not _tv11_authorized(request):
        return _tv11_JSON({"ok":False},status_code=403)
    now=int(_tv11_time.time())
    servers={name:{"state":"not_configured","tunnel_type":"unknown"}
             for name in _TV11_NAMES}
    try:
        db=_tv11_db_open()
        if db is not None:
            with db:
                for sid,received,reported,raw,effective in db.execute(
                    "SELECT server_id,received_ts,sent_ts,payload,effective_state FROM server_state"
                ):
                    if sid not in servers:
                        continue
                    if received>now+30 or now-received>120:
                        servers[sid]={"state":"stale","age_s":max(0,now-received)}
                        continue
                    data=_tv11_json.loads(raw)
                    if data.get("schema")!="hesab-tunnel-v11":
                        servers[sid]={"state":"invalid"}
                        continue
                    # Controller information cannot prove client VPN connectivity.
                    ctrl=data.get("controller",{})
                    health=ctrl.get("state")
                    state=effective if health=="ok" and effective in (
                        "healthy","degraded","both_unavailable"
                    ) else "unknown"
                    paths=ctrl.get("paths",{}) if health=="ok" else {}
                    hstats=data.get("haproxy",{})
                    counters={}
                    for name,epoch in db.execute(
                        "SELECT lane,epoch FROM counters WHERE server_id=?",(sid,)
                    ):
                        counters[name]=int(epoch)
                    a,b=hstats.get("backhaul",{}),hstats.get("mieru",{})
                    connection_share=None
                    byte_share=None
                    if (counters.get("backhaul") is not None and
                        counters.get("backhaul")==counters.get("mieru")):
                        try:
                            x,y=a.get("total_connections"),b.get("total_connections")
                            if type(x) is int and type(y) is int and x+y>0:
                                connection_share=round(100*x/(x+y),1)
                            xb=a.get("bytes_in")+a.get("bytes_out")
                            yb=b.get("bytes_in")+b.get("bytes_out")
                            if type(xb) is int and type(yb) is int and xb+yb>0:
                                byte_share=round(100*xb/(xb+yb),1)
                        except TypeError:
                            pass
                    servers[sid]={
                        "state":state,"tunnel_type":data.get("tunnel_type","unknown"),
                        "updated_ts":int(received),"age_s":max(0,now-received),
                        "controller_age_s":ctrl.get("age_s"),
                        "system":data.get("system",{}),
                        "services":data.get("services",{}),
                        "paths":paths,"haproxy":hstats,
                        "foreign_ips":data.get("foreign_ips",{}),
                        "connection_share_backhaul_pct":connection_share,
                        "byte_share_backhaul_pct":byte_share,
                        "counter_epoch":counters,
                        "udp_state":"unknown",
                        "vpn_end_to_end":"not_tested",
                        "quota_verified":False,
                        "xui_online":None,
                    }
            db.close()
    except (_tv11_sqlite.Error,OSError,ValueError,TypeError):
        servers={sid:{"state":"unavailable"} for sid in _TV11_NAMES}
    return _tv11_JSON({"ok":True,"now_ts":now,"servers":servers},
        headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})

def _tv11_events(request:_tv11_Request):
    if not _tv11_authorized(request):
        return _tv11_JSON({"ok":False},status_code=403)
    result=[]
    try:
        db=_tv11_db_open()
        if db:
            with db:
                rows=db.execute(
                    "SELECT server_id,event_ts,kind,lane,detail FROM events "
                    "ORDER BY event_ts DESC,id DESC LIMIT 60"
                ).fetchall()
                result=[{"server":sid,"at":int(timestamp),"kind":kind,
                         "lane":lane,"detail":str(detail)[:160]} for
                        sid,timestamp,kind,lane,detail in rows if sid in _TV11_NAMES]
            db.close()
    except (_tv11_sqlite.Error,OSError,ValueError,TypeError):
        pass
    return _tv11_JSON({"ok":True,"events":result},
        headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})

def _tv11_samples(request:_tv11_Request):
    if not _tv11_authorized(request):
        return _tv11_JSON({"ok":False},status_code=403)
    sid=request.query_params.get("server","")
    if sid not in _TV11_NAMES:
        return _tv11_JSON({"ok":False},status_code=400)
    rows=[]
    try:
        db=_tv11_db_open()
        if db:
            with db:
                rows=db.execute(
                    "SELECT received_ts,cpu_pct,ram_pct,disk_pct FROM samples "
                    "WHERE server_id=? ORDER BY received_ts DESC,id DESC LIMIT 60",
                    (sid,)).fetchall()
            db.close()
    except (_tv11_sqlite.Error,OSError):
        pass
    return _tv11_JSON({"ok":True,"server":sid,"samples":[
        {"at":int(at),"cpu":cpu,"ram":ram,"disk":disk}
        for at,cpu,ram,disk in reversed(rows)]},
        headers={"Cache-Control":"private, no-store"})

for _tv11_path,_tv11_handler in (
    ("/control-room/v11/status",_tv11_data),
    ("/control-room/v11/events",_tv11_events),
    ("/control-room/v11/samples",_tv11_samples),
):
    if any(r.path==_tv11_path for r in app.router.routes):
        raise RuntimeError("Telemetry V11 route already exists: "+_tv11_path)
    app.add_api_route(_tv11_path,_tv11_handler,methods=["GET"])

_TV11_TEMPLATE=TEMPLATES.get("control_room.html","")
_TV11_ANCHOR='<div id="c2-cards" class="c2-cards"></div>'
if _TV11_TEMPLATE.count(_TV11_ANCHOR)!=1 or _TV11_TEMPLATE.count("{% block content %}")!=1:
    raise RuntimeError("Telemetry V11 cannot safely extend live V10 Control Room")
_TV11_CSS=r'''
<style>
#c2-root #tv11-overview{direction:rtl;border:1px solid #344359;border-radius:16px;
 background:linear-gradient(130deg,#132238,#10192b);padding:17px;margin:0 0 18px;
 color:#f1f5fa;font-size:13px}
#tv11-overview *{box-sizing:border-box}
#tv11-overview .tv11-top{display:flex;align-items:center;justify-content:space-between;
 gap:10px;flex-wrap:wrap}
#tv11-overview .tv11-top h2{font-size:17px;margin:0;color:#f1f5fa;font-weight:850}
#tv11-overview .tv11-top button{padding:7px 13px;border:1px solid #4d5d7a;
 background:#25344c;color:#e6f4ff;border-radius:9px;font:inherit;cursor:pointer}
#tv11-overview .tv11-meta{color:#a4b7cc;font-size:11px;margin-top:5px}
#tv11-overview .tv11-counts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));
 gap:8px;margin:15px 0}
#tv11-overview .tv11-counts div{background:#0d192b;border:1px solid #334256;
 border-radius:10px;padding:11px}
#tv11-overview .tv11-counts small{font-size:11px;color:#afc0d2;display:block}
#tv11-overview .tv11-counts strong{font-size:21px;display:block;margin-top:4px}
#tv11-overview .tv11-lanes{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
#tv11-overview details{background:#0f1b2b;border:1px solid #344359;border-radius:11px;
 padding:11px;min-width:0}
#tv11-overview summary{cursor:pointer;font-weight:850;display:flex;align-items:center;
 justify-content:space-between;gap:7px}
#tv11-overview .tv11-pill{font-size:10px;padding:4px 9px;border-radius:9px;
 background:#344153;color:#bdc9d8}
#tv11-overview .tv11-pill[data-state="healthy"]{background:#163c30;color:#87ecc0}
#tv11-overview .tv11-pill[data-state="degraded"],
#tv11-overview .tv11-pill[data-state="both_unavailable"]{background:#47303a;color:#ffafb7}
#tv11-overview .tv11-info{display:grid;grid-template-columns:1fr 1fr;gap:5px 10px;
 margin:13px 0;line-height:1.7}
#tv11-overview .tv11-info div{min-width:0;overflow-wrap:anywhere}
#tv11-overview .tv11-info small{font-size:10px;color:#a6b5c7;display:block}
#tv11-overview .tv11-route{border-top:1px solid #304052;padding:9px 0;line-height:1.6}
#tv11-overview .tv11-route b{font-weight:850}
#tv11-overview .tv11-route small{display:block;color:#a6b5c7;font-size:10px}
#tv11-overview .tv11-route strong{color:#c4e8dd}
#tv11-overview .tv11-chart{width:100%;height:42px;display:block;margin:9px 0}
#tv11-overview .tv11-events{border-top:1px solid #334256;margin:16px 0 0;padding-top:10px}
#tv11-overview .tv11-events h3{font-size:14px;margin:0 0 8px;color:#f4f6fa}
#tv11-overview .tv11-events li{font-size:11px;line-height:1.7;color:#b5c5d4;margin:4px 0}
#tv11-overview .tv11-alert-note{font-size:11px;color:#aab8cb;margin-top:12px}
#tv11-overview [hidden]{display:none!important}
@media(max-width:850px){
 #tv11-overview .tv11-lanes{grid-template-columns:1fr}
 #tv11-overview .tv11-counts{grid-template-columns:1fr 1fr}
}
</style>
'''
_TV11_HTML=r'''
<section id="tv11-overview" aria-label="مانیتورینگ تونل‌های ایران">
 <div class="tv11-top"><h2>سلامت اتصال و تونل‌های ایران</h2>
 <button id="tv11-refresh" type="button">به‌روزرسانی</button></div>
 <div id="tv11-last" class="tv11-meta" role="status">در انتظار اطلاعات امضاشده Agentها</div>
 <div class="tv11-counts" id="tv11-counts"></div>
 <div class="tv11-lanes" id="tv11-cards"></div>
 <div class="tv11-alert-note">ارقام HAProxy از شروع شمارنده‌اند، نه مصرف روزانه؛
 سهم اتصال و سهم بایت جداست. مانده سهمیه، سلامت UDP و تعداد کاربران آنلاین
 تا زمان اتصال منبع معتبر «نامشخص» باقی می‌ماند. هشدارها فعلاً فقط در پنل ثبت می‌شوند.</div>
 <section class="tv11-events"><h3>رویدادهای اخیر (زمان ایران)</h3><ul id="tv11-events"></ul></section>
</section>
'''
_TV11_JS=r'''
<script>
(function(){
 "use strict";
 if(window.__hesabTelemetryV11)return;window.__hesabTelemetryV11=true;
 const csrf="{{ ctrl_csrf }}",ids=["maya1","maya-s3","maya4"];
 const labels={"maya1":"مایا ۱","maya-s3":"مایا ۳","maya4":"مایا ۴"};
 const root=document.getElementById("tv11-overview");
 if(!root)return;
 const by=id=>document.getElementById(id);
 const add=(parent,tag,value,cls)=>{
   const el=document.createElement(tag);if(cls)el.className=cls;
   if(value!=null)el.textContent=String(value);parent.appendChild(el);return el;
 };
 const amount=(n,suffix="")=>typeof n==="number"&&Number.isFinite(n)?
   new Intl.NumberFormat("fa-IR",{maximumFractionDigits:1}).format(n)+suffix:"—";
 const time=t=>Number.isFinite(t)?new Intl.DateTimeFormat("fa-IR",{
   timeZone:"Asia/Tehran",dateStyle:"short",timeStyle:"short"}).format(new Date(t*1000)):"—";
 const status=s=>({
    healthy:"سالم",degraded:"اختلال یک مسیر",both_unavailable:"هر دو مسیر ناموجود",
    stale:"داده قدیمی",unavailable:"بدون داده",not_configured:"Agent نصب نشده",
    unknown:"نامشخص",invalid:"نامعتبر"
   }[s]||"نامشخص");
 const field=(parent,name,value)=>{
    let box=add(parent,"div",null),s=add(box,"small",name);add(box,"b",value);
 };
 const get=(url)=>fetch(url,{credentials:"same-origin",cache:"no-store",
   headers:{"X-Control-CSRF":csrf}}).then(r=>{if(!r.ok)throw new Error("data unavailable");return r.json()});
 function summary(values){
   const box=by("tv11-counts");box.replaceChildren();
   const all=ids.map(id=>values[id]||{});
   const fresh=all.filter(x=>["healthy","degraded","both_unavailable"].includes(x.state));
   const healthy=fresh.filter(x=>x.state==="healthy").length;
   const disrupted=fresh.filter(x=>["degraded","both_unavailable"].includes(x.state)).length;
   const stale=3-fresh.length;
   const paths=fresh.flatMap(x=>["backhaul","mieru"].map(k=>x.paths?.[k]?.available));
   for(const [label,val] of [["سرورهای ایران",3],["سالم",healthy],
       ["اختلال گزارش‌شده",disrupted],["بدون داده تازه",stale]]){
      const cell=add(box,"div",null);
      add(cell,"small",label);add(cell,"strong",amount(val));
   }
   by("tv11-last").textContent="مسیرهای دارای تست معتبر: "+amount(paths.filter(v=>v===true).length)+
     " سالم / "+amount(paths.filter(v=>v===false).length)+" مختل · بروزرسانی "+time(Date.now()/1000);
 }
 function sparkline(target,samples){
   target.replaceChildren();
   const valid=samples.filter(x=>typeof x.cpu==="number"&&x.cpu>=0&&x.cpu<=100).slice(-45);
   if(valid.length<2){add(target,"small","نمودار CPU: داده کافی وجود ندارد");return}
   const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");
   svg.setAttribute("viewBox","0 0 200 42");svg.setAttribute("class","tv11-chart");
   svg.setAttribute("aria-label","روند CPU اندازه‌گیری‌شده");
   const poly=document.createElementNS("http://www.w3.org/2000/svg","polyline");
   poly.setAttribute("fill","none");poly.setAttribute("stroke","#9ab7ed");
   poly.setAttribute("stroke-width","2.1");
   poly.setAttribute("points",valid.map((p,i)=>(200*i/(valid.length-1)).toFixed(1)+
     ","+(40-0.38*p.cpu).toFixed(1)).join(" "));
   svg.appendChild(poly);target.appendChild(svg);
 }
 async function draw(values){
   const container=by("tv11-cards");
   const open=new Set([...container.querySelectorAll("details[open]")].map(x=>x.dataset.server));
   container.replaceChildren();
   summary(values);
   for(const sid of ids){
      const data=values[sid]||{state:"not_configured"};
      const item=add(container,"details",null);item.dataset.server=sid;
      if(open.has(sid))item.open=true;
      const head=add(item,"summary",null);
      add(head,"span",labels[sid]);
      const pill=add(head,"span",status(data.state),"tv11-pill");pill.dataset.state=data.state;
      const info=add(item,"div",null,"tv11-info"),sys=data.system||{};
      field(info,"آخرین داده",data.updated_ts?time(data.updated_ts):"—");
      field(info,"نوع تونل",data.tunnel_type||"نامشخص");
      field(info,"CPU",amount(sys.cpu_pct,"٪"));
      field(info,"RAM",amount(sys.ram_pct,"٪"));
      field(info,"Disk",amount(sys.disk_pct,"٪"));
      field(info,"Uptime",amount(sys.uptime_s," ثانیه"));
      field(info,"RX/TX NIC",amount(sys.rx_bytes!=null?sys.rx_bytes/1e9:null," / ")+
        amount(sys.tx_bytes!=null?sys.tx_bytes/1e9:null," GB"));
      field(info,"Xray / XUI",data.services?.["x-ui"]||"نامشخص");
      field(info,"TCP 443 محلی",sys.tcp443_loopback||"نامشخص");
      field(info,"سلامت واقعی کلاینت VPN","تست نشده");
      field(info,"سهمیه دیتاسنتر","نامشخص");
      field(info,"UDP","اندازه‌گیری نشده");
      const stats=data.haproxy||{},paths=data.paths||{};
      for(const lane of ["backhaul","mieru"]){
        const detail=add(item,"div",null,"tv11-route");
        const d=paths[lane]||{},h=stats[lane]||{};
        add(detail,"b",lane==="backhaul"?"Backhaul V2":"Mieru");
        add(detail,"small","IP خارج: "+(data.foreign_ips?.[lane]||"نامشخص")+
          " · HAProxy: "+(h.status||"نامشخص"));
        add(detail,"small","HTTPS: "+(d.tcp_https==="ok"?"موفق":d.tcp_https==="degraded"?
          "ناموفق/نیاز به بررسی":"نامشخص")+
          " · تأخیر: "+amount(d.latency_ms,"ms")+
          " · تست‌های موفق: "+amount(d.passed_probes)+"/"+amount(d.total_probes));
        add(detail,"small","اتصالات فعال: "+amount(h.active_connections)+
          " · اتصالات تجمعی: "+amount(h.total_connections)+
          " · ورودی/خروجی HAProxy: "+amount(h.bytes_in!=null?h.bytes_in/1e9:null," GB")+" / "+
          amount(h.bytes_out!=null?h.bytes_out/1e9:null," GB"));
      }
      if(data.connection_share_backhaul_pct!==null&&data.connection_share_backhaul_pct!==undefined){
        add(item,"small","سهم اتصال Backhaul/Mieru: "+
          amount(data.connection_share_backhaul_pct,"٪")+" / "+
          amount(100-data.connection_share_backhaul_pct,"٪"));
      }
      if(data.byte_share_backhaul_pct!==null&&data.byte_share_backhaul_pct!==undefined){
        add(item,"small","سهم بایت Backhaul/Mieru: "+
          amount(data.byte_share_backhaul_pct,"٪")+" / "+
          amount(100-data.byte_share_backhaul_pct,"٪"));
      }
      const spark=add(item,"div",null);
      if(item.open)get("/control-room/v11/samples?server="+encodeURIComponent(sid))
         .then(res=>sparkline(spark,res.samples||[])).catch(()=>{});
      item.addEventListener("toggle",()=>{
         if(item.open)get("/control-room/v11/samples?server="+encodeURIComponent(sid))
           .then(res=>sparkline(spark,res.samples||[])).catch(()=>{});
      });
   }
 }
 async function load(){
   try{
     const [status,history]=await Promise.all([
       get("/control-room/v11/status"),get("/control-room/v11/events")]);
     draw(status.servers||{});
     const list=by("tv11-events");list.replaceChildren();
     for(const x of (history.events||[]).slice(0,20)){
       const li=add(list,"li",null);
       li.textContent=time(x.at)+" · "+(labels[x.server]||x.server)+" · "+
          ({degraded:"اختلال یک مسیر",both_unavailable:"اختلال دو مسیر",
          healthy:"بازیابی مسیرها",stale:"اطلاعات قدیمی",
          counter_reset:"ریست شمارنده HAProxy"}[x.kind]||"رویداد")+
          (x.lane?" · "+x.lane:"");
     }
     if(!list.children.length)add(list,"li","رویدادی ثبت نشده است");
   }catch(e){
     by("tv11-last").textContent="دریافت اطلاعات مانیتورینگ ناموفق؛ وضعیت سرورها نامشخص است";
   }
 }
 by("tv11-refresh").addEventListener("click",load);
 load();setInterval(load,30000);
})();
</script>
'''
_TV11_TEMPLATE=_TV11_TEMPLATE.replace("{% block content %}",
                                      "{% block content %}\n"+_TV11_CSS,1)
_TV11_TEMPLATE=_TV11_TEMPLATE.replace(_TV11_ANCHOR,_TV11_HTML+_TV11_ANCHOR,1)
pos=_TV11_TEMPLATE.rfind("{% endblock %}")
if pos<0:
    raise RuntimeError("Control Room endblock missing")
_TV11_TEMPLATE=_TV11_TEMPLATE[:pos]+_TV11_JS+"\n"+_TV11_TEMPLATE[pos:]
_tv11_Jinja().parse(_TV11_TEMPLATE)
TEMPLATES["control_room.html"]=_TV11_TEMPLATE
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)
