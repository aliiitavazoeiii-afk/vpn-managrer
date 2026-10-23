# HESAB_WAITING_VPN_CONTROL_V1
# Operator-only manual disable in /followups. On confirmed later payment, a
# local 30-second DB worker may re-enable ONLY those same successfully disabled
# XUI clients. Nothing ever disables on a timer. No Shahan control.
import asyncio as _wvc_asyncio
import json as _wvc_json
import secrets as _wvc_secrets
import traceback as _wvc_traceback
import time as _wvc_time
from datetime import datetime as _wvc_datetime
from sqlalchemy import text as _wvc_text
from fastapi import Form as _wvc_Form,Request as _wvc_Request,Depends as _wvc_Depends
from fastapi.responses import JSONResponse as _wvc_JSON
from sqlalchemy.orm import Session as _wvc_Session

_WVC_CONTROL_REASONS=frozenset(("manual_approved","approved_maya1","exact_name"))
_WVC_PAYMENT_CHECK_INTERVAL=30

def _wvc_response(code,status=200,**parts):
    return _wvc_JSON({"ok":status<400,"code":code,**parts},status_code=status,
                     headers={"Cache-Control":"private, no-store"})

def _wvc_sid_payment_max(db,sid):
    return int(db.execute(_wvc_text(
        "SELECT COALESCE(MAX(id),0) FROM payments WHERE subscription_id=:sid"
    ),{"sid":int(sid)}).scalar() or 0)

def _wvc_ready(db,sid,require_waiting):
    s=db.get(Subscription,int(sid))
    if not s or bool(s.is_free):return False
    if _followup_states(db).get(int(sid))=="cut":return False
    if require_waiting and _followup_states(db).get(int(sid))!="waiting":return False
    debt=int(current_debt_for(s,today_local()) or 0)
    if require_waiting:return debt>0
    return (debt<=0 and str(s.payment_status or "").casefold()=="paid"
            and bool(s.expiry_date) and s.expiry_date>=today_local())

def _wvc_match(live,server,sid):
    matches=[r for r in live["rows"] if r.get("sid")==sid]
    if len(matches)!=1:raise RuntimeError("Expected one approved XUI client on "+server)
    row=matches[0]
    if (row.get("reason") not in _WVC_CONTROL_REASONS or
        row.get("control_ambiguous") or
        row.get("finance_state")=="cut" or
        not row.get("email")):
        raise RuntimeError("XUI binding not approved for control on "+server)
    return row

def _wvc_status(sid,db):
    rows=db.execute(_wvc_text("""
      SELECT server,email,state,disabled_at,activated_at
      FROM waiting_vpn_controls WHERE subscription_id=:sid
      ORDER BY server,email
    """),{"sid":sid}).mappings().all()
    return [dict(x) for x in rows]

