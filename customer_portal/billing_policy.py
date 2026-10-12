"""Canonical Jalali first-of-next-month billing calculator.

This module has no database, web, or jdatetime dependency. Both the admin and
customer portal supply their existing verified Jalali calendar conversion
functions. Bill only after the actual expiry date, up to the first day of the
following Jalali month. Amounts are in toman, rounded once, half-up.
"""
from decimal import Decimal, ROUND_HALF_UP


def calculate_invoice(expiry, monthly_fee, as_of, month_start, next_month_start):
    if not expiry:
        return {"due": False, "target": None, "amount": 0}
    fee = int(monthly_fee or 0)
    if fee <= 0:
        return {"due": False, "target": next_month_start(expiry), "amount": 0}
    due = expiry <= as_of
    target = next_month_start(as_of) if due else next_month_start(expiry)
    if not due:
        return {"due": False, "target": target, "amount": 0}

    cursor = expiry
    amount = Decimal(0)
    iterations = 0
    while cursor < target:
        iterations += 1
        if iterations > 240:
            raise ValueError("Invalid billing period exceeds 240 Jalali segments")
        stop = min(next_month_start(cursor), target)
        days = (stop - cursor).days
        month_days = (next_month_start(cursor) - month_start(cursor)).days
        if days <= 0 or month_days <= 0:
            raise ValueError("Invalid Jalali month conversion")
        amount += Decimal(fee) * Decimal(days) / Decimal(month_days)
        cursor = stop
    return {
        "due": True,
        "target": target,
        "amount": int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
    }
