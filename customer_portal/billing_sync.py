import asyncio
import json
from datetime import date, datetime, timezone
import urllib.error
import urllib.request

import jdatetime
from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

SYNC_SCHEMA = """
ALTER TABLE ayria_payment_requests
    ADD COLUMN IF NOT EXISTS paid_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS sync_status VARCHAR(32),
    ADD COLUMN IF NOT EXISTS sync_error TEXT;

CREATE TABLE IF NOT EXISTS ayria_payment_allocations (
    id BIGSERIAL PRIMARY KEY,
    request_id BIGINT NOT NULL REFERENCES ayria_payment_requests(id) ON DELETE CASCADE,
    subscription_id BIGINT NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    amount_toman BIGINT NOT NULL,
    previous_expiry DATE,
    new_expiry DATE NOT NULL,
    periods INTEGER NOT NULL DEFAULT 0,
    kind VARCHAR(32) NOT NULL,
    applied_at TIMESTAMPTZ,
    UNIQUE(request_id, subscription_id)
);
CREATE INDEX IF NOT EXISTS idx_ayria_alloc_request
    ON ayria_payment_allocations(request_id);
CREATE INDEX IF NOT EXISTS idx_ayria_alloc_subscription
    ON ayria_payment_allocations(subscription_id);

CREATE TABLE IF NOT EXISTS billing_anchor (
    subscription_id BIGINT PRIMARY KEY REFERENCES subscriptions(id) ON DELETE CASCADE,
    original_expiry DATE NOT NULL,
    anchor_expiry DATE NOT NULL,
    transition_amount_toman BIGINT NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    paid_at TIMESTAMPTZ
);
"""

_OLD_ACTIVE_SUBSCRIPTIONS = active_subscriptions


def _sync_ensure_schema(conn):
    with conn.cursor() as cur:
        cur.execute(SYNC_SCHEMA)
    conn.commit()


def _periods_due_from(expiry, today):
    if not expiry or expiry > today:
        return 0
    cursor = expiry
    n = 0
    while cursor <= today and n < 240:
        n += 1
        cursor = add_jalali_months(cursor, 1)
    return n


def _anchor_debt(anchor_row, fee, today):
    base = int(anchor_row["transition_amount_toman"] or 0)
    anchor = anchor_row["anchor_expiry"]
    if today < anchor:
        return base
    return base + (_periods_due_from(anchor, today) * int(fee or 0))


def active_subscriptions(conn, phone):
    rows = _OLD_ACTIVE_SUBSCRIPTIONS(conn, phone)
    if not rows:
        return rows

    ids = [int(x["id"]) for x in rows]
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT subscription_id, original_expiry, anchor_expiry, transition_amount_toman, status
            FROM billing_anchor
            WHERE subscription_id = ANY(%s)
            """,
            (ids,),
        )
        anchors = {int(r["subscription_id"]): r for r in cur.fetchall()}

    today = date.today()
    for item in rows:
        a = anchors.get(int(item["id"]))
        if a and a["status"] in ("pending", "scheduled"):
            if a["status"] == "scheduled" and a["original_expiry"] and today < a["original_expiry"]:
                item["debt"] = 0
            else:
                item["debt"] = _anchor_debt(a, item["monthly_fee"], today)
    return rows


def _allocation_plan(conn, selected):
    today = date.today()
    ids = [int(a["id"]) for a in selected]

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT subscription_id, original_expiry, anchor_expiry,
                   transition_amount_toman, status
            FROM billing_anchor
            WHERE subscription_id = ANY(%s)
            """,
            (ids,),
        )
        anchors = {int(r["subscription_id"]): r for r in cur.fetchall()}

    plan = []
    for a in selected:
        sid = int(a["id"])
        fee = int(a["monthly_fee"] or 0)
        current_expiry = a["expiry_date"]
        anchor = anchors.get(sid)

        if anchor and anchor["status"] in ("pending", "scheduled"):
            if anchor["status"] == "scheduled" and anchor["original_expiry"] and today < anchor["original_expiry"]:
                continue
            extra_periods = _periods_due_from(anchor["anchor_expiry"], today) if today >= anchor["anchor_expiry"] else 0
            amount = int(anchor["transition_amount_toman"] or 0) + extra_periods * fee
            new_expiry = add_jalali_months(anchor["anchor_expiry"], extra_periods) if extra_periods else anchor["anchor_expiry"]
            kind = "anchor"
            periods = extra_periods
        else:
            periods = _periods_due_from(current_expiry, today)
            amount = periods * fee
            new_expiry = add_jalali_months(current_expiry, periods) if periods > 0 else current_expiry
            kind = "monthly"

        if amount <= 0 or not new_expiry:
            continue

        plan.append({
            "sid": sid,
            "amount_toman": int(amount),
            "previous_expiry": current_expiry,
            "new_expiry": new_expiry,
            "periods": int(periods),
            "kind": kind,
            "name": str(a.get("display_name") or ""),
        })

    return plan


