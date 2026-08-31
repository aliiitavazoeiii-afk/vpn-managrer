# Core workspace simplification: dashboard -> debt collection -> waiting -> payments/removed -> control room.
# Keeps existing accounting formulas and user-profile edit routes unchanged.
from datetime import timedelta
import re as _core_re

_CORE_NAV = r'''
<nav>
  <a href="/" class="{{ 'active' if request.url.path=='/' else '' }}"><i>⌂</i><span>داشبورد</span></a>
  <a href="/debts" class="{{ 'active' if request.url.path=='/debts' else '' }}"><i>◫</i><span>وصول بدهی</span></a>
  <a href="/followups" class="{{ 'active' if request.url.path.startswith('/followups') else '' }}"><i>◷</i><span>در انتظار</span></a>
  <a href="/payments" class="{{ 'active' if request.url.path.startswith('/payments') else '' }}"><i>↗</i><span>پرداختی‌ها</span></a>
  <a href="/removed" class="{{ 'active' if request.url.path.startswith('/removed') else '' }}"><i>⌫</i><span>حذفی‌ها</span></a>
  <a href="/control-room" class="{{ 'active' if request.url.path.startswith('/control-room') else '' }}"><i>⌘</i><span>اتاق کنترل</span></a>
</nav>
'''

_base = TEMPLATES.get("base.html", "")
if _base:
    _base = _core_re.sub(r"<nav>.*?</nav>", _CORE_NAV, _base, count=1, flags=_core_re.S)
    _base = _core_re.sub(r'<div class="live">.*?</div>', '', _base, count=1, flags=_core_re.S)
    TEMPLATES["base.html"] = _base

for _name in ("debts.html", "followups.html", "payments.html"):
    _tpl = TEMPLATES.get(_name, "")
    if _tpl:
        _tpl = _core_re.sub(r'<nav class="work-flowbar".*?</nav>', '', _tpl, flags=_core_re.S)
        TEMPLATES[_name] = _tpl

_debt_tpl = TEMPLATES.get("debts.html", "")
if _debt_tpl:
    _debt_tpl = _core_re.sub(r'{% block title %}.*?{% endblock %}', '{% block title %}وصول بدهی · حساب VPN{% endblock %}', _debt_tpl, count=1, flags=_core_re.S)
    _debt_tpl = _core_re.sub(r'{% block heading %}.*?{% endblock %}', '{% block heading %}وصول بدهی{% endblock %}', _debt_tpl, count=1, flags=_core_re.S)
    _debt_tpl = _core_re.sub(r'{% block subheading %}.*?{% endblock %}', '{% block subheading %}لیست اقدام امروز؛ پیام، پیگیری یا ثبت پرداخت{% endblock %}', _debt_tpl, count=1, flags=_core_re.S)
    TEMPLATES["debts.html"] = _debt_tpl

_wait_tpl = TEMPLATES.get("followups.html", "")
if _wait_tpl:
    _wait_tpl = _wait_tpl.replace("اکانت به وضعیت «قطع شد» منتقل شد و دیگر در بدهی‌ها نمایش داده نمی‌شود.", "اکانت به «حذفی‌ها» منتقل شد.")
    _wait_tpl = _wait_tpl.replace("این اکانت از لیست انتظار خارج و به حالت قطع‌شده منتقل شود؟", "این اکانت از «در انتظار» خارج و به «حذفی‌ها» منتقل شود؟")
    _wait_tpl = _wait_tpl.replace('<button class="waiting-cut">قطع شد</button>', '<button class="waiting-cut">انتقال به حذفی‌ها</button>')
    TEMPLATES["followups.html"] = _wait_tpl

_profile_tpl = TEMPLATES.get("user_detail.html", "")
if _profile_tpl:
    _profile_tpl = _profile_tpl.replace("جزئیات سرویس و تاریخچه پرداخت", "پروفایل کامل کاربر؛ تاریخ، شماره، بدهی و زیرمجموعه‌ها")
    _profile_tpl = _profile_tpl.replace("سرویس‌های همین شماره", "زیرمجموعه‌های همین شماره")
    TEMPLATES["user_detail.html"] = _profile_tpl

