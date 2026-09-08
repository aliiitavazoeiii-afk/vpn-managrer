# Reference-style command center UI. Business logic stays in existing patches.
from datetime import timedelta as _ref_timedelta

_REF_DASHBOARD = r'''{% extends "base.html" %}
{% block title %}VPN Command Center{% endblock %}
{% block heading %}{% endblock %}
{% block subheading %}{% endblock %}
{% block content %}
<div class="ref-dashboard">
  <section class="ref-hero">
    <div class="ref-hero-copy">
      <div class="ref-eyebrow"><span class="ref-live-dot"></span> مرکز فرماندهی VPN</div>
      <h1>صبح بخیر علی <span>✦</span></h1>
      <p>همه‌چیز برای مدیریت کاربران، وصول و زیرساخت در یک نگاه.</p>
    </div>
    <div class="ref-orb" aria-hidden="true"><i></i><b></b><em></em></div>
  </section>

  <section class="ref-kpis">
    <a href="/" class="ref-kpi ref-kpi-users">
      <div class="ref-kpi-icon">◉</div>
      <div><small>کل کاربران</small><strong>{{ stats.total_users|fa }}</strong><span>{{ stats.active_users|fa }} فعال · {{ stats.removed_users|fa }} حذفی</span></div>
    </a>
    <div class="ref-kpi ref-kpi-income">
      <div class="ref-kpi-icon">◈</div>
      <div><small>درآمد ماهانه VPN</small><strong>{{ stats.monthly_income|money }} <i>تومان</i></strong><span>جمع مبلغ ماهانه کاربران فعال</span></div>
    </div>
    <a href="/debts" class="ref-kpi ref-kpi-debt">
      <div class="ref-kpi-icon">!</div>
      <div><small>بدهی مانده</small><strong>{{ stats.remaining_debt|money }} <i>تومان</i></strong><span>{{ stats.debt_count|fa }} اکانت نیازمند وصول</span></div>
    </a>
    <a href="/payments" class="ref-kpi ref-kpi-paid">
      <div class="ref-kpi-icon">✓</div>
      <div><small>پرداختی امروز</small><strong>{{ stats.paid_today|money }} <i>تومان</i></strong><span>{{ stats.payment_count_today|fa }} پرداخت ثبت‌شده</span></div>
    </a>
  </section>

  <section class="ref-triple">
    <article class="ref-panel ref-panel-debt">
      <header><div><h2>وصول بدهی</h2><span>{{ stats.debt_count|fa }} اکانت</span></div><a href="/debts">مشاهده همه ←</a></header>
      <div class="ref-user-list">
        {% for item in debt_preview %}
        <a class="ref-user-row" href="/users/{{ item.s.id }}">
          <div class="ref-avatar">{{ item.initial }}</div>
          <div class="ref-user-main"><b>{{ item.s.display_name }}</b><small class="ltr">{{ item.s.phone or 'بدون شماره' }}</small></div>
          <div class="ref-user-side"><strong>{{ item.debt|money }}</strong><small>تومان</small></div>
          <div class="ref-user-expand"><span>انقضا {{ item.s.expiry_date|jdate }}</span><em>باز کردن پروفایل ←</em></div>
        </a>
        {% else %}<div class="ref-empty">فعلاً بدهی برای وصول نداریم.</div>{% endfor %}
      </div>
      <a class="ref-panel-foot" href="/debts">ورود به وصول بدهی <span>←</span></a>
    </article>

    <article class="ref-panel ref-panel-waiting">
      <header><div><h2>در انتظار</h2><span>{{ stats.waiting_count|fa }} اکانت</span></div><a href="/followups">مشاهده همه ←</a></header>
      <div class="ref-user-list">
        {% for item in waiting_preview %}
        <a class="ref-user-row" href="/users/{{ item.s.id }}">
          <div class="ref-avatar">{{ item.initial }}</div>
          <div class="ref-user-main"><b>{{ item.s.display_name }}</b><small class="ltr">{{ item.s.phone or 'بدون شماره' }}</small></div>
          <div class="ref-status ref-status-wait">در انتظار پرداخت</div>
          <div class="ref-user-expand"><span>بدهی {{ item.debt|money }} تومان</span><em>باز کردن پروفایل ←</em></div>
        </a>
        {% else %}<div class="ref-empty">کسی در انتظار پرداخت نیست.</div>{% endfor %}
      </div>
      <a class="ref-panel-foot" href="/followups">ورود به در انتظار <span>←</span></a>
    </article>

    <article class="ref-panel ref-panel-paid">
      <header><div><h2>پرداختی‌ها</h2><span>{{ stats.payment_count_today|fa }} امروز</span></div><a href="/payments">مشاهده همه ←</a></header>
      <div class="ref-user-list">
        {% for item in payment_preview %}
        <a class="ref-user-row" href="/users/{{ item.sid }}">
          <div class="ref-avatar">{{ item.initial }}</div>
          <div class="ref-user-main"><b>{{ item.name }}</b><small>{{ item.when }}</small></div>
          <div class="ref-user-side ref-green"><strong>{{ item.amount|money }}</strong><small>تومان</small></div>
          <div class="ref-user-expand"><span>پرداخت ثبت شده</span><em>جزئیات کاربر ←</em></div>
        </a>
        {% else %}<div class="ref-empty">هنوز پرداختی ثبت نشده.</div>{% endfor %}
      </div>
      <a class="ref-panel-foot" href="/payments">تاریخچه پرداخت‌ها <span>←</span></a>
    </article>
  </section>

  <section class="ref-bottom-grid">
    <article class="ref-control-preview">
      <header class="ref-section-head">
        <div><span class="ref-section-icon">⌘</span><div><h2>اتاق کنترل</h2><p>وضعیت سرورها و مانیتورینگ ترافیک</p></div></div>
        <a href="/control-room">ورود به اتاق کنترل ←</a>
      </header>

      <div class="ref-server-title"><span>🇮🇷</span><b>سرورهای ایران</b><small>تمرکز روی ترافیک باقی‌مانده</small></div>
      <div class="ref-server-grid">
        {% for srv in iran_servers %}
        <div class="ref-server-card {{ 'is-danger' if srv.level == 'danger' else '' }}">
          <div class="ref-server-top"><div><span class="ref-server-flag">🇮🇷</span><b>{{ srv.name }}</b></div><span class="ref-server-state"><i></i>{{ srv.state }}</span></div>
          <div class="ref-traffic-ring" style="--p:{{ srv.percent }}"><div><strong>{{ srv.percent|fa }}٪</strong><small>مصرف</small></div></div>
          <div class="ref-server-values"><div><small>باقی‌مانده ترافیک</small><b>{{ srv.remaining }}</b></div><div><small>زمان تخمینی</small><b>{{ srv.eta }}</b></div></div>
          <div class="ref-mini-meters"><span>CPU <b>{{ srv.cpu }}</b></span><span>RAM <b>{{ srv.ram }}</b></span></div>
        </div>
        {% endfor %}
      </div>

      <div class="ref-server-title ref-foreign-title"><span>🌍</span><b>سرورهای خارجی</b><small>۴ سرور</small></div>
      <div class="ref-foreign-grid">
        {% for srv in foreign_servers %}
        <div class="ref-foreign-card"><span>{{ srv.flag }}</span><div><b>{{ srv.name }}</b><small>{{ srv.state }}</small></div><em>{{ srv.note }}</em></div>
        {% endfor %}
      </div>
    </article>

    <aside class="ref-side-stack">
      <article class="ref-quick">
        <header><h2>عملیات سریع</h2><span>⚡</span></header>
        <div class="ref-quick-grid">
          <a href="/debts#add-user-box"><i>＋</i><b>افزودن کاربر</b><small>اکانت جدید</small></a>
          <a href="/debts"><i>✓</i><b>ثبت پرداخت</b><small>تسویه سریع</small></a>
          <a href="/debts"><i>➤</i><b>ارسال پیام</b><small>پیام آماده</small></a>
          <a href="/control-room"><i>⌘</i><b>اتاق کنترل</b><small>سرورها و X-UI</small></a>
        </div>
      </article>

      <article class="ref-profile-card">
        <header><h2>پروفایل کاربر</h2>{% if profile %}<a href="/users/{{ profile.id }}">ویرایش ←</a>{% endif %}</header>
        {% if profile %}
        <div class="ref-profile-person"><div class="ref-profile-avatar">{{ profile_initial }}</div><div><b>{{ profile.display_name }}</b><span class="ref-active-pill">فعال</span><small class="ltr">{{ profile.phone or 'بدون شماره' }}</small></div></div>
        <div class="ref-profile-info">
          <div><small>تاریخ انقضا</small><b>{{ profile.expiry_date|jdate }}</b></div>
          <div><small>زیرمجموعه‌ها</small><b>{{ profile_children|fa }} اکانت</b></div>
          <div><small>مبلغ ماهانه</small><b>{{ profile.monthly_fee_toman|money }} تومان</b></div>
          <div><small>بدهی</small><b>{{ profile.debt_toman|money }} تومان</b></div>
        </div>
        <a class="ref-profile-button" href="/users/{{ profile.id }}">باز کردن پروفایل کامل</a>
        {% else %}<div class="ref-empty">هنوز کاربری ثبت نشده.</div>{% endif %}
      </article>
    </aside>
  </section>
</div>
{% endblock %}'''

