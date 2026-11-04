# HESAB_CONTROL_ROOM_ONE_CLICK_STATUS_V1
# Purely presentational: reuse existing read-only Dual V1 and passive-quality API.
# Does not create a new shell/probe/SSH route or alter any tunnel config.
from jinja2 import Environment as _ocs_Jinja

_OCS_BASE = TEMPLATES.get("control_room.html","")
_OCS_ANCHOR = '<div id="c2-cards" class="c2-cards"></div>'
if (_OCS_BASE.count(_OCS_ANCHOR) != 1 or
    _OCS_BASE.count('id="dh1-root"') != 1 or
    _OCS_BASE.count('id="pq-root"') != 1 or
    _OCS_BASE.count('id="dm2-refresh"') != 1 or
    "t10-compact-css" not in _OCS_BASE):
    raise RuntimeError("Expected installed V10 + Dual V1 + V2 + passive quality UI")
if 'id="ocs-root"' in _OCS_BASE:
    raise RuntimeError("One-click status UI already installed")

_OCS_UI = r'''
<style id="ocs-css">
/* Hide legacy verbose sections; keep all underlying routes and collectors. */
#c2-root #dh1-root, #c2-root #pq-root {display:none!important}
#c2-root #ocs-root{direction:rtl;margin:15px 0 16px;border:1px solid #555085;
 background:#14162e;border-radius:15px;padding:14px 16px;color:#eeebff}
#c2-root .ocs-head{display:flex;gap:10px;align-items:center;
 justify-content:space-between;flex-wrap:wrap}
#c2-root .ocs-head h2{font-size:15px!important;margin:0!important;font-weight:800}
#c2-root #ocs-check{font:inherit;background:#3e3585;border:1px solid #7f6add;
 color:white;padding:10px 15px;font-weight:800;border-radius:10px;cursor:pointer;font-size:12px}
#c2-root #ocs-check:disabled{opacity:.6;cursor:wait}
#c2-root .ocs-status{margin-top:12px;font-size:12px;font-weight:800;
 border-radius:10px;padding:10px 12px;background:#202244;color:#c6cbe7}
#c2-root .ocs-status.ok{background:#17342e;color:#a4eed0}
#c2-root .ocs-status.warning{background:#3c2d23;color:#ffcd91}
#c2-root .ocs-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));
 gap:8px;margin-top:10px}
#c2-root .ocs-server{border:1px solid #373a67;border-radius:10px;
 background:#1a1d3a;padding:11px 12px;min-width:0}
#c2-root .ocs-name{font-weight:800;font-size:12px;margin-bottom:8px}
#c2-root .ocs-line{display:flex;justify-content:space-between;gap:8px;
 align-items:center;padding:5px 0;border-top:1px solid #ffffff13;font-size:11px}
#c2-root .ocs-pill{border:1px solid #6b7398;border-radius:7px;
 color:#d4d9f1;padding:3px 7px;font-size:11px;white-space:nowrap}
#c2-root .ocs-pill.ok{color:#98e7b9;border-color:#4f9e79}
#c2-root .ocs-pill.warning{color:#ffcb92;border-color:#a97447}
#c2-root .ocs-foot{color:#b5bbd7;font-size:10px;margin-top:9px}
@media (max-width:900px){
 #c2-root .ocs-grid{grid-template-columns:1fr}
}
</style>
<section id="ocs-root" aria-label="بررسی ساده وضعیت تونل‌های VPN">
 <div class="ocs-head">
  <h2>وضعیت تونل‌های VPN</h2>
  <button id="ocs-check" type="button">بررسی وضعیت</button>
 </div>
 <div id="ocs-status" class="ocs-status" role="status" aria-live="polite">برای بررسی، روی دکمه بزن.</div>
 <div id="ocs-grid" class="ocs-grid"></div>
 <div id="ocs-foot" class="ocs-foot">این بررسی، اتصال HTTPS مسیرها را می‌سنجد؛ سلامت سرعت انتقال بدون شواهد معتبر قابل تأیید نیست.</div>
</section>
<script id="ocs-js">
(function(){
"use strict";
if(window.__HESAB_ONE_CLICK_STATUS_V1)return;
window.__HESAB_ONE_CLICK_STATUS_V1=true;
const btn=document.getElementById("ocs-check");
const box=document.getElementById("ocs-status");
const grid=document.getElementById("ocs-grid");
const foot=document.getElementById("ocs-foot");
if(!btn||!box||!grid||!foot)return;
const csrf="{{ ctrl_csrf }}";
const ids=["maya1","maya-s3","maya4"];
const names={"maya1":"مایا ۱","maya-s3":"مایا ۳","maya4":"مایا ۴"};
const roles=["backhaul","mieru"];
const sleep=(ms)=>new Promise(resolve=>setTimeout(resolve,ms));
const opts={credentials:"same-origin",cache:"no-store",
 headers:{"X-Control-CSRF":csrf}};
function el(parent,tag,value,cls){
 const node=document.createElement(tag);
 if(cls)node.className=cls;
 if(value!=null)node.textContent=String(value);
 parent.appendChild(node);
 return node;
}
function state(parent,message,kind){
 parent.textContent=message;
 parent.className="ocs-status"+(kind?" "+kind:"");
}
async function get(url,config){
 const reply=await fetch(url,config||opts);
 if(!reply.ok)throw Error("دریافت اطلاعات ناموفق بود");
 const data=await reply.json();
 if(!data.ok)throw Error("اطلاعات معتبر نیست");
 return data;
}
function render(dual,quality){
 const qreport=quality&&quality.source_stale!==true?quality:null;
 grid.replaceChildren();
 let allConnectivityHealthy=true;
 let anythingSuspicious=false;
 let qualityMeasured=0;
 for(const id of ids){
  const s=dual?.servers?.[id]||{};
  const qs=qreport?.servers?.[id]||{};
  const card=el(grid,"div",null,"ocs-server");
  el(card,"div",names[id],"ocs-name");
  for(const role of roles){
   const raw=s.paths?.[role]||{};
   const qq=qs.paths?.[role]||{};
   const sourceCurrent=s.state==="ok"&&s.age_s>=0&&s.age_s<=4500;
   const connectivityGood=sourceCurrent&&raw.state==="healthy";
   const qkind=qq.quality?.state;
   const qMatches=Boolean(qreport&&sourceCurrent&&
       Number.isFinite(qreport.source_at)&&
       Math.abs(qreport.source_at-(Date.now()/1000-s.age_s))<=95);
   const qualityWarn=qMatches&&(
       qkind==="suspected_degradation"||
       qkind==="confirmed_transfer_test_failure"||
       qkind==="path_down");
   const qualityOK=qMatches&&qkind==="normal_by_observed_counters";
   let label="سالم";
   let kind="ok";
   if(!connectivityGood){
     label="هشدار اتصال";
     kind="warning";allConnectivityHealthy=false;anythingSuspicious=true;
   }else if(qualityWarn){
     label="هشدار کیفیت";
     kind="warning";anythingSuspicious=true;
   }
   if(qualityOK)qualityMeasured++;
   const row=el(card,"div",null,"ocs-line");
   el(row,"span",role==="backhaul"?"Backhaul":"Mieru");
   el(row,"span",label,"ocs-pill "+kind);
  }
 }
 if(anythingSuspicious){
  state(box,"هشدار: یک یا چند مسیر نیاز به بررسی دارند.","warning");
 }else if(allConnectivityHealthy){
  state(box,"اتصال هر شش مسیر سالم است.","ok");
 }else{
  state(box,"وضعیت قابل تأیید نیست.","warning");
 }
 if(qualityMeasured===6){
  foot.textContent="کیفیت انتقال فقط طبق شواهد غیرفعال موجود ارزیابی شده؛ تست دانلود جدید اجرا نشده است.";
 }else{
  foot.textContent="هشدار مهم: کیفیت واقعی انتقال داده در "+(6-qualityMeasured)+
   " مسیر اندازه‌گیری نشده است. Healthy بودن HTTPS به‌تنهایی سلامت سرعت را اثبات نمی‌کند.";
 }
}
btn.addEventListener("click",async()=>{
 if(btn.disabled)return;
 btn.disabled=true;
 btn.textContent="در حال بررسی...";
 state(box,"در حال خواندن وضعیت تازه از سه سرور...","");
 grid.replaceChildren();
 try{
  const reply=await fetch("/control-room/dual-hourly/refresh",
    {...opts,method:"POST"});
  const trigger=await reply.json();
  if(!reply.ok||!trigger.ok||!trigger.accepted){
    throw Error(reply.status===429?"درخواست‌های پشت‌سرهم؛ کمی بعد دوباره امتحان کن":
                "آغاز بررسی ناموفق بود");
  }
  const before=trigger.previous_snapshot_mtime_ms;
  let updated=false;
  for(let n=0;n<45;n++){
   await sleep(2000);
   const meta=await get("/control-room/dual-hourly/refresh-meta");
   if(meta.snapshot_mtime_ms>before){updated=true;break;}
  }
  if(!updated)throw Error("گزارش تازه دریافت نشد.");
  const d=await get("/control-room/dual-hourly/status");
  let q=null;
  try{
    const result=await get("/control-room/dual-quality/status");
    q=result.report;
  }catch(_){}
  render(d,q);
 }catch(error){
  grid.replaceChildren();
  state(box,"هشدار: "+(error.message||"امکان تأیید وضعیت نیست."),"warning");
  foot.textContent="در این حالت نتیجه‌ای به‌عنوان سالم تأیید نمی‌شود.";
 }finally{
  btn.disabled=false;btn.textContent="بررسی وضعیت";
 }
});
})();
</script>
'''
_OCS_TEMPLATE=_OCS_BASE.replace(_OCS_ANCHOR,_OCS_ANCHOR+_OCS_UI,1)
if "{#" in _OCS_TEMPLATE:
    raise RuntimeError("Unexpected Jinja syntax")
_ocs_Jinja().parse(_OCS_TEMPLATE)
TEMPLATES["control_room.html"]=_OCS_TEMPLATE
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)
