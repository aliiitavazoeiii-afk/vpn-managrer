# Add a fifth dashboard quick-action card for the full user list.
_QUICK_USERS_CARD = r'''
      <a class="focus-action focus-action-users" href="/users">
        <i>👥</i><div><b>لیست کل کاربران</b><small>مشاهده و مدیریت همه اکانت‌ها</small></div><span>←</span>
      </a>
'''

_quick_tpl = TEMPLATES.get("ref_dashboard.html", "")
if _quick_tpl and "لیست کل کاربران" not in _quick_tpl:
    _anchor = r'''      <a class="focus-action focus-action-orange" href="/control-room">
        <i>⌘</i><div><b>ورود به اتاق کنترل</b><small>سرورها، ترافیک و X-UI</small></div><span>←</span>
      </a>
'''
    if _anchor in _quick_tpl:
        _quick_tpl = _quick_tpl.replace(_anchor, _anchor + _QUICK_USERS_CARD, 1)
        TEMPLATES["ref_dashboard.html"] = _quick_tpl

_base = TEMPLATES.get("base.html", "")
if _base:
    import re as _quick_re
    _base = _quick_re.sub(r'/static/app\.css(?:\?v=[^"\']*)?', '/static/app.css?v=quick-users-1', _base)
    TEMPLATES["base.html"] = _base

if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)
