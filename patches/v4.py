# Hesab VPN v4: manual debt correction + clearer collection cards.
from fastapi import Form

DEBTS_TEMPLATE_V4 = r'''{% extends "base.html" %}
{% block title %}بدهی‌ها · حساب VPN{% endblock %}
{% block heading %}وصول بدهی{% endblock %}
{% block subheading %}شماره را کپی کن، بدهی واقعی را در صورت نیاز اصلاح کن، سپس واریز را ثبت کن{% endblock %}
{% block content %}
{% if paid %}<div class="collect-success">✓ واریز ثبت شد و تاریخ سرویس تمدید شد.</div>{% endif %}
{% if adjusted %}<div class="adjust-success">✓ بدهی اصلاح شد؛ تاریخ مبنای اکانت هم برای محاسبات بعدی تنظیم شد.</div>{% endif %}
<section class="debt-summary-clean">
  <div><small>جمع بدهی امروز</small><strong>{{ total|money }} <em>تومان</em></strong></div>
  <div><small>پرداخت‌کننده بدهکار</small><strong>{{ groups|length|fa }}</strong></div>
  <div><small>سرویس بدهکار</small><strong>{{ service_count|fa }}</strong></div>
</section>
<div class="debt-desk debt-desk-v4">
{% for g in groups %}
  <section class="debt-group-v3 debt-group-v4">
    <button type="button" class="debt-head-v3 debt-head-v4" data-debt-toggle="{{ loop.index0 }}">
      <div class="debt-person">
        {% if g.phone %}
          <span class="group-phone-red" data-copy="{{ g.phone }}" title="کلیک برای کپی شماره">{{ g.phone }} <i>کپی</i></span>
        {% else %}
          <span class="group-phone-red no-phone">بدون شماره همراه</span>
        {% endif %}
        <small>{{ g.services|fa }} سرویس بدهکار{% if g.names %} · {{ g.names }}{% endif %}</small>
      </div>
      <div class="debt-group-total"><small>جمع بدهی</small><strong>{{ g.debt|money }} <em>تومان</em></strong></div>
      <span class="debt-chevron">⌄</span>
    </button>
    <div class="debt-children-v3 debt-children-v4" data-debt-panel="{{ loop.index0 }}" hidden>
      {% for item in g.rows %}{% set s=item.s %}
      <div class="debt-service-v4">
        <div class="debt-identity-v4">
          <a href="/users/{{ s.id }}" class="identity-box-v4 name-green-v4">{{ s.display_name }}</a>
          {% if g.phone %}
            <button type="button" class="identity-box-v4 phone-red-v4" data-copy="{{ g.phone }}" title="کلیک برای کپی">{{ g.phone }}</button>
          {% else %}
            <span class="identity-box-v4 phone-red-v4 muted-v4">بدون شماره</span>
          {% endif %}
          <span class="identity-box-v4 expiry-white-v4">{{ s.expiry_date|jdate }}</span>
        </div>

        <div class="debt-facts-v4">
          <div><small>ماهانه</small><b>{{ s.monthly_fee_toman|money }} تومان</b></div>
          <div><small>سررسید گذشته</small><b>{{ item.periods|fa }} ماه</b></div>
          <div class="debt-now-v4"><small>بدهی فعلی</small><b>{{ item.debt|money }} تومان</b></div>
        </div>

        <div class="debt-actions-v4">
          <form method="post" action="/debts/{{ s.id }}/adjust" class="adjust-form-v4" onsubmit="return confirm('بدهی واقعی {{ s.display_name }} اصلاح شود؟')">
            <label>اگر اکسل عقب بوده، بدهی واقعی:</label>
            <div class="adjust-controls-v4">
              <select name="actual_periods" aria-label="بدهی واقعی">
                {% for p in range(item.periods + 1) %}
                  <option value="{{ p }}" {% if p == item.periods %}selected{% endif %}>{{ (p * s.monthly_fee_toman)|money }} تومان{% if p == 0 %} · تسویه{% endif %}</option>
                {% endfor %}
              </select>
              <button type="submit" class="adjust-btn-v4">اصلاح بدهی</button>
            </div>
          </form>

          <form method="post" action="/debts/{{ s.id }}/pay" class="collect-form-v4" onsubmit="return confirm('واریز {{ item.debt|money }} تومان برای {{ s.display_name }} ثبت شود؟')">
            <button class="collect-btn-v4" type="submit"><span>ثبت واریز</span><b>{{ item.debt|money }} تومان</b></button>
          </form>
        </div>
      </div>
      {% endfor %}
    </div>
  </section>
{% else %}
  <div class="empty debt-empty">هیچ بدهی سررسیدشده‌ای وجود ندارد.</div>
{% endfor %}
</div>
<div id="copy-toast" class="copy-toast">شماره کپی شد</div>
{% endblock %}'''