_REF_CONTROL_ROOM = r'''{% extends "base.html" %}
{% block title %}اتاق کنترل · VPN Command Center{% endblock %}
{% block heading %}{% endblock %}
{% block subheading %}{% endblock %}
{% block content %}
<div class="ref-control-page">
  <section class="ref-control-hero"><div><span>CONTROL ROOM</span><h1>اتاق کنترل</h1><p>مانیتورینگ ترافیک سرورهای ایران و دسترسی یکپارچه به X-UI</p></div><div class="ref-control-pulse"><i></i><b></b></div></section>
  <div class="ref-control-note"><span>⚡</span><div><b>مرحله بعد: اتصال Agent ترافیک</b><small>کارت‌ها آماده‌اند؛ بعد از نصب Agent روی ۴ سرور ایران، مصرف واقعی و زمان باقی‌مانده اینجا نمایش داده می‌شود.</small></div></div>
  <section class="ref-control-section"><header><div><span>🇮🇷</span><div><h2>سرورهای ایران</h2><p>مهم‌ترین شاخص: ترافیک باقی‌مانده و ETA</p></div></div></header><div class="ref-control-server-grid">
  {% for srv in iran_servers %}<article class="ref-control-server"><div class="ref-control-server-head"><div><span>🇮🇷</span><div><b>{{ srv.name }}</b><small>{{ srv.state }}</small></div></div><span class="ref-ready">آماده اتصال</span></div><div class="ref-big-traffic"><small>باقی‌مانده ترافیک</small><strong>{{ srv.remaining }}</strong><span>{{ srv.eta }}</span></div><div class="ref-control-progress"><i style="width:{{ srv.percent }}%"></i></div><div class="ref-control-metrics"><div><small>مصرف</small><b>{{ srv.percent|fa }}٪</b></div><div><small>CPU</small><b>{{ srv.cpu }}</b></div><div><small>RAM</small><b>{{ srv.ram }}</b></div></div><button type="button" disabled>اتصال Agent در مرحله بعد</button></article>{% endfor %}
  </div></section>
  <section class="ref-control-section"><header><div><span>🌍</span><div><h2>سرورهای خارجی</h2><p>وضعیت و دسترسی X-UI</p></div></div></header><div class="ref-control-foreign-grid">{% for srv in foreign_servers %}<article><span>{{ srv.flag }}</span><div><b>{{ srv.name }}</b><small>{{ srv.state }}</small></div><em>{{ srv.note }}</em><button type="button" disabled>X-UI · مرحله بعد</button></article>{% endfor %}</div></section>
</div>
{% endblock %}'''

