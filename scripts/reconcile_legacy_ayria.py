"""Reconcile exactly six legacy Ayria checkouts independently verified canceled.

Run inside the existing customer-portal container:
    python - --apply < scripts/reconcile_legacy_ayria.py

This re-verifies all six references against Ayria with GET requests before any
write, checks invoice amounts/refs, and updates only payment-request statuses.
No subscription, expiry, payment, allocation, or legacy anchor is changed.
Stops and rolls back the entire transaction on any mismatch.
"""
import json
import os
import sys
import urllib.request
from urllib.error import HTTPError, URLError

import psycopg
from psycopg.rows import dict_row

EXPECTED = {1: 400000, 2: 200000, 3: 600000, 4: 200000, 5: 200000, 6: 400000}
ALLOWED_LOCAL_STATUSES = {"created", "waiting"}

if sys.argv[1:] != ["--apply"]:
    print("STOP: Explicit --apply required; nothing changed.")
    raise SystemExit(2)

KEY = (os.environ.get("AYRIA_APG_API_KEY") or "").strip()
WALLET = (os.environ.get("AYRIA_APG_WALLET_ID") or "").strip()
BASE = (os.environ.get("AYRIA_API_BASE") or "https://api.ayriaclub.ir").rstrip("/")
DSN = os.environ["DATABASE_DSN"]
if not KEY or not WALLET or not BASE.startswith("https://"):
    print("STOP: Missing/unsafe provider configuration. Nothing changed.")
    raise SystemExit(3)

try:
    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = '5s'")
            cur.execute(
                """
                SELECT r.id, r.status, r.reference_code, r.amount_rial,
                       r.amount_toman, r.paid_at,
                       (SELECT count(*) FROM ayria_payment_allocations a
                        WHERE a.request_id=r.id) AS allocations
                FROM ayria_payment_requests r
                WHERE r.id = ANY(%s)
                ORDER BY r.id FOR UPDATE
                """,
                (sorted(EXPECTED),),
            )
            rows = cur.fetchall()

            if {int(r["id"]) for r in rows} != set(EXPECTED):
                raise ValueError("A legacy request ID is missing")
            for r in rows:
                rid = int(r["id"])
                if r["status"] not in ALLOWED_LOCAL_STATUSES or r["paid_at"] is not None:
                    raise ValueError(f"request {rid}: local status/paid_at changed")
                if int(r["amount_toman"]) != EXPECTED[rid]:
                    raise ValueError(f"request {rid}: unexpected local amount")
                if int(r["amount_rial"]) != EXPECTED[rid] * 10:
                    raise ValueError(f"request {rid}: rial/toman mismatch")
                if int(r["allocations"]) != 0 or not r["reference_code"]:
                    raise ValueError(f"request {rid}: allocations or reference changed")

            print("Verifying canceled status for all 6 references directly with Ayria...")
            for r in rows:
                rid = int(r["id"])
                reference = str(r["reference_code"])
                req = urllib.request.Request(
                    BASE + "/apg/v1/get/" + reference,
                    method="GET",
                    headers={
                        "Accept": "application/json",
                        "APG-API-KEY": KEY,
                        "APG-WALLET-ID": WALLET,
                    },
                )
                with urllib.request.urlopen(req, timeout=12) as response:
                    remote = json.loads(response.read(128000).decode("utf-8"))
                if not isinstance(remote, dict):
                    raise ValueError(f"request {rid}: invalid provider response")
                if remote.get("canceled") is not True or remote.get("paid") is True:
                    raise ValueError(f"request {rid}: NOT confirmed canceled by provider")
                if str(remote.get("amount")) != str(r["amount_rial"]):
                    raise ValueError(f"request {rid}: remote amount mismatch")
                if str(remote.get("referenceCode")) != reference:
                    raise ValueError(f"request {rid}: remote reference mismatch")
                print(f"  id={rid}: confirmed canceled, amount and reference verified")

            for r in rows:
                cur.execute(
                    """
                    UPDATE ayria_payment_requests
                    SET status='canceled',
                        sync_status='canceled',
                        sync_error=NULL,
                        updated_at=NOW()
                    WHERE id=%s AND paid_at IS NULL AND status IN ('created','waiting')
                    """,
                    (r["id"],),
                )
                if cur.rowcount != 1:
                    raise ValueError(f"request {r['id']}: update failed")
                cur.execute(
                    """
                    INSERT INTO audit_events(kind, message, created_at)
                    VALUES ('ayria_legacy_canceled', %s, NOW())
                    """,
                    (f"request_id={int(r['id'])}; confirmed canceled via Ayria GET before first-day billing rollout",),
                )
        conn.commit()
    print("SUCCESS: 6 LEGACY AYRIA REQUESTS CANCELED LOCALLY")
    print("Only payment-request status fields and six audit events changed.")
    print("No subscriptions, expiries, debt totals, actual payments or billing anchors were modified.")
except (Exception,) as exc:
    print(f"STOP: {type(exc).__name__}: {str(exc)[:200]}")
    print("No partial updates committed: reconciliation transaction rolled back.")
    raise SystemExit(1)
