# Customer portal V2: separate-domain, phone-only login, premium UI,
# aggregate/individual Ayria payments, and customer-requested account deactivation.
from pathlib import Path as _v2_Path
from fastapi.responses import Response as _v2_Response
import hashlib as _v2_hashlib
import time as _v2_time
import json as _v2_json

_V2_DIR = _v2_Path(__file__).resolve().parent
_V2_CSS = (_V2_DIR / "v2.css").read_text(encoding="utf-8")
_V2_POLISH = (_V2_DIR / "v2_polish.css").read_text(encoding="utf-8")
_V2_LOGIN = (_V2_DIR / "login_v2.html").read_text(encoding="utf-8")
_V2_DASH = (_V2_DIR / "dashboard_v2.html").read_text(encoding="utf-8")
_V2_PAYMENT_RETURN = (_V2_DIR / "payment_return.html").read_text(encoding="utf-8")
_V2_SAFARI = (_V2_DIR / "safari_required.html").read_text(encoding="utf-8")
_V2_LOGO = (_V2_DIR / "logo.png").read_bytes()


def _v2_render(source, **ctx):
    return HTMLResponse(jinja.from_string(source).render(**ctx))


def _v2_load_anchor_targets(conn, ids):
    if not ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT subscription_id, anchor_expiry, status
            FROM billing_anchor
            WHERE subscription_id = ANY(%s)
            """,
            (ids,),
        )
        return {int(r["subscription_id"]): r for r in cur.fetchall()}




def _v2_requires_safari(request: Request):
    ua = (request.headers.get("user-agent") or "").lower()
    is_ios = (
        "iphone" in ua
        or "ipad" in ua
        or "ipod" in ua
        or ("macintosh" in ua and "mobile" in ua)
    )
    if not is_ios:
        return False

    blocked_markers = (
        "crios",
        "fxios",
        "edgios",
        "opios",
        "gsa/",
        "fban",
        "fbios",
        "instagram",
    )
    if any(marker in ua for marker in blocked_markers):
        return True

    # Real Safari on iPhone/iPad normally includes both Version/ and Safari/.
    # In-app webviews commonly omit one of them, so fail closed for payments.
    return not ("version/" in ua and "safari/" in ua)


def _v2_safari_gate(request: Request):
    if _v2_requires_safari(request):
        return _v2_render(_V2_SAFARI)
    return None


def _v2_session_phone(request: Request):
    token = request.cookies.get("moshtarakin_customer", "")
    if not token:
        return None
    try:
        data = session_signer.loads(token, max_age=60 * 60 * 24 * 30)
    except (BadSignature, SignatureExpired):
        return None
    phone = normalize_phone(data.get("phone", ""))
    return phone or None


def _v2_payment_redirect(conn, phone, selected, scope):
    amount_toman = sum(int(a["debt"] or 0) for a in selected)
    if amount_toman <= 0:
        return RedirectResponse("/", status_code=303)

    amount_rial = amount_toman * 10
    expiries = [a["expiry_date"] for a in selected if a["expiry_date"]]
    first_expiry = min(expiries).isoformat() if expiries else "no-expiry"
    ids = ",".join(str(int(a["id"])) for a in selected)
    ids_hash = _v2_hashlib.sha256(ids.encode()).hexdigest()[:14]
    cycle_key = f"v2-{scope}:{ids_hash}:{first_expiry}:{amount_toman}"[:96]

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
        request_id = int(existing["id"])
        payment_url = str(existing["payment_url"])
        reference = str(existing["reference_code"])
    else:
        if existing:
            request_id = int(existing["id"])
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ayria_payment_requests
                    SET status='creating', error=NULL, updated_at=NOW()
                    WHERE id=%s
                    """,
                    (request_id,),
                )
        else:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ayria_payment_requests(
                        phone, cycle_key, amount_toman, amount_rial, status
                    )
                    VALUES (%s, %s, %s, %s, 'creating')
                    RETURNING id
                    """,
                    (phone, cycle_key, amount_toman, amount_rial),
                )
                request_id = int(cur.fetchone()["id"])
        conn.commit()

        names = [
            str(a["display_name"] or "").strip()
            for a in selected
            if str(a["display_name"] or "").strip()
        ]
        payload = {
            "referralCode": int(AYRIA_REFERRAL_CODE),
            "amount": amount_rial,
            "payerMobile": phone,
            "payerName": ("، ".join(names[:3]) or "کاربر")[:255],
            "description": "تمدید اشتراک",
            "paymentNumber": f"moshtarakin-{request_id}-{int(_v2_time.time())}",
            "extraData": _v2_json.dumps(
                {
                    "source": "moshtarakin-portal",
                    "requestId": request_id,
                    "phone": phone,
                    "subscriptionIds": [int(a["id"]) for a in selected],
                    "amountToman": amount_toman,
                    "scope": scope,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "issuerMustVerifyPayment": False,
        }

        try:
            ayria_response = ayria_create(payload)
        except Exception as exc:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ayria_payment_requests
                    SET status='failed', error=%s, updated_at=NOW()
                    WHERE id=%s
                    """,
                    (str(exc)[:1000], request_id),
                )
            conn.commit()
            return RedirectResponse("/?payment_error=1", status_code=303)

        payment_url = str(ayria_response["paymentUrl"]).strip()
        reference = str(ayria_response["referenceCode"]).strip()
        tracking = str(ayria_response.get("trackingNumber") or "").strip()

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ayria_payment_requests
                SET status='created',
                    reference_code=%s,
                    tracking_number=%s,
                    payment_url=%s,
                    error=NULL,
                    updated_at=NOW()
                WHERE id=%s
                """,
                (reference, tracking, payment_url, request_id),
            )

    with conn.cursor() as cur:
        for a in selected:
            cur.execute(
                """
                INSERT INTO audit_events(kind, message, created_at)
                VALUES ('followup_waiting', %s, NOW())
                """,
                (
                    f"sid={int(a['id'])}; customer portal payment opened; "
                    f"reference={reference}; phone={phone}; scope={scope}",
                ),
            )
        cur.execute(
            """
            INSERT INTO audit_events(kind, message, created_at)
            VALUES ('customer_portal_payment', %s, NOW())
            """,
            (
                f"Moshtarakin payment opened; request={request_id}; "
                f"reference={reference}; phone={phone}; "
                f"amount_toman={amount_toman}; scope={scope}",
            ),
        )
    conn.commit()
    return RedirectResponse(payment_url, status_code=303)


# Remove V1 customer-facing routes. Keep /health.
_v2_paths = {"/", "/request-code", "/verify", "/logout", "/pay"}
app.router.routes[:] = [
    r for r in app.router.routes
    if getattr(r, "path", None) not in _v2_paths
]


@app.get("/assets/v2.css")
def v2_css():
    return _v2_Response(
        _V2_CSS,
        media_type="text/css; charset=utf-8",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/assets/v2_polish.css")
def v2_polish_css():
    return _v2_Response(
        _V2_POLISH,
        media_type="text/css; charset=utf-8",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/assets/logo.png")
def v2_logo():
    return _v2_Response(
        _V2_LOGO,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/api/ayria/callback")
def v2_browser_payment_return():
    # Browser callback only. Payment truth is verified by the Ayria API and ledger.
    return RedirectResponse("/payment/return", status_code=303)


@app.get("/payment/return", response_class=HTMLResponse)
def v2_payment_return(request: Request):
    phone = _v2_session_phone(request)
    checkout_id = request.cookies.get("moshtarakin_checkout", "")
    if not phone or not checkout_id.isascii() or not checkout_id.isdecimal() or len(checkout_id) > 20:
        return RedirectResponse("/", status_code=303)
    response = _v2_render(_V2_PAYMENT_RETURN)
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/payment/status")
def v2_payment_status(request: Request):
    from fastapi.responses import JSONResponse
    phone = _v2_session_phone(request)
    checkout_id = request.cookies.get("moshtarakin_checkout", "")
    if not phone or not checkout_id.isascii() or not checkout_id.isdecimal() or len(checkout_id) > 20:
        return JSONResponse({"state": "missing"}, status_code=401, headers={"Cache-Control": "no-store"})
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, status, paid_at, sync_status FROM ayria_payment_requests
                   WHERE id=%s AND phone=%s""",
                (int(checkout_id), phone),
            )
            row = cur.fetchone()
    state = "pending"
    if not row:
        state = "missing"
    elif row["status"] == "paid" and row["paid_at"] and row["sync_status"] == "applied":
        state = "paid"
    elif row["status"] in ("failed", "canceled"):
        state = row["status"]
    return JSONResponse(
        {"state": state, "url": f"/payment/success/{int(checkout_id)}" if state == "paid" else None},
        headers={"Cache-Control": "no-store, private", "Referrer-Policy": "no-referrer"},
    )


