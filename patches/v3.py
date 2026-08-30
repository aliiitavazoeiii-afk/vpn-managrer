# Hesab VPN v5: debt desk, search, quick message copy, and manual correction.
from fastapi import Form


def _money3(value):
    try:
        return f"{int(value or 0):,}"
    except Exception:
        return str(value or "0")


env.filters["money"] = _money3


def debt_periods_for(s, as_of=None):
    as_of = as_of or today_local()
    if s.is_free or not s.expiry_date or int(s.monthly_fee_toman or 0) <= 0:
        return 0
    due = s.expiry_date
    periods = 0
    while due <= as_of and periods < 240:
        periods += 1
        due = add_one_jalali_month(due)
    return periods


def current_debt_for(s, as_of=None):
    return debt_periods_for(s, as_of) * int(s.monthly_fee_toman or 0)


def refresh_billing(db):
    today = today_local()
    changed = False
    rows = db.query(Subscription).all()
    for s in rows:
        target = 0 if s.is_free else current_debt_for(s, today)
        status = "unpaid" if target > 0 else "paid"
        if int(s.debt_toman or 0) != target:
            s.debt_toman = target
            changed = True
        if s.payment_status != status:
            s.payment_status = status
            changed = True
        if s.billing_cursor_date != today:
            s.billing_cursor_date = today
            changed = True
    if changed:
        db.commit()


