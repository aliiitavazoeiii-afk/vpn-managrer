# BILLING_FIRST_DAY_LIVE_V1
# Only append AFTER billing_anchor.py and all other payment route overrides.
# New debts use actual expiry -> first of next Jalali month. No pre-due charges.
# Historical paused anchor rows are not rewritten or re-applied.
from importlib.util import spec_from_file_location as _b_spec_file, module_from_spec as _b_from_spec
from sqlalchemy import text as _b_text

_b_invoice_spec = _b_spec_file("_hesab_billing_policy", "/sms-patch/billing_policy.py")
if not _b_invoice_spec or not _b_invoice_spec.loader:
    raise RuntimeError("Canonical billing policy missing; refusing to start with mismatched billing")
_b_invoice_module = _b_from_spec(_b_invoice_spec)
_b_invoice_spec.loader.exec_module(_b_invoice_module)


def _b_month_start(d):
    jy, jm, _ = _date_guard_jparts(d)
    return date(*_date_guard_j2g(jy, jm, 1))


def _b_next_start(d):
    return add_jalali_months(_b_month_start(d), 1)


def _b_plan(s, as_of=None):
    return _b_invoice_module.calculate_invoice(
        getattr(s, "expiry_date", None),
        0 if s.is_free else int(s.monthly_fee_toman or 0),
        as_of or today_local(),
        _b_month_start,
        _b_next_start,
    )


def current_debt_for(s, as_of=None):
    return _b_plan(s, as_of)["amount"]


def refresh_billing(db):
    now = today_local()
    changed = False
    for s in db.query(Subscription).all():
        amount = current_debt_for(s, now)
        status = "unpaid" if amount > 0 else "paid"
        if int(s.debt_toman or 0) != amount:
            s.debt_toman = amount
            changed = True
        if s.payment_status != status:
            s.payment_status = status
            changed = True
        if s.billing_cursor_date != now:
            s.billing_cursor_date = now
            changed = True
    if changed:
        db.commit()


env.globals.update(current_debt_for=current_debt_for)


def _b_settle_one(db, s, note, waiting=False):
    now = today_local()
    plan = _b_plan(s, now)
    if not plan["due"] or plan["amount"] <= 0:
        return 0
    old_expiry = s.expiry_date
    new_expiry = plan["target"]
    if not new_expiry or new_expiry <= old_expiry:
        raise RuntimeError("Refusing nonforward billing transition")

    s.expiry_date = new_expiry
    s.debt_toman = 0
    s.payment_status = "paid"
    s.billing_cursor_date = now
    amount = int(plan["amount"])

    db.add(Payment(
        subscription_id=s.id,
        amount_toman=amount,
        periods=_b_legacy_periods(old_expiry, now),
        previous_expiry=old_expiry,
        new_expiry=new_expiry,
        note=note + "; prorated to first day of next Jalali month",
    ))
    db.add(AuditEvent(
        kind="payment",
        message=f"First-day billing; sid={s.id}; amount={amount}; expiry={old_expiry}->{new_expiry}; source={note}",
    ))
    if waiting:
        _followup_set(db, s.id, None, "settled first-day invoice")
    # Mark only genuinely open legacy anchor preparations as paid after payment.
    # Preserve historical 'paused' and earlier 'paid' records for audit.
    db.execute(
        _b_text("UPDATE billing_anchor SET status='paid', paid_at=NOW() WHERE subscription_id=:sid AND status IN ('pending','scheduled')"),
        {"sid": int(s.id)},
    )
    return amount


def _b_legacy_periods(old_expiry, now):
    due = old_expiry
    count = 0
    while due and due <= now and count < 240:
        due = add_one_jalali_month(due)
        count += 1
    return count


def _b_selected(phone, sid, db):
    if phone:
        return (
            db.query(Subscription)
            .filter(Subscription.phone == phone, Subscription.is_free.is_(False))
            .order_by(Subscription.id.asc())
            .all()
        )
    s = db.get(Subscription, int(sid or 0))
    return [s] if s else []


def _b_debt_pay(sid: int, db: Session = Depends(get_db)):
    refresh_billing(db)
    states = _followup_states(db)
    s = db.get(Subscription, sid)
    if not s or s.is_free or states.get(s.id) in ("cut", "waiting"):
        return RedirectResponse("/debts", 303)
    if _b_settle_one(db, s, "ثبت واریز تکی از وصول"):
        db.commit()
        return RedirectResponse("/debts?paid=1", 303)
    return RedirectResponse("/debts", 303)


