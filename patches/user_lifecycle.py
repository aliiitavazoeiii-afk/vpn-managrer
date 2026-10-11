# USER LIFECYCLE V1 — archive instead of destructive deletion; searchable current and legacy records.
# Appended after existing routes/templates so changes stay isolated.
import ast as _lc_ast
import re as _lc_re
from urllib.parse import quote as _lc_quote


def _lc_archive_rows(db, rows, source):
    states = _followup_states(db)
    archived = []
    for s in rows:
        if s is None or states.get(int(s.id)) == "cut":
            continue
        _followup_set(
            db, s.id, "cut",
            f"archived_from_debt; source={source}; name={s.display_name}; phone={s.phone or ''}",
        )
        archived.append(int(s.id))
    if archived:
        db.add(AuditEvent(
            kind="user_archive",
            message=f"Archived accounts {archived}; source={source}; no subscriptions/payments deleted",
        ))
        db.commit()
    return len(archived)


def _lc_archive_one(sid: int, db: Session = Depends(get_db)):
    s = db.get(Subscription, sid)
    if s is None:
        return RedirectResponse("/debts?manage_error=1", 303)
    _lc_archive_rows(db, [s], "debt-user")
    return RedirectResponse("/debts?user_archived=1", 303)


def _lc_archive_group(phone: str = Form(""), sid: int = Form(0), db: Session = Depends(get_db)):
    normalized = _normalize_phone(phone)
    if normalized:
        rows = db.query(Subscription).filter(Subscription.phone == normalized).all()
    else:
        s = db.get(Subscription, int(sid or 0))
        rows = [s] if s is not None else []
    if not rows:
        return RedirectResponse("/debts?manage_error=1", 303)
    _lc_archive_rows(db, rows, "debt-group")
    return RedirectResponse("/debts?group_archived=1", 303)


# Old physical deletions are only represented by whatever audit data survived.
# Never pretend they are restorable subscriptions, or manufacture payment records.
def _lc_legacy_deleted(db):
    records = (
        db.query(AuditEvent)
        .filter(AuditEvent.kind == "user_delete")
        .order_by(AuditEvent.id.desc())
        .all()
    )
    found = []
    for ev in records:
        msg = str(ev.message or "")
        match = _lc_re.search(
            r"deleted subscriptions=(\[.*?\]); names=(\[.*?\]); deleted payments=",
            msg,
        )
        if not match:
            continue
        try:
            ids = _lc_ast.literal_eval(match.group(1))
            names = _lc_ast.literal_eval(match.group(2))
            if not isinstance(ids, list) or not isinstance(names, list):
                continue
        except (ValueError, SyntaxError):
            continue
        group_phone = ""
        ph = _lc_re.search(r"Phone group delete phone=(\d+)", msg)
        if ph:
            group_phone = ph.group(1)
        for sid, name in zip(ids, names):
            try:
                sid = int(sid)
            except (ValueError, TypeError):
                continue
            found.append({
                "old_id": sid, "name": str(name), "phone": group_phone,
                "deleted_at": ev.created_at, "audit_id": ev.id,
                "add_url": "/add-user?name=" + _lc_quote(str(name))
                + ("&phone=" + _lc_quote(group_phone) if group_phone else ""),
            })
    return found


