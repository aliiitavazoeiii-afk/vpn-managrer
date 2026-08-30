# Hesab VPN user management: add users, delete one account or a whole phone group.
from fastapi import Form
from datetime import datetime


def _ascii_digits(value):
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return str(value or "").translate(table)


def _normalize_phone(value):
    raw = _ascii_digits(value).strip()
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits.startswith("0098"):
        digits = "0" + digits[4:]
    elif digits.startswith("98") and len(digits) == 12:
        digits = "0" + digits[2:]
    elif digits.startswith("9") and len(digits) == 10:
        digits = "0" + digits
    return digits or None


def _parse_money(value):
    raw = _ascii_digits(value)
    for ch in (",", "٬", "،", "_", " "):
        raw = raw.replace(ch, "")
    return int(raw or 0)


def _required_column_fallbacks(obj, expiry_date):
    """Fill only truly required mapped columns that do not have defaults."""
    for col in Subscription.__table__.columns:
        if col.primary_key:
            continue
        if getattr(obj, col.name, None) is not None:
            continue
        if col.nullable or col.default is not None or col.server_default is not None:
            continue
        try:
            pytype = col.type.python_type
        except Exception:
            pytype = None
        if pytype is str:
            setattr(obj, col.name, "")
        elif pytype is int:
            setattr(obj, col.name, 0)
        elif pytype is bool:
            setattr(obj, col.name, False)
        elif pytype is date:
            setattr(obj, col.name, expiry_date or today_local())
        elif pytype is datetime:
            setattr(obj, col.name, datetime.now())


def _next_source_row(db):
    if not hasattr(Subscription, "source_row"):
        return None
    row = db.query(Subscription.source_row).order_by(Subscription.source_row.desc()).first()
    try:
        return int(row[0] or 0) + 1 if row else 1
    except Exception:
        return 1


def _delete_subscription_rows(db, rows, label):
    rows = [s for s in rows if s is not None]
    if not rows:
        return 0
    ids = [s.id for s in rows]
    names = [s.display_name for s in rows]
    payment_count = 0
    if "Payment" in globals() and ids:
        try:
            payment_count = db.query(Payment).filter(Payment.subscription_id.in_(ids)).delete(synchronize_session=False)
        except Exception:
            db.rollback()
            raise
    for s in rows:
        db.delete(s)
    db.flush()
    db.add(AuditEvent(
        kind="user_delete",
        message=f"{label}; deleted subscriptions={ids}; names={names}; deleted payments={payment_count}",
    ))
    db.commit()
    return len(rows)


_today_j = _g2j(today_local().year, today_local().month, today_local().day)
env.globals["today_jparts"] = _today_j

_manage_style = r'''
<style>
.add-user-wrap{margin:0 0 16px;border:1px solid rgba(255,255,255,.09);border-radius:16px;background:rgba(14,19,30,.72);overflow:hidden}
.add-user-wrap>summary{list-style:none;cursor:pointer;padding:14px 16px;font-weight:800;color:#eef2f7;display:flex;align-items:center;justify-content:space-between}
.add-user-wrap>summary::-webkit-details-marker{display:none}.add-user-wrap[open]>summary{border-bottom:1px solid rgba(255,255,255,.07)}
.add-user-form{padding:15px;display:grid;grid-template-columns:1.15fr 1fr .75fr;gap:11px;align-items:end}.add-user-field{display:flex;flex-direction:column;gap:6px}.add-user-field label{font-size:11px;color:#939eaf}.add-user-field input,.add-user-field select{height:42px;border:1px solid rgba(255,255,255,.12);border-radius:10px;background:#0d1421;color:#f4f6f9;padding:0 11px;font:inherit;font-size:13px;outline:none}.add-user-field input:focus,.add-user-field select:focus{border-color:rgba(147,197,253,.55)}
.add-user-date{grid-column:1/3}.add-user-date-grid{display:grid;grid-template-columns:80px 1fr 95px;gap:7px}.add-user-help{grid-column:1/3;font-size:11px;color:#7f899a;line-height:1.7}.add-user-submit{height:42px;border:0;border-radius:10px;background:#eef2f6;color:#10151d;font:inherit;font-size:13px;font-weight:850;cursor:pointer}.add-user-submit:hover{background:#fff}
.group-action-row{display:flex;justify-content:flex-end;padding:0 16px 9px;background:transparent}.danger-mini{border:1px solid rgba(248,113,113,.23);background:transparent;color:#dca0a7;border-radius:9px;padding:6px 9px;font:inherit;font-size:10px;cursor:pointer}.danger-mini:hover{background:rgba(239,68,68,.09);color:#ffc0c6;border-color:rgba(248,113,113,.4)}
.service-delete-form{margin:0}.service-delete-btn{width:100%;border:1px solid rgba(248,113,113,.20);background:transparent;color:#c9949b;border-radius:9px;padding:7px 9px;font:inherit;font-size:10px;cursor:pointer}.service-delete-btn:hover{background:rgba(239,68,68,.08);color:#ffb5bd}
.manage-banner{margin-bottom:14px;border-radius:13px;padding:11px 14px;font-weight:700;border:1px solid rgba(96,165,250,.22);background:rgba(59,130,246,.08);color:#bed9ff}.manage-banner.error{border-color:rgba(248,113,113,.22);background:rgba(239,68,68,.08);color:#ffc1c7}
@media(max-width:900px){.add-user-form{grid-template-columns:1fr 1fr}.add-user-date,.add-user-help{grid-column:1/-1}.add-user-submit{grid-column:1/-1}}@media(max-width:560px){.add-user-form{grid-template-columns:1fr}.add-user-date,.add-user-help,.add-user-submit{grid-column:auto}.add-user-date-grid{grid-template-columns:70px 1fr 88px}}
</style>
'''

