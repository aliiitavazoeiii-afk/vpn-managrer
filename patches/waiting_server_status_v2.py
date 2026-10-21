# HESAB_WAITING_SERVER_STATUS_V2
# Layout-only /followups update: status button alongside "renew SMS / pay / restore",
# compact search and connection-state filters. Same local status API; zero Shahan
# calls, zero extra XUI calls, zero billing/account mutations.
_WSV2_STYLE=r'''
<style>
/* This patch is scoped to the waiting-payment page only. */
.waiting-v2-toolbar{display:flex;align-items:center;justify-content:space-between;gap:11px;flex-wrap:wrap;margin:0 0 12px}
.waiting-v2-filters{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.waiting-v2-filters button{
  border:1px solid rgba(143,151,191,.23);background:rgba(107,91,169,.085);
  color:#bac2dc;border-radius:10px;padding:8px 13px;min-height:37px;
  font-family:inherit;font-size:12px;font-weight:750;line-height:1.25;cursor:pointer;white-space:nowrap
}
.waiting-v2-filters button[aria-pressed="true"]{
  color:#e9e4ff;border-color:rgba(155,127,245,.64);
  background:rgba(126,93,223,.25);box-shadow:inset 0 0 0 1px rgba(156,127,255,.10)
}
.waiting-v2-filters .waiting-v2-filter-count{font-size:10px;opacity:.76;margin-inline-start:3px}
.waiting-v2-toolbar>.waiting-searchbar{
  width:245px;max-width:100%;flex:0 0 245px;min-width:0;height:38px;
  margin:0;grid-template-columns:21px minmax(0,1fr) auto;gap:5px;padding:0 10px
}
.waiting-v2-toolbar>.waiting-searchbar input{min-width:0;font-size:12px}
.waiting-v2-toolbar>.waiting-searchbar small{font-size:10px}
.waiting-v2-server-holder{position:relative;flex:0 0 auto;min-width:0}
.waiting-v2-server-btn{
  display:inline-flex;align-items:center;justify-content:center;gap:6px;
  max-width:220px;min-height:38px;padding:0 11px;white-space:nowrap;
  border:1px solid rgba(151,134,222,.38);border-radius:10px;
  background:rgba(116,95,181,.12);color:#dcd5f7;
  font-family:inherit;font-size:11px;font-weight:750;line-height:1.35;cursor:pointer
}
.waiting-v2-server-btn:hover,.waiting-v2-server-btn[aria-expanded="true"]{
  border-color:rgba(183,161,255,.67);background:rgba(116,95,181,.22)
}
.waiting-v2-server-btn-label{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:185px}
.waiting-v2-server-dot{width:7px;height:7px;flex:none;background:#8790a3;border-radius:50%}
.waiting-v2-server-btn[data-status="active"] .waiting-v2-server-dot{background:#55cfa4}
.waiting-v2-server-btn[data-status="blocked"] .waiting-v2-server-dot{background:#f18b9c}
.waiting-v2-server-btn[data-status="mixed"] .waiting-v2-server-dot{background:#e6bc77}
.waiting-v2-status-pop{
  position:fixed;z-index:9999;direction:rtl;text-align:right;
  width:min(380px,calc(100vw - 24px));max-height:min(460px,65vh);overflow:auto;
  border:1px solid rgba(154,139,225,.39);border-radius:15px;
  background:#15182f;color:#f0effa;padding:13px;
  box-shadow:0 18px 55px rgba(0,0,0,.53);font:inherit
}
.waiting-v2-status-pop h3{margin:0 0 9px;font-size:13px;color:#e9e5ff;font-weight:850}
.waiting-v2-status-pop .waiting-v2-account{font-weight:800;color:#c7c5e0;font-size:11px;margin:10px 0 4px}
.waiting-v2-status-pop .waiting-v2-access{
  display:flex;align-items:center;justify-content:space-between;gap:10px;
  border:1px solid rgba(155,156,203,.12);border-radius:9px;padding:8px 9px;margin:4px 0;
  font-size:11px
}
.waiting-v2-status-pop .waiting-v2-access small{display:block;color:#959bb7;font-size:10px;margin-top:3px}
.waiting-v2-status-pop .waiting-v2-access strong{font-size:11px;white-space:nowrap}
.waiting-v2-status-pop .waiting-v2-active{color:#78ddb4}
.waiting-v2-status-pop .waiting-v2-blocked{color:#ffa1b0}
.waiting-v2-status-pop .waiting-v2-unknown{color:#a7b1c9}
.waiting-v2-status-pop .waiting-v2-reported{color:#e4c487}
.waiting-v2-status-pop .waiting-v2-hint{font-size:10px;color:#9298b1;line-height:1.6;margin:10px 0 0}
@media(max-width:700px){
 .waiting-v2-toolbar{align-items:stretch}
 .waiting-v2-toolbar>.waiting-searchbar{width:100%;flex:1 1 100%}
 .waiting-v2-filters{gap:5px}
 .waiting-v2-filters button{padding:7px 10px;font-size:11px}
 .waiting-v2-server-btn{max-width:190px}
}
</style>
'''
_WSV2_SCRIPT=r'''
<script>
(function(){
 "use strict";
 if(window.__hesabWaitingStatusV2)return;
 window.__hesabWaitingStatusV2=true;
 const list=document.querySelector(".waiting-list");
 const search=document.getElementById("waiting-search");
 const count=document.getElementById("waiting-search-count");
 const noResults=document.getElementById("waiting-no-results");
 const filters=[...document.querySelectorAll("[data-waiting-v2-filter]")];
 if(!list||!search||!filters.length)return;
 const labels={
   active:"فعال",blocked:"غیرفعال",unknown:"نامشخص",
   reported_active:"فعال (گزارش دستی)",reported_blocked:"غیرفعال (گزارش دستی)"
 };
 const knownActive=new Set(["active","reported_active"]);
 const knownBlocked=new Set(["blocked","reported_blocked"]);
 const fa=n=>String(n).replace(/\d/g,d=>"۰۱۲۳۴۵۶۷۸۹"[d]);
 const groups=()=>[...list.querySelectorAll("[data-waiting-group]")];
 let data=null,loadedAt=0,loading=false,filter="all";
 let popup=null,popupAnchor=null;
 const normalize=v=>String(v||"").toLowerCase().replaceAll("ي","ی").replaceAll("ك","ک").trim();
 function itemsFor(group){
   const statuses=data?.statuses||{};
   const rows=[];
   group.querySelectorAll("[data-wss-sid]").forEach(node=>{
     const sid=node.getAttribute("data-wss-sid");
     const account=node.querySelector(".waiting-identity a")?.textContent?.trim()||("#"+sid);
     const entries=Array.isArray(statuses[sid])?statuses[sid]:[];
     if(!entries.length){
       rows.push({account,server:"—",status:"unknown",detail:"برای این حساب وضعیت تأییدشده‌ای ثبت نشده"});
     }else entries.forEach(entry=>rows.push({...entry,account}));
   });
   if(!rows.length) rows.push({account:"—",server:"—",status:"unknown",detail:"داده‌ای موجود نیست"});
   return rows;
 }
 function countsFor(items){
   return {
     active:items.filter(x=>knownActive.has(x.status)).length,
     blocked:items.filter(x=>knownBlocked.has(x.status)).length,
     unknown:items.filter(x=>!knownActive.has(x.status)&&!knownBlocked.has(x.status)).length
   };
 }
 function overallFor(items){
   const n=countsFor(items);
   if(n.active&&n.blocked)return "mixed";
   if(n.active)return "active";
   if(n.blocked)return "blocked";
   return "unknown";
 }
 function closePopup(returnFocus=false){
   if(!popup)return;
   popup.remove();
   if(returnFocus&&popupAnchor&&popupAnchor.isConnected)popupAnchor.focus();
   popup=null;popupAnchor=null;
 }
 function add(tag,text,parent,cls){
   const el=document.createElement(tag);
   if(text!==undefined)el.textContent=String(text);
   if(cls)el.className=cls;
   if(parent)parent.appendChild(el);
   return el;
 }
 function paintButton(group,items){
   const btn=group.querySelector("[data-waiting-v2-status-btn]");
   if(!btn)return;
   const n=countsFor(items);
   const real=items.filter(x=>x.server!=="—");
   let label="وضعیت نامشخص";
   if(real.length===1){
      label=real[0].server+" · "+(labels[real[0].status]||"نامشخص");
   }else if(real.length>1){
      label="سرورها · "+(n.active?fa(n.active)+" فعال":"")+
         (n.active&&n.blocked?" / ":"")+
         (n.blocked?fa(n.blocked)+" غیرفعال":"")+
         (n.unknown?" / "+fa(n.unknown)+" نامشخص":"");
   }
   if(!label.trim()||label==="سرورها · ")label="وضعیت سرورها";
   btn.querySelector(".waiting-v2-server-btn-label").textContent=label;
   btn.dataset.status=overallFor(items);
   btn.title="نمایش دسترسی‌های ثبت‌شده روی سرورها (فعال یعنی مجاز، نه لزوماً آنلاین)";
 }
 function apply(){
   const term=normalize(search.value);
   const totals={all:0,active:0,blocked:0,unknown:0};
   let shown=0;
   for(const group of groups()){
     const items=itemsFor(group);
     const n=countsFor(items);
     paintButton(group,items);
     const termMatch=!term||normalize(group.dataset.search).includes(term)||
       items.some(x=>normalize([x.account,x.username,x.server].join(" ")).includes(term));
     if(termMatch){
       totals.all++;
       if(n.active)totals.active++;
       if(n.blocked)totals.blocked++;
       if(n.unknown)totals.unknown++;
     }
     const stateMatch=filter==="all"||!!n[filter];
     group.hidden=!(termMatch&&stateMatch);
     if(!group.hidden)shown++;
   }
   filters.forEach(btn=>{
     const key=btn.dataset.waitingV2Filter;
     btn.setAttribute("aria-pressed",String(filter===key));
     const n=btn.querySelector("[data-waiting-v2-count]");
     if(n)n.textContent=fa(totals[key]||0);
   });
   if(count)count.textContent=fa(shown)+" نتیجه";
   if(noResults)noResults.hidden=shown!==0;
 }
 function makePopup(group,btn){
   closePopup();
   popupAnchor=btn;
   popup=add("div",undefined,document.body,"waiting-v2-status-pop");
   popup.setAttribute("role","dialog");
   popup.setAttribute("aria-label","وضعیت اتصال حساب‌های این پرداخت‌کننده");
   add("h3","اتصال به سرورها",popup);
   const items=itemsFor(group);
   let lastAccount=null;
   items.forEach(x=>{
     if(x.account!==lastAccount){
       add("div",x.account,popup,"waiting-v2-account");
       lastAccount=x.account;
     }
     const line=add("div",undefined,popup,"waiting-v2-access");
     const left=add("div",undefined,line);
     add("b",x.server||"نامشخص",left);
     if(x.username)add("small",x.username,left);
     const state=add("strong",labels[x.status]||"نامشخص",line,
       knownActive.has(x.status)?"waiting-v2-active":
       knownBlocked.has(x.status)?"waiting-v2-blocked":"waiting-v2-unknown");
     if(x.source==="shahan_manual")state.className="waiting-v2-reported";
     line.title=x.detail||"";
   });
   add("p","فعال یعنی دسترسی مجاز است، نه لزوماً آنلاین. وضعیت شاهان از گزارش دستی است.",popup,"waiting-v2-hint");
   const rect=btn.getBoundingClientRect();
   const left=Math.max(12,Math.min(rect.left,window.innerWidth-popup.offsetWidth-12));
   let top=rect.bottom+7;
   if(top+popup.offsetHeight>window.innerHeight-10&&rect.top>popup.offsetHeight+10){
      top=rect.top-popup.offsetHeight-7;
   }
   popup.style.left=left+"px";
   popup.style.top=Math.max(10,top)+"px";
   btn.setAttribute("aria-expanded","true");
 }
 document.addEventListener("click",e=>{
   const btn=e.target.closest("[data-waiting-v2-status-btn]");
   if(btn){
     e.preventDefault();
     const group=btn.closest("[data-waiting-group]");
     if(popupAnchor===btn){popupAnchor.setAttribute("aria-expanded","false");closePopup(true);return;}
     if(popupAnchor)popupAnchor.setAttribute("aria-expanded","false");
     makePopup(group,btn);
     return;
   }
   if(popup&&!popup.contains(e.target)){
     if(popupAnchor)popupAnchor.setAttribute("aria-expanded","false");
     closePopup();
   }
 });
 document.addEventListener("keydown",e=>{
   if(e.key==="Escape"&&popup){
     if(popupAnchor)popupAnchor.setAttribute("aria-expanded","false");
     closePopup(true);
   }
 });
 window.addEventListener("scroll",()=>closePopup(),{passive:true});
 window.addEventListener("resize",()=>closePopup());
 filters.forEach(btn=>btn.addEventListener("click",()=>{
   filter=btn.dataset.waitingV2Filter;
   closePopup();
   apply();
 }));
 // The old waiting-live search owns a separate bubble listener; intercept to
 // combine status filters + search instead of letting it show hidden rows.
 search.addEventListener("input",e=>{
   e.stopImmediatePropagation();
   apply();
 },true);
 async function refresh(force=false){
   if(loading||document.hidden)return;
   if(!force&&data&&Date.now()-loadedAt<90000){apply();return;}
   loading=true;
   try{
     const res=await fetch("/followups/connection-status",{credentials:"same-origin",cache:"no-store"});
     if(!res.ok)throw Error("Status API unavailable");
     const incoming=await res.json();
     if(!incoming.ok||typeof incoming.statuses!=="object")throw Error("Malformed status response");
     data=incoming;
   }catch(_){
     // Unknown is safer than implying the user has been disconnected.
     data={statuses:{}};
   }finally{
     loadedAt=Date.now();loading=false;apply();
   }
 }
 const observer=new MutationObserver(()=>{
   closePopup();
   apply();
   refresh(true);
 });
 observer.observe(list,{childList:true});
 refresh(true);
 // Cached local sampler/report only; NO new calls to Shahan SSH or 3x-ui.
 setInterval(()=>refresh(false),90000);
})();
</script>
'''
_wsv2_tpl=TEMPLATES.get("followups.html","")
if not _wsv2_tpl or _wsv2_tpl.count('class="wss-summary"')!=1 or _wsv2_tpl.count('class="wss-child"')!=1:
    raise RuntimeError("Waiting V2 expected the earlier status labels; refusing to change unrelated templates")