def _open_allocation_conflict(conn, sid):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT r.id, r.reference_code
            FROM ayria_payment_allocations a
            JOIN ayria_payment_requests r ON r.id=a.request_id
            WHERE a.subscription_id=%s
              AND a.applied_at IS NULL
              AND r.paid_at IS NULL
              AND COALESCE(r.status,'') NOT IN ('failed','canceled')
            ORDER BY r.id DESC
            LIMIT 1
            """,
            (sid,),
        )
        return cur.fetchone()


def _v2_payment_redirect(conn, phone, selected, scope):
    _sync_ensure_schema(conn)
    plan = _allocation_plan(conn, selected)
    if not plan:
        return RedirectResponse("/", status_code=303)

    # Avoid overlapping "all accounts" and "single account" payment requests.
    for item in plan:
        conflict = _open_allocation_conflict(conn, item["sid"])
        if conflict:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT payment_url FROM ayria_payment_requests WHERE id=%s",
                    (int(conflict["id"]),),
                )
                row = cur.fetchone()
            if row and row["payment_url"]:
                return RedirectResponse(str(row["payment_url"]), status_code=303)
            return RedirectResponse("/?payment_error=1", status_code=303)

    amount_toman = sum(x["amount_toman"] for x in plan)
    amount_rial = amount_toman * 10
    ids = ",".join(str(x["sid"]) for x in plan)
    fingerprint = _v2_hashlib.sha256(
        (ids + "|" + "|".join(f"{x['sid']}:{x['amount_toman']}:{x['new_expiry']}" for x in plan)).encode()
    ).hexdigest()[:18]
    cycle_key = f"sync-{scope}:{fingerprint}"[:96]

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, payment_url, reference_code
            FROM ayria_payment_requests
            WHERE phone=%s AND cycle_key=%s
            LIMIT 1
            """,
            (phone, cycle_key),
        )
        existing = cur.fetchone()

    if existing and existing["payment_url"] and existing["reference_code"]:
        return RedirectResponse(str(existing["payment_url"]), status_code=303)

    if existing:
        request_id = int(existing["id"])
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM ayria_payment_allocations WHERE request_id=%s;
                UPDATE ayria_payment_requests
                SET status='creating', error=NULL, sync_error=NULL, updated_at=NOW()
                WHERE id=%s
                """,
                (request_id, request_id),
            )
    else:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ayria_payment_requests(
                    phone, cycle_key, amount_toman, amount_rial, status, sync_status
                )
                VALUES (%s,%s,%s,%s,'creating','pending')
                RETURNING id
                """,
                (phone, cycle_key, amount_toman, amount_rial),
            )
            request_id = int(cur.fetchone()["id"])

    with conn.cursor() as cur:
        for item in plan:
            cur.execute(
                """
                INSERT INTO ayria_payment_allocations(
                    request_id, subscription_id, amount_toman,
                    previous_expiry, new_expiry, periods, kind
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    request_id, item["sid"], item["amount_toman"],
                    item["previous_expiry"], item["new_expiry"],
                    item["periods"], item["kind"],
                ),
            )
    conn.commit()

    payload = {
        "referralCode": int(AYRIA_REFERRAL_CODE),
        "amount": amount_rial,
        "payerMobile": phone,
        "payerName": ("، ".join([x["name"] for x in plan if x["name"]][:3]) or "کاربر")[:255],
        "description": "تمدید اشتراک",
        "paymentNumber": f"moshtarakin-{request_id}-{int(_v2_time.time())}",
        "extraData": _v2_json.dumps(
            {
                "source": "moshtarakin-sync",
                "requestId": request_id,
                "phone": phone,
                "subscriptionIds": [x["sid"] for x in plan],
                "allocations": [
                    {
                        "sid": x["sid"],
                        "amountToman": x["amount_toman"],
                        "newExpiry": str(x["new_expiry"]),
                        "kind": x["kind"],
                    }
                    for x in plan
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "issuerMustVerifyPayment": False,
        "callbackUrl": "https://moshtarakin.filmjadiid.ir/api/ayria/callback",
    }

    try:
        response = ayria_create(payload)
    except Exception as exc:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ayria_payment_requests
                SET status='failed', error=%s, sync_status='failed', sync_error=%s, updated_at=NOW()
                WHERE id=%s
                """,
                (str(exc)[:1000], str(exc)[:1000], request_id),
            )
        conn.commit()
        return RedirectResponse("/?payment_error=1", status_code=303)

    payment_url = str(response["paymentUrl"]).strip()
    reference = str(response["referenceCode"]).strip()
    tracking = str(response.get("trackingNumber") or "").strip()

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE ayria_payment_requests
            SET status='created', reference_code=%s, tracking_number=%s,
                payment_url=%s, error=NULL, sync_status='pending', updated_at=NOW()
            WHERE id=%s
            """,
            (reference, tracking, payment_url, request_id),
        )
        for item in plan:
            cur.execute(
                """
                INSERT INTO audit_events(kind, message, created_at)
                VALUES ('followup_waiting', %s, NOW())
                """,
                (
                    f"sid={item['sid']}; customer portal payment opened; "
                    f"reference={reference}; phone={phone}; scope={scope}",
                ),
            )
    conn.commit()
    return RedirectResponse(payment_url, status_code=303)


def _ayria_get(reference):
    req = urllib.request.Request(
        AYRIA_API_BASE + "/apg/v1/get/" + str(reference),
        method="GET",
        headers={
            "Accept": "application/json",
            "APG-API-KEY": AYRIA_API_KEY,
            "APG-WALLET-ID": AYRIA_WALLET_ID,
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _sync_paid_reference(reference):
    if not reference:
        return {"ok": False, "reason": "missing_reference"}

    try:
        remote = _ayria_get(reference)
    except Exception as exc:
        return {"ok": False, "reason": "ayria_get_failed", "error": str(exc)[:300]}

    if not remote.get("paid") or remote.get("canceled"):
        return {"ok": True, "paid": False}

    with db_conn() as conn:
        _sync_ensure_schema(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM ayria_payment_requests
                WHERE reference_code=%s
                FOR UPDATE
                """,
                (reference,),
            )
            request_row = cur.fetchone()
            if not request_row:
                return {"ok": False, "reason": "unknown_reference"}

            if request_row["paid_at"]:
                return {"ok": True, "paid": True, "already_applied": True}

            expected_rial = int(request_row["amount_rial"] or 0)
            remote_amount = int(remote.get("amount") or 0)
            if remote_amount != expected_rial:
                cur.execute(
                    """
                    UPDATE ayria_payment_requests
                    SET sync_status='conflict', sync_error=%s, updated_at=NOW()
                    WHERE id=%s
                    """,
                    (f"amount mismatch remote={remote_amount} expected={expected_rial}", request_row["id"]),
                )
                conn.commit()
                return {"ok": False, "reason": "amount_mismatch"}

            if str(remote.get("referenceCode") or "") != str(reference):
                return {"ok": False, "reason": "reference_mismatch"}

            cur.execute(
                """
                SELECT *
                FROM ayria_payment_allocations
                WHERE request_id=%s
                ORDER BY id
                FOR UPDATE
                """,
                (request_row["id"],),
            )
            allocations = cur.fetchall()
            if not allocations:
                cur.execute(
                    """
                    UPDATE ayria_payment_requests
                    SET sync_status='legacy', sync_error='no per-account allocation; not auto-applied', updated_at=NOW()
                    WHERE id=%s
                    """,
                    (request_row["id"],),
                )
                conn.commit()
                return {"ok": False, "reason": "legacy_without_allocations"}

            # Preflight every child before mutating any account. This is what prevents
            # a group payment from accidentally extending siblings that were changed
            # independently after checkout.
            for alloc in allocations:
                if alloc["applied_at"]:
                    continue
                cur.execute(
                    "SELECT id, expiry_date, display_name FROM subscriptions WHERE id=%s FOR UPDATE",
                    (alloc["subscription_id"],),
                )
                sub = cur.fetchone()
                if not sub:
                    cur.execute(
                        """
                        UPDATE ayria_payment_requests
                        SET sync_status='conflict', sync_error=%s, updated_at=NOW()
                        WHERE id=%s
                        """,
                        (f"subscription missing sid={alloc['subscription_id']}", request_row["id"]),
                    )
                    conn.commit()
                    return {"ok": False, "reason": "subscription_missing"}

                if sub["expiry_date"] != alloc["previous_expiry"]:
                    cur.execute(
                        """
                        UPDATE ayria_payment_requests
                        SET sync_status='conflict', sync_error=%s, updated_at=NOW()
                        WHERE id=%s
                        """,
                        (
                            f"expiry changed sid={sub['id']} current={sub['expiry_date']} expected={alloc['previous_expiry']}",
                            request_row["id"],
                        ),
                    )
                    conn.commit()
                    return {"ok": False, "reason": "expiry_conflict"}

            now = datetime.now(timezone.utc)

            for alloc in allocations:
                if alloc["applied_at"]:
                    continue

                cur.execute(
                    "SELECT id, display_name, expiry_date FROM subscriptions WHERE id=%s FOR UPDATE",
                    (alloc["subscription_id"],),
                )
                sub = cur.fetchone()

                cur.execute(
                    """
                    UPDATE subscriptions
                    SET expiry_date=%s,
                        debt_toman=0,
                        payment_status='paid',
                        billing_cursor_date=%s
                    WHERE id=%s
                    """,
                    (alloc["new_expiry"], date.today(), alloc["subscription_id"]),
                )

                if alloc["kind"] == "anchor":
                    cur.execute(
                        """
                        UPDATE billing_anchor
                        SET status='paid', paid_at=NOW()
                        WHERE subscription_id=%s
                        """,
                        (alloc["subscription_id"],),
                    )

                cur.execute(
                    """
                    INSERT INTO payments(
                        subscription_id, amount_toman, periods,
                        previous_expiry, new_expiry, note
                    )
                    VALUES (%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        alloc["subscription_id"],
                        alloc["amount_toman"],
                        alloc["periods"],
                        alloc["previous_expiry"],
                        alloc["new_expiry"],
                        f"Ayria auto sync; reference={reference}; allocation={alloc['id']}",
                    ),
                )

                cur.execute(
                    """
                    INSERT INTO audit_events(kind, message, created_at)
                    VALUES ('payment', %s, NOW())
                    """,
                    (
                        f"Ayria auto payment {alloc['amount_toman']}; sid={alloc['subscription_id']}; "
                        f"expiry {alloc['previous_expiry']} -> {alloc['new_expiry']}; reference={reference}",
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO audit_events(kind, message, created_at)
                    VALUES ('followup_clear', %s, NOW())
                    """,
                    (
                        f"sid={alloc['subscription_id']}; Ayria paid; reference={reference}",
                    ),
                )
                cur.execute(
                    "UPDATE ayria_payment_allocations SET applied_at=%s WHERE id=%s",
                    (now, alloc["id"]),
                )

            cur.execute(
                """
                UPDATE ayria_payment_requests
                SET status='paid', paid_at=NOW(), sync_status='applied',
                    sync_error=NULL, updated_at=NOW()
                WHERE id=%s
                """,
                (request_row["id"],),
            )
        conn.commit()

    return {"ok": True, "paid": True, "applied": True}


@app.post("/api/ayria/callback")
async def ayria_callback(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    reference = str(body.get("referenceCode") or request.query_params.get("referenceCode") or "").strip()
    result = await asyncio.to_thread(_sync_paid_reference, reference)
    return JSONResponse(result, status_code=200 if result.get("ok") else 400)


async def _ayria_sync_loop():
    while True:
        try:
            refs = []
            with db_conn() as conn:
                _sync_ensure_schema(conn)
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT reference_code
                        FROM ayria_payment_requests
                        WHERE reference_code IS NOT NULL
                          AND paid_at IS NULL
                          AND COALESCE(status,'') NOT IN ('failed','canceled')
                          AND EXISTS (
                              SELECT 1
                              FROM ayria_payment_allocations a
                              WHERE a.request_id=ayria_payment_requests.id
                          )
                        ORDER BY id
                        LIMIT 50
                        """
                    )
                    refs = [str(r["reference_code"]) for r in cur.fetchall()]

            for ref in refs:
                await asyncio.to_thread(_sync_paid_reference, ref)
        except Exception:
            pass
        await asyncio.sleep(30)


@app.on_event("startup")
async def _start_ayria_sync_loop():
    asyncio.create_task(_ayria_sync_loop())
