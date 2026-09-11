# Partial / historical payment registration for waiting groups.
# Lets the operator record the amount that was actually paid, rather than forcing full current debt.
from fastapi import Form
from datetime import datetime as _partial_datetime
from zoneinfo import ZoneInfo as _partial_ZoneInfo
import re as _partial_re


def _partial_money(value):
    raw = str(value or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    for ch in (",", "٬", "،", "_", " "):
        raw = raw.replace(ch, "")
    return int(raw or 0)


def _partial_paid_at(paid_jalali):
    raw = str(paid_jalali or "").strip()
    if not raw:
        return _partial_datetime.utcnow()
    d = parse_jalali_date(raw)
    if d > today_local():
        raise ValueError("future payment date")
    local_dt = _partial_datetime(d.year, d.month, d.day, 12, 0, tzinfo=TZ)
    return local_dt.astimezone(_partial_ZoneInfo("UTC")).replace(tzinfo=None)


def _waiting_payment_units(candidates):
    units = []
    for s in candidates:
        if not s or s.is_free or not s.expiry_date:
            continue
        fee = int(s.monthly_fee_toman or 0)
        periods = debt_periods_for(s, today_local())
        if fee <= 0 or periods <= 0:
            continue
        for idx in range(periods):
            units.append({
                "sid": s.id,
                "due": add_jalali_months(s.expiry_date, idx),
                "fee": fee,
            })
    units.sort(key=lambda x: (x["due"], x["sid"]))
    return units


# Replace the old one-click group-payment block with two explicit choices:
# full settlement, or actual/historical amount.
_tpl = TEMPLATES.get("followups.html", "")
if _tpl and "waiting-actual-pay" not in _tpl:
    _replacement = r'''
      <div class="waiting-head-pay waiting-pay-tools">
        <form method="post" action="/followups/pay-group" class="waiting-group-pay-form"
              onsubmit="return confirm('تسویه کامل {{ g.debt|money }} تومان برای این سرگروه ثبت شود؟')">
          <input type="hidden" name="phone" value="{{ g.phone or '' }}">
          <input type="hidden" name="sid" value="{% if not g.phone %}{{ g.rows[0].s.id }}{% else %}0{% endif %}">
          <button type="submit" class="waiting-group-pay-btn">تسویه کامل</button>
        </form>

        <details class="waiting-actual-pay">
          <summary>ثبت مبلغ واقعی</summary>
          <form method="post" action="/followups/pay-amount" class="waiting-amount-form"
                onsubmit="return confirm('مبلغ واردشده از قدیمی‌ترین سررسیدهای این گروه کم شود؟')">
            <input type="hidden" name="phone" value="{{ g.phone or '' }}">
            <input type="hidden" name="sid" value="{% if not g.phone %}{{ g.rows[0].s.id }}{% else %}0{% endif %}">
            <label>مبلغی که واقعاً واریز شده</label>
            <div class="waiting-amount-input"><input name="amount" type="text" inputmode="numeric" autocomplete="off" placeholder="مثلاً 400000" required><span>تومان</span></div>
            <label>تاریخ واریز قبلی <small>(اختیاری)</small></label>
            <input name="paid_jalali" type="text" inputmode="numeric" autocomplete="off" placeholder="مثلاً 1405/05/10">
            <p>از قدیمی‌ترین سررسیدها کم می‌شود. اگر بدهی جدیدتری باقی بماند، آن اکانت به «وصول بدهی» برمی‌گردد و پرداخت قبلی به‌اشتباه تسویه کامل حساب نمی‌شود.</p>
            <button type="submit">ثبت مبلغ واقعی</button>
          </form>
        </details>
      </div>
'''
    _pattern = r'<div class="waiting-head-pay">.*?</div>\s*(?=<span class="waiting-chevron">)'
    _tpl, _n = _partial_re.subn(_pattern, _replacement, _tpl, count=1, flags=_partial_re.S)

    _banner_anchor = '{% if request.query_params.get("undo") %}<div class="collect-success">✓ پرداخت لغو شد و اکانت دوباره به «در انتظار» برگشت.</div>{% endif %}'
    _extra = r'''
{% if request.query_params.get("amount_paid") %}<div class="collect-success">✓ مبلغ واقعی واریزی ثبت شد. بدهی جدیدِ باقی‌مانده، در صورت وجود، به «وصول بدهی» برگشت.</div>{% endif %}
{% if request.query_params.get("amount_error") == "amount" %}<div class="collect-error">مبلغ واردشده معتبر نیست یا از بدهی فعلی بیشتر است.</div>{% endif %}
{% if request.query_params.get("amount_error") == "period" %}<div class="collect-error">این مبلغ با دوره‌های کامل ماهانه این گروه جور درنمی‌آید. برای جلوگیری از ثبت اشتباه، پرداخت انجام نشد.</div>{% endif %}
{% if request.query_params.get("amount_error") == "date" %}<div class="collect-error">تاریخ واریز معتبر نیست.</div>{% endif %}
'''
    if _banner_anchor in _tpl:
        _tpl = _tpl.replace(_banner_anchor, _banner_anchor + _extra, 1)

    TEMPLATES["followups.html"] = _tpl

_base = TEMPLATES.get("base.html", "")
if _base:
    _base = _partial_re.sub(r'/static/app\.css(?:\?v=[^"\']*)?', '/static/app.css?v=waiting-partial-1', _base)
    TEMPLATES["base.html"] = _base

if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)


