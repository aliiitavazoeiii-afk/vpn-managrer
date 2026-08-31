# UI-only navigation aid and static cache bump. No accounting/workflow logic changes.

_FLOWBAR = r'''
<nav class="work-flowbar" aria-label="گردش کار حساب‌ها">
  <a href="/debts" class="{% if request.url.path == '/debts' %}active{% endif %}"><span>۱</span><b>بدهی‌ها</b><small>ارسال پیام و اقدام اولیه</small></a>
  <i>‹</i>
  <a href="/followups" class="{% if request.url.path == '/followups' %}active{% endif %}"><span>۲</span><b>در انتظار</b><small>منتظر پرداخت یا قطع</small></a>
  <i>‹</i>
  <a href="/payments" class="{% if request.url.path == '/payments' %}active{% endif %}"><span>۳</span><b>پرداختی‌ها</b><small>تاریخچه و برگشت پرداخت</small></a>
</nav>
'''

for _name in ("debts.html", "followups.html", "payments.html"):
    _tpl = TEMPLATES.get(_name, "")
    if _tpl and "work-flowbar" not in _tpl:
        _tpl = _tpl.replace("{% block content %}", "{% block content %}" + _FLOWBAR, 1)
        TEMPLATES[_name] = _tpl

# Force fresh static assets after the visual reset.
_base = TEMPLATES.get("base.html", "")
if _base:
    import re as _re
    _base = _re.sub(r'/static/app\.css\?v=\d+', '/static/app.css?v=20', _base)
    _base = _re.sub(r'/static/app\.js\?v=\d+', '/static/app.js?v=20', _base)
    TEMPLATES["base.html"] = _base

if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)
