# HESAB_MOBILE_DASHBOARD_V12
# Presentation ONLY. Appended to the existing, mounted maya1_control.py
# after all current Control Room panels. Does not create routes or change
# accounting, VPN, X-UI, session, forms, requests, or server actions.
from jinja2 import Environment as _hm12_Jinja
import re as _hm12_re

_HM12_CSS = r'''
<style id="hm12-admin-mobile">
/* HESAB MOBILE V12 — admin: maintain desktop unchanged. */
@media (max-width: 860px) {
  html{font-size:16px!important;-webkit-text-size-adjust:100%}
  html,body{max-width:100%;margin:0;overflow-x:clip}
  body.hm12-ready{padding-top:env(safe-area-inset-top,0px)!important}
  body.hm12-ready .hm12-shell{display:block!important;grid-template-columns:minmax(0,1fr)!important;
    width:100%!important;max-width:100%!important;min-width:0!important}
  body.hm12-ready .main{width:100%!important;max-width:100%!important;min-width:0!important;
    box-sizing:border-box!important;margin:0!important;
    padding:calc(70px + env(safe-area-inset-top,0px)) 12px calc(25px + env(safe-area-inset-bottom,0px))!important}
  body.hm12-ready .sidebar{
    position:fixed!important;inset:0 0 0 auto!important;width:min(84vw,320px)!important;
    max-width:320px!important;height:100dvh!important;max-height:100dvh!important;
    z-index:10042!important;overflow-y:auto!important;overscroll-behavior:contain!important;
    box-sizing:border-box!important;padding:calc(16px + env(safe-area-inset-top,0px)) 14px
        calc(28px + env(safe-area-inset-bottom,0px))!important;
    margin:0!important;visibility:hidden!important;pointer-events:none!important;
    transform:translateX(104%)!important;transition:transform .23s ease,visibility .23s!important;
    box-shadow:-35px 0 90px #000a!important}
  body.hm12-ready.hm12-open .sidebar{transform:translateX(0)!important;
    visibility:visible!important;pointer-events:auto!important}
  body.hm12-ready .sidebar nav{display:flex!important;flex-direction:column!important;
    gap:5px!important;overflow:visible!important}
  body.hm12-ready .sidebar nav a{display:flex!important;min-height:48px!important;
    width:100%!important;max-width:100%!important;box-sizing:border-box!important;
    font-size:13px!important;justify-content:flex-start!important}
  body.hm12-ready.hm12-open{overflow:hidden!important;touch-action:auto}
  body.hm12-ready .hm12-top{
    position:fixed;top:0;right:0;left:0;z-index:10040;
    min-height:calc(61px + env(safe-area-inset-top,0px));
    display:flex;align-items:center;justify-content:space-between;gap:10px;
    box-sizing:border-box;padding:calc(8px + env(safe-area-inset-top,0px)) 12px 8px;
    background:rgba(11,13,37,.96);border-bottom:1px solid rgba(161,147,255,.17);
    box-shadow:0 12px 34px #0507196b;backdrop-filter:blur(16px)}
  body.hm12-ready .hm12-open-button{display:inline-flex;align-items:center;justify-content:center;
    width:46px;height:44px;flex:none;background:#272451;color:#fff;border-radius:13px;
    border:1px solid #5e5090;font-size:23px;cursor:pointer}
  body.hm12-ready .hm12-title{display:flex;align-items:center;gap:9px;min-width:0;
    margin-inline-end:auto;line-height:1.4}
  body.hm12-ready .hm12-mark{width:32px;height:32px;display:grid;place-items:center;
    flex:none;background:linear-gradient(145deg,#8059e9,#4359b6);border-radius:10px;
    color:white;font-weight:850}
  body.hm12-ready .hm12-copy{min-width:0}
  body.hm12-ready .hm12-copy b{display:block;font-size:13px;color:#faf9ff!important;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  body.hm12-ready .hm12-copy small{display:block;font-size:10px;color:#9ca6d2;
    overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
  body.hm12-ready .hm12-backdrop{position:fixed;inset:0;z-index:10041;
    background:rgba(0,0,12,.72);backdrop-filter:blur(4px);
    border:0;border-radius:0;width:100%;height:100dvh;cursor:pointer}
  body.hm12-ready .hm12-backdrop[hidden]{display:none!important}
  body.hm12-ready :is(.panel,.card,.kpi,.ref-panel,.ref-quick,.ref-profile-card,
   .ref-control-section,.ref-control-preview,.debt-group-v3,.waiting-group,.pay-row){
    box-sizing:border-box;max-width:100%;min-width:0}
  body.hm12-ready :is(.ref-dashboard,.ref-control-page,.core-dashboard,.ref-hero,
   .ref-control-hero,.ref-bottom-grid,.ref-triple,.ref-kpis,.ref-quick-grid){min-width:0;max-width:100%}
  body.hm12-ready :is(.ref-kpis,.ref-triple,.ref-bottom-grid,.ref-side-stack,
   .ref-server-grid,.ref-foreign-grid,.ref-control-server-grid,
   .ref-control-foreign-grid,.core-dashboard,.removed-summary){
    display:grid!important;grid-template-columns:minmax(0,1fr)!important;
    gap:12px!important}
  body.hm12-ready .ref-triple .ref-panel:last-child{grid-column:auto!important}
  body.hm12-ready .ref-quick-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important}
  body.hm12-ready .focus-quick-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important}
  body.hm12-ready .ref-hero,
  body.hm12-ready .ref-control-hero{min-height:0!important;padding:18px!important;
    border-radius:18px!important;gap:12px!important;align-items:center!important}
  body.hm12-ready :is(.ref-hero h1,.ref-control-hero h1){font-size:clamp(22px,5.7vw,30px)!important;line-height:1.45!important}
  body.hm12-ready .ref-hero p,body.hm12-ready .ref-control-hero p{
    font-size:12px!important;line-height:1.9!important}
  body.hm12-ready .ref-orb,body.hm12-ready .ref-control-pulse{display:none!important}
  body.hm12-ready .ref-kpi{min-height:90px!important;padding:15px!important}
  body.hm12-ready .ref-kpi strong{font-size:21px!important;white-space:normal!important;
    overflow-wrap:anywhere}
  body.hm12-ready :is(.ref-panel>header,.ref-section-head,.ref-quick header,
   .ref-profile-card header,.section-head,.topbar){
    min-width:0;max-width:100%;flex-wrap:wrap!important;gap:9px!important;
    height:auto!important}
  body.hm12-ready :is(.panel,.ref-panel,.ref-control-section){padding:15px!important}
  body.hm12-ready .ref-user-row:hover{transform:none!important}
  body.hm12-ready .ref-user-expand{opacity:1!important;max-height:none!important;
    overflow:visible!important;margin-top:5px!important}
  body.hm12-ready :is(.debt-summary-clean,.waiting-summary,.removed-row,
   .waiting-head,.debt-head-v3,.debt-service-v3,.waiting-service){
    grid-template-columns:minmax(0,1fr)!important;gap:10px!important}
  body.hm12-ready :is(.debt-head-v3,.waiting-head){padding:15px!important}
  body.hm12-ready :is(.service-actions,.waiting-actions,.removed-actions){
    display:flex!important;flex-wrap:wrap!important;gap:8px!important;
    width:100%!important;max-width:100%!important;grid-column:1/-1!important}
  body.hm12-ready :is(.debt-searchbar,.waiting-searchbar,.removed-search){
    min-width:0!important;max-width:100%!important;grid-template-columns:24px minmax(0,1fr)!important}
  body.hm12-ready :is(input,select,textarea){max-width:100%!important;box-sizing:border-box!important;
    font-size:16px!important;min-width:0}
  body.hm12-ready input[type="checkbox"],body.hm12-ready input[type="radio"]{min-width:auto!important}
  body.hm12-ready :is(button,.primary-btn,.collect-btn,.waiting-pay,[role="button"]){
    touch-action:manipulation}
  body.hm12-ready :is(.collect-btn,.waiting-pay,.group-pay-btn,.waiting-group-pay-btn,
   .c2-btn,.c3-detail-button){min-height:42px!important}
  body.hm12-ready form{max-width:100%;min-width:0}
  body.hm12-ready .hm12-table-scroll{overflow-x:auto!important;max-width:100%;
    -webkit-overflow-scrolling:touch;scrollbar-width:thin;border-radius:12px;
    border:1px solid #ffffff17}
  body.hm12-ready .hm12-table-scroll table{display:table!important;width:max-content;
    min-width:100%;max-width:none!important;border-collapse:collapse}
  body.hm12-ready .hm12-table-scroll th,
  body.hm12-ready .hm12-table-scroll td{white-space:normal!important;
    min-width:70px;padding:11px!important;overflow-wrap:anywhere}
  body.hm12-ready .hm12-table-scroll:focus-visible{outline:2px solid #ad98ff;outline-offset:2px}
  body.hm12-ready :is(.pla-rows,.nf-rows,.c2-table-wrap,
   .sms-scroll,.sms-table-wrapper){max-width:100%;overflow-x:auto!important;
    -webkit-overflow-scrolling:touch}
  body.hm12-ready :is(.pla-panel,.nf-panel,.sms-card){min-width:0;max-width:100%}
  body.hm12-ready :is(.pla-kpis,.sms-grid,.nf-form){grid-template-columns:minmax(0,1fr)!important}
  body.hm12-ready :is(.pla-search,.sms-compose-foot){flex-wrap:wrap!important}
  body.hm12-ready :is(.pla-search input,.pla-search select,.nf-form input){
    min-width:0!important;max-width:100%!important}
  body.hm12-ready :is(.modal,.dialog,[role="dialog"],.entry-modal-card){
    max-width:calc(100vw - 24px)!important;max-height:calc(100dvh - 28px)!important;
    overflow-y:auto!important}
  body.hm12-ready .ref-control-section{overflow:visible}
  /* Critical three-server Control Room: explicit one-column mobile layout. */
  body.hm12-ready #c2-root{width:100%!important;max-width:100%!important;min-width:0!important}
  body.hm12-ready #c2-root .c4-heading{gap:12px!important;align-items:stretch!important;
    flex-direction:column!important}
  body.hm12-ready #c2-root .c4-heading-main{min-width:0!important;gap:10px!important}
  body.hm12-ready #c2-root .c4-logo{width:42px;height:42px}
  body.hm12-ready #c2-root #c4-shell{width:100%;min-width:0;
    padding:13px 10px!important;border-radius:17px}
  body.hm12-ready #c2-root .c4-section-head{flex-wrap:wrap!important;gap:10px!important}
  body.hm12-ready #c2-root .t10-head-tools{width:100%;justify-content:space-between;
    flex-wrap:wrap;gap:9px}
  body.hm12-ready #c2-root #c2-cards.c2-cards{display:grid!important;
    grid-template-columns:minmax(0,1fr)!important;gap:12px!important}
  body.hm12-ready #c2-root .t10-wrapper{width:100%;min-width:0!important;max-width:100%}
  body.hm12-ready #c2-root #c2-cards .t10-wrapper .c4-server-card{
    min-width:0!important;min-height:0!important;width:100%!important;
    padding:16px 13px!important}
  body.hm12-ready #c2-root .c4-card-top{flex-wrap:wrap;gap:9px}
  body.hm12-ready #c2-root .c4-center{
    display:grid!important;grid-template-columns:105px minmax(0,1fr)!important;
    gap:10px!important;margin:17px 0!important}
  body.hm12-ready #c2-root .c4-ring,
  body.hm12-ready #c2-root .t10-ring{width:100px!important;height:100px!important;
    box-sizing:border-box}
  body.hm12-ready #c2-root .c4-values>div{padding:10px!important;min-width:0}
  body.hm12-ready #c2-root .c4-values strong{font-size:15px!important}
  body.hm12-ready #c2-root .c4-bottom{display:grid!important;
    grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:6px}
  body.hm12-ready #c2-root .c4-bottom>div{min-width:0;padding:10px 6px}
  body.hm12-ready #c2-root .c4-bottom b{font-size:12px!important;overflow-wrap:anywhere}
  body.hm12-ready #c2-root .t10-purchase{padding:10px!important;gap:7px}
  body.hm12-ready #c2-root .t10-purchase-label{width:100%;flex-basis:100%}
  body.hm12-ready #c2-root .t10-purchase button{min-height:43px!important;flex:1 1 65px}
  body.hm12-ready #c2-root #c2-panel{max-width:100%;min-width:0;padding:12px!important}
  body.hm12-ready #c2-root .c2-panel-top,
  body.hm12-ready #c2-root #c3-table-controls{
    display:flex!important;align-items:stretch!important;
    flex-direction:column!important;gap:10px!important}
  body.hm12-ready #c2-root #c3-table-controls>*{width:100%!important;
    max-width:100%!important;min-width:0!important;flex:0 1 auto!important}
  body.hm12-ready #c2-root .c2-kpis{grid-template-columns:repeat(2,minmax(0,1fr))!important}
  body.hm12-ready #c2-root .c2-kpis b{font-size:17px!important}
  body.hm12-ready #c2-root .c2-table-wrap{
    max-height:min(63dvh,700px)!important;overflow:auto!important;
    overscroll-behavior:contain!important;scrollbar-width:thin}
  body.hm12-ready #c2-root .c2-table-wrap table{
    display:table!important;min-width:790px!important;width:max-content!important}
  body.hm12-ready #c2-root .c2-table-wrap th,
  body.hm12-ready #c2-root .c2-table-wrap td{font-size:12px!important}
  body.hm12-ready #c2-root #c3-detail-backdrop .c3-dialog{max-height:90dvh!important;
    width:calc(100vw - 20px)!important;overflow-y:auto!important}
  body.hm12-ready #c2-root .dh1-grid{
    display:grid!important;grid-template-columns:minmax(0,1fr)!important}
  body.hm12-ready #c2-root .dh1-row{grid-template-columns:70px minmax(0,1fr) auto!important;
    font-size:11px}
  body.hm12-ready :is(.c4-return,.c2-btn,.c3-detail-button,.hm12-open-button):focus-visible{
    outline:2px solid #d4beff;outline-offset:2px}
}
@media(max-width:390px){
 body.hm12-ready .main{padding-right:9px!important;padding-left:9px!important}
 body.hm12-ready #c2-root .c4-center{grid-template-columns:93px minmax(0,1fr)!important;gap:7px!important}
 body.hm12-ready #c2-root .t10-ring{width:90px!important;height:90px!important}
 body.hm12-ready .ref-quick-grid,body.hm12-ready .focus-quick-grid{
   grid-template-columns:minmax(0,1fr)!important}
}
@media (prefers-reduced-motion: reduce){
 body.hm12-ready .sidebar{transition:none!important}
}
</style>
'''