def _wvc_disable_one(sid,db):
    # This route intentionally owns the decision to disable; it does NOT change
    # financial waiting/cut states or auto-disable anyone.
    refresh_billing(db)
    if not _wvc_ready(db,sid,True):
        return {"sid":sid,"ok":False,"message":"حساب در انتظار با بدهی معتبر نیست."}
    targets=[]
    errors=[]
    # Preflight every server BEFORE ANY mutation to prevent hidden bindings.
    # Remote calls occur only when operator presses the button.
    for server in _ML_SERVERS:
        try:
            live=_ml_one(server,db)
        except Exception:
            return {"sid":sid,"ok":False,"message":"حداقل یک سرور مایا در دسترس نیست؛ تغییری انجام نشد."}
        matches=[r for r in live["rows"] if r.get("sid")==sid]
        if not matches:continue
        try:
            row=_wvc_match(live,server,sid)
        except Exception:
            return {"sid":sid,"ok":False,"message":"یکی از تطبیق‌ها مبهم است؛ تغییری انجام نشد."}
        targets.append((server,row))
    if not targets:
        return {"sid":sid,"ok":False,"message":"برای این حساب اتصال مجاز X-UI پیدا نشد (شاهان فعلاً پشتیبانی نمی‌شود)."}
    watermark=_wvc_sid_payment_max(db,sid)
    for server,row in targets:
        email=row["email"]
        if not row["client_enabled"]:
            errors.append(server+": از قبل خاموش بوده؛ مالکیت این قطع ثبت نشد")
            continue
        existing=db.execute(_wvc_text("""
          SELECT id,state FROM waiting_vpn_controls
          WHERE subscription_id=:sid AND server=:srv AND email=:email
        """),{"sid":sid,"srv":server,"email":email}).mappings().first()
        if existing and existing["state"] in ("disabling","activating","needs_review"):
            errors.append(server+": عملیات قبلی نیازمند بررسی است")
            continue
        # A durable marker is written first; only confirmed remote toggles
        # are eligible for automatic re-enable after payment.
        db.execute(_wvc_text("""
          INSERT INTO waiting_vpn_controls
           (subscription_id,server,email,state,payment_watermark,disabled_at,activated_at,updated_at)
          VALUES (:sid,:srv,:email,'disabling',:mark,NULL,NULL,NOW())
          ON CONFLICT (subscription_id,server,email)
          DO UPDATE SET state='disabling',payment_watermark=EXCLUDED.payment_watermark,
                        disabled_at=NULL,activated_at=NULL,updated_at=NOW()
        """),{"sid":sid,"srv":server,"email":email,"mark":watermark})
        db.commit()
        try:
            result=_ml_call("toggle",server,email=email,expected=True,target=False)
            if result.get("client_enabled") is not False:raise RuntimeError("Unconfirmed disable")
        except Exception:
            db.execute(_wvc_text("""
              UPDATE waiting_vpn_controls SET state='needs_review',updated_at=NOW()
              WHERE subscription_id=:sid AND server=:srv AND email=:email
                AND state='disabling'
            """),{"sid":sid,"srv":server,"email":email})
            db.commit()
            errors.append(server+": نتیجه قطع نامشخص؛ پنل را بررسی کن")
        else:
            db.execute(_wvc_text("""
              UPDATE waiting_vpn_controls SET state='disabled',disabled_at=NOW(),updated_at=NOW()
              WHERE subscription_id=:sid AND server=:srv AND email=:email AND state='disabling'
            """),{"sid":sid,"srv":server,"email":email})
            db.add(AuditEvent(kind="vpn_waiting_disabled",
                       message=f"sid={sid}; server={server}; client={email}; confirmed manual waiting disable"))
            db.commit()
    confirmed=[s for s,st in targets if any(r["server"]==s and r["state"]=="disabled" for r in _wvc_status(sid,db))]
    return {"sid":sid,"ok":bool(confirmed) and not errors,
            "confirmed":confirmed,"warnings":errors,
            "message":("قطع X-UI تأیید شد" if not errors else "بخشی از عملیات نیازمند بررسی است")}

def _wvc_disable(request:_wvc_Request,
                 sid:int=_wvc_Form(0),phone:str=_wvc_Form(""),
                 csrf:str=_wvc_Form(""),db:_wvc_Session=_wvc_Depends(get_db)):
    if (request.headers.get("origin")!="https://hesab.filmjadiid.ir" or
        request.headers.get("sec-fetch-site") not in (None,"same-origin")):
        return _wvc_response("ORIGIN_DENIED",403)
    token=request.session.get("maya1_control_csrf")
    if not isinstance(token,str) or len(token)<30 or not _wvc_secrets.compare_digest(token,csrf):
        return _wvc_response("CSRF_DENIED",403)
    if sid<=0 or sid>10000000:return _wvc_response("INVALID_SID",400)
    # For groups, the client posts a list of individual account IDs; do NOT
    # trust a phone number supplied by the browser to select extra accounts.
    if phone:return _wvc_response("GROUP_NOT_SUPPORTED",400)
    try:
        status=_wvc_disable_one(sid,db)
        return _wvc_response("DONE" if status["ok"] else "REVIEW",200 if status["ok"] else 409,
                             **status)
    except Exception as exc:
        print("WVC_MANUAL_DISABLE_ERROR",sid,type(exc).__name__,str(exc)[:180])
        db.rollback()
        return _wvc_response("ERROR",502,message="قطع تأیید نشد؛ پیش از تلاش دوباره وضعیت پنل را بررسی کن.")

