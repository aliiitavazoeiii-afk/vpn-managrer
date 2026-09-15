# Allow debt correction in both directions while keeping expiry/debt consistent.
# Loaded after date_guard so negative Jalali month shifts are safe and canonical.

# Update the debt desk UI: remove the HTML upper limit and explain both directions.
_debt_tpl = TEMPLATES.get("debts.html", "")
if _debt_tpl:
    _debt_tpl = _debt_tpl.replace(' max="{{ item.debt }}"', '')
    _debt_tpl = _debt_tpl.replace(
        "اگر سیستم بیشتر حساب کرده، مبلغ واقعی را وارد کن.",
        "مبلغ واقعی را وارد کن؛ می‌تواند کمتر یا بیشتر از مبلغ محاسبه‌شده باشد.",
    )
    _debt_tpl = _debt_tpl.replace(
        "مبلغ اصلاحی باید صفر یا مضربی از تعرفه ماهانه باشد و از بدهی محاسبه‌شده بیشتر نباشد.",
        "مبلغ اصلاحی باید صفر یا مضربی از تعرفه ماهانه باشد.",
    )
    TEMPLATES["debts.html"] = _debt_tpl
    if hasattr(env.loader, "mapping"):
        env.loader.mapping.update(TEMPLATES)


def debt_adjust_bidirectional(sid: int, amount: int = Form(...), db: Session = Depends(get_db)):
    refresh_billing(db)
    s = db.get(Subscription, sid)
    if not s or s.is_free or not s.expiry_date:
        return RedirectResponse("/debts?adjust_error=1", 303)

    fee = int(s.monthly_fee_toman or 0)
    periods = debt_periods_for(s)
    computed = periods * fee

    try:
        amount = int(amount)
    except Exception:
        return RedirectResponse("/debts?adjust_error=1", 303)

    if fee <= 0 or amount < 0 or amount % fee != 0:
        return RedirectResponse("/debts?adjust_error=1", 303)

    target_periods = amount // fee
    # debt_periods_for itself is capped at 240 periods, so keep manual corrections representable.
    if target_periods > 240:
        return RedirectResponse("/debts?adjust_error=1", 303)

    prev = s.expiry_date

    # Positive shift means less debt -> move expiry forward.
    # Negative shift means more debt -> move expiry backward.
    shift_months = periods - target_periods
    if shift_months:
        s.expiry_date = add_jalali_months(s.expiry_date, shift_months)

    s.debt_toman = amount
    s.payment_status = "unpaid" if amount > 0 else "paid"
    s.billing_cursor_date = today_local()

    db.add(AuditEvent(
        kind="debt_adjustment",
        message=(
            f"Debt corrected {computed} -> {amount} for {s.display_name}; "
            f"periods {periods} -> {target_periods}; expiry {prev} -> {s.expiry_date}"
        ),
    ))
    db.commit()
    return RedirectResponse("/debts?adjusted=1", 303)


# Replace the previous POST route with the bidirectional correction route.
app.router.routes[:] = [
    r for r in app.router.routes
    if not (
        getattr(r, "path", None) == "/debts/{sid}/adjust"
        and "POST" in (getattr(r, "methods", set()) or set())
    )
]
app.add_api_route("/debts/{sid}/adjust", debt_adjust_bidirectional, methods=["POST"])
