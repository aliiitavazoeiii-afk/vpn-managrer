# HESAB_MAYA_DYNAMIC_LINKS_V2
# Always-visible operator entry to the existing V1 approved-link workflow.
# No new API credentials, XUI actions, financial writes or background loops.
# Allows explicit operator review of XUI names involved in exact-name conflicts.
_MDL_APPROVED_REASONS=frozenset(("unmatched_review","exact_name_conflict"))
_MDL2_TEMPLATE=TEMPLATES.get("control_room.html","")
_MDL2_ACTION='<div id="c2-cards" class="c2-cards"></div>'
_MDL2_OLD_GUARD='if(!item || item.sid || item.reason!=="unmatched_review")return;'
_MDL2_NEW_GUARD='if(!item || item.sid || !["unmatched_review","exact_name_conflict"].includes(item.reason))return;'
if (_MDL2_TEMPLATE.count(_MDL2_ACTION)!=1 or
    _MDL2_TEMPLATE.count(_MDL2_OLD_GUARD)!=1 or
    _MDL2_TEMPLATE.count("window.hesabLinkMaya=(server,item)=>")!=1):
    raise RuntimeError("Matching V1 UI not found or control-room layout differs")
_MDL2_TOOLBAR=r'''
<div id="mdl2-toolbar">
  <button id="mdl2-open" type="button">تطبیق حساب جدید X-UI</button>
  <span>برای حساب‌های تازه یا نام‌های متفاوت در مایا ۱، ۳ و ۴</span>
</div>
'''
_MDL2_CSS=r'''
<style>
#mdl2-toolbar{display:flex;align-items:center;flex-wrap:wrap;gap:11px;margin:-4px 0 16px;direction:rtl}
#mdl2-toolbar>button{font:inherit;font-size:12px;font-weight:800;cursor:pointer;color:#f5efff;
 background:linear-gradient(130deg,#5943aa,#7354bd);border:1px solid #9b7bdb;
 padding:11px 16px;border-radius:11px;min-height:42px}
#mdl2-toolbar>button:hover{filter:brightness(1.13)}
#mdl2-toolbar>span{color:var(--c2-muted,#a4a7c0);font-size:11px}
#mdl2-picker{position:fixed;inset:0;display:grid;place-items:center;z-index:9600;
 background:rgba(4,5,17,.8);padding:14px;direction:rtl}
#mdl2-picker[hidden]{display:none!important}
#mdl2-picker *{box-sizing:border-box}
#mdl2-picker .mdl2-sheet{width:min(480px,100%);background:#191931;color:#eef0ff;
 border:1px solid #66579c;padding:22px;border-radius:17px;box-shadow:0 20px 70px #000a}
#mdl2-picker h3{font-size:18px;margin:0 0 9px}
#mdl2-picker p{font-size:12px;color:#c2c3df;line-height:1.8}
#mdl2-picker label{font-weight:800;font-size:12px;display:block;margin:15px 0 6px}
#mdl2-picker select{width:100%;font:inherit;font-size:13px;min-height:42px;border-radius:9px;
 color:#f5f3ff;background:#242440;border:1px solid #746ba3;padding:7px 11px}
#mdl2-picker .mdl2-aux{font-size:11px;line-height:1.9;min-height:23px;color:#c7bee7;margin:9px 0}
#mdl2-picker .mdl2-actions{display:flex;gap:9px;margin-top:16px;justify-content:flex-start}
#mdl2-picker button{font:inherit;font-weight:800;font-size:12px;color:#f5f3ff;
 background:#3a3558;border:1px solid #6a5f94;padding:9px 14px;border-radius:10px;cursor:pointer}
#mdl2-picker button.mdl2-choose{background:#6951b7;border-color:#8d70d9}
#mdl2-picker button:disabled{opacity:.5;cursor:not-allowed}
</style>
'''
_MDL2_SCRIPT=r'''
<script>
(function(){
 "use strict";
 if(window.__hesabMayaPickerV2)return;window.__hesabMayaPickerV2=true;
 const open=document.getElementById("mdl2-open");
 if(!open)return;
 const names={maya1:"مایا ۱","maya-s3":"مایا ۳",maya4:"مایا ۴"};
 const eligible=row=>row && !row.sid && !row.control_ambiguous &&
   ["unmatched_review","exact_name_conflict"].includes(row.reason);
 const make=(tag,label,parent,cls)=>{
   const el=document.createElement(tag);
   if(label!==undefined)el.textContent=String(label);
   if(parent)parent.appendChild(el);
   if(cls)el.className=cls;
   return el;
 };
 open.onclick=async()=>{
   document.getElementById("mdl2-picker")?.remove();
   const popup=make("div",undefined,document.body);popup.id="mdl2-picker";
   popup.setAttribute("role","dialog");popup.setAttribute("aria-modal","true");
   popup.setAttribute("aria-label","تطبیق حساب جدید");
   const sheet=make("div",undefined,popup,"mdl2-sheet");
   make("h3","تطبیق حساب جدید X-UI",sheet);
   make("p","ابتدا سرور و کلاینت تطبیق‌نشده را انتخاب کن؛ سپس شناسه حساب VPN را تأیید کن.",sheet);
   make("label","سرور",sheet);
   const server=make("select",undefined,sheet);
   for(const k of ["maya4","maya-s3","maya1"]){
     const opt=make("option",names[k],server);opt.value=k;
   }
   make("label","کلاینت X-UI",sheet);
   const client=make("select",undefined,sheet);
   const info=make("p","در حال دریافت اطلاعات زنده...",sheet,"mdl2-aux");
   const buttons=make("div",undefined,sheet,"mdl2-actions");
   const next=make("button","ادامه تطبیق",buttons,"mdl2-choose");
   const close=make("button","انصراف",buttons);
   next.disabled=true;
   close.onclick=()=>popup.remove();
   popup.onclick=e=>{if(e.target===popup)popup.remove();};
   let reports={};
   const render=()=>{
     client.replaceChildren();next.disabled=true;
     const data=reports[server.value];
     if(!data||!data.ok){
       make("option","ارتباط زنده با این سرور در دسترس نیست",client).value="";
       info.textContent="امکان تطبیق بدون فهرست زنده X-UI وجود ندارد.";
       return;
     }
     const rows=(data.rows||[]).filter(eligible);
     if(!rows.length){
       make("option","کلاینت تطبیق‌نشده قابل تأیید وجود ندارد",client).value="";
       const others=(data.rows||[]).filter(x=>!x.sid);
       info.textContent="کل "+data.total+" · تطبیق‌شده "+data.linked+
        " · بدون تطبیق "+others.length+" · قابل تأیید ۰. "+
        (others.length?"برخی موارد مستثنا یا نیازمند بررسی ویژه‌اند.":"ممکن است این کاربر از قبل به حسابی متصل باشد.");
       return;
     }
     for(const r of rows){
       const opt=make("option",r.email+(r.reason==="exact_name_conflict"?" · تعارض نام":""),client);
       opt.value=r.email;
     }
     info.textContent="کل "+data.total+" · تطبیق‌شده "+data.linked+
       " · قابل تأیید دستی "+rows.length+" کلاینت";
     next.disabled=false;
   };
   server.onchange=render;
   next.onclick=()=>{
     const data=reports[server.value];
     const matches=(data?.rows||[]).filter(r=>eligible(r)&&r.email===client.value);
     if(matches.length!==1)return;
     popup.remove();
     if(typeof window.hesabLinkMaya==="function")
       window.hesabLinkMaya(server.value,matches[0]);
   };
   try{
     const r=await fetch("/control-room/v2/data",{
       credentials:"same-origin",cache:"no-store"});
     if(!r.ok)throw Error("HTTP "+r.status);
     const data=await r.json();
     if(!data.ok||!Array.isArray(data.servers))throw Error("Invalid server report");
     for(const entry of data.servers)reports[entry.server]=entry;
     render();
   }catch(e){
     info.textContent="دریافت اطلاعات زنده ناموفق بود: "+String(e.message);
     client.replaceChildren();next.disabled=true;
   }
 };
})();
</script>
'''
_MDL2_TEMPLATE=_MDL2_TEMPLATE.replace(_MDL2_ACTION,_MDL2_TOOLBAR+_MDL2_ACTION,1)
_MDL2_TEMPLATE=_MDL2_TEMPLATE.replace(_MDL2_OLD_GUARD,_MDL2_NEW_GUARD,1)
_MDL2_TEMPLATE=_MDL2_TEMPLATE.replace("{% block content %}","{% block content %}"+_MDL2_CSS,1)
_MDL2_START,_MDL2_END=_MDL2_TEMPLATE.rsplit("{% endblock %}",1)
_MDL2_TEMPLATE=_MDL2_START+_MDL2_SCRIPT+"\n{% endblock %}"+_MDL2_END
TEMPLATES["control_room.html"]=_MDL2_TEMPLATE
if hasattr(env.loader,"mapping"):env.loader.mapping.update(TEMPLATES)