TEMPLATES["ref_dashboard.html"] = _REF_DASHBOARD
TEMPLATES["control_room.html"] = _REF_CONTROL_ROOM

# Static server placeholders. No fake provider usage data: these become live after the agent phase.
def _ref_servers():
    iran = [
        {"name": "IR-1", "state": "آماده اتصال", "percent": 0, "remaining": "—", "eta": "—", "cpu": "—", "ram": "—", "level": "normal"},
        {"name": "IR-2", "state": "آماده اتصال", "percent": 0, "remaining": "—", "eta": "—", "cpu": "—", "ram": "—", "level": "normal"},
        {"name": "IR-3", "state": "آماده اتصال", "percent": 0, "remaining": "—", "eta": "—", "cpu": "—", "ram": "—", "level": "normal"},
        {"name": "IR-4", "state": "آماده اتصال", "percent": 0, "remaining": "—", "eta": "—", "cpu": "—", "ram": "—", "level": "normal"},
    ]
    foreign = [
        {"name": "Foreign-1", "flag": "🌐", "state": "آماده اتصال X-UI", "note": "X-UI"},
        {"name": "Foreign-2", "flag": "🌐", "state": "آماده اتصال X-UI", "note": "X-UI"},
        {"name": "Foreign-3", "flag": "🌐", "state": "آماده اتصال X-UI", "note": "X-UI"},
        {"name": "Foreign-4", "flag": "🌐", "state": "آماده اتصال X-UI", "note": "X-UI"},
    ]
    return iran, foreign


def _ref_initial(name):
    value = str(name or "?").strip()
    return value[:1].upper() if value else "?"


