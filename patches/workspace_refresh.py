# Workspace refresh: dashboard revenue hero, dedicated add-user page, and readable user screens.
# Loaded last so presentation changes do not alter existing accounting/follow-up behavior.
import re as _ws_re
from fastapi import Form

# --- Dashboard hero ---------------------------------------------------------
_dash = TEMPLATES.get("ref_dashboard.html", "")
if _dash:
    _dash = _dash.replace(
        '<div class="focus-kicker"><span></span> VPN COMMAND CENTER</div>',
        '<div class="focus-kicker"><span></span> LIVE BUSINESS OVERVIEW</div>',
        1,
    )
    _dash = _dash.replace(
        '<h1>صبح بخیر علی <em>✦</em></h1>',
        '<h1 class="focus-command-title">VPN COMMAND CENTER</h1>',
        1,
    )
    _income = r'''
    <div class="focus-income-card">
      <small>درآمد ماهانه فعلی</small>
      <strong>{{ stats.monthly_income|money }}</strong>
      <span>تومان</span>
    </div>
'''
    _orb_anchor = '    <div class="focus-orb" aria-hidden="true">'
    if _orb_anchor in _dash and "focus-income-card" not in _dash:
        _dash = _dash.replace(_orb_anchor, _income + _orb_anchor, 1)

    # Add-user is now a standalone workspace.
    _dash = _dash.replace('href="/debts#add-user-box"', 'href="/add-user"')
    TEMPLATES["ref_dashboard.html"] = _dash


# --- Debt desk: replace embedded add form with a user-list launcher ----------
_DEBT_USERS_BOX = r'''
<section class="debt-users-launch">
  <div class="debt-users-launch-main">
    <span class="debt-users-launch-icon">👥</span>
    <div>
      <small>مدیریت کاربران</small>
      <strong>لیست کاربران</strong>
      <p>مشاهده، جستجو و ورود به جزئیات همه اکانت‌ها</p>
    </div>
  </div>
  <div class="debt-users-launch-actions">
    <a class="debt-users-primary" href="/users">باز کردن لیست کاربران <span>←</span></a>
    <a class="debt-users-secondary" href="/add-user">＋ افزودن کاربر</a>
  </div>
</section>
'''

_debt_tpl = TEMPLATES.get("debts.html", "")
if _debt_tpl:
    # user_manage.py puts exactly one non-nested <details> add form here.
    _debt_tpl, _removed = _ws_re.subn(
        r'<details class="add-user-wrap" id="add-user-box">.*?</details>',
        _DEBT_USERS_BOX,
        _debt_tpl,
        count=1,
        flags=_ws_re.S,
    )
    if not _removed and "debt-users-launch" not in _debt_tpl:
        _anchor = '<div class="debt-searchbar">'
        if _anchor in _debt_tpl:
            _debt_tpl = _debt_tpl.replace(_anchor, _DEBT_USERS_BOX + _anchor, 1)
    TEMPLATES["debts.html"] = _debt_tpl


# --- Dedicated add-user page ------------------------------------------------
_ADD_USER_PAGE = r'''{% extends "base.html" %}
{% block title %}افزودن کاربر · حساب VPN{% endblock %}
{% block heading %}افزودن کاربر{% endblock %}
{% block subheading %}ساخت اکانت جدید یا افزودن زیرمجموعه به یک شماره موجود{% endblock %}
{% block content %}
<div class="add-user-page">
  {% if request.query_params.get("created") %}
  <div class="add-user-success">✓ کاربر با موفقیت ثبت شد.</div>
  {% endif %}
  {% if request.query_params.get("error") %}
  <div class="add-user-error">اطلاعات ورودی معتبر نیست؛ دوباره بررسی کن.</div>
  {% endif %}

  <section class="add-user-page-card">
    <header>
      <div class="add-user-page-icon">＋</div>
      <div>
        <h2>کاربر جدید</h2>
        <p>اگر شماره همراه از قبل وجود داشته باشد، اکانت جدید خودکار زیر همان سرگروه قرار می‌گیرد.</p>
      </div>
      <a href="/users">لیست کاربران ←</a>
    </header>

    <form method="post" action="/add-user" class="add-user-page-form">
      <div class="add-user-page-field">
        <label>نام اکانت</label>
        <input name="display_name" type="text" required autofocus placeholder="مثلاً hadi">
      </div>
      <div class="add-user-page-field">
        <label>شماره همراه</label>
        <input name="phone" type="text" inputmode="tel" autocomplete="off" placeholder="0912...">
      </div>
      <div class="add-user-page-field">
        <label>مبلغ ماهانه</label>
        <input name="monthly_fee" type="text" inputmode="numeric" data-money-input value="200,000">
      </div>

      <div class="add-user-page-field add-user-page-date">
        <label>تاریخ انقضا · شمسی</label>
        <div class="add-user-page-date-grid">
          <select name="jd">{% for d in range(1,32) %}<option value="{{ d }}" {% if d == today_jparts[2] %}selected{% endif %}>{{ d|fa }}</option>{% endfor %}</select>
          <select name="jm">{% for month_name in jalali_months %}<option value="{{ loop.index }}" {% if loop.index == today_jparts[1] %}selected{% endif %}>{{ month_name }}</option>{% endfor %}</select>
          <select name="jy">{% for y in jalali_years_around(today_jparts[0]) %}<option value="{{ y }}" {% if y == today_jparts[0] %}selected{% endif %}>{{ y|fa }}</option>{% endfor %}</select>
        </div>
      </div>

      <div class="add-user-page-note">
        <b>گروه‌بندی خودکار</b>
        <span>شماره تکراری = زیرمجموعه همان پرداخت‌کننده · شماره جدید = سرگروه مستقل</span>
      </div>
      <button class="add-user-page-submit" type="submit">ثبت کاربر جدید</button>
    </form>
  </section>
</div>
{% endblock %}'''

