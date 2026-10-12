"""Install after billing_sync.py in the customer-portal container.

Uses the same canonical invoice policy as the Hesab admin. No checkout is
offered before the actual expiry; after payment the new expiry is the first of
the next Jalali month. Existing verified Ayria sync, allocation locks, and
transaction checks remain unchanged.
"""
from zoneinfo import ZoneInfo as _b_ZoneInfo
from billing_policy import calculate_invoice as _b_calc

_b_old_active_subscriptions = active_subscriptions


def _b_tehran_today():
    return datetime.now(_b_ZoneInfo("Asia/Tehran")).date()


def _b_portal_start(value):
    j = jdatetime.date.fromgregorian(date=value)
    return jdatetime.date(j.year, j.month, 1).togregorian()


def _b_portal_next(value):
    start = _b_portal_start(value)
    j = jdatetime.date.fromgregorian(date=start)
    yy, mm = (j.year + 1, 1) if j.month == 12 else (j.year, j.month + 1)
    return jdatetime.date(yy, mm, 1).togregorian()


def _b_portal_invoice(item, today):
    return _b_calc(
        item.get("expiry_date"),
        0 if item.get("is_free") else int(item.get("monthly_fee") or 0),
        today,
        _b_portal_start,
        _b_portal_next,
    )


def active_subscriptions(conn, phone):
    items = _b_old_active_subscriptions(conn, phone)
    today = _b_tehran_today()
    for item in items:
        invoice = _b_portal_invoice(item, today)
        current = item.get("expiry_date")
        target = invoice["target"] or current
        amount = int(invoice["amount"])
        item["debt"] = amount
        item["portal_payable_amount"] = amount
        item["is_overdue"] = bool(invoice["due"] and amount > 0)
        item["transition_original_expiry"] = current
        item["transition_target_expiry"] = target
        item["transition_original_jalali"] = jalali_text(current)
        item["transition_target_jalali"] = jalali_text(target)
        item["transition_status"] = "first_day" if invoice["due"] else None
    return items


def _allocation_plan(conn, selected):
    today = _b_tehran_today()
    result = []
    for item in selected:
        # Selected entries originate from authenticated active_subscriptions()
        # and have already excluded archived and nonmatching-phone accounts.
        invoice = _b_portal_invoice(item, today)
        if not invoice["due"] or invoice["amount"] <= 0:
            continue
        prev = item.get("expiry_date")
        new_expiry = invoice["target"]
        if not prev or not new_expiry or new_expiry <= prev:
            raise RuntimeError("Unsafe month-first checkout plan")
        result.append({
            "sid": int(item["id"]),
            "amount_toman": int(invoice["amount"]),
            "previous_expiry": prev,
            "new_expiry": new_expiry,
            "periods": _periods_due_from(prev, today),
            "kind": "month_first",
            "name": str(item.get("display_name") or ""),
        })
    return result
