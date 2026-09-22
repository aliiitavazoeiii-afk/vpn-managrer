# Allow "actual payment" in followups to exceed current debt.
# Any surplus is treated as prepaid full monthly periods and advances expiry.
import re as _prepay_re

_tpl = TEMPLATES.get("followups.html", "")
if _tpl:
    _tpl = _tpl.replace(
        "مبلغ واردشده معتبر نیست یا از بدهی فعلی بیشتر است.",
        "مبلغ واردشده معتبر نیست.",
    )
    _tpl = _tpl.replace(
        "از قدیمی‌ترین سررسیدها کم می‌شود. اگر بدهی جدیدتری باقی بماند، آن اکانت به «وصول بدهی» برمی‌گردد و پرداخت قبلی به‌اشتباه تسویه کامل حساب نمی‌شود.",
        "از قدیمی‌ترین سررسیدها اعمال می‌شود؛ اگر مبلغ از بدهی فعلی بیشتر باشد، مازاد به‌عنوان پرداخت ماه‌های بعد ثبت می‌شود و تاریخ انقضا جلو می‌رود.",
    )
    _tpl = _tpl.replace(
        "مبلغ واقعی واریزی ثبت شد. بدهی جدیدِ باقی‌مانده، در صورت وجود، به «وصول بدهی» برگشت.",
        "مبلغ واقعی واریزی ثبت شد؛ بدهی قبلی تسویه و هر مبلغ اضافه به ماه‌های بعد اعمال شد.",
    )
    TEMPLATES["followups.html"] = _tpl


def _prepay_candidates(phone, sid, db, states):
    if phone:
        rows = (
            db.query(Subscription)
            .filter(Subscription.phone == phone, Subscription.is_free.is_(False))
            .order_by(Subscription.expiry_date.asc().nullslast(), Subscription.id.asc())
            .all()
        )
    else:
        s = db.get(Subscription, int(sid or 0))
        rows = [s] if s else []

    return [
        s for s in rows
        if s
        and states.get(s.id) == "waiting"
        and not s.is_free
        and s.expiry_date
        and int(s.monthly_fee_toman or 0) > 0
    ]


def followup_pay_amount_with_prepay(
    phone: str = Form(""),
    sid: int = Form(0),
    amount: str = Form(...),
    paid_jalali: str = Form(""),
    db: Session = Depends(get_db),
):
    refresh_billing(db)
    states = _followup_states(db)
    candidates = _prepay_candidates(phone, sid, db, states)

    if not candidates:
        return RedirectResponse("/followups?amount_error=amount", 303)

    try:
        value = _partial_money(amount)
    except Exception:
        value = 0
    if value <= 0:
        return RedirectResponse("/followups?amount_error=amount", 303)

    try:
        paid_at = _partial_paid_at(paid_jalali)
    except Exception:
        return RedirectResponse("/followups?amount_error=date", 303)

    old_total_debt = sum(current_debt_for(s, today_local()) for s in candidates)

    # Allocate one complete monthly period at a time.
    # "next_due" starts at each account's current expiry. Once overdue months are
    # consumed, the same ordering naturally continues into future/prepaid months.
    virtual_due = {s.id: s.expiry_date for s in candidates}
    by_id = {s.id: s for s in candidates}
    allocations = {s.id: 0 for s in candidates}
    remaining = int(value)

    # Hard guard against accidental pathological input while allowing years of prepay.
    max_periods = 1200
    allocated_periods = 0

    while remaining > 0:
        target_sid = min(
            virtual_due,
            key=lambda x: (virtual_due[x], x),
        )
        s = by_id[target_sid]
        fee = int(s.monthly_fee_toman or 0)

        if fee <= 0 or remaining < fee:
            return RedirectResponse("/followups?amount_error=period", 303)

        allocations[target_sid] += 1
        virtual_due[target_sid] = add_jalali_months(virtual_due[target_sid], 1)
        remaining -= fee
        allocated_periods += 1

        if allocated_periods > max_periods:
            return RedirectResponse("/followups?amount_error=amount", 303)

    paid_total = 0
    affected = 0

    for target_sid, periods in allocations.items():
        if periods <= 0:
            continue

        s = db.get(Subscription, target_sid)
        if not s:
            continue

        fee = int(s.monthly_fee_toman or 0)
        applied_amount = fee * periods
        prev = s.expiry_date
        new_expiry = add_jalali_months(prev, periods)

        s.expiry_date = new_expiry
        new_debt = current_debt_for(s, today_local())
        s.debt_toman = new_debt
        s.payment_status = "unpaid" if new_debt > 0 else "paid"
        s.billing_cursor_date = today_local()

        db.add(Payment(
            subscription_id=s.id,
            amount_toman=applied_amount,
            periods=periods,
            previous_expiry=prev,
            new_expiry=new_expiry,
            paid_at=paid_at,
            note="ثبت مبلغ واقعی با پشتیبانی پرداخت ماه‌های آینده",
        ))
        db.add(AuditEvent(
            kind="payment",
            message=(
                f"Actual payment/prepay {applied_amount}; sid={s.id}; "
                f"name={s.display_name}; periods={periods}; "
                f"expiry {prev} -> {new_expiry}; remaining_debt={new_debt}"
            ),
        ))

        _followup_set(
            db,
            s.id,
            None,
            f"actual payment/prepay; amount={applied_amount}; remaining_debt={new_debt}",
        )

        paid_total += applied_amount
        affected += 1

    prepaid = max(0, int(value) - int(old_total_debt))

    db.add(AuditEvent(
        kind="partial_group_payment",
        message=(
            f"Actual payment with prepay; phone={phone}; requested={value}; "
            f"applied={paid_total}; old_debt={old_total_debt}; prepaid={prepaid}; "
            f"affected={affected}"
        ),
    ))
    db.commit()

    return RedirectResponse(
        f"/followups?amount_paid=1&amount={paid_total}&prepaid={prepaid}",
        303,
    )


# Override the previous /followups/pay-amount POST route.
app.router.routes[:] = [
    r for r in app.router.routes
    if not (
        getattr(r, "path", None) == "/followups/pay-amount"
        and "POST" in (getattr(r, "methods", set()) or set())
    )
]
app.add_api_route("/followups/pay-amount", followup_pay_amount_with_prepay, methods=["POST"])

_base = TEMPLATES.get("base.html", "")
if _base:
    _base = _prepay_re.sub(
        r'/static/app\.css(?:\?v=[^"\']*)?',
        '/static/app.css?v=prepay-1',
        _base,
    )
    TEMPLATES["base.html"] = _base

if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)