_lc_removed = TEMPLATES.get("removed.html", "")
if _lc_removed:
    _lc_removed = _lc_removed.replace(
        "{{ ((s.display_name or '') ~ ' ' ~ (s.phone or ''))|lower }}",
        "{{ ((s.display_name or '') ~ ' ' ~ (s.phone or '') ~ ' ' ~ s.id)|lower }}",
    )
    _lc_removed = _lc_removed.replace(
        '<div class="removed-actions"><a href="/users/{{ s.id }}">پروفایل</a>',
        '<div class="removed-actions"><a href="/users/{{ s.id }}">پروفایل</a>'
        '<a href="/add-user?name={{ s.display_name|urlencode }}&phone={{ (s.phone or "")|urlencode }}&fee={{ s.monthly_fee_toman }}">افزودن مجدد</a>',
    )
    _legacy_block = r'''
{% if legacy %}
<h3 class="lc-legacy-title">حذف‌های قدیمی از دیتابیس <small>صرفاً سابقهٔ ثبت عملیات؛ قابل بازگردانی خودکار نیستند</small></h3>
<div class="removed-list">
{% for h in legacy %}
  <section class="removed-row lc-legacy-row" data-removed-row
      data-search="{{ (h.name ~ ' ' ~ h.old_id ~ ' ' ~ h.phone)|lower }}">
    <div><small>نام سابق</small><b>{{ h.name }}</b></div>
    <div><small>شماره (اگر ثبت شده)</small><b class="ltr">{{ h.phone or '—' }}</b></div>
    <div><small>شناسه قبلی</small><b>{{ h.old_id }}</b></div>
    <div><small>وضعیت</small><b class="lc-legacy-label">حذف دائمی قدیمی</b></div>
    <div class="removed-actions"><a href="{{ h.add_url }}">افزودن مجدد</a></div>
  </section>
{% endfor %}
</div>
{% endif %}
'''
    _lc_removed = _lc_removed.replace(
        '<div id="removed-empty"',
        _legacy_block + '\n<div id="removed-empty"',
        1,
    )
    _lc_removed = _lc_removed.replace("{{ rows|length|fa }} نتیجه", "{{ (rows|length + legacy|length)|fa }} نتیجه")
    _lc_removed = _lc_removed.replace(
        'placeholder="جستجو با نام یا شماره همراه…"',
        'placeholder="جستجو با نام، شماره یا شناسه اکانت…"',
    )
    _lc_removed = _lc_removed.replace(
        '{% block content %}',
        '{% block content %}<style>[data-removed-row][hidden]{display:none!important}.lc-legacy-title{font-size:16px;margin:25px 0 13px;color:#fff}.lc-legacy-title small{font-weight:400;color:#9aaabd;font-size:11px}.lc-legacy-row{border-color:rgba(245,158,11,.20)}.lc-legacy-label{color:#e6b773!important}</style>',
        1,
    )
    TEMPLATES["removed.html"] = _lc_removed


def _lc_removed_page(request: Request, db: Session = Depends(get_db)):
    refresh_billing(db)
    states = _followup_states(db)
    removed_ids = [sid for sid, status in states.items() if status == "cut"]
    rows = (
        db.query(Subscription)
        .filter(Subscription.id.in_(removed_ids))
        .order_by(Subscription.display_name.asc()).all()
        if removed_ids else []
    )
    legacy = _lc_legacy_deleted(db)
    return render(
        "removed.html", request, rows=rows, legacy=legacy,
        total_debt=sum(int(s.debt_toman or 0) for s in rows if not s.is_free),
    )


