# HESAB_DUAL_PASSIVE_QUALITY_V1
# Read-only Control Room add-on. No active network test or remote command.
import json as _pq_json
import time as _pq_time
from pathlib import Path as _pq_Path
from fastapi import Request as _pq_Request
from fastapi.responses import JSONResponse as _pq_JSON
from jinja2 import Environment as _pq_Jinja

_PQ_PATH=_pq_Path("/srv/maya-live/dual_quality_v1/status.json")
_PQ_NAMES=("maya1","maya-s3","maya4")
_PQ_ROLES=("backhaul","mieru")
_PQ_AGE=4500

def _pq_endpoint(request:_pq_Request):
    if not _dh1_auth(request):
        return _pq_JSON({"ok":False},status_code=403)
    try:
        if not _PQ_PATH.is_file() or not 0<_PQ_PATH.stat().st_size<=240000:
            raise OSError("no passive snapshot")
        data=_pq_json.loads(_PQ_PATH.read_text(encoding="utf8"))
        if data.get("format")!="HESAB_DUAL_PASSIVE_QUALITY_V1":
            raise ValueError("format")
        at=data.get("source_at")
        if type(at) is not int or not -60<=_pq_time.time()-at<=30*86400:
            raise ValueError("invalid timestamp")
        if _pq_time.time()-at>_PQ_AGE:
            for server in data.get("servers",{}).values():
                if not isinstance(server,dict):continue
                server["state"]="stale"
                for path in server.get("paths",{}).values():
                    if isinstance(path,dict):
                        path["health"]="stale"
                        path["quality"]={"state":"stale","confidence":"none",
                                         "reason":"source_snapshot_older_than_75_min"}
                        path["latest_counters"]=None
                        path["last_quality_evaluated_at"]=None
            data["source_stale"]=True
            data["alerts"]=[]
        # Internal root-generated file, but avoid leaking unbounded/injected content.
        if (not isinstance(data.get("servers"),dict)
            or set(data["servers"])!=set(_PQ_NAMES)
            or not isinstance(data.get("alerts"),list)
            or len(data["alerts"])>12):
            raise ValueError("invalid server layout")
        for sid in _PQ_NAMES:
            paths=data["servers"][sid].get("paths",{})
            if not isinstance(paths,dict) or set(paths)!=set(_PQ_ROLES):
                raise ValueError("invalid path layout")
            for role in _PQ_ROLES:
                if not isinstance(paths[role].get("trend"),list) or len(paths[role]["trend"])>48:
                    raise ValueError("invalid trend")
        return _pq_JSON({"ok":True,"report":data},
                      headers={"Cache-Control":"private, no-store"})
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,AttributeError):
        return _pq_JSON({"ok":True,"report":None},
                      headers={"Cache-Control":"private, no-store"})

if any(getattr(r,"path",None)=="/control-room/dual-quality/status"
       for r in app.router.routes):
    raise RuntimeError("Passive quality status endpoint duplicated")
app.add_api_route("/control-room/dual-quality/status",_pq_endpoint,methods=["GET"])