@app.get("/payment/dismiss")
def v2_payment_dismiss():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("moshtarakin_checkout", path="/")
    return response


@app.get("/", response_class=HTMLResponse)
def v2_home(request: Request):
    phone = _v2_session_phone(request)
    if not phone:
        return _v2_render(_V2_LOGIN, error=None)

    # Celebrate only after verified Ayria payment AND per-account application.
    checkout_id = request.cookies.get("moshtarakin_checkout", "")
    if checkout_id.isascii() and checkout_id.isdecimal():
        with db_conn() as receipt_conn:
            with receipt_conn.cursor() as receipt_cur:
                receipt_cur.execute(
                    """SELECT id FROM ayria_payment_requests
                       WHERE id=%s AND phone=%s AND status='paid'
                         AND paid_at IS NOT NULL AND sync_status='applied'""",
                    (int(checkout_id), phone),
                )
                confirmed = receipt_cur.fetchone()
        if confirmed:
            response = RedirectResponse(f"/payment/success/{int(checkout_id)}", status_code=303)
            response.delete_cookie("moshtarakin_checkout", path="/")
            return response
        return RedirectResponse("/payment/return", status_code=303)

    with db_conn() as conn:
        accounts = active_subscriptions(conn, phone)
        account_ids = [int(a["id"]) for a in accounts]
        anchors = _v2_load_anchor_targets(conn, account_ids)
        # A successful Ayria allocation, not merely a zero balance, is proof of payment.
        confirmed_payments = {}
        if account_ids:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ON (a.subscription_id)
                           a.subscription_id, a.amount_toman, a.applied_at
                    FROM ayria_payment_allocations a
                    JOIN ayria_payment_requests r ON r.id=a.request_id
                    WHERE a.subscription_id = ANY(%s)
                      AND a.applied_at IS NOT NULL
                      AND r.paid_at IS NOT NULL
                      AND r.status = 'paid'
                    ORDER BY a.subscription_id, a.applied_at DESC, a.id DESC
                    """,
                    (account_ids,),
                )
                confirmed_payments = {
                    int(row["subscription_id"]): {
                        "amount_toman": int(row["amount_toman"]),
                    }
                    for row in cur.fetchall()
                }

    for item in accounts:
        currently_due = int(item.get("portal_payable_amount", item.get("debt", 0)) or 0)
        item["verified_payment"] = (
            confirmed_payments.get(int(item["id"]))
            if currently_due == 0 and int(item.get("debt") or 0) == 0
            else None
        )
        name = str(item.get("display_name") or "?").strip()
        item["initial"] = name[:1].upper() if name else "?"
        anchor = anchors.get(int(item["id"]))
        target = anchor["anchor_expiry"] if anchor and anchor.get("anchor_expiry") else item.get("expiry_date")
        item["target_expiry_jalali"] = jalali_text(target)
        item["is_anchor_target"] = bool(anchor and anchor.get("anchor_expiry"))

    total_debt = sum(int(a["debt"] or 0) for a in accounts)
    total_payable = sum(int(a.get("portal_payable_amount", a.get("debt", 0)) or 0) for a in accounts)
    message = None
    message_is_error = False
    if request.query_params.get("payment_error"):
        message = "ساخت درگاه انجام نشد. لطفاً چند لحظه بعد دوباره تلاش کنید."
        message_is_error = True
    elif request.query_params.get("payment_pending"):
        message = "وضعیت پرداخت قبلی در آیریا هنوز قطعی نیست. برای جلوگیری از پرداخت تکراری، لینک تازه صادر نشد. چند لحظه بعد دوباره تلاش کنید."
        message_is_error = True
    elif request.query_params.get("disabled"):
        message = "اکانت انتخاب‌شده غیرفعال شد و از لیست فعال شما خارج شد."

    return _v2_render(
        _V2_DASH,
        phone=phone,
        accounts=accounts,
        total_debt=total_debt,
        total_payable=total_payable,
        csrf=csrf_for(phone),
        message=message,
        message_is_error=message_is_error,
        show_welcome=request.query_params.get("welcome") == "1",
    )


@app.post("/login")
def v2_login(phone: str = Form(...)):
    normalized = normalize_phone(phone)
    if not normalized:
        return _v2_render(_V2_LOGIN, error="شماره موبایل معتبر نیست.")

    with db_conn() as conn:
        if not phone_exists(conn, normalized):
            return _v2_render(_V2_LOGIN, error="اکانتی با این شماره در سیستم پیدا نشد.")

    token = session_signer.dumps({"phone": normalized})
    response = RedirectResponse("/?welcome=1", status_code=303)
    response.set_cookie(
        "moshtarakin_customer",
        token,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return response


@app.post("/logout")
def v2_logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("moshtarakin_customer", path="/")
    response.delete_cookie("moshtarakin_checkout", path="/")
    return response


@app.post("/pay-all")
def v2_pay_all(request: Request, csrf: str = Form(...)):
    phone = _v2_session_phone(request)
    if not phone or not verify_csrf(phone, csrf):
        return RedirectResponse("/", status_code=303)

    with db_conn() as conn:
        accounts = active_subscriptions(conn, phone)
        selected = [
            a for a in accounts
            if int(a.get("portal_payable_amount", a.get("debt", 0)) or 0) > 0
        ]
        if not selected:
            return RedirectResponse("/", status_code=303)
        return _v2_payment_redirect(conn, phone, selected, "all")


@app.post("/pay/{sid}")
def v2_pay_one(sid: int, request: Request, csrf: str = Form(...)):
    phone = _v2_session_phone(request)
    if not phone or not verify_csrf(phone, csrf):
        return RedirectResponse("/", status_code=303)

    with db_conn() as conn:
        accounts = active_subscriptions(conn, phone)
        selected = [
            a for a in accounts
            if int(a["id"]) == int(sid) and int(a["debt"] or 0) > 0
        ]
        if not selected:
            return RedirectResponse("/", status_code=303)
        return _v2_payment_redirect(conn, phone, selected, f"sid-{int(sid)}")


@app.post("/disable/{sid}")
def v2_disable(sid: int, request: Request, csrf: str = Form(...)):
    phone = _v2_session_phone(request)
    if not phone or not verify_csrf(phone, csrf):
        return RedirectResponse("/", status_code=303)

    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, display_name, phone, debt_toman
                FROM subscriptions
                WHERE id=%s AND phone=%s
                LIMIT 1
                """,
                (int(sid), phone),
            )
            account = cur.fetchone()
            if not account:
                return RedirectResponse("/", status_code=303)

            cur.execute(
                """
                INSERT INTO audit_events(kind, message, created_at)
                VALUES ('followup_cut', %s, NOW())
                """,
                (
                    f"sid={int(sid)}; disabled by customer portal; "
                    f"phone={phone}; name={account['display_name']}; "
                    f"debt={int(account['debt_toman'] or 0)}",
                ),
            )
            cur.execute(
                """
                INSERT INTO audit_events(kind, message, created_at)
                VALUES ('customer_portal_disable', %s, NOW())
                """,
                (
                    f"Customer disabled account; sid={int(sid)}; "
                    f"phone={phone}; name={account['display_name']}",
                ),
            )
        conn.commit()

    return RedirectResponse("/?disabled=1", status_code=303)