DEBTS_TEMPLATE_V3 = r'''{% extends "base.html" %}
{% block title %}بدهی‌ها · حساب VPN{% endblock %}
{% block heading %}وصول بدهی{% endblock %}
{% block subheading %}نام یا شماره را پیدا کن، پیام آماده را کپی کن و واریز را همان‌جا ثبت کن{% endblock %}
{% block content %}
{% if paid %}<div class="collect-success">✓ واریز ثبت شد و تاریخ سرویس تمدید شد.</div>{% endif %}
{% if adjusted %}<div class="collect-success">✓ بدهی واقعی ثبت شد و تاریخ مبنای سرویس با آن هماهنگ شد.</div>{% endif %}
{% if adjust_error %}<div class="collect-error">مبلغ اصلاحی باید صفر یا مضربی از تعرفه ماهانه باشد و از بدهی محاسبه‌شده بیشتر نباشد.</div>{% endif %}

<section class="debt-summary-clean">
  <div><small>جمع بدهی امروز</small><strong>{{ total|money }} <em>تومان</em></strong></div>
  <div><small>پرداخت‌کننده بدهکار</small><strong>{{ groups|length|fa }}</strong></div>
  <div><small>سرویس بدهکار</small><strong>{{ service_count|fa }}</strong></div>
</section>

<div class="debt-searchbar">
  <span>⌕</span>
  <input id="debt-search" type="search" autocomplete="off" placeholder="جستجو با نام یا شماره همراه…">
  <small id="debt-search-count">{{ groups|length|fa }} نتیجه</small>
</div>

<div class="debt-desk">
{% for g in groups %}
  <section class="debt-group-v3" data-debt-group data-search="{{ g.search_text }}">
    <button type="button" class="debt-head-v3" data-debt-toggle="{{ loop.index0 }}">
      <div class="identity-box name-box">
        <small>نام</small>
        <strong>{{ g.primary_name }}</strong>
        {% if g.services > 1 %}<span>{{ g.services|fa }} سرویس</span>{% endif %}
      </div>

      {% if g.phone %}
      <span class="identity-box phone-box phone-copy" data-copy="{{ g.phone }}" title="کلیک برای کپی شماره">
        <small>شماره همراه</small><strong>{{ g.phone }}</strong><i>کپی</i>
      </span>
      {% else %}
      <span class="identity-box phone-box no-phone"><small>شماره همراه</small><strong>ندارد</strong></span>
      {% endif %}

      <div class="identity-box expiry-box">
        <small>انقضا</small><strong>{{ g.first_expiry|jdate }}</strong>
      </div>

      <div class="debt-group-total">
        <small>جمع بدهی</small>
        <strong>{{ g.debt|money }} <em>تومان</em></strong>
      </div>
      <span class="debt-chevron">⌄</span>
    </button>

    <div class="debt-children-v3" data-debt-panel="{{ loop.index0 }}" hidden>
      {% for item in g.rows %}{% set s=item.s %}
      <div class="debt-service-v3">
        <div class="debt-service-main">
          <a href="/users/{{ s.id }}" class="debt-service-name">{{ s.display_name }}</a>
          <span class="debt-expiry">انقضا: <b>{{ s.expiry_date|jdate }}</b></span>
        </div>

        <div class="debt-metric"><small>ماهانه</small><b>{{ s.monthly_fee_toman|money }}</b></div>
        <div class="debt-metric"><small>سررسید گذشته</small><b>{{ item.periods|fa }} ماه</b></div>
        <div class="debt-metric danger"><small>بدهی</small><b>{{ item.debt|money }}</b></div>

        <div class="service-actions">
          <form method="post" action="/debts/{{ s.id }}/pay" class="collect-form" onsubmit="return confirm('واریز {{ item.debt|money }} تومان برای {{ s.display_name }} ثبت شود؟')">
            <button class="collect-btn" type="submit"><span>ثبت واریز</span><b>{{ item.debt|money }}</b></button>
          </form>

          <details class="debt-adjust">
            <summary>اصلاح بدهی</summary>
            <form method="post" action="/debts/{{ s.id }}/adjust" class="adjust-form">
              <label>بدهی واقعی</label>
              <div><input name="amount" type="number" min="0" max="{{ item.debt }}" step="{{ s.monthly_fee_toman }}" value="{{ item.debt }}"><span>تومان</span></div>
              <small>اگر سیستم بیشتر حساب کرده، مبلغ واقعی را وارد کن.</small>
              <button type="submit">ثبت اصلاح</button>
            </form>
          </details>
        </div>
      </div>
      {% endfor %}

      <div class="ready-message">
        <div class="ready-message-head">
          <div><small>پیام آماده</small><b>{% if g.phone %}برای {{ g.phone }}{% else %}بدون شماره همراه{% endif %}</b></div>
          <button type="button" data-copy-target="debt-message-{{ loop.index0 }}">کپی پیام</button>
        </div>
        <textarea id="debt-message-{{ loop.index0 }}" readonly>سلام ارادت
{% for item in g.rows %}{% if loop.first %}اکانت شما {{ item.s.expiry_date|jdate }} تمام شده.
{% else %}اکانت {{ item.s.display_name }} {{ item.s.expiry_date|jdate }} تمام شده.
{% endif %}{% endfor %}
در صورت تمایل به ادامه مصرف لینک پرداخت از سامانه آیریا خدمتتون ارسال شده.
اگر لینک به دستتون نرسید حتما اطلاع بدید چون اکانت‌های پرداخت‌نشده امشب قطع خواهد شد.</textarea>
      </div>
    </div>
  </section>
{% else %}
  <div class="empty debt-empty">هیچ بدهی سررسیدشده‌ای وجود ندارد.</div>
{% endfor %}
</div>

<div id="debt-no-results" class="empty debt-empty" hidden>موردی با این نام یا شماره پیدا نشد.</div>
<div id="copy-toast" class="copy-toast">کپی شد</div>
{% endblock %}'''

TEMPLATES["debts.html"] = DEBTS_TEMPLATE_V3
for _name, _tpl in list(TEMPLATES.items()):
    TEMPLATES[_name] = (
        _tpl.replace('/static/app.css?v=2', '/static/app.css?v=5')
            .replace('/static/app.css?v=3', '/static/app.css?v=5')
            .replace('/static/app.css?v=4', '/static/app.css?v=5')
            .replace('/static/app.js?v=2', '/static/app.js?v=5')
            .replace('/static/app.js?v=3', '/static/app.js?v=5')
            .replace('/static/app.js?v=4', '/static/app.js?v=5')
    )
if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)
env.globals.update(debt_periods_for=debt_periods_for, current_debt_for=current_debt_for)


