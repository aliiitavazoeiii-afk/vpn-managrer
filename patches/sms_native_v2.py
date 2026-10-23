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
          SELECT id,status,message FROM native_sms_v2_jobs
          WHERE source='debt' AND phone=:phone AND cycle_key=:cycle
          LIMIT 1
        """),{"phone":normalized,"cycle":cycle}).mappings().first()
        if prev:
            # A one-time explicit corrected copy can be prepared even though
            # a previous draft for this billing cycle exists. Never rewrite
            # the original record or bypass its unique (phone,cycle) index.
            # Label the new draft as manual: opening it must not repeat a
            # financial followup transition for the same customer.
            old_status=str(prev["status"] or "")
            old_body=str(prev["message"] or "")
            if (old_status in ("cancelled","operator_opened","sent","delivered")
                and (old_body!=message or old_status=="cancelled")):
                source="manual"
                cycle=None
                ids=[]
            elif old_status in ("queued","claimed","opened","uncertain",
                                 "attempting","failed"):
                db.rollback()
                return None,"PREVIOUS_SMS_UNCERTAIN_OR_PENDING_REVIEW"
            else:
                db.rollback()
                return None,"NATIVE_SMS_ALREADY_REGISTERED"
    if source=="manual":
        message=str(message or "").strip()
        if not message or len(message)>1000:
            db.rollback()
            return None,"INVALID_MESSAGE"
        prev=db.execute(_ns_text("""
          SELECT id FROM native_sms_v2_jobs WHERE phone=:phone AND message=:body
          AND status <> 'cancelled'
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
      notice("درخواست به صف گوشی اضافه شد. می‌توانی برای بقیه مشتری‌ها هم درخواست ثبت کنی؛ در اپ با بازکردن هر پیام، همان مشتری به «در انتظار» می‌رود.",false);
      // No wait for Android: all customer requests can be queued in one visit.
      // The operator-open endpoint is responsible for followup_waiting.
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


# HESAB_WAITING_RENEWAL_SMS_V1
# Inject one manual-reminder action alongside full settlement and restore-all.
# Does NOT pay, clear a debt, update followup states, or transmit an SMS.
from fastapi import Form as _wr_Form, Depends as _wr_Depends
from fastapi.responses import JSONResponse as _wr_JSON
from sqlalchemy.orm import Session as _wr_Session

_WR_MESSAGE = "سلام وقت بخیر، اکانتتون تمدید بشه؟"

def _wr_queue(
    phone: str = _wr_Form(""),
    db: _wr_Session = _wr_Depends(get_db),
):
    normalized = _ns_clean_phone(phone)
    if not normalized:
        return _wr_JSON({"ok":False,"code":"INVALID_PHONE"},status_code=400)
    # Do not create reminder drafts for users no longer in waiting.
    states = _followup_states(db)
    subs = db.query(Subscription).filter(
        Subscription.phone == normalized, Subscription.is_free.is_(False)
    ).all()
    today = today_local()
    waiting = any(
        states.get(int(sub.id)) == "waiting"
        and sub.expiry_date is not None
        and current_debt_for(sub, today)>0
        for sub in subs
    )
    if not waiting:
        return _wr_JSON({"ok":False,"code":"NOT_WAITING"},status_code=409)
    job_id, error = _ns_enqueue(db,normalized,"manual",_WR_MESSAGE)
    if error:
        return _wr_JSON({"ok":False,"code":error},status_code=409)
    return {"ok":True,"status":"queued","job_id":job_id,
            "sent":False,"followup_changed":False}

if not any(getattr(route,"path",None)=="/sms/waiting-renewal"
           for route in app.router.routes):
    app.add_api_route("/sms/waiting-renewal", _wr_queue,methods=["POST"])

