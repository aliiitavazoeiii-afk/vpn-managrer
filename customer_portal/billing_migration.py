import argparse
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

import jdatetime
import psycopg
from psycopg.rows import dict_row
import os

DATABASE_DSN = os.environ["DATABASE_DSN"]
ANCHOR_JALALI = (1405, 8, 1)
ANCHOR_DATE = jdatetime.date(*ANCHOR_JALALI).togregorian()

SCHEMA = """
CREATE TABLE IF NOT EXISTS billing_anchor (
    subscription_id BIGINT PRIMARY KEY REFERENCES subscriptions(id) ON DELETE CASCADE,
    original_expiry DATE NOT NULL,
    anchor_expiry DATE NOT NULL,
    transition_amount_toman BIGINT NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    paid_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_billing_anchor_status ON billing_anchor(status);
"""


def jalali(value):
    if not value:
        return "-"
    j = jdatetime.date.fromgregorian(date=value)
    return f"{j.year:04d}/{j.month:02d}/{j.day:02d}"


def next_jalali_month_start(g_date):
    j = jdatetime.date.fromgregorian(date=g_date)
    if j.month == 12:
        n = jdatetime.date(j.year + 1, 1, 1)
    else:
        n = jdatetime.date(j.year, j.month + 1, 1)
    return n.togregorian()


def jalali_month_start(g_date):
    j = jdatetime.date.fromgregorian(date=g_date)
    return jdatetime.date(j.year, j.month, 1).togregorian()


def prorated_to_anchor(expiry, fee):
    if not expiry or fee <= 0 or expiry >= ANCHOR_DATE:
        return 0

    cursor = expiry
    total = Decimal(0)
    fee_d = Decimal(int(fee))

    while cursor < ANCHOR_DATE:
        month_start = jalali_month_start(cursor)
        next_start = next_jalali_month_start(cursor)
        segment_end = min(next_start, ANCHOR_DATE)
        days = Decimal((segment_end - cursor).days)
        month_days = Decimal((next_start - month_start).days)
        total += fee_d * days / month_days
        cursor = segment_end

    return int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def cut_ids(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT kind, message
            FROM audit_events
            WHERE kind IN ('followup_cut','followup_clear')
            ORDER BY id DESC
            """
        )
        rows = cur.fetchall()
    states = {}
    import re
    for row in rows:
        m = re.search(r"\bsid=(\d+)\b", str(row["message"] or ""))
        if not m:
            continue
        sid = int(m.group(1))
        if sid in states:
            continue
        states[sid] = row["kind"] == "followup_cut"
    return {sid for sid, is_cut in states.items() if is_cut}


def load_rows(conn):
    excluded = cut_ids(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, display_name, phone, expiry_date, monthly_fee_toman,
                   debt_toman, payment_status, is_free
            FROM subscriptions
            WHERE is_free IS FALSE
            ORDER BY id
            """
        )
        rows = cur.fetchall()
    return [r for r in rows if int(r["id"]) not in excluded]


def preview(conn):
    rows = load_rows(conn)
    total = 0
    future = []
    print(f"ANCHOR: {ANCHOR_DATE} (1405/08/01)")
    print("id | name | expiry | fee | current_debt | proposed_to_1405/08/01")
    print("-" * 110)
    for r in rows:
        expiry = r["expiry_date"]
        fee = int(r["monthly_fee_toman"] or 0)
        if expiry and expiry > ANCHOR_DATE:
            future.append(r)
            proposed = 0
        else:
            proposed = prorated_to_anchor(expiry, fee)
        total += proposed
        print(
            f"{r['id']} | {str(r['display_name'])[:28]} | {jalali(expiry)} | "
            f"{fee:,} | {int(r['debt_toman'] or 0):,} | {proposed:,}"
        )

    print("-" * 110)
    print(f"accounts={len(rows)} proposed_total={total:,} toman")
    if future:
        print("\nWARNING: these accounts expire AFTER 1405/08/01 and are NOT shortened:")
        for r in future:
            print(f"  sid={r['id']} name={r['display_name']} expiry={jalali(r['expiry_date'])}")


def apply(conn):
    rows = load_rows(conn)
    with conn.cursor() as cur:
        cur.execute(SCHEMA)

        for r in rows:
            expiry = r["expiry_date"]
            fee = int(r["monthly_fee_toman"] or 0)

            if not expiry or expiry > ANCHOR_DATE:
                continue

            amount = prorated_to_anchor(expiry, fee)
            status = "pending" if amount > 0 else "paid"

            cur.execute(
                """
                INSERT INTO billing_anchor(
                    subscription_id, original_expiry, anchor_expiry,
                    transition_amount_toman, status, paid_at
                )
                VALUES (%s,%s,%s,%s,%s,CASE WHEN %s='paid' THEN NOW() ELSE NULL END)
                ON CONFLICT(subscription_id) DO UPDATE SET
                    original_expiry=EXCLUDED.original_expiry,
                    anchor_expiry=EXCLUDED.anchor_expiry,
                    transition_amount_toman=EXCLUDED.transition_amount_toman,
                    status=EXCLUDED.status,
                    paid_at=EXCLUDED.paid_at
                """,
                (r["id"], expiry, ANCHOR_DATE, amount, status, status),
            )

            cur.execute(
                """
                UPDATE subscriptions
                SET debt_toman=%s,
                    payment_status=%s
                WHERE id=%s
                """,
                (amount, "unpaid" if amount > 0 else "paid", r["id"]),
            )

        cur.execute(
            """
            INSERT INTO audit_events(kind, message, created_at)
            VALUES ('billing_anchor_migration', %s, NOW())
            """,
            (f"Prepared first-of-month billing alignment to 1405/08/01; accounts={len(rows)}",),
        )
    conn.commit()
    print("APPLIED: billing alignment rows created. No expiry date was shortened or advanced yet.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["preview", "apply"])
    args = parser.parse_args()

    with psycopg.connect(DATABASE_DSN, row_factory=dict_row) as conn:
        if args.mode == "preview":
            preview(conn)
        else:
            apply(conn)


if __name__ == "__main__":
    main()