_LC_USERS_TEMPLATE = r'''{% extends "base.html" %}
{% block title %}جستجوی همه کاربران · حساب VPN{% endblock %}
{% block heading %}وضعیت همه کاربران{% endblock %}
{% block subheading %}فعال، بدهکار، در انتظار، حذفی و حذف‌های قدیمی؛ در یک جستجو{% endblock %}
{% block content %}
<style>
.lc-searchbar{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px}
.lc-searchbar input,.lc-searchbar select{background:#0b1726;border:1px solid rgba(255,255,255,.15);border-radius:12px;padding:13px;color:#f3f6fc;font:inherit;font-size:14px}
.lc-searchbar input{flex:1;min-width:240px}.lc-searchbar select{min-width:170px}
.lc-row{display:grid;grid-template-columns:minmax(160px,1.2fr) minmax(140px,1fr) 130px 145px minmax(170px,1fr);gap:12px;align-items:center;padding:15px;margin:8px 0;background:rgba(12,22,36,.88);border:1px solid rgba(255,255,255,.09);border-radius:14px}
.lc-row small{display:block;color:#879cb4;font-size:10px;margin-bottom:5px}.lc-row b{font-size:13px;color:#f0f5fb}.lc-row a{color:#a4d5ff;text-decoration:none;font-weight:750;font-size:12px}
.lc-status{display:inline-block;padding:5px 9px;border-radius:9px;font-size:12px;font-weight:800}
.lc-status.cut{background:#4b2630;color:#ffd8da}.lc-status.waiting{background:#4b351f;color:#ffe3a2}
.lc-status.debt{background:#4b2831;color:#ffd0cd}.lc-status.active{background:#153d32;color:#9ff4cd}
.lc-actions{display:flex;gap:10px;flex-wrap:wrap}
.lc-count{color:#9cabbc;font-size:12px;margin:10px 0 16px}
[data-lc-row][hidden]{display:none!important}
@media(max-width:850px){.lc-row{grid-template-columns:1fr 1fr}.lc-row>div:last-child{grid-column:1/-1}}
@media(max-width:500px){.lc-row{grid-template-columns:1fr}.lc-row>div:last-child{grid-column:auto}}
</style>
<div class="lc-searchbar">
  <input id="lc-q" type="search" autocomplete="off" placeholder="نام، شماره موبایل یا شناسه اکانت…">
  <select id="lc-filter">
    <option value="">همه وضعیت‌ها</option><option value="active">فعال / بدون بدهی</option>
    <option value="debt">بدهکار</option><option value="waiting">در انتظار</option>
    <option value="cut">حذفی‌ها</option><option value="legacy">حذف دائمی قدیمی</option>
  </select>
  <a href="/add-user">＋ افزودن کاربر</a>
</div>
<div class="lc-count" id="lc-count">{{ (rows|length + legacy|length)|fa }} نتیجه</div>
<div id="lc-list">
{% for x in rows %}
<section class="lc-row" data-lc-row data-status="{{ x.state }}"
 data-search="{{ (x.s.display_name ~ ' ' ~ (x.s.phone or '') ~ ' ' ~ x.s.id)|lower }}">
 <div><small>اکانت / شناسه {{ x.s.id }}</small><b>{{ x.s.display_name }}</b></div>
 <div><small>شماره همراه</small><b class="ltr">{{ x.s.phone or '—' }}</b></div>
 <div><small>وضعیت پیگیری</small><span class="lc-status {{ x.state }}">{{ x.label }}</span></div>
 <div><small>انقضا</small><b>{{ x.s.expiry_date|jdate }}</b></div>
 <div class="lc-actions">
   <a href="/users/{{ x.s.id }}">پروفایل</a>
   {% if x.state == 'cut' %}<a href="/removed">حذفی‌ها</a>
   <a href="/add-user?name={{ x.s.display_name|urlencode }}&phone={{ (x.s.phone or '')|urlencode }}&fee={{ x.s.monthly_fee_toman }}">افزودن مجدد</a>{% endif %}
 </div>
</section>
{% endfor %}
{% for h in legacy %}
<section class="lc-row" data-lc-row data-status="legacy" data-search="{{ (h.name ~ ' ' ~ h.old_id ~ ' ' ~ h.phone)|lower }}">
 <div><small>شناسه سابق {{ h.old_id }}</small><b>{{ h.name }}</b></div>
 <div><small>شماره همراه</small><b class="ltr">{{ h.phone or 'ثبت نشده' }}</b></div>
 <div><span class="lc-status cut">حذف دائمی قدیمی</span></div>
 <div><small>تاریخ ثبت حذف</small><b>{{ h.deleted_at or '—' }}</b></div>
 <div class="lc-actions"><a href="{{ h.add_url }}">افزودن مجدد</a></div>
</section>
{% endfor %}
</div>
<p id="lc-empty" hidden>نتیجه‌ای با این مشخصات پیدا نشد.</p>
<script>
(function(){
const q=document.getElementById('lc-q'),f=document.getElementById('lc-filter');
const rows=[...document.querySelectorAll('[data-lc-row]')];
const normalize=s=>String(s||'').toLowerCase().replace(/ي/g,'ی').replace(/ك/g,'ک')
 .replace(/[۰-۹]/g,c=>String('۰۱۲۳۴۵۶۷۸۹'.indexOf(c)))
 .replace(/[٠-٩]/g,c=>String('٠١٢٣٤٥٦٧٨٩'.indexOf(c)));
const apply=()=>{
 const term=normalize(q.value.trim()),filter=f.value;
 let visible=0;
 for(const row of rows){const show=(!filter||row.dataset.status===filter)&&
 (!term||normalize(row.dataset.search).includes(term));row.hidden=!show;if(show)visible++;}
 document.getElementById('lc-count').textContent=String(visible).replace(/\d/g,d=>'۰۱۲۳۴۵۶۷۸۹'[d])+' نتیجه';
 document.getElementById('lc-empty').hidden=visible!==0;
};
q.addEventListener('input',apply);f.addEventListener('change',apply);
const url=new URLSearchParams(location.search);if(url.has('q'))q.value=url.get('q');apply();
})();
</script>
{% endblock %}'''
TEMPLATES["user_status.html"] = _LC_USERS_TEMPLATE


