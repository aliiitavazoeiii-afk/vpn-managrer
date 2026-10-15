# HESAB_NATIVE_SMS_V2_ADMIN
# Native Android SMS v2 (NOT the old gateway or Chrome UI automation).
# Must be appended after sms_browser_bridge and sms_nojump patches.
import re as _ns_re
from fastapi import Request as _ns_Request, Form as _ns_Form, Depends as _ns_Depends
from fastapi.responses import JSONResponse as _ns_JSON, RedirectResponse as _ns_Redirect
from sqlalchemy import text as _ns_text
from sqlalchemy.orm import Session as _ns_Session

_NS_DDL = """
CREATE TABLE IF NOT EXISTS native_sms_v2_jobs (
 id BIGSERIAL PRIMARY KEY, phone VARCHAR(11) NOT NULL, message TEXT NOT NULL,
 source VARCHAR(12) NOT NULL, cycle_key VARCHAR(32),
 account_ids INTEGER[] NOT NULL DEFAULT '{}',
 status VARCHAR(24) NOT NULL DEFAULT 'queued',
 device_id VARCHAR(128),parts INTEGER,result_code INTEGER,error TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 claimed_at TIMESTAMPTZ,started_at TIMESTAMPTZ,sent_at TIMESTAMPTZ,
 delivered_at TIMESTAMPTZ,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS native_sms_one_debt_cycle_v2
 ON native_sms_v2_jobs (phone,cycle_key) WHERE source='debt';
"""

def _ns_setup(db):
    # Execute DDL only during initial activation; never consume or alter sms_jobs.
    for statement in _NS_DDL.split(";"):
        if statement.strip():
            db.execute(_ns_text(statement))
    db.commit()


def _ns_error(code, status=409):
    return _ns_JSON({"ok":False,"code":code},status_code=status)


def _ns_clean_phone(raw):
    p=_sms_normalize_phone(raw)
    return p if _ns_re.fullmatch(r"09[0-9]{9}",p or "") else ""


def _ns_enqueue(db, phone, source, message=""):
    _ns_setup(db)
    normalized=_ns_clean_phone(phone)
    if not normalized:
        return None,"INVALID_PHONE"
    # Serialize native-send clicks for the same target.
    db.execute(_ns_text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
               {"k":"native-v2-"+normalized})
    cycle=None
    ids=[]
    if source=="debt":
        states=_followup_states(db)
        now=today_local()
        rows=db.query(Subscription).filter(
            Subscription.phone==normalized,Subscription.is_free.is_(False)
        ).order_by(Subscription.id.asc()).all()
        eligible=[s for s in rows if s.expiry_date is not None and
            s.expiry_date<=now and current_debt_for(s,now)>0
            and states.get(s.id) not in ("waiting","cut")]
        if not eligible:
            db.rollback()
            return None,"NO_ACTIONABLE_DEBT"
        earliest=min(s.expiry_date for s in eligible)
        cycle=earliest.isoformat()
        message=_ABAN_SMS_PATTERN.format(expiry=jdate(earliest))
        ids=[int(s.id) for s in eligible]
        older=db.execute(_ns_text("""
          SELECT id FROM sms_jobs WHERE phone=:phone
            AND message=:body AND status IN ('sent','delivered','operator_confirmed')
          ORDER BY id DESC LIMIT 1
        """),{"phone":normalized,"body":message}).first()
        if older:
            db.rollback()
            return None,"IDENTICAL_OLD_SMS_ALREADY_CONFIRMED"
        prev=db.execute(_ns_text("""
          SELECT id FROM native_sms_v2_jobs
          WHERE source='debt' AND phone=:phone AND cycle_key=:cycle
          LIMIT 1
        """),{"phone":normalized,"cycle":cycle}).first()
        if prev:
            db.rollback()
            return None,"NATIVE_SMS_ALREADY_REGISTERED"
    else:
        message=str(message or "").strip()
        if not message or len(message)>1000:
            db.rollback()
            return None,"INVALID_MESSAGE"
        prev=db.execute(_ns_text("""
          SELECT id FROM native_sms_v2_jobs WHERE phone=:phone AND message=:body
          AND created_at > NOW() - INTERVAL '1 day' LIMIT 1
        """),{"phone":normalized,"body":message}).first()
        if prev:
            db.rollback()
            return None,"IDENTICAL_SMS_ALREADY_REGISTERED"
    if len(message)>1000:
        db.rollback()
        return None,"MESSAGE_TOO_LONG"
    # Manual handoff does not touch the radio. Historical native SMS failures
    # must not block preparation of a new human-approved Google Messages draft.
    job_id=db.execute(_ns_text("""
      INSERT INTO native_sms_v2_jobs(phone,message,source,cycle_key,account_ids,status)
      VALUES (:phone,:body,:source,:cycle,:ids,'queued') RETURNING id
    """),{"phone":normalized,"body":message,"source":source,
          "cycle":cycle,"ids":ids}).scalar_one()
    db.add(AuditEvent(kind="native_sms_v2_queued",
                      message=f"job={job_id}; phone={normalized}; "
                              f"source={source}; account_ids={ids}; no send yet"))
    db.commit()
    return int(job_id),None