def debts_v3(request: Request, paid: int = 0, adjusted: int = 0, adjust_error: int = 0, db: Session = Depends(get_db)):
    refresh_billing(db)
    rows = db.query(Subscription).filter(
        Subscription.is_free.is_(False), Subscription.debt_toman > 0
    ).order_by(Subscription.expiry_date.asc().nullslast(), Subscription.display_name.asc()).all()

    grouped = {}
    for s in rows:
        periods = debt_periods_for(s)
        debt = current_debt_for(s)
        key = f"phone:{s.phone}" if s.phone else f"service:{s.id}"
        if key not in grouped:
            grouped[key] = {
                "phone": s.phone,
                "rows": [],
                "debt": 0,
                "services": 0,
                "first_expiry": s.expiry_date,
            }
        g = grouped[key]
        g["rows"].append({"s": s, "periods": periods, "debt": debt})
        g["debt"] += debt
        g["services"] += 1
        if s.expiry_date and (not g["first_expiry"] or s.expiry_date < g["first_expiry"]):
            g["first_expiry"] = s.expiry_date

    groups = list(grouped.values())
    for g in groups:
        names = [x["s"].display_name for x in g["rows"]]
        g["primary_name"] = names[0] if len(names) == 1 else "، ".join(names[:2]) + (f" +{len(names)-2}" if len(names) > 2 else "")
        g["search_text"] = ((g.get("phone") or "") + " " + " ".join(names)).lower()

    groups.sort(key=lambda g: (g["first_expiry"] or date.max, -(g["debt"] or 0)))
    return render(
        "debts.html",
        request,
        groups=groups,
        total=sum(g["debt"] for g in groups),
        service_count=len(rows),
        paid=bool(paid),
        adjusted=bool(adjusted),
        adjust_error=bool(adjust_error),
    )


def debt_quick_pay_v3(sid: int, db: Session = Depends(get_db)):
    refresh_billing(db)
    s = db.get(Subscription, sid)
    if not s or s.is_free:
        return RedirectResponse("/debts", 303)
    periods = debt_periods_for(s)
    amount = current_debt_for(s)
    if periods <= 0 or amount <= 0:
        return RedirectResponse("/debts", 303)
    prev = s.expiry_date
    s.expiry_date = add_jalali_months(s.expiry_date, periods)
    s.debt_toman = 0
    s.payment_status = "paid"
    s.billing_cursor_date = today_local()
    db.add(Payment(
        subscription_id=s.id,
        amount_toman=amount,
        periods=periods,
        previous_expiry=prev,
        new_expiry=s.expiry_date,
        note="ثبت واریز از صفحه بدهی",
    ))
    db.add(AuditEvent(kind="payment", message=f"Debt desk payment {amount} for {s.display_name}"))
    db.commit()
    return RedirectResponse("/debts?paid=1", 303)


def debt_adjust_v3(sid: int, amount: int = Form(...), db: Session = Depends(get_db)):
    refresh_billing(db)
    s = db.get(Subscription, sid)
    if not s or s.is_free or not s.expiry_date:
        return RedirectResponse("/debts?adjust_error=1", 303)

    fee = int(s.monthly_fee_toman or 0)
    periods = debt_periods_for(s)
    computed = periods * fee

    try:
        amount = int(amount)
    except Exception:
        return RedirectResponse("/debts?adjust_error=1", 303)

    if fee <= 0 or amount < 0 or amount > computed or amount % fee != 0:
        return RedirectResponse("/debts?adjust_error=1", 303)

    target_periods = amount // fee
    already_paid_periods = periods - target_periods
    prev = s.expiry_date

    if already_paid_periods > 0:
        s.expiry_date = add_jalali_months(s.expiry_date, already_paid_periods)

    s.debt_toman = amount
    s.payment_status = "unpaid" if amount > 0 else "paid"
    s.billing_cursor_date = today_local()
    db.add(AuditEvent(
        kind="debt_adjustment",
        message=f"Debt corrected {computed} -> {amount} for {s.display_name}; expiry {prev} -> {s.expiry_date}",
    ))
    db.commit()
    return RedirectResponse("/debts?adjusted=1", 303)


app.router.routes[:] = [
    r for r in app.router.routes
    if not (
        getattr(r, "path", None) == "/debts"
        and "GET" in (getattr(r, "methods", set()) or set())
    )
]
app.add_api_route("/debts", debts_v3, methods=["GET"])
app.add_api_route("/debts/{sid}/pay", debt_quick_pay_v3, methods=["POST"])
app.add_api_route("/debts/{sid}/adjust", debt_adjust_v3, methods=["POST"])