def _ref_when(ts):
    if not ts:
        return "—"
    try:
        utc = ZoneInfo("UTC")
        dt = ts.replace(tzinfo=utc).astimezone(TZ) if ts.tzinfo is None else ts.astimezone(TZ)
        now = datetime.now(TZ)
        sec = max(0, int((now - dt).total_seconds()))
        if sec < 3600:
            mins = max(1, sec // 60)
            return f"{mins} دقیقه پیش"
        if sec < 86400:
            return f"{sec // 3600} ساعت پیش"
        return f"{sec // 86400} روز پیش"
    except Exception:
        return "ثبت شده"


def reference_dashboard(request: Request, db: Session = Depends(get_db)):
    refresh_billing(db)
    states = _followup_states(db) if "_followup_states" in globals() else {}
    subscriptions = db.query(Subscription).all()
    active = [s for s in subscriptions if states.get(s.id) != "cut"]
    active_paid = [s for s in active if not s.is_free]
    removed_users = sum(1 for s in subscriptions if states.get(s.id) == "cut")

    debt_rows = [s for s in active_paid if int(s.debt_toman or 0) > 0 and states.get(s.id) not in ("waiting", "cut")]
    debt_rows.sort(key=lambda s: (-int(s.debt_toman or 0), s.expiry_date or today_local()))
    waiting_rows = [s for s in active_paid if states.get(s.id) == "waiting"]
    waiting_rows.sort(key=lambda s: (s.expiry_date or today_local(), s.display_name or ""))

    debt_preview = [{"s": s, "debt": int(s.debt_toman or 0), "initial": _ref_initial(s.display_name)} for s in debt_rows[:4]]
    waiting_preview = [{"s": s, "debt": int(s.debt_toman or 0), "initial": _ref_initial(s.display_name)} for s in waiting_rows[:4]]

    now_local = datetime.now(TZ)
    start_local = datetime(now_local.year, now_local.month, now_local.day, tzinfo=TZ)
    end_local = start_local + _ref_timedelta(days=1)
    utc = ZoneInfo("UTC")
    start_utc = start_local.astimezone(utc).replace(tzinfo=None)
    end_utc = end_local.astimezone(utc).replace(tzinfo=None)
    paid_today = (db.query(func.coalesce(func.sum(Payment.amount_toman), 0)).filter(Payment.paid_at >= start_utc, Payment.paid_at < end_utc).scalar() or 0)
    payment_count_today = db.query(Payment).filter(Payment.paid_at >= start_utc, Payment.paid_at < end_utc).count()

    payment_preview = []
    for p in db.query(Payment).order_by(Payment.paid_at.desc(), Payment.id.desc()).limit(4).all():
        s = db.get(Subscription, p.subscription_id)
        if not s:
            continue
        payment_preview.append({"sid": s.id, "name": s.display_name, "initial": _ref_initial(s.display_name), "amount": int(p.amount_toman or 0), "when": _ref_when(p.paid_at)})

    profile = active[0] if active else None
    profile_children = 1
    if profile and profile.phone:
        profile_children = sum(1 for s in subscriptions if s.phone == profile.phone and states.get(s.id) != "cut")

    stats = {
        "total_users": len(subscriptions),
        "active_users": len(active),
        "removed_users": removed_users,
        "monthly_income": sum(int(s.monthly_fee_toman or 0) for s in active_paid),
        "remaining_debt": sum(int(s.debt_toman or 0) for s in active_paid),
        "debt_count": len(debt_rows),
        "waiting_count": len(waiting_rows),
        "paid_today": int(paid_today),
        "payment_count_today": int(payment_count_today),
    }
    iran_servers, foreign_servers = _ref_servers()
    return render("ref_dashboard.html", request, stats=stats, debt_preview=debt_preview, waiting_preview=waiting_preview, payment_preview=payment_preview, profile=profile, profile_initial=_ref_initial(profile.display_name) if profile else "?", profile_children=profile_children, iran_servers=iran_servers, foreign_servers=foreign_servers)


def reference_control_room(request: Request):
    iran_servers, foreign_servers = _ref_servers()
    return render("control_room.html", request, iran_servers=iran_servers, foreign_servers=foreign_servers)

# Override only presentation routes. Existing accounting/payment/profile routes are untouched.
app.router.routes[:] = [r for r in app.router.routes if not (
    (getattr(r, "path", None) == "/" and "GET" in (getattr(r, "methods", set()) or set())) or
    (getattr(r, "path", None) == "/control-room" and "GET" in (getattr(r, "methods", set()) or set()))
)]
app.add_api_route("/", reference_dashboard, methods=["GET"])
app.add_api_route("/control-room", reference_control_room, methods=["GET"])

# Cache bust the final bundle.
_base_ref = TEMPLATES.get("base.html", "")
if _base_ref:
    import re as _ref_re
    _base_ref = _ref_re.sub(r'/static/app\.css(?:\?v=[^"\']*)?', '/static/app.css?v=ref-ui-1', _base_ref)
    _base_ref = _ref_re.sub(r'/static/app\.js(?:\?v=[^"\']*)?', '/static/app.js?v=ref-ui-1', _base_ref)
    TEMPLATES["base.html"] = _base_ref

if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)
