# HESAB_MAYA_DYNAMIC_LINKS_V1
# Newly created XUI clients can be linked to an explicit subscription ID by
# the logged-in operator. No XUI writes. Existing root approvals are untouched.
from sqlalchemy import text as _mdl_text
from fastapi import Request as _mdl_Request, Depends as _mdl_Depends, Form as _mdl_Form
from fastapi.responses import JSONResponse as _mdl_JSON
from sqlalchemy.orm import Session as _mdl_Session
import secrets as _mdl_secrets

_MDL_PREVIOUS_RESOLVE=_ml_resolve
_MDL_APPROVED_REASONS=frozenset(("unmatched_review",))

def _ml_resolve(server,clients,db):
    original=_MDL_PREVIOUS_RESOLVE(server,clients,db)
    stored=db.execute(_mdl_text("""
      SELECT email,subscription_id FROM maya_new_approved_links
      WHERE server=:server LIMIT 2000
    """),{"server":server}).mappings().all()
    if not stored:return original
    by_email={str(x["email"]):int(x["subscription_id"]) for x in stored}
    states=_followup_states(db)
    used={r["sid"] for r in original if r.get("sid")}
    for row in original:
        key=str(row.get("email") or "").strip().casefold()
        sid=by_email.get(key)
        if not sid:continue
        # Root-approved manual links and explicit exclusions always outrank
        # later database proposals. No silent reassignment.
        if row.get("sid") not in (None,sid) or row.get("control_ambiguous"):
            continue
        if row.get("sid") is None and row.get("reason") not in _MDL_APPROVED_REASONS:
            continue
        if sid in used and row.get("sid")!=sid:
            continue
        s=db.get(Subscription,sid)
        if s is None or states.get(sid)=="cut":
            continue
        row.update({
            "sid":sid,"name":s.display_name,
            "expiry":s.expiry_date.isoformat() if s.expiry_date else "",
            "finance_state":states.get(sid) or "normal",
            "reason":"manual_approved"
        })
        used.add(sid)
    return original

def _mdl_account(sid:int,db):
    if type(sid) is not int or not 0<sid<=100000000:
        return None
    sub=db.get(Subscription,sid)
    if sub is None or _followup_states(db).get(sid)=="cut":
        return None
    return sub

def _mdl_get_account(sid:int,db:_mdl_Session=_mdl_Depends(get_db)):
    sub=_mdl_account(sid,db)
    if sub is None:
        return _mdl_JSON({"ok":False,"error":"شناسه فعال پیدا نشد."},status_code=404)
    return _mdl_JSON({"ok":True,"sid":sub.id,"name":sub.display_name,
        "expiry":sub.expiry_date.isoformat() if sub.expiry_date else None},
        headers={"Cache-Control":"private, no-store"})

def _mdl_post_link(request:_mdl_Request,
                   server:str=_mdl_Form(""),email:str=_mdl_Form(""),
                   sid:int=_mdl_Form(0),csrf:str=_mdl_Form(""),
                   db:_mdl_Session=_mdl_Depends(get_db)):
    if (request.headers.get("origin")!="https://hesab.filmjadiid.ir" or
        request.headers.get("sec-fetch-site") not in (None,"same-origin")):
        return _mdl_JSON({"ok":False,"error":"Origin denied"},status_code=403)
    token=request.session.get("maya1_control_csrf")
    if not isinstance(token,str) or len(token)<30 or not _mdl_secrets.compare_digest(token,csrf):
        return _mdl_JSON({"ok":False,"error":"Invalid operator session"},status_code=403)
    if server not in _ML_SERVERS or not 0<len(email)<160 or email!=email.strip():
        return _mdl_JSON({"ok":False,"error":"سرور یا نام کلاینت نامعتبر است."},status_code=400)
    account=_mdl_account(sid,db)
    if account is None:
        return _mdl_JSON({"ok":False,"error":"حساب موجود یا قابل تطبیق نیست."},status_code=409)
    normalized=email.casefold()
    try:
        # Serialize concurrent approvals in this dedicated table. Never holds
        # locks for routine display or waiting-status reads.
        db.execute(_mdl_text("SELECT pg_advisory_xact_lock(14050423)"))
        exists=db.execute(_mdl_text("""
          SELECT 1 FROM maya_new_approved_links
          WHERE server=:server AND (email=:email OR subscription_id=:sid)
        """),{"server":server,"email":normalized,"sid":sid}).first()
        if exists:
            db.rollback()
            return _mdl_JSON({"ok":False,"error":"این کلاینت یا شناسه قبلاً تطبیق داده شده است."},status_code=409)
        # Live roster, EXACT client, root-approval conflicts, and duplicate
        # already-linked account are all verified BEFORE INSERT.
        live=_ml_one(server,db)
        matches=[r for r in live["rows"] if r["email"].strip().casefold()==normalized]
        if (len(matches)!=1 or matches[0].get("sid") is not None
            or matches[0].get("reason") not in _MDL_APPROVED_REASONS
            or matches[0].get("control_ambiguous")):
            db.rollback()
            return _mdl_JSON({"ok":False,"error":"تطبیق جدید مجاز نیست؛ احتمال تکرار یا تعارض وجود دارد."},status_code=409)
        if any(r.get("sid")==sid for r in live["rows"]):
            db.rollback()
            return _mdl_JSON({"ok":False,"error":"این حساب قبلاً روی همین سرور به کلاینت دیگری متصل است."},status_code=409)
        db.execute(_mdl_text("""
          INSERT INTO maya_new_approved_links(server,email,subscription_id)
          VALUES (:server,:email,:sid)
        """),{"server":server,"email":normalized,"sid":sid})
        db.commit()
        return _mdl_JSON({"ok":True,"server":server,"email":email,
            "sid":sid,"name":account.display_name,"changed_xui":False},
            headers={"Cache-Control":"private, no-store"})
    except Exception as exc:
        db.rollback()
        print("MAYA_DYNAMIC_LINK_ERROR",type(exc).__name__,str(exc)[:135])
        return _mdl_JSON({"ok":False,"error":"نتیجه ذخیره نامشخص است؛ پیش از تکرار صفحه را به‌روز کن."},status_code=502)

