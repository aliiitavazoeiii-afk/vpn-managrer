# Group-wide payment from the debt inbox: settle every currently actionable overdue child in one phone group.
from fastapi import Form
import re

_GROUP_PAY_STYLE = r'''
<style>
.group-pay-form{margin:0}
.group-pay-btn{border:1px solid rgba(184,243,74,.34);background:rgba(184,243,74,.08);color:#d9ffa0;border-radius:8px;padding:5px 9px;font:inherit;font-size:10px;font-weight:850;cursor:pointer}
.group-pay-btn:hover{background:rgba(184,243,74,.15);color:#efffcf;border-color:rgba(184,243,74,.52)}
</style>
'''

_tpl = TEMPLATES.get("debts.html", "")
if _tpl:
    _tpl = _tpl.replace("{% block content %}", "{% block content %}" + _GROUP_PAY_STYLE, 1)

    # Put the bulk payment button immediately beside the follow-up button.
    track_pattern = re.compile(
        r'(<form\s+method="post"\s+action="/followups/track-group".*?</form>)',
        flags=re.S,
    )
    group_pay_ui = r'''
      <form method="post" action="/debts/pay-group" data-preserve-position class="group-pay-form"
            onsubmit="return confirm('پرداخت کلی برای {{ g.services|fa }} اکانت بدهکار به مبلغ {{ g.debt|money }} تومان ثبت شود؟')">
        <input type="hidden" name="phone" value="{{ g.phone or '' }}">
        <input type="hidden" name="sid" value="{% if not g.phone %}{{ g.rows[0].s.id }}{% else %}0{% endif %}">
        <button type="submit" class="group-pay-btn">پرداخت شد کلی</button>
      </form>
'''
    if "/debts/pay-group" not in _tpl:
        m = track_pattern.search(_tpl)
        if m:
            _tpl = _tpl[:m.end()] + group_pay_ui + _tpl[m.end():]

    banner_anchor = '{% if request.query_params.get("tracked") %}<div class="manage-banner">✓ مورد به «در انتظار» منتقل شد.</div>{% endif %}'
    group_banner = r'''
{% if request.query_params.get("group_paid") %}<div class="manage-banner">✓ پرداخت کلی ثبت شد؛ همه اکانت‌های بدهکار این گروه طبق سررسید خودشان تمدید شدند.</div>{% endif %}
'''
    if banner_anchor in _tpl and "group_paid" not in _tpl:
        _tpl = _tpl.replace(banner_anchor, banner_anchor + group_banner, 1)

    for old in ("v=2", "v=3", "v=4", "v=5", "v=6", "v=7", "v=8", "v=9"):
        _tpl = _tpl.replace(old, "v=10")

    TEMPLATES["debts.html"] = _tpl
    if hasattr(env.loader, "mapping"):
        env.loader.mapping.update(TEMPLATES)


def debt_group_pay(phone: str = Form(""), sid: int = Form(0), db: Session = Depends(get_db)):
    refresh_billing(db)
    states = _followup_states(db) if "_followup_states" in globals() else {}

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
        if not s or s.is_free:
            continue
        # Only settle rows that belong to the current debt inbox. Waiting/cut siblings are intentionally untouched.
        if states.get(s.id) in ("waiting", "cut"):
            continue
        periods = debt_periods_for(s)
        amount = current_debt_for(s)
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
            note="ثبت واریز کلی از صفحه بدهی",
        ))
        db.add(AuditEvent(
            kind="payment",
            message=(
                f"Debt group payment {amount}; sid={s.id}; name={s.display_name}; "
                f"phone={s.phone or ''}; expiry {prev} -> {s.expiry_date}"
            ),
        ))
        paid_count += 1
        paid_total += int(amount)

    if paid_count:
        db.add(AuditEvent(
            kind="group_payment",
            message=f"Group payment completed; phone={phone}; count={paid_count}; total={paid_total}",
        ))
        db.commit()

    return RedirectResponse(
        f"/debts?group_paid=1&count={paid_count}&total={paid_total}",
        303,
    )


app.add_api_route("/debts/pay-group", debt_group_pay, methods=["POST"])