_HM12_JS = r'''
<script id="hm12-admin-menu">
(function(){
 "use strict";
 function init(){
   if(document.body.classList.contains("hm12-ready"))return;
   const sidebar=document.querySelector(".sidebar");
   const main=document.querySelector(".main");
   if(!sidebar||!main)return;
   if(!sidebar.id)sidebar.id="hm12-sidebar";
   const shell=sidebar.parentElement;
   if(shell&&shell!==document.body)shell.classList.add("hm12-shell");
   const top=document.createElement("header");
   top.className="hm12-top";
   top.setAttribute("role","banner");
   const open=document.createElement("button");
   open.type="button";open.className="hm12-open-button";
   open.setAttribute("aria-label","باز کردن منوی مدیریت");
   open.setAttribute("aria-expanded","false");
   open.setAttribute("aria-controls",sidebar.id);
   open.textContent="☰";
   const title=document.createElement("div");title.className="hm12-title";
   const mark=document.createElement("span");mark.className="hm12-mark";
   mark.setAttribute("aria-hidden","true");mark.textContent="⌘";
   const copy=document.createElement("div");copy.className="hm12-copy";
   const brand=document.createElement("b");brand.textContent="مدیریت VPN";
   const page=document.createElement("small");
   const h=document.querySelector(".topbar h1, .ref-hero h1, .c4-heading h1, .main h1");
   page.textContent=h&&h.textContent.trim()?h.textContent.trim():"داشبورد";
   copy.append(brand,page);title.append(mark,copy);top.append(open,title);
   const backdrop=document.createElement("button");
   backdrop.type="button";backdrop.className="hm12-backdrop";
   backdrop.hidden=true;backdrop.setAttribute("aria-label","بستن منو");
   document.body.append(top,backdrop);
   sidebar.setAttribute("aria-label","منوی اصلی مدیریت");
   function isMobile(){return window.matchMedia("(max-width: 860px)").matches}
   let returnFocus=null;
   function close(){
     document.body.classList.remove("hm12-open");
     open.setAttribute("aria-expanded","false");
     backdrop.hidden=true;
     if(isMobile()){sidebar.setAttribute("aria-hidden","true");sidebar.inert=true}
     else{sidebar.removeAttribute("aria-hidden");sidebar.inert=false}
     if(returnFocus&&document.contains(returnFocus)&&isMobile())returnFocus.focus();
     returnFocus=null;
   }
   function show(){
     if(!isMobile())return;
     returnFocus=document.activeElement;
     sidebar.inert=false;sidebar.removeAttribute("aria-hidden");
     document.body.classList.add("hm12-open");
     open.setAttribute("aria-expanded","true");
     backdrop.hidden=false;
     const focusable=sidebar.querySelector("nav a,button,a");
     if(focusable)focusable.focus({preventScroll:true});
   }
   open.addEventListener("click",function(){
     if(document.body.classList.contains("hm12-open"))close();else show();
   });
   backdrop.addEventListener("click",close);
   sidebar.addEventListener("click",function(ev){
     if(ev.target.closest("a[href]"))close();
   });
   document.addEventListener("keydown",function(ev){
     if(!isMobile()||!document.body.classList.contains("hm12-open"))return;
     if(ev.key==="Escape"){close();return}
     if(ev.key==="Tab"){
       const links=[...sidebar.querySelectorAll("a[href],button:not([disabled])")];
       if(!links.length){ev.preventDefault();return}
       const first=links[0],last=links[links.length-1];
       if(ev.shiftKey&&document.activeElement===first){ev.preventDefault();last.focus()}
       else if(!ev.shiftKey&&document.activeElement===last){ev.preventDefault();first.focus()}
     }
   });
   function sync(){
     if(!isMobile())close();
     else if(!document.body.classList.contains("hm12-open")){
       sidebar.setAttribute("aria-hidden","true");sidebar.inert=true;
     }
   }
   window.addEventListener("resize",sync,{passive:true});
   /* Retain all table columns and original row actions; scroll locally. */
   function scrollTables(){
     document.querySelectorAll(".main table").forEach(function(table){
       if(table.closest(".hm12-table-scroll,.c2-table-wrap,.nf-rows,.pla-rows,.table-wrap,.table-responsive,.sms-scroll"))return;
       if(table.parentElement&&table.parentElement.classList.contains("hm12-table-scroll"))return;
       const wrap=document.createElement("div");
       wrap.className="hm12-table-scroll";wrap.tabIndex=0;
       wrap.setAttribute("role","region");
       wrap.setAttribute("aria-label","جدول قابل پیمایش افقی");
       table.parentNode.insertBefore(wrap,table);
       wrap.appendChild(table);
     });
   }
   scrollTables();
   /* Dynamically rendered admin tables can appear after page load. */
   let scheduled=false;
   const observer=new MutationObserver(function(){
     if(scheduled)return;
     scheduled=true;
     requestAnimationFrame(function(){scheduled=false;scrollTables()});
   });
   observer.observe(main,{childList:true,subtree:true});
   document.body.classList.add("hm12-ready");
   sync();
 }
 if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init,{once:true});
 else init();
})();
</script>
'''