TEMPLATES["add_user_page.html"] = _ADD_USER_PAGE


def workspace_add_user_page(request: Request):
    _today = today_local()
    try:
        _parts = _date_guard_g2j(_today.year, _today.month, _today.day)
    except Exception:
        _parts = _g2j(_today.year, _today.month, _today.day)
    return render("add_user_page.html", request, today_jparts=_parts)


def workspace_add_user(
    display_name: str = Form(...),
    phone: str = Form(""),
    monthly_fee: str = Form("200000"),
    jy: int = Form(...),
    jm: int = Form(...),
    jd: int = Form(...),
    db: Session = Depends(get_db),
):
    name = str(display_name or "").strip()
    try:
        normalized_phone = _normalize_phone(phone)
        fee = _parse_money(monthly_fee)
        if not name or fee < 0:
            raise ValueError("invalid user")
        expiry = parse_jalali_date(f"{int(jy):04d}/{int(jm):02d}/{int(jd):02d}")
    except Exception:
        return RedirectResponse("/add-user?error=1", 303)

    existing_same_phone = 0
    if normalized_phone:
        existing_same_phone = db.query(Subscription).filter(
            Subscription.phone == normalized_phone
        ).count()

    s = Subscription()
    values = {
        "display_name": name,
        "phone": normalized_phone,
        "expiry_date": expiry,
        "monthly_fee_toman": fee,
        "debt_toman": 0,
        "payment_status": "paid",
        "is_free": False,
        "payment_method": "phone" if normalized_phone else "none",
        "billing_cursor_date": today_local(),
    }
    for key, value in values.items():
        if hasattr(s, key):
            setattr(s, key, value)

    if hasattr(s, "source_row"):
        s.source_row = _next_source_row(db)

    _required_column_fallbacks(s, expiry)
    db.add(s)
    try:
        db.flush()
        debt = current_debt_for(s, today_local())
        if hasattr(s, "debt_toman"):
            s.debt_toman = debt
        if hasattr(s, "payment_status"):
            s.payment_status = "unpaid" if debt > 0 else "paid"
        db.add(AuditEvent(
            kind="user_add",
            message=(
                f"User added from dedicated page: id={s.id}; name={name}; "
                f"phone={normalized_phone}; expiry={expiry}; monthly_fee={fee}; "
                f"matched_existing_phone={bool(existing_same_phone)}"
            ),
        ))
        db.commit()
        sid = s.id
    except Exception:
        db.rollback()
        return RedirectResponse("/add-user?error=1", 303)

    return RedirectResponse(f"/add-user?created=1&sid={sid}", 303)


app.add_api_route("/add-user", workspace_add_user_page, methods=["GET"])
app.add_api_route("/add-user", workspace_add_user, methods=["POST"])


# --- User list and user profile readability ---------------------------------
def _ws_wrap_content(template, css_class, lead=""):
    if not template or css_class in template:
        return template
    start = template.find("{% block content %}")
    end = template.rfind("{% endblock %}")
    if start < 0 or end <= start:
        return template
    insert_at = start + len("{% block content %}")
    template = template[:insert_at] + lead + f'<div class="{css_class}">' + template[insert_at:]
    end = template.rfind("{% endblock %}")
    template = template[:end] + "</div>" + template[end:]
    return template

_USERS_LEAD = r'''
<section class="users-page-toolbar">
  <div><span>👥</span><div><b>مدیریت کاربران</b><small>لیست کامل اکانت‌ها و زیرمجموعه‌ها</small></div></div>
  <a href="/add-user">＋ افزودن کاربر جدید</a>
</section>
'''

for _name in ("users.html", "user_list.html", "users_list.html"):
    if _name in TEMPLATES:
        TEMPLATES[_name] = _ws_wrap_content(
            TEMPLATES[_name], "users-readable-page", _USERS_LEAD
        )

if "user_detail.html" in TEMPLATES:
    TEMPLATES["user_detail.html"] = _ws_wrap_content(
        TEMPLATES["user_detail.html"], "user-detail-readable-page"
    )


# Final cache bust.
_base = TEMPLATES.get("base.html", "")
if _base:
    _base = _ws_re.sub(
        r'/static/app\.css(?:\?v=[^"\']*)?',
        '/static/app.css?v=workspace-refresh-1',
        _base,
    )
    TEMPLATES["base.html"] = _base

if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)
