# Payment history with safe undo for accidental payment registration.

PAYMENTS_UNDO_TEMPLATE = r'''{% extends "base.html" %}
{% block title %}پرداختی‌ها · حساب VPN{% endblock %}
{% block heading %}پرداختی‌ها{% endblock %}
{% block subheading %}تاریخچه واریزها؛ آخرین پرداخت هر اکانت در صورت امن بودن قابل برگشت است{% endblock %}
{% block content %}
<style>
.pay-history{display:flex;flex-direction:column;gap:8px}.pay-row{display:grid;grid-template-columns:minmax(180px,1.1fr) 145px 150px 150px minmax(170px,.8fr);gap:10px;align-items:center;padding:11px 13px;border:1px solid rgba(255,255,255,.075);border-radius:13px;background:rgba(15,20,31,.76)}.pay-cell small{display:block;font-size:10px;color:#838e9f;margin-bottom:2px}.pay-cell b,.pay-cell a{font-size:14px;color:#f3f6f9;text-decoration:none;font-weight:800}.pay-cell.amount b{color:#b9f44f}.pay-dates{font-size:11px;color:#9aa5b5;line-height:1.7}.pay-actions form{margin:0}.undo-pay{width:100%;height:36px;border:1px solid rgba(248,113,113,.28);border-radius:9px;background:rgba(239,68,68,.07);color:#ffb7bf;font:inherit;font-size:11px;font-weight:800;cursor:pointer}.undo-pay:hover{background:rgba(239,68,68,.13)}.undo-pay[disabled]{opacity:.35;cursor:not-allowed}.pay-note{font-size:10px;color:#747f91;margin-top:3px}.pay-banner{margin-bottom:13px;padding:10px 13px;border-radius:11px;border:1px solid rgba(96,165,250,.22);background:rgba(59,130,246,.08);color:#c5dcff;font-weight:750}.pay-banner.err{border-color:rgba(248,113,113,.22);background:rgba(239,68,68,.08);color:#ffc3c9}
@media(max-width:900px){.pay-row{grid-template-columns:1fr 1fr}.pay-actions{grid-column:1/-1;max-width:220px}}@media(max-width:560px){.pay-row{grid-template-columns:1fr}.pay-actions{grid-column:auto;max-width:none}}
</style>
{% if request.query_params.get("undone") %}<div class="pay-banner">✓ پرداخت اشتباهی برگشت داده شد؛ تاریخ و بدهی اکانت به وضعیت قبل برگشت.</div>{% endif %}
{% if request.query_params.get("undo_error") %}<div class="pay-banner err">این پرداخت قابل برگشت نیست؛ بعد از آن پرداخت یا تغییر دیگری روی اکانت ثبت شده است.</div>{% endif %}
<div class="pay-history">
{% for item in rows %}{% set p=item.p %}{% set s=item.s %}
  <section class="pay-row">
    <div class="pay-cell"><small>اکانت</small>{% if s %}<a href="/users/{{ s.id }}">{{ s.display_name }}</a>{% else %}<b>اکانت حذف‌شده</b>{% endif %}<div class="pay-note">{{ p.note or '' }}</div></div>
    <div class="pay-cell amount"><small>مبلغ</small><b>{{ p.amount_toman|money }} تومان</b></div>
    <div class="pay-cell"><small>تاریخ قبل</small><b>{{ p.previous_expiry|jdate }}</b></div>
    <div class="pay-cell"><small>تاریخ بعد</small><b>{{ p.new_expiry|jdate }}</b></div>
    <div class="pay-actions">
      {% if item.undoable %}
      <form method="post" action="/payments/{{ p.id }}/undo" onsubmit="return confirm('این پرداخت اشتباهی برگشت داده شود؟ تاریخ و بدهی اکانت به قبل از پرداخت برمی‌گردد.')">
        <button type="submit" class="undo-pay">↶ لغو پرداخت / برگردان</button>
      </form>
      {% else %}
      <button type="button" class="undo-pay" disabled title="فقط آخرین پرداخت اکانت و قبل از تغییر بعدی قابل برگشت است">قابل برگشت نیست</button>
      {% endif %}
    </div>
  </section>
{% else %}
  <div class="empty debt-empty">هنوز پرداختی ثبت نشده است.</div>
{% endfor %}
</div>
{% endblock %}'''

TEMPLATES["payments.html"] = PAYMENTS_UNDO_TEMPLATE
if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)


def payments_with_undo(request: Request, db: Session = Depends(get_db)):
    payments = db.query(Payment).order_by(Payment.id.desc()).all()
    seen = set()
    rows = []
    for p in payments:
        s = db.get(Subscription, p.subscription_id)
        is_latest = p.subscription_id not in seen
        seen.add(p.subscription_id)
        undoable = bool(
            is_latest
            and s is not None
            and p.previous_expiry is not None
            and p.new_expiry is not None
            and s.expiry_date == p.new_expiry
        )
        rows.append({"p": p, "s": s, "undoable": undoable})
    return render("payments.html", request, rows=rows)


def undo_payment(pid: int, db: Session = Depends(get_db)):
    p = db.get(Payment, pid)
    if not p:
        return RedirectResponse("/payments?undo_error=1", 303)

    s = db.get(Subscription, p.subscription_id)
    if not s:
        return RedirectResponse("/payments?undo_error=1", 303)

    latest = (
        db.query(Payment)
        .filter(Payment.subscription_id == s.id)
        .order_by(Payment.id.desc())
        .first()
    )
    if (
        not latest
        or latest.id != p.id
        or p.previous_expiry is None
        or p.new_expiry is None
        or s.expiry_date != p.new_expiry
    ):
        return RedirectResponse("/payments?undo_error=1", 303)

    old_current_expiry = s.expiry_date
    old_debt = int(s.debt_toman or 0)
    payment_amount = int(p.amount_toman or 0)
    payment_note = str(p.note or "")

    s.expiry_date = p.previous_expiry
    recalculated = 0 if s.is_free else current_debt_for(s, today_local())
    s.debt_toman = recalculated
    s.payment_status = "unpaid" if recalculated > 0 else "paid"
    s.billing_cursor_date = today_local()

    # If the accidental payment was made from the waiting desk, restore that workflow state.
    from_waiting = ("در انتظار" in payment_note) or ("waiting" in payment_note.lower())
    if from_waiting and "_followup_set" in globals() and recalculated > 0:
        _followup_set(db, s.id, "waiting", f"payment undo; restored waiting; payment_id={p.id}")

    db.add(AuditEvent(
        kind="payment_undo",
        message=(
            f"Undo payment id={p.id}; sid={s.id}; name={s.display_name}; amount={payment_amount}; "
            f"expiry {old_current_expiry} -> {s.expiry_date}; debt {old_debt} -> {recalculated}; "
            f"restored_waiting={from_waiting}"
        ),
    ))
    db.delete(p)
    db.commit()

    if from_waiting and recalculated > 0:
        return RedirectResponse(f"/followups?undo=1&sid={s.id}", 303)
    return RedirectResponse("/payments?undone=1", 303)


# Replace the original payments GET with the safer history page.
app.router.routes[:] = [
    r for r in app.router.routes
    if not (getattr(r, "path", None) == "/payments" and "GET" in (getattr(r, "methods", set()) or set()))
]
app.add_api_route("/payments", payments_with_undo, methods=["GET"])
app.add_api_route("/payments/{pid}/undo", undo_payment, methods=["POST"])
