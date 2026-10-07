# BILLING_ANCHOR_14050801_V1
# Transitional billing alignment to 1405/08/01 (2026-10-23) and first-of-month billing.
from sqlalchemy import text as _anchor_text

_anchor_original_refresh_billing = refresh_billing
_anchor_original_current_debt_for = current_debt_for
_anchor_cache = {}


def _anchor_extra_periods(anchor_date, as_of):
    if not anchor_date or not as_of or as_of < anchor_date:
        return 0
    n = 0
    cursor = anchor_date
    while cursor <= as_of and n < 240:
        n += 1
        cursor = add_jalali_months(cursor, 1)
    return n


def _anchor_load(db):
    global _anchor_cache
    rows = db.execute(
        _anchor_text(
            """
            SELECT subscription_id, original_expiry, anchor_expiry, transition_amount_toman, status
            FROM billing_anchor
            WHERE status IN ('pending','scheduled')
            """
        )
    ).mappings().all()
    _anchor_cache = {int(r["subscription_id"]): dict(r) for r in rows}
    return _anchor_cache


def _anchor_amount_for(a, s, when):
    if a.get("status") == "scheduled" and a.get("original_expiry") and when < a["original_expiry"]:
        return 0
    extra = _anchor_extra_periods(a["anchor_expiry"], when)
    return int(a["transition_amount_toman"] or 0) + extra * int(s.monthly_fee_toman or 0)


def refresh_billing(db):
    _anchor_original_refresh_billing(db)
    try:
        rows = _anchor_load(db)
    except Exception:
        return

    if not rows:
        return

    today = today_local()
    subs = (
        db.query(Subscription)
        .filter(Subscription.id.in_(list(rows.keys())))
        .all()
    )
    for s in subs:
        a = rows.get(int(s.id))
        if not a:
            continue
        amount = _anchor_amount_for(a, s, today)
        s.debt_toman = amount
        s.payment_status = "unpaid" if amount > 0 else "paid"
        s.billing_cursor_date = today
    db.flush()


def current_debt_for(s, as_of=None):
    a = _anchor_cache.get(int(getattr(s, "id", 0) or 0))
    if a:
        when = as_of or today_local()
        return _anchor_amount_for(a, s, when)
    return _anchor_original_current_debt_for(s, as_of) if as_of is not None else _anchor_original_current_debt_for(s)


def _anchor_apply_manual(db, s, note):
    row = db.execute(
        _anchor_text(
            """
            SELECT subscription_id, original_expiry, anchor_expiry,
                   transition_amount_toman, status
            FROM billing_anchor
            WHERE subscription_id=:sid
            FOR UPDATE
            """
        ),
        {"sid": int(s.id)},
    ).mappings().first()

    if not row or row["status"] not in ("pending", "scheduled"):
        return False

    today = today_local()
    if row["status"] == "scheduled" and row["original_expiry"] and today < row["original_expiry"]:
        return False

    extra = _anchor_extra_periods(row["anchor_expiry"], today)
    amount = int(row["transition_amount_toman"] or 0) + extra * int(s.monthly_fee_toman or 0)
    new_expiry = add_jalali_months(row["anchor_expiry"], extra) if extra else row["anchor_expiry"]
    prev = s.expiry_date

    s.expiry_date = new_expiry
    s.debt_toman = 0
    s.payment_status = "paid"
    s.billing_cursor_date = today

    db.add(Payment(
        subscription_id=s.id,
        amount_toman=amount,
        periods=extra,
        previous_expiry=prev,
        new_expiry=new_expiry,
        note=note,
    ))
    db.add(AuditEvent(
        kind="payment",
        message=(
            f"Anchor manual payment {amount}; sid={s.id}; "
            f"expiry {prev} -> {new_expiry}"
        ),
    ))
    _followup_set(db, s.id, None, "anchor transition paid manually")
    db.execute(
        _anchor_text(
            """
            UPDATE billing_anchor
            SET status='paid', paid_at=NOW()
            WHERE subscription_id=:sid
            """
        ),
        {"sid": int(s.id)},
    )
    return True


_anchor_old_followup_pay = followup_pay
def followup_pay_anchor(sid: int, db: Session = Depends(get_db)):
    refresh_billing(db)
    s = db.get(Subscription, sid)
    if s and _anchor_apply_manual(db, s, "ثبت واریز دستی دوره همسان‌سازی سررسید"):
        db.commit()
        return RedirectResponse("/followups?paid=1", 303)
    return _anchor_old_followup_pay(sid, db)


app.router.routes[:] = [
    r for r in app.router.routes
    if not (
        getattr(r, "path", None) == "/followups/{sid}/pay"
        and "POST" in (getattr(r, "methods", set()) or set())
    )
]
app.add_api_route("/followups/{sid}/pay", followup_pay_anchor, methods=["POST"])


_anchor_old_debt_group_pay = debt_group_pay
def debt_group_pay_anchor(phone: str = Form(""), sid: int = Form(0), db: Session = Depends(get_db)):
    refresh_billing(db)
    if phone:
        candidates = db.query(Subscription).filter(
            Subscription.phone == phone,
            Subscription.is_free.is_(False)
        ).order_by(Subscription.id.asc()).all()
    else:
        s = db.get(Subscription, int(sid or 0))
        candidates = [s] if s else []

    applied = 0
    total = 0
    for s in candidates:
        if not s:
            continue
        before = current_debt_for(s, today_local())
        if _anchor_apply_manual(db, s, "ثبت واریز کلی دستی دوره همسان‌سازی سررسید"):
            applied += 1
            total += int(before or 0)

    if applied:
        db.commit()
        return RedirectResponse(f"/debts?group_paid=1&count={applied}&total={total}", 303)

    return _anchor_old_debt_group_pay(phone, sid, db)


app.router.routes[:] = [
    r for r in app.router.routes
    if not (
        getattr(r, "path", None) == "/debts/pay-group"
        and "POST" in (getattr(r, "methods", set()) or set())
    )
]
app.add_api_route("/debts/pay-group", debt_group_pay_anchor, methods=["POST"])


_anchor_old_followup_group_pay = followup_group_pay
def followup_group_pay_anchor(phone: str = Form(""), sid: int = Form(0), db: Session = Depends(get_db)):
    refresh_billing(db)
    if phone:
        candidates = db.query(Subscription).filter(
            Subscription.phone == phone,
            Subscription.is_free.is_(False)
        ).order_by(Subscription.id.asc()).all()
    else:
        s = db.get(Subscription, int(sid or 0))
        candidates = [s] if s else []

    states = _followup_states(db)
    applied = 0
    total = 0
    for s in candidates:
        if not s or states.get(s.id) != "waiting":
            continue
        before = current_debt_for(s, today_local())
        if _anchor_apply_manual(db, s, "ثبت واریز کلی دستی از در انتظار - همسان‌سازی سررسید"):
            applied += 1
            total += int(before or 0)

    if applied:
        db.commit()
        return RedirectResponse(f"/followups?group_paid=1&count={applied}&total={total}", 303)

    return _anchor_old_followup_group_pay(phone, sid, db)


app.router.routes[:] = [
    r for r in app.router.routes
    if not (
        getattr(r, "path", None) == "/followups/pay-group"
        and "POST" in (getattr(r, "methods", set()) or set())
    )
]
app.add_api_route("/followups/pay-group", followup_group_pay_anchor, methods=["POST"])