if _wsv2_tpl.count(_WSS_STYLE)!=1 or _wsv2_tpl.count(_WSS_JS)!=1:
    raise RuntimeError("Waiting V2 could not find previous inline CSS/JS exactly")
# Remove the earlier status presentation and its observer/fetcher completely.
_wsv2_tpl=_wsv2_tpl.replace(_WSS_STYLE,"",1).replace(_WSS_JS,"",1)
_wsv2_tpl=_wsv2_tpl.replace(
  '<small>نام <span class="wss-summary" title=""></span></small>',
  '<small>نام</small>',1)
_wsv2_tpl=_wsv2_tpl.replace(
  '<span>انقضا {{ s.expiry_date|jdate }} <span class="wss-child"></span></span>',
  '<span>انقضا {{ s.expiry_date|jdate }}</span>',1)
_wsv2_anchor='<div class="waiting-head-pay waiting-pay-tools">'
if _wsv2_tpl.count(_wsv2_anchor)!=1:
    raise RuntimeError("Waiting V2 action toolbar changed")
_wsv2_button=r'''
        <div class="waiting-v2-server-holder">
          <button type="button" class="waiting-v2-server-btn" data-waiting-v2-status-btn
                  data-status="unknown" aria-expanded="false"
                  title="نمایش وضعیت اتصال به سرورها">
            <span class="waiting-v2-server-dot" aria-hidden="true"></span>
            <span class="waiting-v2-server-btn-label">وضعیت سرورها</span>
          </button>
        </div>
'''
_wsv2_tpl=_wsv2_tpl.replace(_wsv2_anchor,_wsv2_anchor+"\n"+_wsv2_button,1)
_wsv2_search='<div class="waiting-searchbar">'
if _wsv2_tpl.count(_wsv2_search)!=1:
    raise RuntimeError("Waiting V2 search container not unique")
