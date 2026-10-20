# HESAB_OPERATOR_WORKSPACE_V5
# Read-oriented users/payments improvements + admin-editable SMS text.
# Post /sms/send (manual send form) is retired. No automatic SMS transmission.
from datetime import datetime as _op_dt, timedelta as _op_td, timezone as _op_tz
from zoneinfo import ZoneInfo as _op_zone
import re as _op_re
from fastapi import Request as _op_Request, Depends as _op_Depends, Form as _op_Form
from fastapi.responses import JSONResponse as _op_JSON, RedirectResponse as _op_Redirect
from sqlalchemy import text as _op_text
from sqlalchemy.orm import Session as _op_Session

_OP_TZ = _op_zone("Asia/Tehran")
_OP_ADMIN_ORIGIN = "https://hesab.filmjadiid.ir"
_OP_DEF_DEBT = (
    "سلام اکانت شما {تاریخ_انقضا} تمام شده.\n"
    "برای تمدید با شماره همراه خودتون وارد این سایت بشید و نسبت به پرداخت اقدام فرمایید.\n\n"
    "usersmanager.ir"
)
_OP_DEF_WAITING = (
    "سلام اکانت شما {تاریخ_انقضا} تمام شده.\n"
    "برای تمدید با شماره همراه خودتون وارد این سایت بشید و نسبت به پرداخت اقدام فرمایید.\n\n"
    "usersmanager.ir"
)
_OP_DEFAULTS = {"debt":_OP_DEF_DEBT,"waiting":_OP_DEF_WAITING}
_OP_TOKENS = frozenset(("{تاریخ_انقضا}","{نام_کاربر}"))
_OP_DDL = """
CREATE TABLE IF NOT EXISTS sms_default_texts (
    scope VARCHAR(16) PRIMARY KEY,
    body TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

def _op_sms_initialize(db):
    db.execute(_op_text(_OP_DDL))
    for scope, body in _OP_DEFAULTS.items():
        db.execute(_op_text("""
          INSERT INTO sms_default_texts(scope,body) VALUES (:scope,:body)
          ON CONFLICT(scope) DO NOTHING
        """), {"scope":scope,"body":body})

def _op_sms_get(db):
    _op_sms_initialize(db)
    found=db.execute(_op_text("""
        SELECT scope,body FROM sms_default_texts
        WHERE scope IN ('debt','waiting')
    """)).mappings().all()
    return {r["scope"]:r["body"] for r in found}

def _op_sms_validate(value):
    value=str(value or "").replace("\r\n","\n").strip()
    if not value or len(value)>1000:
        raise ValueError("INVALID_TEXT_LENGTH")
    # Detect braces reliably: unknown tokens would otherwise be sent literally.
    for token in _op_re.findall(r"\{[^{}]*\}",value):
        if token not in _OP_TOKENS:
            raise ValueError("UNKNOWN_VARIABLE")
    if "{" in value.replace("{تاریخ_انقضا}","").replace("{نام_کاربر}","") or \
       "}" in value.replace("{تاریخ_انقضا}","").replace("{نام_کاربر}",""):
        raise ValueError("INVALID_BRACES")
    if "{تاریخ_انقضا}" not in value:
        raise ValueError("EXPIRY_REQUIRED")
    return value

def _op_sms_render(db, scope, expiry, name=""):
    if scope not in _OP_DEFAULTS or expiry is None:
        raise ValueError("SMS template or expiry missing")
    templates=_op_sms_get(db)
    text=templates.get(scope) or _OP_DEFAULTS[scope]
    # Uses existing proven Jalali date display; no browser-supplied date.
    label=_ews_expiry_label(expiry) if callable(globals().get("_ews_expiry_label")) else jdate(expiry)
    return text.replace("{تاریخ_انقضا}",label).replace("{نام_کاربر}",str(name or "کاربر"))

_OP_SMS_TEMPLATE = r'''{% extends "base.html" %}
{% block title %}تنظیم متن پیامک‌ها · حساب VPN{% endblock %}
{% block heading %}متن‌های پیش‌فرض پیامک{% endblock %}
{% block subheading %}این متن‌ها هنگام ثبت درخواست هر مشتری با تاریخ انقضای واقعی او در صف گوشی قرار می‌گیرند{% endblock %}
{% block content %}
<style>
.op-sms-setting{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px}
.op-sms-card{background:rgba(15,24,39,.85);border:1px solid #2b4056;border-radius:16px;padding:19px;display:flex;flex-direction:column;gap:12px}
.op-sms-card h2{font-size:17px;margin:0;color:#e8f3ff}.op-sms-card p{font-size:12px;line-height:1.9;color:#a3b7ca;margin:0}
.op-sms-card textarea{width:100%;min-height:190px;resize:vertical;background:#0d1829;color:#f4f8ff;line-height:2;direction:rtl;
 font:inherit;border:1px solid #416181;border-radius:12px;padding:13px;box-sizing:border-box}
.op-sms-card button{background:#dcecff;color:#182b41;border:0;border-radius:10px;font:inherit;font-weight:850;padding:12px;cursor:pointer}
.op-sms-example{margin:0 0 15px;color:#adc6de;line-height:2;font-size:13px}
.op-sms-message{background:#183d34;border:1px solid #366b60;color:#dafff4;padding:12px;margin-bottom:12px;border-radius:11px}
.op-sms-message.error{background:#4a282d;color:#ffdddd;border-color:#854a53}
@media(max-width:750px){.op-sms-setting{grid-template-columns:1fr}}
</style>
<p class="op-sms-example">در متن از <code>{تاریخ_انقضا}</code> برای روز و ماه انقضای واقعی هر مشتری (مثلاً ۶ مهر) و در صورت نیاز <code>{نام_کاربر}</code> استفاده کن. تاریخ هر شماره از قدیمی‌ترین اشتراک واجد شرایط در همان فهرست خوانده می‌شود. ارسال نهایی در Google Messages دستی است.</p>
{% if request.query_params.get("saved") %}<div class="op-sms-message">✓ متن پیش‌فرض ذخیره شد؛ درخواست‌های جدید از آن استفاده می‌کنند.</div>{% endif %}
{% if request.query_params.get("error") %}<div class="op-sms-message error">قالب ذخیره نشد. وجود {تاریخ_انقضا}، طول کمتر از هزار کاراکتر و صحت متغیرها را بررسی کن.</div>{% endif %}
<div class="op-sms-setting">
{% for type,title,description in types %}
<form class="op-sms-card" method="post" action="/sms/templates/save">
<h2>{{ title }}</h2>
<p>{{ description }}</p>
<input type="hidden" name="scope" value="{{ type }}">
<textarea name="body" rows="7" maxlength="1000" required>{{ templates[type] }}</textarea>
<button type="submit">ذخیره متن {{ title }}</button>
</form>
{% endfor %}
</div>
{% endblock %}'''
TEMPLATES["sms.html"]=_OP_SMS_TEMPLATE

def _op_sms_settings(request:_op_Request,db:_op_Session=_op_Depends(get_db)):
    templates=_op_sms_get(db)
    db.commit()
    return render("sms.html",request,templates=templates,types=[
        ("debt","وصول بدهی","متن این قسمت هنگام افزودن مشتری از لیست وصول بدهی به صف اپ استفاده می‌شود."),
        ("waiting","در انتظار پرداخت","متن این قسمت با گزینه پیامک تمدید در صفحه در انتظار پرداخت استفاده می‌شود.")
    ])

def _op_sms_save(request:_op_Request,scope:str=_op_Form(""),
                 body:str=_op_Form(""),db:_op_Session=_op_Depends(get_db)):
    # This POST changes only editable templates. The admin session middleware
    # still guards the route; same-origin check prevents cross-site form POST.
    if (request.headers.get("origin","")!=_OP_ADMIN_ORIGIN or
        not request.headers.get("referer","").startswith(_OP_ADMIN_ORIGIN+"/") or
        request.headers.get("sec-fetch-site","") not in ("","same-origin")):
        return _op_JSON({"ok":False,"error":"origin"},status_code=403)
    if scope not in _OP_DEFAULTS:
        return _op_Redirect("/sms?error=scope",303)
    try:
        validated=_op_sms_validate(body)
        _op_sms_initialize(db)
        db.execute(_op_text("""
          UPDATE sms_default_texts SET body=:body,updated_at=NOW() WHERE scope=:scope
        """), {"scope":scope,"body":validated})
        db.add(AuditEvent(kind="sms_template_edit",
                          message=f"Default SMS text updated for scope={scope}; no outgoing message sent"))
        db.commit()
    except Exception:
        db.rollback()
        return _op_Redirect("/sms?error=body",303)
    return _op_Redirect("/sms?saved="+scope,303)

def _op_no_manual_send():
    return _op_JSON({"ok":False,"error":"manual_form_retired"},status_code=410)

# Waiting reminders use exactly the stored body for this role. They never set
# payment status, move followups, or treat opening the SMS app as carrier send.
def _op_waiting_sms(request:_op_Request,phone:str=_op_Form(""),
                    db:_op_Session=_op_Depends(get_db)):
    if (request.headers.get("origin","")!=_OP_ADMIN_ORIGIN or
        not request.headers.get("referer","").startswith(_OP_ADMIN_ORIGIN+"/") or
        request.headers.get("sec-fetch-site","") not in ("","same-origin")):
        return _op_JSON({"ok":False,"code":"ORIGIN_DENIED"},status_code=403)
    phone=_ns_clean_phone(phone)
    if not phone:
        return _op_JSON({"ok":False,"code":"INVALID_PHONE"},status_code=400)
    states=_followup_states(db)
    now=today_local()
    candidates=db.query(Subscription).filter(
        Subscription.phone==phone,Subscription.is_free.is_(False)
    ).all()
    waiting=[s for s in candidates if states.get(int(s.id))=="waiting"
             and s.expiry_date is not None and s.expiry_date<=now
             and current_debt_for(s,now)>0]
    if not waiting:
        return _op_JSON({"ok":False,"code":"NOT_IN_WAITING"},status_code=409)
    earliest=min(s.expiry_date for s in waiting)
    first=min(waiting,key=lambda s:(s.expiry_date,s.id))
    message=_op_sms_render(db,"waiting",earliest,first.display_name)
    job_id,error=_ns_enqueue(db,phone,"manual",message)
    if error:
        return _op_JSON({"ok":False,"code":error},status_code=409)
    return {"ok":True,"status":"queued","job_id":job_id,"sent":False,
            "followup_state_unchanged":True}

# Remove generic SMS compose UI endpoint. Keep legacy database entries intact.
for _path,_method in (
    ("/sms","GET"),
    ("/sms/send","POST"),
    ("/sms/templates/save","POST"),
    ("/sms/waiting-renewal","POST"),
    ("/followups/sms-reminder","POST"),
):
    app.router.routes[:]=[
       r for r in app.router.routes if not (
           getattr(r,"path",None)==_path and
           _method in (getattr(r,"methods",set()) or set())
       )
    ]
app.add_api_route("/sms",_op_sms_settings,methods=["GET"])
app.add_api_route("/sms/send",_op_no_manual_send,methods=["POST"])
app.add_api_route("/sms/templates/save",_op_sms_save,methods=["POST"])
app.add_api_route("/sms/waiting-renewal",_op_waiting_sms,methods=["POST"])
app.add_api_route("/followups/sms-reminder",_op_waiting_sms,methods=["POST"])

# Avoid stale text in preexisting waiting preview; the text is now edited
# centrally, and dynamically populated when the operator queues a reminder.
_op_wait=TEMPLATES.get("followups.html","")
if _op_wait:
    _op_wait=_op_wait.replace(
        '<div class="waiting-sms-reminder-text">{{ g.first_expiry|ews_message }}</div>',
        '<div class="waiting-sms-reminder-text">متن این پیام از بخش «پیامک» خوانده می‌شود و تاریخ انقضای هر مشتری خودکار جایگزین می‌شود.</div>'
    ).replace(
        'title="{{ g.first_expiry|ews_message }}"',
        'title="متن قابل تنظیم در صفحه پیامک‌ها؛ تاریخ انقضا خودکار"'
    )
    TEMPLATES["followups.html"]=_op_wait

# ---- Recently added users: last 10 (newest subscription ID first). ----
# Subscription IDs increase at insert time even on older imported accounts;
# full directory remains searchable, paged 10 visible records at a time.
_OP_USER_PAGE_JS=r'''
<script>
(function(){
  const input=document.getElementById("lc-q"),
        filter=document.getElementById("lc-filter"),
        container=document.getElementById("lc-list"),
        counter=document.getElementById("lc-count");
  if(!input||!filter||!container||!counter)return;
  const rows=[...container.querySelectorAll("[data-lc-row]")];
  const normalize=s=>String(s||"").toLowerCase()
    .replace(/ي/g,"ی").replace(/ك/g,"ک")
    .replace(/[۰-۹]/g,c=>"۰۱۲۳۴۵۶۷۸۹".indexOf(c))
    .replace(/[٠-٩]/g,c=>"٠١٢٣٤٥٦٧٨٩".indexOf(c));
  let page=1;
  const nav=document.getElementById("op-users-pages");
  const apply=()=>{
    const q=normalize(input.value.trim()),f=filter.value;
    const matched=rows.filter(el=>
       (!f||el.dataset.status===f)&&(!q||normalize(el.dataset.search).includes(q)));
    const pages=Math.max(1,Math.ceil(matched.length/10));
    page=Math.max(1,Math.min(page,pages));
    for(const row of rows)row.hidden=true;
    for(const row of matched.slice((page-1)*10,page*10))row.hidden=false;
    const fa=n=>String(n).replace(/\d/g,d=>"۰۱۲۳۴۵۶۷۸۹"[d]);
    counter.textContent=fa(matched.length)+" نتیجه · صفحه "+fa(page)+" از "+fa(pages);
    document.getElementById("lc-empty").hidden=matched.length!==0;
    nav.innerHTML="";
    const prev=document.createElement("button"),next=document.createElement("button");
    prev.textContent="صفحه قبل";next.textContent="صفحه بعد";
    prev.disabled=page===1;next.disabled=page===pages;
    prev.onclick=()=>{page--;apply()};
    next.onclick=()=>{page++;apply()};
    nav.append(prev,document.createTextNode(" "+fa(page)+" / "+fa(pages)+" "),next);
  };
  input.addEventListener("input",()=>{page=1;apply()});
  filter.addEventListener("change",()=>{page=1;apply()});
  const q=new URLSearchParams(location.search).get("q");
  if(q)input.value=q;
  apply();
})();
</script>
'''
_op_user_tpl=TEMPLATES.get("user_status.html","")
if not _op_user_tpl or 'id="lc-list"' not in _op_user_tpl:
    raise RuntimeError("Operator workspace: searchable users template unavailable")
_op_old_script_start=_op_user_tpl.rfind("<script>")
_op_old_script_end=_op_user_tpl.rfind("</script>")
if _op_old_script_start<0 or _op_old_script_end<_op_old_script_start:
    raise RuntimeError("Operator workspace: user list script unavailable")
_op_user_tpl=_op_user_tpl[:_op_old_script_start]+_OP_USER_PAGE_JS+_op_user_tpl[_op_old_script_end+9:]
_op_user_tpl=_op_user_tpl.replace(
    '<p id="lc-empty" hidden>',
    '<div id="op-users-pages" class="op-users-pages" style="display:flex;gap:13px;align-items:center;justify-content:center;margin:14px 0"></div><p id="lc-empty" hidden>',1
)
_op_user_tpl=_op_user_tpl.replace(
    '<div class="lc-count" id="lc-count">',
    '<p style="font-size:12px;color:#9ec4ee">۱۰ کاربر آخر در صفحه اول؛ برای جست‌وجو همه سوابق بررسی می‌شوند.</p><div class="lc-count" id="lc-count">',
    1
)
TEMPLATES["user_status.html"]=_op_user_tpl

def _op_all_users(request:_op_Request, db:_op_Session=_op_Depends(get_db)):
    refresh_billing(db)
    states=_followup_states(db)
    rows=[]
    for s in db.query(Subscription).order_by(Subscription.id.desc()).all():
        state=states.get(int(s.id))
        if state=="cut":key,label="cut","حذفی / آرشیوشده"
        elif state=="waiting":key,label="waiting","در انتظار پرداخت"
        elif current_debt_for(s,today_local())>0:key,label="debt","بدهکار / وصول"
        else:key,label="active","فعال / بدون بدهی"
        rows.append({"s":s,"state":key,"label":label})
    return render("user_status.html",request,rows=rows,legacy=_lc_legacy_deleted(db))

# Safe GET overrides only. Keep /users/{sid} profile and add/delete POST routes.
for _path in ("/user-status","/users"):
    app.router.routes[:]=[r for r in app.router.routes
        if not (getattr(r,"path",None)==_path and "GET" in (getattr(r,"methods",set()) or set()))]
    app.add_api_route(_path,_op_all_users,methods=["GET"])

# On /add-user, show the same ten latest entries, including the fresh POST
# redirect result. The original create POST remains entirely unchanged.
_OP_ADD_RECENT=r'''
<section class="op-recent-users" style="margin-top:18px;padding:18px;border:1px solid #30415b;border-radius:16px;background:#111c2d">
<h2 style="font-size:18px;margin:0 0 12px">۱۰ کاربر آخری که اضافه شده‌اند</h2>
{% for s in recent_users %}
<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 0;border-top:1px solid #2b3a50;flex-wrap:wrap">
<div><b>{{ s.display_name }}</b><small style="display:block;color:#a4b5ca">شناسه {{ s.id|fa }} · {{ s.phone or 'بدون شماره' }} · انقضا {{ s.expiry_date|jdate }}</small></div>
<a href="/users/{{ s.id }}" style="color:#badbff">پروفایل ←</a>
</div>
{% else %}<p>هنوز کاربری وجود ندارد.</p>{% endfor %}
<a href="/users" style="display:inline-block;margin-top:13px;color:#a9d6ff">مشاهده و جست‌وجوی همه کاربران ←</a>
</section>
'''
_op_add_tpl=TEMPLATES.get("add_user_page.html","")
if not _op_add_tpl:
    raise RuntimeError("Operator workspace: add-user page missing")
_op_add_end=_op_add_tpl.rfind("{% endblock %}")
_op_add_tpl=_op_add_tpl[:_op_add_end]+_OP_ADD_RECENT+_op_add_tpl[_op_add_end:]
TEMPLATES["add_user_page.html"]=_op_add_tpl

def _op_add_user_page(request:_op_Request,db:_op_Session=_op_Depends(get_db)):
    d=today_local()
    try:parts=_date_guard_g2j(d.year,d.month,d.day)
    except Exception:parts=_g2j(d.year,d.month,d.day)
    recent=db.query(Subscription).order_by(Subscription.id.desc()).limit(10).all()
    return render("add_user_page.html",request,today_jparts=parts,recent_users=recent)

app.router.routes[:]=[r for r in app.router.routes
    if not (getattr(r,"path",None)=="/add-user" and "GET" in (getattr(r,"methods",set()) or set()))]
app.add_api_route("/add-user",_op_add_user_page,methods=["GET"])

# ---- Financial history: group by actual paid_at date + search ALL records. ----
# Preserve the original undo endpoint, guard, and every stored amount.
_OP_PAYMENTS_TEMPLATE=r'''{% extends "base.html" %}
{% block title %}پرداختی‌ها · حساب VPN{% endblock %}
{% block heading %}تاریخچه پرداخت‌ها{% endblock %}
{% block subheading %}پرداخت‌های امروز، دیروز و روزهای قبل بر اساس زمان ثبت واقعی{% endblock %}
{% block content %}
<style>
.op-pay-search{width:100%;box-sizing:border-box;background:#101d2e;border:1px solid #486381;border-radius:12px;
 font:inherit;color:#eaf4ff;padding:13px;margin:0 0 15px}
.op-pay-day{border:1px solid #2b3b50;border-radius:14px;margin:12px 0 20px;overflow:hidden}
.op-pay-day h2{margin:0;padding:12px 15px;background:#17263b;font-size:15px;color:#e2f1ff}
.op-pay-entry{display:grid;grid-template-columns:minmax(145px,1.3fr) minmax(110px,.8fr) minmax(160px,1fr) minmax(130px,1fr);gap:10px;align-items:center;
 padding:13px 15px;border-top:1px solid #2e3b4b;font-size:12px}
.op-pay-entry b{color:#b5f598}.op-pay-entry a{color:#bcdcff;text-decoration:none}
.op-pay-note{display:block;color:#9caab8;font-size:11px;margin-top:3px}
.op-pay-undo{border:1px solid #82444e;background:#402831;color:#ffe1e1;border-radius:9px;padding:8px;font:inherit;cursor:pointer}
.op-pay-undo:disabled{opacity:.45;cursor:not-allowed}
.op-pay-empty{padding:15px;color:#a3b5c6}
@media(max-width:720px){.op-pay-entry{grid-template-columns:1fr 1fr}.op-pay-entry>div:last-child{grid-column:1/-1}}
</style>
{% if request.query_params.get("undone") %}<div class="pay-banner">✓ پرداخت اشتباهی برگشت داده شد.</div>{% endif %}
{% if request.query_params.get("undo_error") %}<div class="pay-banner err">این پرداخت قابل برگشت نیست.</div>{% endif %}
<input id="op-pay-query" class="op-pay-search" type="search" autocomplete="off" placeholder="جست‌وجوی نام مشتری، شماره موبایل، شناسه اکانت یا مبلغ...">
<p id="op-pay-count" style="color:#a2b5ca;font-size:12px"></p>
<div id="op-pay-groups">
{% for day in days %}
<section class="op-pay-day">
<h2>{{ day.label }} · {{ day.items|length|fa }} پرداخت · {{ day.total|money }} تومان</h2>
{% for item in day.items %}
<div class="op-pay-entry" data-op-pay-row data-search="{{ item.search|e }}">
<div>{% if item.s %}<a href="/users/{{ item.s.id }}"><strong>{{ item.s.display_name }}</strong></a>
<small style="display:block">{{ item.s.phone or 'بدون شماره' }} · شناسه {{ item.s.id|fa }}</small>
{% else %}اکانت حذف‌شده · شناسه {{ item.p.subscription_id }}{% endif %}
<span class="op-pay-note">{{ item.p.note or '' }}</span></div>
<div><b>{{ item.p.amount_toman|money }} تومان</b><small style="display:block">ساعت {{ item.clock }}</small></div>
<div>انقضای قبل: {{ item.p.previous_expiry|jdate }}<br>انقضای بعد: {{ item.p.new_expiry|jdate }}</div>
<div>{% if item.undoable %}
<form method="post" action="/payments/{{ item.p.id }}/undo" onsubmit="return confirm('این پرداخت اشتباهی برگشت داده شود؟')">
<button class="op-pay-undo" type="submit">↶ لغو پرداخت</button></form>
{% else %}<button type="button" class="op-pay-undo" disabled>قابل برگشت نیست</button>{% endif %}</div>
</div>
{% endfor %}
</section>
{% else %}<div class="op-pay-empty">هنوز پرداختی ثبت نشده است.</div>{% endfor %}
</div>
<p id="op-pay-empty" class="op-pay-empty" hidden>پرداختی با این مشخصات پیدا نشد.</p>
<script>
(function(){
 const input=document.getElementById("op-pay-query"),groups=[...document.querySelectorAll(".op-pay-day")];
 const normalize=s=>String(s||"").toLowerCase().replace(/ي/g,"ی").replace(/ك/g,"ک")
   .replace(/[۰-۹]/g,c=>"۰۱۲۳۴۵۶۷۸۹".indexOf(c))
   .replace(/[٠-٩]/g,c=>"٠١٢٣٤٥٦٧٨٩".indexOf(c))
   .replace(/[,٬،\s]/g,"");
 const apply=()=>{
   const q=normalize(input.value),all=[...document.querySelectorAll("[data-op-pay-row]")];
   let shown=0;
   for(const g of groups){
     let n=0;
     for(const row of g.querySelectorAll("[data-op-pay-row]")){
       const show=!q||normalize(row.dataset.search).includes(q);
       row.hidden=!show;if(show){shown++;n++;}
     }
     g.hidden=n===0;
   }
   document.getElementById("op-pay-count").textContent=shown+" پرداخت";
   document.getElementById("op-pay-empty").hidden=shown!==0||all.length===0;
 };
 input.addEventListener("input",apply);apply();
})();
</script>
{% endblock %}'''
TEMPLATES["payments.html"]=_OP_PAYMENTS_TEMPLATE

def _op_local_payment_time(value):
    if value is None:return None
    if value.tzinfo is None:
        value=value.replace(tzinfo=_op_tz.utc)
    return value.astimezone(_OP_TZ)

def _op_payments_page(request:_op_Request,db:_op_Session=_op_Depends(get_db)):
    payments=db.query(Payment).order_by(Payment.paid_at.desc(),Payment.id.desc()).all()
    seen=set()
    grouped={}
    today=_op_dt.now(_OP_TZ).date()
    subs={}
    for p in payments:
        sid=p.subscription_id
        if sid not in subs:subs[sid]=db.get(Subscription,sid)
        s=subs[sid]
        latest=sid not in seen
        seen.add(sid)
        undoable=(latest and s is not None and p.previous_expiry is not None
            and p.new_expiry is not None and s.expiry_date==p.new_expiry)
        ts=_op_local_payment_time(p.paid_at)
        date_key=ts.date() if ts is not None else today
        when=("امروز" if date_key==today else "دیروز" if date_key==today-_op_td(days=1)
              else jdate(date_key))
        if date_key not in grouped:
            grouped[date_key]={"label":when,"items":[],"total":0}
        search=" ".join((
            str(s.display_name or "") if s else "",
            str(s.phone or "") if s else "",
            str(s.id) if s else str(sid),
            str(p.amount_toman or 0),
            str(p.note or ""),when
        )).lower()
        grouped[date_key]["items"].append({
           "p":p,"s":s,"undoable":undoable,
           "clock":ts.strftime("%H:%M") if ts else "—","search":search
        })
        grouped[date_key]["total"]+=int(p.amount_toman or 0)
    days=[grouped[d] for d in sorted(grouped.keys(),reverse=True)]
    return render("payments.html",request,days=days)
app.router.routes[:]=[r for r in app.router.routes if not (
    getattr(r,"path",None)=="/payments" and "GET" in (getattr(r,"methods",set()) or set()))]
app.add_api_route("/payments",_op_payments_page,methods=["GET"])

if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)
