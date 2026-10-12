"""Read-only preview of first-of-next-Jalali-month billing.

Does NOT migrate dates, debts, anchors, payments, or payment requests.
Run inside customer-portal with DATABASE_DSN configured:
    python /srv/billing_due_preview.py
    python /srv/billing_due_preview.py --as-of 1405/08/05
"""
import argparse
import os
import re
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

import jdatetime
import psycopg
from psycopg.rows import dict_row


def parse_jalali(value):
    y, m, d = (int(x) for x in value.split("/"))
    return jdatetime.date(y, m, d).togregorian()


def jalali(value):
    j = jdatetime.date.fromgregorian(date=value)
    return f"{j.year:04d}/{j.month:02d}/{j.day:02d}"


def month_start(value):
    j = jdatetime.date.fromgregorian(date=value)
    return jdatetime.date(j.year, j.month, 1).togregorian()


def next_month_start(value):
    j = jdatetime.date.fromgregorian(date=value)
    return jdatetime.date(j.year + (j.month == 12), (j.month % 12) + 1, 1).togregorian()


def prorated(expiry, target, monthly_fee):
    """Gregorian date intervals and actual Jalali month lengths; [expiry, target)."""
    if not expiry or target <= expiry or monthly_fee <= 0:
        return 0
    cursor = expiry
    amount = Decimal(0)
    count = 0
    while cursor < target:
        count += 1
        if count > 240:
            raise ValueError("Over 240 billing segments")
        segment_end = min(next_month_start(cursor), target)
        length = (next_month_start(cursor) - month_start(cursor)).days
        amount += Decimal(monthly_fee) * Decimal((segment_end - cursor).days) / Decimal(length)
        cursor = segment_end
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def invoice(expiry, fee, today):
    """Eligibility is original real expiry, not proposed due amount."""
    if not expiry or fee <= 0:
        return None
    # The next cycle first is computed from the actual evaluation day, not fixed 1 Aban.
    target = next_month_start(today) if expiry <= today else next_month_start(expiry)
    due = expiry <= today
    amount = prorated(expiry, target, fee) if due else 0
    return {"due": due, "target": target, "amount": amount}


def audit(conn, today):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT kind, message FROM audit_events
            WHERE kind IN ('followup_waiting','followup_cut','followup_clear')
            ORDER BY id DESC
        """)
        states = {}
        for e in cur.fetchall():
            m = re.search(r"\bsid=(\d+)\b", str(e["message"] or ""))
            if not m:
                continue
            sid = int(m.group(1))
            if sid not in states:
                states[sid] = {
                    "followup_cut": "cut",
                    "followup_waiting": "waiting",
                    "followup_clear": None
                }[e["kind"]]
        cur.execute("""
            SELECT s.id, s.expiry_date, s.monthly_fee_toman, s.debt_toman, s.is_free,
                   a.status AS anchor_status, a.original_expiry AS anchor_original
            FROM subscriptions s
            LEFT JOIN billing_anchor a ON a.subscription_id = s.id
            ORDER BY s.id
        """)
        rows = cur.fetchall()
    counts = dict(cut=0, free=0, due_collection=0, due_waiting=0, future=0, missing_expiry=0)
    due_total = 0
    changed_anchor = []
    for s in rows:
        sid = int(s["id"])
        state = states.get(sid)
        if state == "cut":
            counts["cut"] += 1
            continue
        if s["is_free"]:
            counts["free"] += 1
            continue
        if not s["expiry_date"]:
            counts["missing_expiry"] += 1
            continue
        plan = invoice(s["expiry_date"], int(s["monthly_fee_toman"] or 0), today)
        if s["anchor_status"] in ("pending", "scheduled") and s["expiry_date"] != s["anchor_original"]:
            changed_anchor.append(sid)
        if not plan["due"]:
            counts["future"] += 1
            continue
        if state == "waiting":
            counts["due_waiting"] += 1
            continue
        counts["due_collection"] += 1
        due_total += plan["amount"]
        print(
            f"sid={sid} expiry={jalali(s['expiry_date'])} "
            f"target={jalali(plan['target'])} fee={s['monthly_fee_toman']} "
            f"invoice={plan['amount']} current_debt={s['debt_toman']} "
            f"anchor={s['anchor_status'] or 'NONE'}"
        )
    print("--- SUMMARY (READ-ONLY) ---")
    print(f"as_of={jalali(today)} total_subscriptions={len(rows)}")
    for key, value in counts.items():
        print(f"{key}={value}")
    print(f"due_collection_total_toman={due_total}")
    print(f"changed_open_anchors={len(changed_anchor)}")
    print("NO DATABASE CHANGES")


def smoke_test():
    due = parse_jalali("1405/07/20")
    future = parse_jalali("1405/08/05")
    current = parse_jalali("1405/07/20")
    p = invoice(due, 300000, current)
    assert p["due"] and jalali(p["target"]) == "1405/08/01"
    assert p["amount"] == 110000  # 11 days of a 30-day Mehr
    p = invoice(future, 300000, current)
    assert not p["due"] and p["amount"] == 0 and jalali(p["target"]) == "1405/09/01"
    p = invoice(future, 300000, future)
    assert p["due"] and jalali(p["target"]) == "1405/09/01"
    p = invoice(parse_jalali("1405/08/01"), 300000, parse_jalali("1405/08/01"))
    assert p["amount"] == 300000 and jalali(p["target"]) == "1405/09/01"
    print("SMOKE TEST PASSED")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", help="Optional Jalali date YYYY/MM/DD; preview only")
    parser.add_argument("--test-only", action="store_true")
    args = parser.parse_args()
    smoke_test()
    if args.test_only:
        return
    as_of = parse_jalali(args.as_of) if args.as_of else datetime.now(ZoneInfo("Asia/Tehran")).date()
    with psycopg.connect(os.environ["DATABASE_DSN"], row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        audit(conn, as_of)
        conn.rollback()


if __name__ == "__main__":
    main()