TEMPLATES["debts.html"] = DEBTS_TEMPLATE_V4
# Load Estedad as the visual UI font while retaining system fallbacks.
_base = TEMPLATES.get("base.html", "")
if _base and "family=Estedad" not in _base:
    _base = _base.replace("</head>", '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Estedad:wght@400;500;600;700;800&display=swap" rel="stylesheet"></head>')
    TEMPLATES["base.html"] = _base
for _name, _tpl in list(TEMPLATES.items()):
    TEMPLATES[_name] = _tpl.replace('/static/app.css?v=3', '/static/app.css?v=4').replace('/static/app.js?v=3', '/static/app.js?v=4')
if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)


def debts_v4(request: Request, paid: int = 0, adjusted: int = 0, db: Session = Depends(get_db)):
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
            grouped[key] = {"phone": s.phone, "rows": [], "debt": 0, "services": 0, "first_expiry": s.expiry_date}
        g = grouped[key]
        g["rows"].append({"s": s, "periods": periods, "debt": debt})
        g["debt"] += debt
        g["services"] += 1
        if s.expiry_date and (not g["first_expiry"] or s.expiry_date < g["first_expiry"]):
            g["first_expiry"] = s.expiry_date
    groups = list(grouped.values())
    for g in groups:
        names = [x["s"].display_name for x in g["rows"]]
        g["names"] = "، ".join(names[:3]) + (f" +{len(names)-3}" if len(names) > 3 else "")
    groups.sort(key=lambda g: (g["first_expiry"] or date.max, -(g["debt"] or 0)))
    return render("debts.html", request, groups=groups, total=sum(g["debt"] for g in groups), service_count=len(rows), paid=bool(paid), adjusted=bool(adjusted))


def debt_adjust_v4(sid: int, actual_periods: int = Form(...), db: Session = Depends(get_db)):
    refresh_billing(db)
    s = db.get(Subscription, sid)
    if not s or s.is_free or not s.expiry_date:
        return RedirectResponse("/debts", 303)
    current_periods = debt_periods_for(s)
    desired_periods = max(0, min(int(actual_periods), current_periods))
    if desired_periods < current_periods:
        shift = current_periods - desired_periods
        previous_expiry = s.expiry_date
        previous_debt = current_debt_for(s)
        s.expiry_date = add_jalali_months(s.expiry_date, shift)
        s.debt_toman = desired_periods * int(s.monthly_fee_toman or 0)
        s.payment_status = "unpaid" if desired_periods > 0 else "paid"
        s.billing_cursor_date = today_local()
        db.add(AuditEvent(
            kind="debt_adjustment",
            message=(f"Manual debt correction for {s.display_name}: {previous_debt} -> {s.debt_toman}; "
                     f"expiry {previous_expiry} -> {s.expiry_date}; stale Excel correction")
        ))
        db.commit()
    return RedirectResponse("/debts?adjusted=1", 303)

# Replace the GET debt route again so it accepts the v4 adjusted banner.
app.router.routes[:] = [r for r in app.router.routes if not (
    getattr(r, "path", None) == "/debts" and "GET" in (getattr(r, "methods", set()) or set())
)]
app.add_api_route("/debts", debts_v4, methods=["GET"])
app.add_api_route("/debts/{sid}/adjust", debt_adjust_v4, methods=["POST"])