_add_user_ui = r'''
<details class="add-user-wrap" id="add-user-box">
  <summary><span>＋ افزودن کاربر</span><small>شماره تکراری = زیرمجموعه همان سرگروه</small></summary>
  <form method="post" action="/manage/users/add" class="add-user-form" data-preserve-position>
    <div class="add-user-field"><label>نام اکانت</label><input name="display_name" type="text" required placeholder="مثلاً hadi"></div>
    <div class="add-user-field"><label>شماره همراه</label><input name="phone" type="text" inputmode="tel" placeholder="0912..." autocomplete="off"></div>
    <div class="add-user-field"><label>مبلغ ماهانه</label><input name="monthly_fee" type="text" inputmode="numeric" data-money-input value="200,000"></div>
    <div class="add-user-field add-user-date"><label>تاریخ انقضا · شمسی</label><div class="add-user-date-grid">
      <select name="jd">{% for d in range(1,32) %}<option value="{{ d }}" {% if d == today_jparts[2] %}selected{% endif %}>{{ d|fa }}</option>{% endfor %}</select>
      <select name="jm">{% for month_name in jalali_months %}<option value="{{ loop.index }}" {% if loop.index == today_jparts[1] %}selected{% endif %}>{{ month_name }}</option>{% endfor %}</select>
      <select name="jy">{% for y in jalali_years_around(today_jparts[0]) %}<option value="{{ y }}" {% if y == today_jparts[0] %}selected{% endif %}>{{ y|fa }}</option>{% endfor %}</select>
    </div></div>
    <div class="add-user-help">اگر این شماره از قبل برای کاربر دیگری ثبت شده باشد، اکانت جدید خودکار زیر همان شماره نمایش داده می‌شود. اگر شماره جدید باشد، یک گروه مستقل ساخته می‌شود.</div>
    <button class="add-user-submit" type="submit">ثبت کاربر</button>
  </form>
</details>
'''

_banners = r'''
{% if request.query_params.get("user_added") %}<div class="manage-banner">✓ کاربر اضافه شد. اگر تاریخ سررسیدش هنوز نرسیده باشد، در لیست بدهی‌ها نمایش داده نمی‌شود.</div>{% endif %}
{% if request.query_params.get("user_deleted") %}<div class="manage-banner">✓ اکانت حذف شد.</div>{% endif %}
{% if request.query_params.get("group_deleted") %}<div class="manage-banner">✓ سرگروه و همه اکانت‌های آن شماره حذف شدند.</div>{% endif %}
{% if request.query_params.get("manage_error") %}<div class="manage-banner error">عملیات انجام نشد؛ اطلاعات ورودی را بررسی کن.</div>{% endif %}
'''