app.add_api_route("/control-room/maya-link/account",_mdl_get_account,methods=["GET"])
app.add_api_route("/control-room/maya-link/approve",_mdl_post_link,methods=["POST"])

_MDL_CSS=r'''
<style>
#mdl-backdrop{position:fixed;inset:0;z-index:9500;display:grid;place-items:center;
 background:rgba(4,5,17,.78);padding:16px;direction:rtl}
#mdl-backdrop *{box-sizing:border-box}
#mdl-backdrop .mdl-sheet{
 background:#171932;border:1px solid rgba(177,150,255,.35);
 box-shadow:0 20px 70px #0009;border-radius:18px;width:min(480px,100%);padding:22px;color:#eeedff
}
#mdl-backdrop h3{font-size:19px;margin:0 0 8px;color:#f4f1ff}
#mdl-backdrop p{font-size:12px;line-height:1.9;color:#b0b2ce;margin:6px 0 15px}
#mdl-backdrop label{display:block;margin:14px 0 7px;font-size:12px;font-weight:750}
#mdl-backdrop input{
 width:100%;height:44px;border:1px solid #71629f;border-radius:11px;
 color:#fff;background:#111327;padding:0 12px;font:inherit;direction:ltr;text-align:right
}
#mdl-backdrop .mdl-found{margin-top:11px;padding:12px;border:1px solid #454568;
 border-radius:10px;font-size:12px;line-height:1.85;color:#cdd2ff}
#mdl-backdrop .mdl-error{min-height:20px;color:#ffb5c4;font-size:12px;margin-top:8px}
#mdl-backdrop .mdl-actions{display:flex;gap:8px;justify-content:flex-start;flex-wrap:wrap;margin-top:17px}
#mdl-backdrop button{font:inherit;font-weight:800;font-size:12px;border:1px solid #6e668a;
 background:#242444;color:#e8e7f6;border-radius:9px;padding:10px 13px;cursor:pointer}
#mdl-backdrop button.mdl-primary{background:#624bb4;color:#fff;border-color:#8b75da}
#mdl-backdrop button:disabled{opacity:.45;cursor:wait}
</style>
'''
_MDL_SCRIPT=r'''
<script>
(function(){
 "use strict";
 if(window.hesabLinkMaya)return;
 const csrf="{{ ctrl_csrf }}";
 const serverLabels={maya1:"مایا ۱","maya-s3":"مایا ۳",maya4:"مایا ۴"};
 window.hesabLinkMaya=(server,item)=>{
   if(!item || item.sid || item.reason!=="unmatched_review")return;
   const make=(tag,text,parent,cls)=>{
     const e=document.createElement(tag);
     if(text!==undefined)e.textContent=String(text);
     if(cls)e.className=cls;
     if(parent)parent.appendChild(e);
     return e;
   };
   document.getElementById("mdl-backdrop")?.remove();
   const back=make("div",undefined,document.body);
   back.id="mdl-backdrop";back.setAttribute("role","dialog");back.setAttribute("aria-modal","true");
   back.setAttribute("aria-label","تطبیق دستی اکانت X-UI");
   const sheet=make("div",undefined,back,"mdl-sheet");
   make("h3","تطبیق کاربر تازه",sheet);
   make("p","نام کلاینت: "+item.email+" · سرور: "+(serverLabels[server]||server),sheet);
   make("p","شناسه همان حساب را از سایت حساب VPN وارد کن. این عملیات فقط تطبیق را ذخیره می‌کند.",sheet);
   const label=make("label","شناسه حساب VPN",sheet);
   const input=make("input",undefined,sheet);
   input.type="number";input.min="1";input.step="1";input.placeholder="مثلاً 375";
   const found=make("div","ابتدا شناسه را بررسی کن.",sheet,"mdl-found");
   const err=make("div","",sheet,"mdl-error");
   const actions=make("div",undefined,sheet,"mdl-actions");
   const lookup=make("button","بررسی شناسه",actions);
   const approve=make("button","تأیید تطبیق",actions,"mdl-primary");
   const close=make("button","انصراف",actions);
   approve.disabled=true;
   let current=null,busy=false;
   const dismiss=()=>back.remove();
   close.onclick=dismiss;
   back.addEventListener("click",e=>{if(e.target===back&&!busy)dismiss();});
   input.addEventListener("input",()=>{current=null;approve.disabled=true;found.textContent="ابتدا شناسه را بررسی کن.";err.textContent="";});
   const enableBusy=value=>{busy=value;input.disabled=value;lookup.disabled=value;approve.disabled=value;close.disabled=value;};
   lookup.onclick=async()=>{
     const sid=Number(input.value);
     if(!Number.isSafeInteger(sid)||sid<1){err.textContent="شناسه معتبر وارد کن.";return;}
     enableBusy(true);err.textContent="";
     try{
       const res=await fetch("/control-room/maya-link/account?sid="+encodeURIComponent(sid),{
         credentials:"same-origin",cache:"no-store"});
       const val=await res.json();
       if(!res.ok||!val.ok)throw Error(val.error||"حساب پیدا نشد");
       current=val;
       found.textContent="#"+val.sid+" · "+val.name+" · سررسید "+(val.expiry||"نامشخص");
     }catch(ex){err.textContent=ex.message;current=null;}
     finally{enableBusy(false);approve.disabled=!current;}
   };
   approve.onclick=async()=>{
     if(!current || current.sid!==Number(input.value)||busy)return;
     if(!confirm("کلاینت "+item.email+" روی "+serverLabels[server]+" به حساب #"+
        current.sid+" ("+current.name+") متصل شود؟"))return;
     enableBusy(true);err.textContent="";
     const form=new FormData();
     for(const [k,v] of Object.entries({server,email:item.email,sid:current.sid,csrf}))
       form.set(k,String(v));
     try{
       const res=await fetch("/control-room/maya-link/approve",{
         method:"POST",credentials:"same-origin",body:form,cache:"no-store"});
       const val=await res.json();
       if(!res.ok||!val.ok)throw Error(val.error||"ذخیره تأیید نشد");
       found.textContent="✓ تطبیق ثبت شد. اطلاعات سرورها با گزارش موجود به‌روز می‌شود.";
       window.location.reload();
     }catch(ex){err.textContent=ex.message;enableBusy(false);approve.disabled=!current;}
   };
   input.focus();
 };
})();
</script>
'''
_mdl_tpl=TEMPLATES.get("control_room.html","")
_mdl_anchors=(
 '}else create("small",item.reason==="approved_archived_read_only"?"آرشیوشده · فقط نمایش":item.control_ambiguous?"تعارض ورودی":"نیازمند تطبیق",controls);',
 '}else create("small",item.control_ambiguous?"تعارض ورودی":"نیازمند تطبیق",controls);',
)
_mdl_found=[x for x in _mdl_anchors if _mdl_tpl.count(x)==1]
if len(_mdl_found)!=1:
    raise RuntimeError("Control room unmatched-action slot changed; abort")
_mdl_anchor=_mdl_found[0]
_mdl_repl='''}else if(!item.sid && !item.control_ambiguous && item.reason==="unmatched_review"){
     const b=create("button","تطبیق",controls,"c2-btn");
     b.type="button";b.disabled=state.mutating;
     b.onclick=()=>window.hesabLinkMaya(server,item);
   }else create("small",item.reason==="approved_archived_read_only"?"آرشیوشده · فقط نمایش":item.control_ambiguous?"تعارض ورودی":"نیازمند تطبیق",controls);'''
_mdl_tpl=_mdl_tpl.replace(_mdl_anchor,_mdl_repl,1)
_mdl_tpl=_mdl_tpl.replace("{% block content %}","{% block content %}"+_MDL_CSS,1)
_mdl_before,_mdl_after=_mdl_tpl.rsplit("{% endblock %}",1)
_mdl_tpl=_mdl_before+_MDL_SCRIPT+"\n{% endblock %}"+_mdl_after
TEMPLATES["control_room.html"]=_mdl_tpl
if hasattr(env.loader,"mapping"):env.loader.mapping.update(TEMPLATES)