app.add_api_route("/followups/vpn/disable",_wvc_disable,methods=["POST"])

# Ensure an existing operator session gets a CSRF nonce from the waiting page
# itself; visiting the separate control-room first must not be necessary.
_wvc_waiting_get=[
  r for r in app.router.routes
  if getattr(r,"path",None)=="/followups" and
     "GET" in (getattr(r,"methods",set()) or set())
]
if len(_wvc_waiting_get)!=1:
    raise RuntimeError("Expected one existing waiting GET handler")
_wvc_existing_get=_wvc_waiting_get[0].endpoint
def _wvc_waiting_with_csrf(request:_wvc_Request,db:_wvc_Session=_wvc_Depends(get_db)):
    token=request.session.get("maya1_control_csrf")
    if not isinstance(token,str) or len(token)<30:
        request.session["maya1_control_csrf"]=_wvc_secrets.token_urlsafe(32)
    return _wvc_existing_get(request,db=db)
app.router.routes[:]=[
 r for r in app.router.routes
 if not (getattr(r,"path",None)=="/followups" and
         "GET" in (getattr(r,"methods",set()) or set()))
]
app.add_api_route("/followups",_wvc_waiting_with_csrf,methods=["GET"])

def _wvc_reactivate_one(db,row):
    ident=int(row["id"]);sid=int(row["subscription_id"])
    server=str(row["server"]);email=str(row["email"])
    # Claim first (fail closed after crash/timeout; do not blindly retry).
    claimed=db.execute(_wvc_text("""
      UPDATE waiting_vpn_controls SET state='activating',updated_at=NOW()
      WHERE id=:id AND state='disabled' RETURNING id
    """),{"id":ident}).first()
    if not claimed:
        db.rollback();return
    db.commit()
    try:
        refresh_billing(db)
        if not _wvc_ready(db,sid,False):
            # Payment was reversed/new debt appeared, keep disabled for later.
            db.execute(_wvc_text("""
              UPDATE waiting_vpn_controls SET state='disabled',updated_at=NOW()
              WHERE id=:id AND state='activating'
            """),{"id":ident})
            db.commit();return
        live=_ml_one(server,db)
        client=_wvc_match(live,server,sid)
        if client["email"].casefold()!=email.casefold():
            raise RuntimeError("XUI client identity changed")
        if client["client_enabled"]:
            # Enabled elsewhere; never toggle an already enabled account.
            result="already_enabled"
        else:
            response=_ml_call("toggle",server,email=email,expected=False,target=True)
            if response.get("client_enabled") is not True:
                raise RuntimeError("Panel did not confirm automatic re-enable")
            result="auto_enabled"
        db.execute(_wvc_text("""
          UPDATE waiting_vpn_controls SET state='restored',activated_at=NOW(),updated_at=NOW()
          WHERE id=:id AND state='activating'
        """),{"id":ident})
        db.add(AuditEvent(kind="vpn_waiting_restored",
               message=f"sid={sid}; server={server}; client={email}; result={result}"))
        db.commit()
    except Exception as exc:
        print("WVC_AUTO_ENABLE_REVIEW",sid,server,type(exc).__name__,str(exc)[:180])
        db.rollback()
        db.execute(_wvc_text("""
          UPDATE waiting_vpn_controls SET state='needs_review',updated_at=NOW()
          WHERE id=:id AND state='activating'
        """),{"id":ident})
        db.commit()