_tpl = TEMPLATES.get("debts.html", "")
if _tpl:
    # Management styling and status banners.
    _tpl = _tpl.replace("{% block content %}", "{% block content %}" + _manage_style + _banners, 1)

    # Add-user form immediately before debt search.
    search_anchor = '<div class="debt-searchbar">'
    if search_anchor in _tpl:
        _tpl = _tpl.replace(search_anchor, _add_user_ui + search_anchor, 1)

    # Stable key lets the browser restore the exact group and viewport after a POST/redirect.
    group_anchor = '<section class="debt-group-v3" data-debt-group data-search="{{ g.search_text }}">'
    if group_anchor in _tpl:
        _tpl = _tpl.replace(
            group_anchor,
            '<section class="debt-group-v3" data-debt-group data-search="{{ g.search_text }}" data-group-key="{% if g.phone %}phone-{{ g.phone }}{% else %}sid-{{ g.rows[0].s.id }}{% endif %}">',
            1,
        )

    # Whole-group delete control. For a phone group it deletes every subscription carrying that phone,
    # including paid/future siblings that are not visible in the debt-only list.
    head_end = '    </button>\n\n    <div class="debt-children-v3"'
    group_delete_ui = r'''    </button>
    <div class="group-action-row">
      <form method="post" action="/manage/group/delete" data-preserve-position onsubmit="return confirm('{% if g.phone %}کل سرگروه و تمام اکانت‌های این شماره حذف شوند؟{% else %}این کاربر حذف شود؟{% endif %} این عمل قابل برگشت نیست.')">
        <input type="hidden" name="phone" value="{{ g.phone or '' }}">
        <input type="hidden" name="sid" value="{% if not g.phone %}{{ g.rows[0].s.id }}{% else %}0{% endif %}">
        <button type="submit" class="danger-mini">{% if g.phone and g.services > 1 %}حذف کل سرگروه{% else %}حذف کاربر{% endif %}</button>
      </form>
    </div>

    <div class="debt-children-v3"'''
    if head_end in _tpl:
        _tpl = _tpl.replace(head_end, group_delete_ui, 1)

    # Per-subscription delete control.
    actions_anchor = '''        <div class="service-actions">
          <form method="post" action="/debts/{{ s.id }}/pay"'''
    child_delete_ui = '''        <div class="service-actions">
          <form method="post" action="/manage/users/{{ s.id }}/delete" class="service-delete-form" data-preserve-position onsubmit="return confirm('اکانت {{ s.display_name }} حذف شود؟ این عمل قابل برگشت نیست.')">
            <button type="submit" class="service-delete-btn">حذف این اکانت</button>
          </form>
          <form method="post" action="/debts/{{ s.id }}/pay"'''
    if actions_anchor in _tpl:
        _tpl = _tpl.replace(actions_anchor, child_delete_ui, 1)

    # Bump static asset version so scroll-restoration JS is not cached.
    for old in ("v=2", "v=3", "v=4", "v=5", "v=6"):
        _tpl = _tpl.replace(old, "v=7")

    TEMPLATES["debts.html"] = _tpl
    if hasattr(env.loader, "mapping"):
        env.loader.mapping.update(TEMPLATES)


def add_managed_user(
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
        jy, jm, jd = int(jy), int(jm), int(jd)
        gy, gm, gd = _j2g(jy, jm, jd)
        expiry = date(gy, gm, gd)
    except Exception:
        return RedirectResponse("/debts?manage_error=1", 303)

    existing_same_phone = 0
    if normalized_phone:
        existing_same_phone = db.query(Subscription).filter(Subscription.phone == normalized_phone).count()

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
                f"User manually added: id={s.id}; name={name}; phone={normalized_phone}; "
                f"expiry={expiry}; monthly_fee={fee}; matched_existing_phone={bool(existing_same_phone)}"
            ),
        ))
        db.commit()
    except Exception:
        db.rollback()
        return RedirectResponse("/debts?manage_error=1", 303)

    return RedirectResponse("/debts?user_added=1", 303)


def delete_managed_user(sid: int, db: Session = Depends(get_db)):
    s = db.get(Subscription, sid)
    if not s:
        return RedirectResponse("/debts?manage_error=1", 303)
    try:
        _delete_subscription_rows(db, [s], f"Single account delete id={sid}")
    except Exception:
        db.rollback()
        return RedirectResponse("/debts?manage_error=1", 303)
    return RedirectResponse("/debts?user_deleted=1", 303)


def delete_managed_group(phone: str = Form(""), sid: int = Form(0), db: Session = Depends(get_db)):
    try:
        normalized_phone = _normalize_phone(phone)
        if normalized_phone:
            rows = db.query(Subscription).filter(Subscription.phone == normalized_phone).all()
            if not rows:
                raise ValueError("group not found")
            _delete_subscription_rows(db, rows, f"Phone group delete phone={normalized_phone}")
            return RedirectResponse("/debts?group_deleted=1", 303)
        target = db.get(Subscription, int(sid or 0))
        if not target:
            raise ValueError("user not found")
        _delete_subscription_rows(db, [target], f"No-phone group delete id={target.id}")
        return RedirectResponse("/debts?user_deleted=1", 303)
    except Exception:
        db.rollback()
        return RedirectResponse("/debts?manage_error=1", 303)


app.add_api_route("/manage/users/add", add_managed_user, methods=["POST"])
app.add_api_route("/manage/users/{sid}/delete", delete_managed_user, methods=["POST"])
app.add_api_route("/manage/group/delete", delete_managed_group, methods=["POST"])
