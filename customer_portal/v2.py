# Customer portal V2: separate-domain, phone-only login, premium UI,
# aggregate/individual Ayria payments, and customer-requested account deactivation.
from pathlib import Path as _v2_Path
from fastapi.responses import Response as _v2_Response
import hashlib as _v2_hashlib
import time as _v2_time
import json as _v2_json

_V2_DIR = _v2_Path(__file__).resolve().parent
_V2_CSS = (_V2_DIR / "v2.css").read_text(encoding="utf-8")
_V2_LOGIN = (_V2_DIR / "login_v2.html").read_text(encoding="utf-8")
_V2_DASH = (_V2_DIR / "dashboard_v2.html").read_text(encoding="utf-8")
_V2_SAFARI = (_V2_DIR / "safari_required.html").read_text(encoding="utf-8")


def _v2_render(source, **ctx):
    return HTMLResponse(jinja.from_string(source).render(**ctx))




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


@app.get("/", response_class=HTMLResponse)
def v2_home(request: Request):
    phone = _v2_session_phone(request)
    if not phone:
        return _v2_render(_V2_LOGIN, error=None)

    with db_conn() as conn:
        accounts = active_subscriptions(conn, phone)

    for item in accounts:
        name = str(item.get("display_name") or "?").strip()
        item["initial"] = name[:1].upper() if name else "?"

    total_debt = sum(int(a["debt"] or 0) for a in accounts)
    expiries = [a["expiry_date"] for a in accounts if a["expiry_date"]]
    nearest = jalali_text(min(expiries)) if expiries else "—"

    message = None
    message_is_error = False
    if request.query_params.get("payment_error"):
        message = "ساخت درگاه انجام نشد. لطفاً چند لحظه بعد دوباره تلاش کنید."
        message_is_error = True
    elif request.query_params.get("disabled"):
        message = "اکانت انتخاب‌شده غیرفعال شد و از لیست فعال شما خارج شد."

    return _v2_render(
        _V2_DASH,
        phone=phone,
        accounts=accounts,
        total_debt=total_debt,
        nearest_expiry=nearest,
        csrf=csrf_for(phone),
        message=message,
        message_is_error=message_is_error,
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
    response = RedirectResponse("/", status_code=303)
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
    return response


@app.post("/pay-all")
def v2_pay_all(request: Request, csrf: str = Form(...)):
    gate = _v2_safari_gate(request)
    if gate:
        return gate
    phone = _v2_session_phone(request)
    if not phone or not verify_csrf(phone, csrf):
        return RedirectResponse("/", status_code=303)

    with db_conn() as conn:
        accounts = active_subscriptions(conn, phone)
        selected = [a for a in accounts if int(a["debt"] or 0) > 0]
        if not selected:
            return RedirectResponse("/", status_code=303)
        return _v2_payment_redirect(conn, phone, selected, "all")


@app.post("/pay/{sid}")
def v2_pay_one(sid: int, request: Request, csrf: str = Form(...)):
    gate = _v2_safari_gate(request)
    if gate:
        return gate
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
