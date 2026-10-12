"""Read-only Ayria audit of unresolved legacy payment requests.

Run inside the customer-portal container, where DATABASE_DSN and Ayria
credentials already exist. Does not change payment/request/account status.
Prints request IDs and coarse statuses only: never keys, phones, URLs or refs.
"""
import os
import sys
import json
from collections import Counter
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import psycopg
from psycopg.rows import dict_row

BASE = (os.getenv("AYRIA_API_BASE") or "https://api.ayriaclub.ir").rstrip("/")
KEY = (os.getenv("AYRIA_APG_API_KEY") or "").strip()
WALLET = (os.getenv("AYRIA_APG_WALLET_ID") or "").strip()
DSN = os.environ["DATABASE_DSN"]
if not KEY or not WALLET:
    print("STOP: Ayria credentials are not configured", flush=True)
    sys.exit(2)

with psycopg.connect(DSN, row_factory=dict_row) as conn:
    conn.execute("SET TRANSACTION READ ONLY")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT r.id, r.status, r.reference_code, r.amount_rial,
                   r.payment_url IS NOT NULL AS has_payment_url,
                   r.sms_job_id IS NOT NULL AS has_sms_job,
                   (SELECT COUNT(*) FROM ayria_payment_allocations a
                    WHERE a.request_id=r.id) AS allocations
            FROM ayria_payment_requests r
            WHERE r.paid_at IS NULL AND r.status IN ('created','waiting')
            ORDER BY r.id
            """
        )
        rows = cur.fetchall()
    conn.rollback()

print("READ-ONLY REMOTE PAYMENT STATUS AUDIT")
print("ID | local | link | sms | alloc | provider | amount_match | ref_match")
summary = Counter()
for row in rows:
    rid = int(row["id"])
    if not row["reference_code"]:
        provider, amount_ok, ref_ok = "NO_REFERENCE", "-", "-"
    else:
        req = Request(
            BASE + "/apg/v1/get/" + str(row["reference_code"]),
            method="GET",
            headers={
                "Accept": "application/json",
                "APG-API-KEY": KEY,
                "APG-WALLET-ID": WALLET,
            },
        )
        try:
            with urlopen(req, timeout=12) as res:
                remote = json.loads(res.read(128000).decode("utf-8"))
            if not isinstance(remote, dict):
                raise ValueError("unexpected response shape")
            paid = remote.get("paid")
            canceled = remote.get("canceled")
            if paid is True and canceled is not True:
                provider = "PAID"
            elif canceled is True and paid is not True:
                provider = "CANCELED"
            elif paid is False and canceled is False:
                provider = "OPEN_OR_UNPAID"
            else:
                provider = "UNKNOWN_FLAGS"
            amount_ok = "YES" if str(remote.get("amount")) == str(row["amount_rial"]) else "NO"
            ref_ok = "YES" if str(remote.get("referenceCode")) == str(row["reference_code"]) else "NO"
        except HTTPError as exc:
            provider, amount_ok, ref_ok = f"HTTP_{exc.code}", "-", "-"
        except (URLError, TimeoutError, ValueError, KeyError, OSError, json.JSONDecodeError):
            provider, amount_ok, ref_ok = "LOOKUP_ERROR", "-", "-"
    summary[provider] += 1
    print(
        f"{rid} | {row['status']} | {int(row['has_payment_url'])} | "
        f"{int(row['has_sms_job'])} | {row['allocations']} | "
        f"{provider} | {amount_ok} | {ref_ok}"
    )
print("SUMMARY:", " ".join(f"{key}={value}" for key, value in sorted(summary.items())))
print("NO DATABASE CHANGES")