_PQ_HTML=r'''
<style id="pq-css">
#c2-root #pq-root{direction:rtl;margin:16px 0 22px}
#c2-root #pq-root h2{font-size:15px!important;margin:0 0 8px;color:#eff1ff}
#c2-root .pq-note{color:#adb8dc;font-size:11px;margin:0 0 12px}
#c2-root .pq-server-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:11px}
#c2-root .pq-server{min-width:0}
#c2-root .pq-server h3{color:#e9ebff;font-size:12px;margin:0 0 7px}
#c2-root .pq-route{background:#171a34;border:1px solid #343d69;
  border-radius:13px;padding:12px;margin-bottom:9px;min-width:0}
#c2-root .pq-row{display:flex;align-items:center;justify-content:space-between;
  flex-wrap:wrap;gap:5px;margin-bottom:8px}
#c2-root .pq-route strong{font-size:12px}
#c2-root .pq-tag{border:1px solid #53648b;border-radius:7px;padding:3px 6px;
  font-size:10px;color:#dfe6ff}
#c2-root .pq-tag.good{color:#8ee0aa;border-color:#558969}
#c2-root .pq-tag.bad{color:#ffa4ac;border-color:#87525c}
#c2-root .pq-tag.unknown{color:#f6d4a3;border-color:#8d7755}
#c2-root .pq-metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));
  gap:5px}
#c2-root .pq-metric{padding:7px;border:1px solid #ffffff14;border-radius:8px;
  background:#ffffff05;min-width:0}
#c2-root .pq-metric small{font-size:9px;color:#a7afd4;display:block;margin-bottom:4px}
#c2-root .pq-metric span{font-size:10px;overflow-wrap:anywhere;direction:auto}
#c2-root .pq-chart{display:flex;align-items:end;gap:3px;height:30px;margin-top:8px;
 border-bottom:1px solid #ffffff22}
#c2-root .pq-bar{background:#8777e9;min-width:3px;flex:1;max-width:12px;
 border-radius:3px 3px 0 0}
#c2-root .pq-alerts{margin:10px 0;padding:10px;border:1px solid #56567b;
 border-radius:11px;font-size:11px;color:#ced4e8}
#c2-root .pq-foot{font-size:10px;color:#adb6d5;margin-top:7px}
@media (max-width:950px) {
 #c2-root .pq-server-grid{grid-template-columns:1fr}
}
</style>
<section id="pq-root" aria-label="تحلیل غیرفعال کیفیت انتقال">
  <h2>کیفیت انتقال داده · مستقل از Health Check</h2>
  <p class="pq-note">تحلیل غیرفعال Snapshotهای حساب · هیچ دانلود آزمایشی اجرا نمی‌شود ·
  سرعت انتقال فقط با شمارنده‌های معتبر قابل محاسبه است</p>
  <div id="pq-cards" class="pq-server-grid"></div>
  <div id="pq-alerts" class="pq-alerts" aria-live="polite">در حال بررسی شواهد کیفیت...</div>
</section>
'''
_PQ_JS=r'''
<script id="pq-js">
(function(){
"use strict";
if(window.__HESAB_PASSIVE_DUAL_QUALITY_V1)return;
window.__HESAB_PASSIVE_DUAL_QUALITY_V1=true;
const root=document.getElementById("pq-cards");
const alerts=document.getElementById("pq-alerts");
if(!root||!alerts)return;
const names={"maya1":"مایا ۱","maya-s3":"مایا ۳","maya4":"مایا ۴"};
const csrf="{{ ctrl_csrf }}";
function el(parent,tag,value,cls){
 const node=document.createElement(tag);
 if(cls)node.className=cls;
 if(value!==null&&value!==undefined)node.textContent=String(value);
 parent.appendChild(node);return node;
}
const nfmt=n=>typeof n==="number"&&Number.isFinite(n)?
 n.toLocaleString("fa-IR"):"—";
const byte=n=>typeof n==="number"&&Number.isFinite(n)?
 nfmt(Math.round(n/1024))+" KiB":"—";
function qualitative(q){
 const kind=q?.state||"not_measured";
 if(kind==="suspected_degradation")return ["افت انتقال مشکوک","unknown"];
 if(kind==="confirmed_transfer_test_failure")return ["اختلال تأییدشده با تست","bad"];
 if(kind==="normal_by_observed_counters")return ["طبیعی طبق شواهد محدود","good"];
 if(kind==="path_down")return ["اتصال قطع","bad"];
 if(kind==="stale")return ["اطلاعات قدیمی","unknown"];
 if(kind==="inconclusive")return ["شواهد ناکافی","unknown"];
 return ["کیفیت انتقال اندازه‌گیری نشده","unknown"];
}
function metric(parent,title,value){
 const item=el(parent,"div",null,"pq-metric");
 el(item,"small",title);
 el(item,"span",value);
}
function showTrend(parent,points){
 const good=Array.isArray(points)?points.filter(p=>Number.isFinite(p.bytes_out_per_s)): [];
 if(good.length<2){
  el(parent,"div","روند نرخ انتقال: داده معتبر موجود نیست","pq-foot");return;
 }
 const bar=el(parent,"div",null,"pq-chart");
 const max=Math.max(...good.map(p=>p.bytes_out_per_s),1);
 for(const point of good.slice(-36)){
  const unit=el(bar,"span",null,"pq-bar");
  unit.style.height=(Math.max(3,Math.round(30*point.bytes_out_per_s/max)))+"px";
  unit.title=nfmt(Math.round(point.bytes_out_per_s))+" B/s";
 }
}
function draw(report){
 root.replaceChildren();
 const stale=!report||report.source_stale===true;
 for(const sid of ["maya1","maya-s3","maya4"]){
  const server=report?.servers?.[sid]||{};
  const block=el(root,"div",null,"pq-server");
  el(block,"h3",names[sid]);
  for(const role of ["backhaul","mieru"]){
   const path=server.paths?.[role]||{};
   const card=el(block,"div",null,"pq-route");
   const top=el(card,"div",null,"pq-row");
   el(top,"strong",role==="backhaul"?"Backhaul":"Mieru");
   const conn=stale?"نامشخص":path.health==="healthy"?"اتصال سالم":
    path.health==="down"?"اتصال قطع":"اتصال نامشخص";
   el(top,"span",conn,"pq-tag "+(path.health==="healthy"&&!stale?"good":path.health==="down"?"bad":"unknown"));
   const [qtitle,qclass]=qualitative(stale?{state:"stale"}:path.quality);
   el(card,"div",qtitle,"pq-tag "+qclass);
   const metrics=el(card,"div",null,"pq-metrics");
   const c=stale?null:path.latest_counters;
   metric(metrics,"IP خارجی",!stale&&path.ip?path.ip:"—");
   metric(metrics,"HTTPS",!stale&&Number.isFinite(path.https_passed)&&Number.isFinite(path.https_total)?
      nfmt(path.https_passed)+"/"+nfmt(path.https_total):"—");
   metric(metrics,"میانگین پاسخ HTTPS",!stale?nfmt(path.https_avg_ms)+" ms":"—");
   metric(metrics,"اتصال‌های فعال",c?nfmt(c.active_connections):"—");
   metric(metrics,"اتصال‌های جدید در بازه",c?nfmt(c.new_connections):"—");
   metric(metrics,"داده ورودی HAProxy در بازه",c?byte(c.bytes_in_delta):"—");
   metric(metrics,"داده خروجی HAProxy در بازه",c?byte(c.bytes_out_delta):"—");
   metric(metrics,"نرخ داده خروجی از دید HAProxy",c?nfmt(c.bytes_out_per_s)+" B/s":"—");
   metric(metrics,"خطاهای ثبت‌شده در بازه",c?nfmt(c.connection_errors_delta+c.response_errors_delta):"—");
   const test=stale?null:path.last_transfer_test;
   el(card,"div",test?"آخرین تست دانلود: "+test.state:"آخرین تست دانلود معتبر: انجام نشده","pq-foot");
   showTrend(card,stale?[]:path.trend);
   el(card,"div","اطمینان ارزیابی: "+(stale?"—":
       path.quality?.confidence==="medium"?"متوسط":
       path.quality?.confidence==="limited"?"محدود":
       path.quality?.confidence==="low"?"پایین":"ناموجود"),"pq-foot");
  }
 }
 alerts.replaceChildren();
 el(alerts,"strong","هشدارهای کیفیت");
 if(stale){
  el(alerts,"div","گزارش غیرفعال موجود نیست یا قدیمی است؛ ارزیابی کیفیت ممکن نیست.");
 }else if(Array.isArray(report.alerts)&&report.alerts.length){
  for(const a of report.alerts.slice(0,12))
    el(alerts,"div",(names[a.server]||a.server)+" · "+a.role+
      " — افت انتقال مشکوک؛ برای تأیید به تست دانلود مستقل نیاز است");
 }else{
  el(alerts,"div","شواهد کافی برای هشدار ثبت نشده است؛ این به‌معنی تأیید سلامت انتقال نیست.");
 }
 const ts=report?.source_at?new Date(report.source_at*1000).toLocaleString("fa-IR",
   {timeZone:"Asia/Tehran"}):"—";
 el(alerts,"div","آخرین Snapshot اتصال: "+ts+" · آزمایش فعال انتقال انجام نشده است","pq-foot");
}
async function refresh(){
 try{
  const r=await fetch("/control-room/dual-quality/status",{
    credentials:"same-origin",cache:"no-store",
    headers:{"X-Control-CSRF":csrf}});
  if(!r.ok)throw Error("HTTP");
  const body=await r.json();
  if(!body.ok)throw Error("payload");
  draw(body.report);
 }catch(_){draw(null);}
}
draw(null);
refresh();
setInterval(refresh,30000);
window.__HESAB_PASSIVE_QUALITY_REFRESH_NOW=refresh;
})();
</script>
'''
_PQ_TEMPLATE=TEMPLATES.get("control_room.html","")
_PQ_ANCHOR='<div id="dh1-grid" class="dh1-grid"></div>\n</section>'
if (_PQ_TEMPLATE.count(_PQ_ANCHOR)!=1 or "t10-compact-css" not in _PQ_TEMPLATE
    or 'id="dh1-script"' not in _PQ_TEMPLATE
    or 'id="dm2-refresh"' not in _PQ_TEMPLATE):
    raise RuntimeError("Quality add-on requires current Dual V1 + manual refresh V2")
if 'id="pq-root"' in _PQ_TEMPLATE:
    raise RuntimeError("Passive quality UI already installed")
_PQ_TEMPLATE=_PQ_TEMPLATE.replace(_PQ_ANCHOR,_PQ_ANCHOR+_PQ_HTML+_PQ_JS,1)
if "{#" in _PQ_TEMPLATE:
    raise RuntimeError("Unexpected Jinja delimiter")
_pq_Jinja().parse(_PQ_TEMPLATE)
TEMPLATES["control_room.html"]=_PQ_TEMPLATE
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)
