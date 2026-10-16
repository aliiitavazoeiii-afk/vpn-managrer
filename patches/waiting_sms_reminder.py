# WAITING_SMS_REMINDER_V1
# Added after HESAB_NATIVE_SMS_V2_ADMIN, without changing payment, debt,
# or customer state. The operator queues a prewritten manual SMS draft.
from fastapi import Request as _ws_Request, Form as _ws_Form, Depends as _ws_Depends
from fastapi.responses import JSONResponse as _ws_JSON
from sqlalchemy.orm import Session as _ws_Session

_WS_BODY = "سلام وقت بخیر، اکانتتون تمدید بشه؟"
_WS_ALLOWED_ORIGIN = "https://hesab.filmjadiid.ir"

def _ws_queue_reminder(
    request: _ws_Request,
    phone: str = _ws_Form(...),
    db: _ws_Session = _ws_Depends(get_db),
):
    # Same-origin admin action. The existing main-app session middleware still
    # enforces admin authentication. No public device endpoint enqueues jobs.
    origin = request.headers.get("origin", "")
    ref = request.headers.get("referer", "")
    fetch_site = request.headers.get("sec-fetch-site", "")
    if (origin != _WS_ALLOWED_ORIGIN or
        not ref.startswith(_WS_ALLOWED_ORIGIN + "/") or
        fetch_site not in ("", "same-origin")):
        return _ws_JSON({"ok":False,"code":"ORIGIN_DENIED"},status_code=403)
    normalized = _ns_clean_phone(phone)
    if not normalized:
        return _ws_JSON({"ok":False,"code":"INVALID_PHONE"},status_code=400)
    # Only accounts that are actually still in the waiting-payment workflow.
    # Do not change an account's waiting state while queueing another reminder.
    states = _followup_states(db)
    now = today_local()
    active = db.query(Subscription).filter(
        Subscription.phone == normalized,
        Subscription.is_free.is_(False),
    ).all()
    if not any(
        states.get(s.id) == "waiting" and s.expiry_date is not None
        and current_debt_for(s,now)>0
        for s in active
    ):
        return _ws_JSON({"ok":False,"code":"NOT_IN_WAITING"},status_code=409)
    job_id,error = _ns_enqueue(db,normalized,"manual",_WS_BODY)
    if error:
        return _ws_JSON({"ok":False,"code":error},status_code=409)
    return {"ok":True,"job_id":job_id,"status":"queued",
            "message":_WS_BODY,"followup_state_unchanged":True}

# Do not replace unrelated followups/pay/... routes.
app.add_api_route("/followups/sms-reminder",_ws_queue_reminder,methods=["POST"])

_WS_BOX = r'''
<div class="waiting-sms-reminder-box" data-waiting-sms-reminder-box>
  <div class="waiting-sms-reminder-title">✉ پیامک یادآوری تمدید</div>
  <div class="waiting-sms-reminder-text">سلام وقت بخیر، اکانتتون تمدید بشه؟</div>
  <div class="waiting-sms-reminder-actions">
    {% if g.phone %}
      <button type="button" class="waiting-sms-reminder-btn"
              data-waiting-sms-remind data-phone="{{ g.phone }}"
              title="افزودن پیام به صف گوشی، بدون ارسال خودکار">افزودن به صف پیامک</button>
    {% else %}
      <button type="button" class="waiting-sms-reminder-btn" disabled>شماره موبایل ندارد</button>
    {% endif %}
    <span class="waiting-sms-reminder-result" role="status" aria-live="polite"></span>
  </div>
</div>
'''