def _wvc_reconcile_once():
    generator=get_db()
    db=next(generator)
    try:
        candidates=db.execute(_wvc_text("""
          SELECT c.id,c.subscription_id,c.server,c.email
          FROM waiting_vpn_controls c
          WHERE c.state='disabled'
            AND EXISTS (
             SELECT 1 FROM payments p
             WHERE p.subscription_id=c.subscription_id AND p.id>c.payment_watermark
            )
          ORDER BY c.id LIMIT 20
        """)).mappings().all()
        for row in candidates:
            sid=int(row["subscription_id"])
            if _wvc_ready(db,sid,False):
                _wvc_reactivate_one(db,row)
            else:
                # Leave disabled until the subscription is genuinely settled.
                db.rollback()
    finally:
        generator.close()

async def _wvc_background_loop():
    while True:
        try:
            # Run synchronous local DB / occasional remote XUI calls off-loop.
            await _wvc_asyncio.to_thread(_wvc_reconcile_once)
        except Exception as exc:
            print("WVC_WORKER_ERROR",type(exc).__name__,str(exc)[:200])
        await _wvc_asyncio.sleep(_WVC_PAYMENT_CHECK_INTERVAL)

@app.on_event("startup")
async def _wvc_startup():
    _wvc_asyncio.create_task(_wvc_background_loop())

_WVC_STYLE=r'''
<style>
.waiting-vpn-stop{
 display:inline-flex;align-items:center;justify-content:center;gap:5px;
 white-space:nowrap;min-height:34px;padding:0 11px;cursor:pointer;
 border:1px solid rgba(248,125,142,.52);border-radius:10px;
 background:rgba(204,73,97,.12);color:#ffb9c4;
 font-family:inherit;font-size:11px;font-weight:800
}
.waiting-vpn-stop:hover{background:rgba(204,73,97,.22)}
.waiting-vpn-stop:disabled{opacity:.48;cursor:wait}
.waiting-vpn-notice{position:fixed;bottom:18px;right:18px;z-index:9001;
 padding:12px 17px;max-width:min(490px,calc(100vw - 36px));font:inherit;
 color:#fae9ef;background:#2c1929;border:1px solid #a84866;border-radius:12px;
 box-shadow:0 15px 40px #0008;line-height:1.9}
.waiting-vpn-stop-note{font-size:10px;color:#929bb7;display:block;margin-top:2px}
</style>
'''
_WVC_JS=r'''
<script>
(function(){
 "use strict";
 if(window.__hesabWaitingVpnStopV1)return;
 window.__hesabWaitingVpnStopV1=true;
 const notice=(s)=>{
   let el=document.getElementById("waiting-vpn-feedback");
   if(!el){el=document.createElement("div");el.id="waiting-vpn-feedback";
     el.className="waiting-vpn-notice";el.setAttribute("role","status");document.body.append(el);}
   el.textContent=s;
 };
 document.addEventListener("click",e=>{
   const btn=e.target.closest("[data-waiting-vpn-expand]");
   if(!btn)return;
   e.preventDefault();e.stopImmediatePropagation();
   const group=btn.closest("[data-waiting-group]");
   const panel=group?.querySelector(".waiting-services");
   const head=group?.querySelector("[data-waiting-toggle]");
   if(panel){
     panel.hidden=false;
     head?.classList.add("open");
     head?.setAttribute("aria-expanded","true");
     notice("برای قطع VPN، اکانت موردنظر را از زیرمجموعه انتخاب کن.");
     panel.querySelector(".waiting-vpn-stop")?.focus();
   }
 },true);
 document.addEventListener("submit",async e=>{
   const form=e.target.closest(".waiting-vpn-stop-form");
   if(!form)return;
   e.preventDefault();e.stopImmediatePropagation();
   const btn=form.querySelector("button");
   if(!btn||btn.disabled)return;
   const name=form.dataset.accountName||"این اکانت";
   if(!confirm("اکانت "+name+" فقط روی سرورهای X-UI مایا قطع شود؟\nحساب در «در انتظار» باقی می‌ماند و بعد از پرداخت کامل تأییدشده به صورت خودکار وصل خواهد شد."))return;
   btn.disabled=true;
   try{
     const res=await fetch("/followups/vpn/disable",{
       method:"POST",credentials:"same-origin",body:new FormData(form),
       cache:"no-store",headers:{"X-Requested-With":"XMLHttpRequest"}
     });
     const data=await res.json();
     const message=data.message||"نتیجه تغییر وضعیت نامشخص است";
     const warnings=(data.warnings||[]).join("، ");
     notice(message+(warnings?" · "+warnings:"")+".");
     // The old five-minute sampler may not reflect the result immediately.
     if(res.ok&&data.ok)btn.textContent="✓ قطع تأیید شد";
   }catch(_){
     notice("نتیجه قطع نامشخص است؛ قبل از تکرار وضعیت X-UI را بررسی کن.");
   }finally{btn.disabled=false;}
 },true);
})();
</script>
'''
_wvc_tpl=TEMPLATES.get("followups.html","")
if _wvc_tpl.count('class="waiting-actions"')!=1:
    raise RuntimeError("Waiting child control slot missing; refuse unrelated UI edits")