def _b_debt_group_pay(phone: str = Form(""), sid: int = Form(0), db: Session = Depends(get_db)):
    refresh_billing(db)
    states = _followup_states(db)
    count = 0
    total = 0
    for s in _b_selected(phone, sid, db):
        if not s or s.is_free or states.get(s.id) in ("cut", "waiting"):
            continue
        value = _b_settle_one(db, s, "ثبت واریز کلی از وصول")
        if value:
            count += 1
            total += value
    if count:
        db.commit()
    return RedirectResponse(f"/debts?group_paid=1&count={count}&total={total}", 303)


def _b_waiting_pay(sid: int, db: Session = Depends(get_db)):
    refresh_billing(db)
    states = _followup_states(db)
    s = db.get(Subscription, sid)
    if not s or s.is_free or states.get(s.id) != "waiting":
        return RedirectResponse("/followups", 303)
    if _b_settle_one(db, s, "ثبت واریز تکی از در انتظار", waiting=True):
        db.commit()
        return RedirectResponse("/followups?paid=1", 303)
    return RedirectResponse("/followups", 303)


def _b_waiting_group_pay(phone: str = Form(""), sid: int = Form(0), db: Session = Depends(get_db)):
    refresh_billing(db)
    states = _followup_states(db)
    count = 0
    total = 0
    for s in _b_selected(phone, sid, db):
        if not s or s.is_free or states.get(s.id) != "waiting":
            continue
        value = _b_settle_one(db, s, "ثبت واریز کلی از در انتظار", waiting=True)
        if value:
            count += 1
            total += value
    if count:
        db.commit()
    return RedirectResponse(f"/followups?group_paid=1&count={count}&total={total}", 303)


# The prepayment calculator and month-multiple manual debt adjustment are not
# day-accurate. Fail closed until they have dedicated proration/credit handling.
# Do NOT let them post incorrect expiry updates against a prorated invoice.
def _b_incompatible_partial(phone: str = Form(""), sid: int = Form(0),
                            amount: str = Form(""), paid_jalali: str = Form(""),
                            db: Session = Depends(get_db)):
    return RedirectResponse("/followups?amount_error=prorated", 303)


def _b_incompatible_adjust(sid: int, amount: str = Form(""),
                           db: Session = Depends(get_db)):
    return RedirectResponse("/debts?adjust_error=prorated", 303)


def _b_override_route(path, fn):
    app.router.routes[:] = [
        r for r in app.router.routes
        if not (getattr(r, "path", None) == path and
                "POST" in (getattr(r, "methods", set()) or set()))
    ]
    app.add_api_route(path, fn, methods=["POST"])


_b_override_route("/debts/{sid}/pay", _b_debt_pay)
_b_override_route("/debts/pay-group", _b_debt_group_pay)
_b_override_route("/followups/{sid}/pay", _b_waiting_pay)
_b_override_route("/followups/pay-group", _b_waiting_group_pay)
_b_override_route("/followups/pay-amount", _b_incompatible_partial)
_b_override_route("/debts/{sid}/adjust", _b_incompatible_adjust)

# Make temporary restrictions explicit; preserve the rest of the existing UI.
for _b_template in ("debts.html", "followups.html"):
    _b_markup = TEMPLATES.get(_b_template, "")
    if _b_markup:
        _notice = (
            '<div class="manage-banner">محاسبه بدهی‌ها تا یکم ماه بعد انجام می‌شود. '
            'در این مرحله اصلاح دستی مبلغ و پرداخت ناقص غیرفعال است؛ '
            'برای اصلاح حساب از ویرایش تاریخ انقضا استفاده کنید.</div>'
        )
        _b_markup = _b_markup.replace("{% block content %}", "{% block content %}" + _notice, 1)
        if _b_template == "followups.html":
            _b_markup = _b_markup.replace(
                '<summary>ثبت مبلغ واقعی</summary>',
                '<summary>ثبت مبلغ واقعی (موقتاً غیرفعال)</summary>', 1
            ).replace(
                '<form method="post" action="/followups/pay-amount"',
                '<form method="post" action="/followups/pay-amount"', 1
            )
        TEMPLATES[_b_template] = _b_markup
if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)