_wsv2_filters=r'''
<div class="waiting-v2-toolbar">
  <div class="waiting-v2-filters" role="group" aria-label="فیلتر وضعیت اتصال">
    <button type="button" data-waiting-v2-filter="all" aria-pressed="true">همه <span data-waiting-v2-count></span></button>
    <button type="button" data-waiting-v2-filter="active" aria-pressed="false">فعال <span data-waiting-v2-count></span></button>
    <button type="button" data-waiting-v2-filter="blocked" aria-pressed="false">غیرفعال <span data-waiting-v2-count></span></button>
    <button type="button" data-waiting-v2-filter="unknown" aria-pressed="false">نامشخص <span data-waiting-v2-count></span></button>
  </div>
'''
_wsv2_tpl=_wsv2_tpl.replace(_wsv2_search,_wsv2_filters+_wsv2_search,1)
_wsv2_list='<div class="waiting-list">'
if _wsv2_tpl.count(_wsv2_list)!=1:
    raise RuntimeError("Waiting V2 list container not unique")
_wsv2_tpl=_wsv2_tpl.replace(_wsv2_list,'</div>\n'+_wsv2_list,1)
_wsv2_tpl=_wsv2_tpl.replace('{% block content %}','{% block content %}'+_WSV2_STYLE,1)
_wsv2_head,_wsv2_tail=_wsv2_tpl.rsplit('{% endblock %}',1)
_wsv2_tpl=_wsv2_head+_WSV2_SCRIPT+'\n{% endblock %}'+_wsv2_tail
TEMPLATES["followups.html"]=_wsv2_tpl
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)