CORE_DASHBOARD_TEMPLATE = r'''{% extends "base.html" %}
{% block title %}داشبورد · حساب VPN{% endblock %}
{% block heading %}داشبورد{% endblock %}
{% block subheading %}فقط اعداد اصلی کسب‌وکار VPN{% endblock %}
{% block content %}
<section class="core-dashboard">
  <div class="core-kpi">
    <small>کل کاربران</small>
    <strong>{{ stats.total_users|fa }}</strong>
    <span>{{ stats.active_users|fa }} فعال · {{ stats.removed_users|fa }} حذفی</span>
  </div>
  <div class="core-kpi">
    <small>درآمد ماهانه VPN</small>
    <strong>{{ stats.monthly_income|money }}</strong>
    <span>تومان · جمع مبلغ ماهانه کاربران فعال</span>
  </div>
  <a class="core-kpi core-link" href="/debts">
    <small>بدهی مانده</small>
    <strong>{{ stats.remaining_debt|money }}</strong>
    <span>تومان · وصول بدهی + در انتظار</span>
  </a>
  <a class="core-kpi core-link" href="/payments">
    <small>پرداختی امروز</small>
    <strong>{{ stats.paid_today|money }}</strong>
    <span>تومان · {{ stats.payment_count_today|fa }} پرداخت</span>
  </a>
</section>
{% endblock %}'''

REMOVED_TEMPLATE = r'''{% extends "base.html" %}
{% block title %}حذفی‌ها · حساب VPN{% endblock %}
{% block heading %}حذفی‌ها{% endblock %}
{% block subheading %}اکانت‌هایی که از «در انتظار» به قطع/حذفی منتقل شده‌اند؛ اطلاعاتشان حذف نشده است{% endblock %}
{% block content %}
<section class="removed-summary">
  <div><small>تعداد اکانت</small><strong>{{ rows|length|fa }}</strong></div>
  <div><small>بدهی ثبت‌شده</small><strong>{{ total_debt|money }} <em>تومان</em></strong></div>
</section>
<div class="removed-search"><span>⌕</span><input id="removed-search" type="search" autocomplete="off" placeholder="جستجو با نام یا شماره همراه…"><small id="removed-count">{{ rows|length|fa }} نتیجه</small></div>
<div class="removed-list">
{% for s in rows %}
  <section class="removed-row" data-removed-row data-search="{{ ((s.display_name or '') ~ ' ' ~ (s.phone or ''))|lower }}">
    <div class="removed-person"><small>اکانت</small><a href="/users/{{ s.id }}">{{ s.display_name }}</a></div>
    <div><small>شماره همراه</small><b class="ltr">{{ s.phone or '—' }}</b></div>
    <div><small>انقضا</small><b>{{ s.expiry_date|jdate }}</b></div>
    <div><small>بدهی</small><b class="removed-debt">{{ s.debt_toman|money }} تومان</b></div>
    <div class="removed-actions"><a href="/users/{{ s.id }}">پروفایل</a><form method="post" action="/removed/{{ s.id }}/restore" onsubmit="return confirm('این اکانت دوباره به وصول بدهی برگردد؟')"><button type="submit">برگردان به وصول</button></form></div>
  </section>
{% else %}<div class="empty debt-empty">فعلاً هیچ اکانتی در حذفی‌ها نیست.</div>{% endfor %}
</div>
<div id="removed-empty" class="empty debt-empty" hidden>نتیجه‌ای پیدا نشد.</div>
<script>(function(){const input=document.getElementById('removed-search');if(!input)return;const rows=[...document.querySelectorAll('[data-removed-row]')];const count=document.getElementById('removed-count');const empty=document.getElementById('removed-empty');const fa=n=>String(n).replace(/\d/g,d=>'۰۱۲۳۴۵۶۷۸۹'[d]);const apply=()=>{const q=input.value.trim().toLowerCase();let visible=0;rows.forEach(row=>{const show=!q||(row.dataset.search||'').toLowerCase().includes(q);row.hidden=!show;if(show)visible++;});if(count)count.textContent=fa(visible)+' نتیجه';if(empty)empty.hidden=visible!==0;};input.addEventListener('input',apply);})();</script>
{% endblock %}'''