def followup_pay_amount(
    phone: str = Form(""),
    sid: int = Form(0),
    amount: str = Form(...),
    paid_jalali: str = Form(""),
    db: Session = Depends(get_db),
):
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

    candidates = [
        s for s in candidates
        if s and states.get(s.id) == "waiting" and current_debt_for(s, today_local()) > 0
    ]
    units = _waiting_payment_units(candidates)
    total_debt = sum(int(x["fee"]) for x in units)

    try:
        value = _partial_money(amount)
    except Exception:
        value = 0
    if value <= 0 or value > total_debt:
        return RedirectResponse("/followups?amount_error=amount", 303)

    try:
        paid_at = _partial_paid_at(paid_jalali)
    except Exception:
        return RedirectResponse("/followups?amount_error=date", 303)

    # Allocate strictly from the oldest unpaid billing periods first.
    remaining = value
    allocations = {}
    for unit in units:
        if remaining <= 0:
            break
        fee = int(unit["fee"])
        if remaining < fee:
            return RedirectResponse("/followups?amount_error=period", 303)
        allocations[unit["sid"]] = allocations.get(unit["sid"], 0) + 1
        remaining -= fee

    if remaining != 0:
        return RedirectResponse("/followups?amount_error=period", 303)

    paid_total = 0
    affected = 0
    for target_sid, periods in allocations.items():
        s = db.get(Subscription, target_sid)
        if not s or periods <= 0:
            continue

        fee = int(s.monthly_fee_toman or 0)
        applied_amount = fee * int(periods)
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
            note="ثبت مبلغ واقعی پرداخت قبلی از صفحه در انتظار",
        ))
        db.add(AuditEvent(
            kind="payment",
            message=(
                f"Historical/partial waiting payment {applied_amount}; sid={s.id}; "
                f"name={s.display_name}; periods={periods}; expiry {prev} -> {new_expiry}; "
                f"remaining_debt={new_debt}"
            ),
        ))

        # The old reminder/payment is now accounted for. Any debt still remaining on
        # this subscription is newer debt and must return to the debt inbox rather
        # than falsely staying marked as already followed-up.
        _followup_set(
            db,
            s.id,
            None,
            f"historical payment backfill; amount={applied_amount}; remaining_debt={new_debt}"
        )
        paid_total += applied_amount
        affected += 1

    db.add(AuditEvent(
        kind="partial_group_payment",
        message=(
            f"Actual payment registered; phone={phone}; requested={value}; "
            f"applied={paid_total}; affected={affected}; old_group_debt={total_debt}"
        ),
    ))
    db.commit()

    return RedirectResponse(
        f"/followups?amount_paid=1&amount={paid_total}&remaining={max(total_debt-paid_total, 0)}",
        303,
    )


app.add_api_route("/followups/pay-amount", followup_pay_amount, methods=["POST"])