def _ns_debt_send(phone: str=_ns_Form(...),
                  cycle: str=_ns_Form(""),
                  message: str=_ns_Form(""),
                  db: _ns_Session=_ns_Depends(get_db)):
    job,err=_ns_enqueue(db,phone,"debt")
    if err:
        return _ns_error(err)
    return {"ok":True,"job_id":job,"status":"queued","moved":0}


def _ns_manual_send(phone: str=_ns_Form(...),message: str=_ns_Form(...),
                    db: _ns_Session=_ns_Depends(get_db)):
    job,err=_ns_enqueue(db,phone,"manual",message)
    if err:
        return _ns_Redirect("/sms?native_error="+err,303)
    return _ns_Redirect(f"/sms?native_queued=1&job={job}",303)


def _ns_status(job_id: int=0, db: _ns_Session=_ns_Depends(get_db)):
    if job_id <= 0:
        return _ns_error("INVALID_JOB",400)
    _ns_setup(db)
    row=db.execute(_ns_text("""
      SELECT id,status,source,created_at,sent_at,delivered_at,
             result_code,COALESCE(error,'') AS error
      FROM native_sms_v2_jobs WHERE id=:id
    """),{"id":job_id}).mappings().first()
    if row is None:
        return _ns_error("NOT_FOUND",404)
    # The response deliberately excludes phone and text.
    return {"ok":True,"id":row["id"],"status":row["status"],
            "source":row["source"],"result_code":row["result_code"],
            "error":row["error"][:150],
            "sent":row["sent_at"] is not None,
            "delivered":row["delivered_at"] is not None}