CONTROL_ROOM_TEMPLATE = r'''{% extends "base.html" %}
{% block title %}اتاق کنترل · حساب VPN{% endblock %}
{% block heading %}اتاق کنترل{% endblock %}
{% block subheading %}این بخش را بعداً بر اساس نیازهای عملیاتی توسعه می‌دهیم{% endblock %}
{% block content %}<section class="control-placeholder"><div class="control-icon">⌘</div><h2>اتاق کنترل آماده است</h2><p>فعلاً چیزی اینجا اضافه نشده تا درباره امکاناتش با هم تصمیم بگیریم.</p></section>{% endblock %}'''

TEMPLATES["dashboard.html"] = CORE_DASHBOARD_TEMPLATE
TEMPLATES["removed.html"] = REMOVED_TEMPLATE
TEMPLATES["control_room.html"] = CONTROL_ROOM_TEMPLATE
if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)


def core_dashboard(request: Request, db: Session = Depends(get_db)):
    refresh_billing(db)
    states = _followup_states(db) if "_followup_states" in globals() else {}
    subscriptions = db.query(Subscription).all()
    active = [s for s in subscriptions if states.get(s.id) != "cut"]
    active_paid = [s for s in active if not s.is_free]
    removed_users = sum(1 for s in subscriptions if states.get(s.id) == "cut")

    now_local = datetime.now(TZ)
    start_local = datetime(now_local.year, now_local.month, now_local.day, tzinfo=TZ)
    end_local = start_local + timedelta(days=1)
    utc = ZoneInfo("UTC")
    start_utc = start_local.astimezone(utc).replace(tzinfo=None)
    end_utc = end_local.astimezone(utc).replace(tzinfo=None)

    paid_today = (db.query(func.coalesce(func.sum(Payment.amount_toman), 0)).filter(Payment.paid_at >= start_utc, Payment.paid_at < end_utc).scalar() or 0)
    payment_count_today = db.query(Payment).filter(Payment.paid_at >= start_utc, Payment.paid_at < end_utc).count()

    stats = {
        "total_users": len(subscriptions),
        "active_users": len(active),
        "removed_users": removed_users,
        "monthly_income": sum(int(s.monthly_fee_toman or 0) for s in active_paid),
        "remaining_debt": sum(int(s.debt_toman or 0) for s in active_paid),
        "paid_today": int(paid_today),
        "payment_count_today": int(payment_count_today),
    }
    return render("dashboard.html", request, stats=stats)


def removed_page(request: Request, db: Session = Depends(get_db)):
    refresh_billing(db)
    states = _followup_states(db) if "_followup_states" in globals() else {}
    removed_ids = [sid for sid, state in states.items() if state == "cut"]
    rows = db.query(Subscription).filter(Subscription.id.in_(removed_ids)).order_by(Subscription.display_name.asc()).all() if removed_ids else []
    return render("removed.html", request, rows=rows, total_debt=sum(int(s.debt_toman or 0) for s in rows if not s.is_free))


def restore_removed(sid: int, db: Session = Depends(get_db)):
    s = db.get(Subscription, sid)
    if s and "_followup_set" in globals():
        _followup_set(db, sid, None, f"restored from removed archive; name={s.display_name}")
        db.commit()
    return RedirectResponse("/debts?restored=1", 303)


def control_room_page(request: Request):
    return render("control_room.html", request)


app.router.routes[:] = [r for r in app.router.routes if not (getattr(r, "path", None) == "/" and "GET" in (getattr(r, "methods", set()) or set()))]
app.add_api_route("/", core_dashboard, methods=["GET"])
app.add_api_route("/removed", removed_page, methods=["GET"])
app.add_api_route("/removed/{sid}/restore", restore_removed, methods=["POST"])
app.add_api_route("/control-room", control_room_page, methods=["GET"])