_hm12_base=TEMPLATES.get("base.html","")
if (not isinstance(_hm12_base,str)
    or _hm12_base.lower().count("</head>")!=1
    or _hm12_base.lower().count("</body>")!=1
    or _hm12_base.count("hm12-admin-mobile")!=0
    or _hm12_base.count("hm12-admin-menu")!=0
    or 'class="sidebar"' not in _hm12_base
    or 'class="main"' not in _hm12_base):
    raise RuntimeError("MOBILE_V12_ADMIN_BASE_PREFLIGHT_STOP")
_hm12_base=_hm12_re.sub(r"(?i)</head>",lambda m:_HM12_CSS+m.group(),_hm12_base,count=1)
_hm12_base=_hm12_re.sub(r"(?i)</body>",lambda m:_HM12_JS+m.group(),_hm12_base,count=1)
if not _hm12_re.search(r'<meta\s+name=["\']viewport',_hm12_base,_hm12_re.I):
    _hm12_base=_hm12_re.sub(r"(?i)</head>",
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n</head>',
        _hm12_base,count=1)
_hm12_check=_HM12_CSS+_HM12_JS
if "{{" in _hm12_check or "{%" in _hm12_check or "{#" in _hm12_check:
    raise RuntimeError("MOBILE_V12_UNEXPECTED_JINJA_IN_CSS_OR_JS")
_hm12_Jinja().parse(_hm12_base)
TEMPLATES["base.html"]=_hm12_base
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)