_WS_STYLE = r'''
<style>
.waiting-sms-reminder-box{margin:12px 4px 18px;padding:15px 17px;
  background:linear-gradient(125deg,rgba(38,62,91,.50),rgba(15,25,40,.80));
  border:1px solid rgba(135,176,223,.23);border-radius:14px;text-align:right;
  display:flex;flex-direction:column;gap:10px}
.waiting-sms-reminder-title{font-size:12px;font-weight:800;color:#dbe9fa}
.waiting-sms-reminder-text{padding:11px 13px;border-radius:10px;
  background:#0c1523;color:#edf3fc;border:1px solid rgba(167,188,216,.12);
  font-size:13px;line-height:1.9}
.waiting-sms-reminder-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.waiting-sms-reminder-btn{font:inherit;font-size:12px;font-weight:800;
  background:#d9e8ff;color:#10213b;border:0;border-radius:10px;
  padding:11px 15px;cursor:pointer}
.waiting-sms-reminder-btn:disabled{opacity:.55;cursor:not-allowed}
.waiting-sms-reminder-result{font-size:11px;color:#b9d1ea;line-height:1.9}
@media(max-width:650px){.waiting-sms-reminder-btn{width:100%}}
</style>
'''

_WS_SCRIPT = r'''
<script>
(function(){
  "use strict";
  if(window.__hesabWaitingSmsReminderV1)return;
  window.__hesabWaitingSmsReminderV1=true;
  document.addEventListener("click",async function(e){
    const btn=e.target.closest("[data-waiting-sms-remind]");
    if(!btn)return;
    e.preventDefault();e.stopPropagation();
    if(btn.disabled)return;
    const box=btn.closest("[data-waiting-sms-reminder-box]");
    const result=box&&box.querySelector(".waiting-sms-reminder-result");
    const number=btn.getAttribute("data-phone")||"";
    if(!/^09[0-9]{9}$/.test(number)){
      if(result)result.textContent="شماره همراه معتبر نیست.";
      return;
    }
    btn.disabled=true;
    if(result)result.textContent="در حال ثبت درخواست در صف اپ...";
    try{
      const data=new FormData();data.set("phone",number);
      const response=await fetch("/followups/sms-reminder",{
        method:"POST",body:data,credentials:"same-origin",cache:"no-store",
        headers:{"Accept":"application/json","X-Requested-With":"XMLHttpRequest"}
      });
      const json=await response.json();
      if(!response.ok||!json.ok){
        if(result)result.textContent=json.code==="IDENTICAL_SMS_ALREADY_REGISTERED"?
          "این پیام برای این شماره طی ۲۴ ساعت گذشته در صف ثبت شده است.":
          "درخواست ثبت نشد: "+(json.code||response.status);
        return;
      }
      if(result)result.textContent="✓ پیام به صف اپ افزوده شد؛ ارسال نهایی با شماست.";
    }catch(_){
      if(result)result.textContent="وضعیت ثبت مشخص نیست؛ پیش از تکرار، صف اپ را بررسی کن.";
    }finally{
      btn.disabled=false;
    }
  },true);
})();
</script>
'''

_ws_tpl = TEMPLATES.get("followups.html","")
_ws_anchor = '<div class="waiting-services" data-waiting-panel="{{ loop.index0 }}" hidden>'
if _ws_tpl.count(_ws_anchor)!=1 or "data-waiting-sms-reminder-box" in _ws_tpl:
    raise RuntimeError("Waiting SMS: unexpected followups template; refusing to patch")
_ws_tpl=_ws_tpl.replace(_ws_anchor,_ws_anchor+"\n"+_WS_BOX,1)
if _ws_tpl.count("{% block content %}")!=1 or _ws_tpl.count("{% endblock %}")<1:
    raise RuntimeError("Waiting SMS: template blocks changed; refusing patch")
_ws_tpl=_ws_tpl.replace("{% block content %}","{% block content %}\n"+_WS_STYLE,1)
_end=_ws_tpl.rfind("{% endblock %}")
_ws_tpl=_ws_tpl[:_end]+_WS_SCRIPT+"\n"+_ws_tpl[_end:]
TEMPLATES["followups.html"]=_ws_tpl
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)