_WR_FORM = r"""
        <form method="post" action="/sms/waiting-renewal"
              class="waiting-renewal-form" data-waiting-renewal-form>
          <input type="hidden" name="phone" value="{{ g.phone or '' }}">
          {% if g.phone %}
          <button type="submit" class="waiting-renewal-btn"
            title="سلام وقت بخیر، اکانتتون تمدید بشه؟">✉ پیامک تمدید</button>
          {% else %}
          <button type="button" class="waiting-renewal-btn" disabled
            title="شماره همراه موجود نیست">بدون شماره</button>
          {% endif %}
        </form>
"""
_WR_STYLE_SCRIPT = r"""
<style>
.waiting-renewal-form{display:inline-flex;align-items:center;margin:0;min-width:0}
.waiting-renewal-btn{min-height:34px;padding:6px 12px;border-radius:9px;
 background:rgba(105,168,255,.12);border:1px solid rgba(105,168,255,.45);
 color:#c5deff;font:inherit;font-size:11px;font-weight:800;
 cursor:pointer;white-space:nowrap}
.waiting-renewal-btn:hover{background:rgba(105,168,255,.22)}
.waiting-renewal-btn:disabled{opacity:.5;cursor:not-allowed}
.waiting-renewal-feedback{position:fixed;bottom:20px;right:20px;z-index:30000;
 background:#15334c;color:#e6f4ff;border:1px solid #396f9d;
 border-radius:12px;padding:12px 17px;max-width:min(430px,calc(100vw - 40px));
 font-size:12px;line-height:1.8;box-shadow:0 12px 35px #0006}
.waiting-renewal-feedback.error{background:#48222c;border-color:#bb6674;color:#fff0f0}
@media(max-width:780px){.waiting-renewal-form{flex:1 1 auto}.waiting-renewal-btn{width:100%}}
</style>
<script>
(function(){
  "use strict";
  if(window.__hesabWaitingRenewalSms)return;
  window.__hesabWaitingRenewalSms=true;
  let timer=0;
  function flash(text,error){
    let el=document.getElementById("waiting-renewal-feedback");
    if(!el){
      el=document.createElement("div");
      el.id="waiting-renewal-feedback";
      el.className="waiting-renewal-feedback";
      el.setAttribute("role","status");
      document.body.append(el);
    }
    el.classList.toggle("error",!!error);
    el.textContent=text;
    clearTimeout(timer);
    timer=setTimeout(()=>el.remove(),6500);
  }
  // Capture before waiting_live's generic POST listener, so a reminder
  // cannot accidentally trigger its financial/payment UI logic.
  document.addEventListener("submit",async function(event){
    const form=event.target;
    if(!(form instanceof HTMLFormElement) ||
       !form.matches('form[data-waiting-renewal-form]'))return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if(form.dataset.sending==="1")return;
    form.dataset.sending="1";
    const btn=form.querySelector("button[type=submit]");
    if(btn)btn.disabled=true;
    try{
      const response=await fetch("/sms/waiting-renewal",{
        method:"POST",body:new FormData(form),credentials:"same-origin",
        cache:"no-store",headers:{"Accept":"application/json",
        "X-Requested-With":"XMLHttpRequest"}});
      const data=await response.json();
      if(!response.ok || !data.ok){
        if(data.code==="IDENTICAL_SMS_ALREADY_REGISTERED"){
          flash("این پیام تمدید قبلاً برای این شماره در ۲۴ ساعت گذشته ثبت شده است.",true);
        }else{
          flash("درخواست پیامک ثبت نشد: "+(data.code||response.status),true);
        }
        return;
      }
      flash("پیامک تمدید به صف اپ اضافه شد؛ در گوشی آن را باز کن و دستی بفرست.",false);
      btn.textContent="✓ در صف گوشی";
      btn.disabled=true;
      form.dataset.queued="1";
    }catch(_){
      flash("وضعیت درخواست نامشخص است؛ قبل از تکرار، صف گوشی را بررسی کن.",true);
    }finally{
      form.dataset.sending="0";
      if(btn && form.dataset.queued!=="1")btn.disabled=false;
    }
  },true);
})();
</script>
"""
_wr_tpl = TEMPLATES.get("followups.html","")
if not _wr_tpl:
    raise RuntimeError("Waiting renewal SMS: followups template missing")
if "data-waiting-renewal-form" not in _wr_tpl:
    # The final settled header contains payment, actual amount, restore-all;
    # insert before its closing div, immediately beside those controls.
    _wr_re = _ns_re.compile(
      r'(<div class="waiting-head-pay waiting-pay-tools">[\s\S]*?)'
      r'(</div>\s*(?=<span class="waiting-chevron">))',
      _ns_re.S
    )
    _wr_tpl, _wr_count = _wr_re.subn(
        lambda m:m.group(1)+_WR_FORM+m.group(2),
        _wr_tpl, count=1
    )
    if _wr_count!=1:
        raise RuntimeError("Waiting renewal SMS: group-action header not found")
    # Must remain within the last content block and be independent of
    # the waiting page's existing payment handlers.
    _wr_end=_wr_tpl.rfind("{% endblock %}")
    if _wr_end < 0:
        raise RuntimeError("Waiting renewal SMS: template block not found")
    _wr_tpl=_wr_tpl[:_wr_end]+_WR_STYLE_SCRIPT+"\n"+_wr_tpl[_wr_end:]
    TEMPLATES["followups.html"]=_wr_tpl
    if hasattr(env.loader,"mapping"):
        env.loader.mapping.update(TEMPLATES)
