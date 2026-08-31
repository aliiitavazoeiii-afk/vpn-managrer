# Bulk payment for every waiting/debtor child in one waiting group.
from fastapi import Form
import re

_WAITING_GROUP_PAY_STYLE = r'''
<style>
.waiting-head-pay{display:flex;align-items:center;justify-content:flex-end;min-width:120px}
.waiting-group-pay-form{margin:0}
.waiting-group-pay-btn{height:34px;border:1px solid rgba(184,243,74,.38);border-radius:9px;background:rgba(184,243,74,.09);color:#dcffa7;padding:0 11px;font:inherit;font-size:10px;font-weight:850;cursor:pointer;white-space:nowrap}
.waiting-group-pay-btn:hover{background:rgba(184,243,74,.16);border-color:rgba(184,243,74,.56);color:#f0ffd4}
@media(max-width:900px){.waiting-head-pay{justify-content:flex-start}}
</style>
'''

_tpl = TEMPLATES.get("followups.html", "")
if _tpl:
    _tpl = _tpl.replace("{% block content %}", "{% block content %}" + _WAITING_GROUP_PAY_STYLE, 1)

    # Add a bulk-payment action directly in the collapsed group row, before the chevron.
    chevron_anchor = '<span class="waiting-chevron">⌄</span>'
    bulk_ui = r'''
      <div class="waiting-head-pay">
        <form method="post" action="/followups/pay-group" class="waiting-group-pay-form"
              onsubmit="return confirm('پرداخت کلی برای {{ g.services|fa }} اکانت در انتظار به مبلغ {{ g.debt|money }} تومان ثبت شود؟')">
          <input type="hidden" name="phone" value="{{ g.phone or '' }}">
          <input type="hidden" name="sid" value="{% if not g.phone %}{{ g.rows[0].s.id }}{% else %}0{% endif %}">
          <button type="submit" class="waiting-group-pay-btn">پرداخت شد کلی</button>
        </form>
      </div>
'''
    if chevron_anchor in _tpl and "/followups/pay-group" not in _tpl:
        _tpl = _tpl.replace(chevron_anchor, bulk_ui + chevron_anchor, 1)

    paid_banner_anchor = '{% if request.query_params.get("paid") %}<div class="collect-success">✓ پرداخت ثبت شد و اکانت از انتظار خارج شد.</div>{% endif %}'
    bulk_banner = r'''
{% if request.query_params.get("group_paid") %}<div class="collect-success">✓ پرداخت کلی ثبت شد؛ همه اکانت‌های بدهکار این سرگروه از «در انتظار» خارج شدند.</div>{% endif %}
'''
    if paid_banner_anchor in _tpl and "group_paid" not in _tpl:
        _tpl = _tpl.replace(paid_banner_anchor, paid_banner_anchor + bulk_banner, 1)

    TEMPLATES["followups.html"] = _tpl
    if hasattr(env.loader, "mapping"):
        env.loader.mapping.update(TEMPLATES)


def followup_group_pay(phone: str = Form(""), sid: int = Form(0), db: Session = Depends(get_db)):
    refresh_billing(db)
    states = _followup_states(db)

    if phone:
        candidates = (
            db.query(Subscription)
            .filter(Subscription.phone == phone, Subscription.is_free.is_(False))
            .order_by(Subscription.id.asc())
            .all()
        )
    else:
        s = db.get(Subscription, int(sid or 0))
        candidates = [s] if s else []

    paid_count = 0
    paid_total = 0
    for s in candidates:
        if not s or s.is_free or states.get(s.id) != "waiting":
            continue

        periods = debt_periods_for(s)
        amount = current_debt_for(s, today_local())
        if periods <= 0 or amount <= 0 or not s.expiry_date:
            continue

        prev = s.expiry_date
        s.expiry_date = add_jalali_months(s.expiry_date, periods)
        s.debt_toman = 0
        s.payment_status = "paid"
        s.billing_cursor_date = today_local()

        db.add(Payment(
            subscription_id=s.id,
            amount_toman=amount,
            periods=periods,
            previous_expiry=prev,
            new_expiry=s.expiry_date,
            note="ثبت واریز کلی از صفحه در انتظار",
        ))
        db.add(AuditEvent(
            kind="payment",
            message=(
                f"Waiting group payment {amount}; sid={s.id}; name={s.display_name}; "
                f"phone={s.phone or ''}; expiry {prev} -> {s.expiry_date}"
            ),
        ))
        _followup_set(db, s.id, None, "paid by waiting group payment")
        paid_count += 1
        paid_total += int(amount)

    if paid_count:
        db.add(AuditEvent(
            kind="group_payment",
            message=f"Waiting group payment completed; phone={phone}; count={paid_count}; total={paid_total}",
        ))
        db.commit()

    return RedirectResponse(
        f"/followups?group_paid=1&count={paid_count}&total={paid_total}",
        303,
    )


app.add_api_route("/followups/pay-group", followup_group_pay, methods=["POST"])
