# Focused dashboard: hero -> quick actions -> control room.
# UI/template only. Existing billing/payment/follow-up logic is untouched.

_FOCUSED_DASHBOARD = r'''{% extends "base.html" %}
{% block title %}VPN Command Center{% endblock %}
{% block heading %}{% endblock %}
{% block subheading %}{% endblock %}
{% block content %}
<div class="focus-dashboard">
  <section class="focus-hero">
    <div class="focus-hero-copy">
      <div class="focus-kicker"><span></span> VPN COMMAND CENTER</div>
      <h1>صبح بخیر علی <em>✦</em></h1>
      <p>مرکز فرماندهی کسب‌وکار VPN؛ سریع، ساده و همیشه جلوی چشم.</p>
    </div>
    <div class="focus-orb" aria-hidden="true"><i></i><b></b><em></em><span></span></div>
  </section>

  <section class="focus-quick-section">
    <header class="focus-section-head">
      <div>
        <span class="focus-head-icon">⚡</span>
        <div><h2>عملیات سریع</h2><p>کارهای روزانه بدون رفتن بین چند صفحه</p></div>
      </div>
    </header>
    <div class="focus-quick-grid">
      <a class="focus-action focus-action-purple" href="/debts#add-user-box">
        <i>＋</i><div><b>افزودن کاربر</b><small>ساخت اکانت جدید یا زیرمجموعه</small></div><span>←</span>
      </a>
      <a class="focus-action focus-action-green" href="/debts">
        <i>✓</i><div><b>ثبت پرداخت</b><small>وصول و تسویه سریع حساب</small></div><span>←</span>
      </a>
      <a class="focus-action focus-action-blue" href="/debts">
        <i>➤</i><div><b>ارسال پیام</b><small>متن آماده سررسید و پیگیری</small></div><span>←</span>
      </a>
      <a class="focus-action focus-action-orange" href="/control-room">
        <i>⌘</i><div><b>ورود به اتاق کنترل</b><small>سرورها، ترافیک و X-UI</small></div><span>←</span>
      </a>
    </div>
  </section>

  <section class="focus-control-section">
    <header class="focus-section-head focus-control-head">
      <div>
        <span class="focus-head-icon">⌘</span>
        <div><h2>اتاق کنترل</h2><p>نمای زنده زیرساخت؛ تمرکز اصلی روی ترافیک سرورهای ایران</p></div>
      </div>
      <a href="/control-room">باز کردن اتاق کنترل <span>←</span></a>
    </header>

    <div class="focus-server-group-head">
      <div><span>🇮🇷</span><div><b>سرورهای ایران</b><small>ترافیک باقی‌مانده و زمان تخمینی تا اتمام</small></div></div>
      <span class="focus-ready-pill">۴ سرور</span>
    </div>

    <div class="focus-server-grid">
      {% for srv in iran_servers %}
      <article class="focus-server-card">
        <div class="focus-server-top">
          <div><span class="focus-flag">🇮🇷</span><div><b>{{ srv.name }}</b><small>{{ srv.state }}</small></div></div>
          <span class="focus-online"><i></i>{{ srv.state }}</span>
        </div>
        <div class="focus-server-main">
          <div class="focus-ring" style="--p:{{ srv.percent }}"><div><strong>{{ srv.percent|fa }}٪</strong><small>مصرف</small></div></div>
          <div class="focus-server-numbers">
            <div><small>ترافیک باقی‌مانده</small><strong>{{ srv.remaining }}</strong></div>
            <div><small>زمان تخمینی</small><strong>{{ srv.eta }}</strong></div>
          </div>
        </div>
        <div class="focus-server-metrics">
          <div><small>CPU</small><b>{{ srv.cpu }}</b></div>
          <div><small>RAM</small><b>{{ srv.ram }}</b></div>
          <div><small>مانیتور</small><b>در انتظار Agent</b></div>
        </div>
      </article>
      {% endfor %}
    </div>

    <div class="focus-server-group-head focus-foreign-head">
      <div><span>🌍</span><div><b>سرورهای خارجی</b><small>وضعیت و دسترسی مدیریتی X-UI</small></div></div>
      <span class="focus-ready-pill">۴ سرور</span>
    </div>
    <div class="focus-foreign-grid">
      {% for srv in foreign_servers %}
      <article class="focus-foreign-card">
        <span class="focus-foreign-flag">{{ srv.flag }}</span>
        <div><b>{{ srv.name }}</b><small>{{ srv.state }}</small></div>
        <em>{{ srv.note }}</em>
        <span class="focus-xui-pill">X-UI</span>
      </article>
      {% endfor %}
    </div>
  </section>
</div>
{% endblock %}'''

TEMPLATES["ref_dashboard.html"] = _FOCUSED_DASHBOARD

# Cache-bust the final stylesheet after the scale/layout change.
_base = TEMPLATES.get("base.html", "")
if _base:
    import re as _focus_re
    _base = _focus_re.sub(r'/static/app\.css(?:\?v=[^"\']*)?', '/static/app.css?v=focus-2', _base)
    TEMPLATES["base.html"] = _base

if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)