if _wvc_tpl.count('data-waiting-v2-status-btn')<1:
    raise RuntimeError("Waiting V2 status UI missing")
_wvc_form=r'''
          <form class="waiting-vpn-stop-form" method="post" action="/followups/vpn/disable"
                data-account-name="{{ s.display_name }}">
            <input type="hidden" name="sid" value="{{ s.id }}">
            <input type="hidden" name="csrf" value="{{ request.session.get('maya1_control_csrf','') }}">
            <button type="submit" class="waiting-vpn-stop">غیرفعال‌کردن VPN</button>
          </form>
'''
_wvc_head_anchor='<div class="waiting-head-pay waiting-pay-tools">'
if _wvc_tpl.count(_wvc_head_anchor)!=1:
    raise RuntimeError("Waiting group action bar missing")
_wvc_head_control=r'''
        {% if g.services == 1 %}
          <form class="waiting-vpn-stop-form" method="post" action="/followups/vpn/disable"
                data-account-name="{{ g.rows[0].s.display_name }}">
            <input type="hidden" name="sid" value="{{ g.rows[0].s.id }}">
            <input type="hidden" name="csrf" value="{{ request.session.get('maya1_control_csrf','') }}">
            <button type="submit" class="waiting-vpn-stop">غیرفعال‌کردن VPN</button>
          </form>
        {% else %}
          <button type="button" class="waiting-vpn-stop" data-waiting-vpn-expand
            title="یک یا چند اکانت دارد؛ برای قطع دقیق، زیرمجموعه را انتخاب کن">انتخاب برای قطع VPN</button>
        {% endif %}
'''
_wvc_tpl=_wvc_tpl.replace(_wvc_head_anchor,
                          _wvc_head_anchor+"\n"+_wvc_head_control,1)
_wvc_tpl=_wvc_tpl.replace('<div class="waiting-actions">',
                          '<div class="waiting-actions">\n'+_wvc_form,1)
_wvc_tpl=_wvc_tpl.replace("{% block content %}","{% block content %}"+_WVC_STYLE,1)
_wvc_head,_wvc_tail=_wvc_tpl.rsplit("{% endblock %}",1)
_wvc_tpl=_wvc_head+_WVC_JS+"\n{% endblock %}"+_wvc_tail
TEMPLATES["followups.html"]=_wvc_tpl
if hasattr(env.loader,"mapping"):env.loader.mapping.update(TEMPLATES)