def _lc_user_status(request: Request, db: Session = Depends(get_db)):
    refresh_billing(db)
    states = _followup_states(db)
    rows = []
    for s in db.query(Subscription).order_by(Subscription.display_name.asc()).all():
        state = states.get(int(s.id))
        if state == "cut":
            key, label = "cut", "حذفی / آرشیوشده"
        elif state == "waiting":
            key, label = "waiting", "در انتظار پرداخت"
        elif current_debt_for(s, today_local()) > 0:
            key, label = "debt", "بدهکار / وصول"
        else:
            key, label = "active", "فعال / بدون بدهی"
        rows.append({"s": s, "state": key, "label": label})
    return render("user_status.html", request, rows=rows, legacy=_lc_legacy_deleted(db))


# Link the operator's primary "all users" entry points to the status-aware search.
_lc_base = TEMPLATES.get("ref_dashboard.html", "")
if _lc_base:
    _lc_base = _lc_base.replace('href="/users"', 'href="/user-status"')
    TEMPLATES["ref_dashboard.html"] = _lc_base

_lc_debts = TEMPLATES.get("debts.html", "")
if _lc_debts:
    _lc_debts = _lc_debts.replace(
        "کل سرگروه و تمام اکانت‌های این شماره حذف شوند؟",
        "این سرگروه و اکانت‌های فعالش به حذفی‌ها منتقل شوند؟",
    ).replace(
        "این کاربر حذف شود؟", "این کاربر به حذفی‌ها منتقل شود؟"
    ).replace(
        "این عمل قابل برگشت نیست.", "سوابق حساب و پرداخت حفظ می‌شوند.",
    ).replace(
        "حذف این اکانت", "انتقال به حذفی‌ها",
    ).replace(
        "حذف کل سرگروه", "آرشیو سرگروه",
    ).replace(
        ">حذف کاربر</button>", ">آرشیو کاربر</button>",
    )
    _lc_debts = _lc_debts.replace('href="/users"', 'href="/user-status"')
    _lc_debts = _lc_debts.replace(
        "{% block content %}", 
        '''{% block content %}
{% if request.query_params.get("user_archived") or request.query_params.get("group_archived") %}
<div class="manage-banner">✓ کاربر به حذفی‌ها منتقل شد؛ سوابق حساب و پرداخت محفوظ است.</div>
{% endif %}''',
        1,
    )
    TEMPLATES["debts.html"] = _lc_debts

_lc_add = TEMPLATES.get("add_user_page.html", "")
if _lc_add:
    _lc_add = _lc_add.replace(
        'name="display_name" type="text" required autofocus',
        'name="display_name" type="text" value="{{ request.query_params.get('name', '') }}" required autofocus',
    ).replace(
        'name="phone" type="text" inputmode="tel" autocomplete="off"',
        'name="phone" type="text" value="{{ request.query_params.get('phone', '') }}" inputmode="tel" autocomplete="off"',
    ).replace(
        'name="monthly_fee" type="text" inputmode="numeric" data-money-input value="200,000"',
        'name="monthly_fee" type="text" inputmode="numeric" data-money-input value="{{ request.query_params.get('fee', '200000') }}"',
    )
    TEMPLATES["add_user_page.html"] = _lc_add

if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)


def _lc_replace_route(path, method, endpoint):
    app.router.routes[:] = [
        r for r in app.router.routes
        if not (
            getattr(r, "path", None) == path
            and method in (getattr(r, "methods", set()) or set())
        )
    ]
    app.add_api_route(path, endpoint, methods=[method])


_lc_replace_route("/manage/users/{sid}/delete", "POST", _lc_archive_one)
_lc_replace_route("/manage/group/delete", "POST", _lc_archive_group)
_lc_replace_route("/removed", "GET", _lc_removed_page)
app.add_api_route("/user-status", _lc_user_status, methods=["GET"])
