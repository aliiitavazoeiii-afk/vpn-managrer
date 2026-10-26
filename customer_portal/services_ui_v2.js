/* HESAB_SERVICES_SPEEDTEST_V2 — browser-only, user initiated */
(function(){
"use strict";
const byId=(id)=>document.getElementById(id);
const panel=byId("sv-speed-panel"), open=byId("sv-speed-open"), close=byId("sv-speed-close");
const button=byId("sv-speed-start"), msg=byId("sv-speed-message"), results=byId("sv-speed-results");
if(!panel||!open||!close||!button||!msg||!results)return;
open.addEventListener("click",()=>{panel.hidden=false;panel.scrollIntoView({behavior:"smooth",block:"start"});});
close.addEventListener("click",()=>{panel.hidden=true;open.focus();});
const format=(value,denom,unit)=>Number.isFinite(value)&&value>=0 ? (value/denom).toFixed(1)+" "+unit : "—";
let report="";
button.addEventListener("click",async()=>{
 if(button.disabled)return;
 button.disabled=true;results.hidden=true;report="";
 msg.textContent="در حال آماده‌سازی تست سرعت…";
 try{
  const {default:SpeedTest}=await import("https://esm.sh/@cloudflare/speedtest@1.15.0");
  const test=new SpeedTest({autoStart:false,measurements:[
    {type:"latency",numPackets:12},
    {type:"download",bytes:100000,count:6},
    {type:"download",bytes:1000000,count:5},
    {type:"download",bytes:10000000,count:2},
    {type:"upload",bytes:100000,count:5},
    {type:"upload",bytes:1000000,count:4},
    {type:"upload",bytes:10000000,count:2}
  ]});
  let finished=false;
  test.onError=(error)=>{
   if(finished)return;
   msg.textContent="اندازه‌گیری با خطا مواجه شد. دسترسی به Cloudflare و VPN را بررسی کنید.";
   button.disabled=false;
   console.warn("Cloudflare speed test failed:",String(error).slice(0,140));
  };
  test.onFinish=(measurement)=>{
   finished=true;
   const down=measurement.getDownloadBandwidth();
   const up=measurement.getUploadBandwidth();
   const ping=measurement.getUnloadedLatency();
   const jitter=measurement.getUnloadedJitter();
   byId("sv-download").textContent=format(down,1000000,"Mbps");
   byId("sv-upload").textContent=format(up,1000000,"Mbps");
   byId("sv-latency").textContent=format(ping,1,"ms");
   byId("sv-jitter").textContent=format(jitter,1,"ms");
   const vpn=byId("sv-vpn-on").checked?"روشن (اعلام کاربر)":"خاموش (اعلام کاربر)";
   report=[
    "گزارش تست سرعت Cloudflare",
    "زمان: "+new Date().toLocaleString("fa-IR"),
    "وضعیت VPN: "+vpn,
    "دانلود: "+format(down,1000000,"Mbps"),
    "آپلود: "+format(up,1000000,"Mbps"),
    "پینگ: "+format(ping,1,"ms"),
    "Jitter: "+format(jitter,1,"ms"),
    "تست از مرورگر مشترک تا شبکه Cloudflare"
   ].join("\n");
   results.hidden=false;
   msg.textContent="تست تکمیل شد. می‌توانید گزارش را برای پشتیبانی کپی کنید.";
   button.disabled=false;
  };
  msg.textContent="در حال تست سرعت اینترنت… اتصال خود را تغییر ندهید.";
  test.play();
 }catch(err){
  msg.textContent="موتور Cloudflare در این مرورگر یا شبکه بارگیری نشد. در مرورگر دیگری امتحان کنید.";
  console.warn("Cloudflare speed test setup:",String(err).slice(0,140));
  button.disabled=false;
 }
});
byId("sv-copy-report").addEventListener("click",async()=>{
 if(!report)return;
 try{
  await navigator.clipboard.writeText(report);
  msg.textContent="گزارش کپی شد؛ می‌توانید آن را در واتساپ برای پشتیبانی ارسال کنید.";
 }catch(err){
  msg.textContent="کپی خودکار در این مرورگر مجاز نیست. نتیجه را به‌صورت دستی ارسال کنید.";
 }
});
})();