# The old AJAX widget expected immediate waiting and a redirect.
# Replace it with truthful async status polling. Wait for SMS sent callback
# before removing anyone from debts.
_NS_SCRIPT = r"""<script>
(function(){
  "use strict";
  if (window.__hesabNativeSmsV2) return;
  window.__hesabNativeSmsV2 = true;
  let busy=false;
  function notice(value, bad) {
    let n=document.getElementById("native-sms-v2-banner");
    if(!n){n=document.createElement("div");n.id="native-sms-v2-banner";
      n.setAttribute("role","status");
      n.style.cssText="position:fixed;bottom:24px;right:24px;z-index:999999;"+
        "padding:15px 21px;border-radius:12px;max-width:420px;"+
        "background:#19324a;color:white;font-size:14px;box-shadow:0 10px 30px #0006;";
      document.body.append(n);}
    n.style.background=bad?"#65312f":"#19324a";
    n.textContent=value;
  }
  document.addEventListener("submit", async function(e) {
    const f=e.target;
    if(!(f instanceof HTMLFormElement) || !f.matches("form[data-debt-sms-form]")) return;
    e.preventDefault();e.stopImmediatePropagation();
    if(busy)return;
    busy=true;
    const btn=f.querySelector("button[type=submit]");
    if(btn)btn.disabled=true;
    try {
      const r=await fetch("/sms/debt-send",{
        method:"POST",body:new FormData(f),credentials:"same-origin",
        headers:{"Accept":"application/json","X-Requested-With":"XMLHttpRequest"}});
      const a=await r.json();
      if(!r.ok || !a.ok){notice("پیامک ثبت نشد: "+(a.code||r.status),true);return}
      notice("پیام در گوشی آماده است. پس از زدن Send در Google Messages، وضعیت سایت خودکار به‌روز می‌شود.",false);
      // Compose opened is NOT sent. Watch only the authenticated backend
      // status, which advances after Android verifies the matching sent SMS.
      for(let i=0;i<160;i++){
        await new Promise(resolve=>setTimeout(resolve,3000));
        const result=await fetch("/sms/native-v2/status?job_id="+encodeURIComponent(a.job_id),
          {credentials:"same-origin",cache:"no-store"});
        if(!result.ok)continue;
        const state=await result.json();
        if(state.status==="sent" || state.status==="delivered"){
          notice("ارسال در گوشی تأیید شد؛ مشتری به در انتظار منتقل می‌شود.",false);
          window.setTimeout(()=>window.location.reload(),700);
          return;
        }
        if(state.status==="cancelled"){
          notice("پیش‌نویس بدون ارسال لغو شد؛ وضعیت مشتری تغییر نکرد.",true);
          return;
        }
      }
      notice("هنوز تأیید ارسال دریافت نشده. در صورت ارسال واقعی، سایت بعد از تأیید گوشی به‌روزرسانی می‌شود.",true);
    } catch (_) {
      notice("نتیجه ثبت قطعی نیست؛ پیش از هر ارسال مجدد وضعیت را بررسی کن.",true);
    } finally {
      busy=false;
      if(btn)btn.disabled=false;
    }
  }, true);
})();
</script>"""

_ns_tpl=TEMPLATES.get("debts.html","")
pattern=_ns_re.compile(
    r'<script>\s*\(function\(\)\{\s*"use strict";\s*'
    r'if\(window\.__hesabSmsNoJumpV1\).*?</script>',_ns_re.S
)
_ns_tpl,_ns_count=pattern.subn(lambda m:_NS_SCRIPT,_ns_tpl,count=1)
if _ns_count != 1:
    raise RuntimeError("Native SMS: older debt AJAX script not found; refusing silent changes")
TEMPLATES["debts.html"]=_ns_tpl
_sms_page=TEMPLATES.get("sms.html","")
if _sms_page:
    _sms_page=_sms_page.replace(
        '{% if request.query_params.get("queued") %}',
        """{% if request.query_params.get("native_queued") %}
        <div class="sms-banner ok">درخواست برای بازکردن Google Messages در گوشی ثبت شد؛ ارسال نهایی دستی است.</div>
        {% endif %}
        {% if request.query_params.get("native_error") %}
        <div class="sms-banner bad">پیامک ثبت نشد: {{ request.query_params.get("native_error") }}</div>
        {% endif %}
        {% if request.query_params.get("queued") %}""",1)
    TEMPLATES["sms.html"]=_sms_page
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)


# Finally override the deliberate browser-only POST blockers.
app.router.routes[:]=[
  r for r in app.router.routes
  if not (getattr(r,"path",None) in
     ("/sms/send","/sms/debt-send") and
     "POST" in (getattr(r,"methods",set()) or set()))
]
app.add_api_route("/sms/debt-send",_ns_debt_send,methods=["POST"])
app.add_api_route("/sms/send",_ns_manual_send,methods=["POST"])
app.add_api_route("/sms/native-v2/status",_ns_status,methods=["GET"])
