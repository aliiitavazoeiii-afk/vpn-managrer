# PORTAL_LOGIN_ACTIVITY_V1
# Additive activity recording for the currently active V2 /login endpoint.
# In this system a "successful login" only means an existing phone number was
# entered; possession of the SIM card is not verified.
# No billing, payment, account, SMS, or authentication decisions are modified.
import ipaddress as _pla_ipaddress
import logging as _pla_logging
from fastapi import Form as _pla_Form, Request as _pla_Request

_PLA_SQL = """
CREATE TABLE IF NOT EXISTS customer_portal_login_events (
  id BIGSERIAL PRIMARY KEY,
  phone VARCHAR(32) NOT NULL,
  display_name VARCHAR(200),
  ip_address VARCHAR(96),
  result VARCHAR(16) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT customer_portal_login_result_check
      CHECK (result IN ('success', 'not_found', 'invalid'))
);
CREATE INDEX IF NOT EXISTS idx_customer_portal_login_time
  ON customer_portal_login_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_customer_portal_login_phone_time
  ON customer_portal_login_events (phone, created_at DESC);
"""

_PLA_log = _pla_logging.getLogger("hesab.portal_login_activity")


@app.on_event("startup")
def _pla_prepare_schema():
    # Additive, idempotent database creation. If this fails, startup/rollout
    # should fail, rather than displaying a false empty report.
    with db_conn() as conn:
        with conn.cursor() as cursor:
            for statement in _PLA_SQL.split(";"):
                if statement.strip():
                    cursor.execute(statement)
        conn.commit()


def _pla_safe_ip(request):
    # Uvicorn may already apply proxy forwarding, subject to proxy trust config.
    # Keep only IP addresses, never store arbitrary forwarded header content.
    try:
        raw = request.client.host if request.client else ""
        return str(_pla_ipaddress.ip_address(raw))[:96]
    except ValueError:
        return None


_pla_original_login = v2_login


def _pla_login_with_activity(
    request: _pla_Request,
    phone: str = _pla_Form(...),
):
    # Preserve the original login response and cookie behavior, including
    # failure responses. Activity logging must not grant or deny a login.
    response = _pla_original_login(phone=phone)
    normalized = normalize_phone(phone)
    success = (
        response.status_code in (302, 303)
        and "moshtarakin_customer=" in response.headers.get("set-cookie", "")
    )
    result = "success" if success else ("not_found" if normalized else "invalid")
    stored_phone = str(normalized or "").strip()[:32]
    ip = _pla_safe_ip(request)

    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                name = None
                if success:
                    cur.execute(
                        """SELECT display_name FROM subscriptions
                           WHERE phone=%s
                           ORDER BY id ASC LIMIT 1""",
                        (normalized,),
                    )
                    first = cur.fetchone()
                    name = str(first["display_name"] or "")[:200] if first else None
                cur.execute(
                    """INSERT INTO customer_portal_login_events
                       (phone, display_name, ip_address, result)
                       VALUES (%s,%s,%s,%s)""",
                    (stored_phone, name, ip, result),
                )
            conn.commit()
    except Exception:
        # Logging failure does not interrupt a paying customer's session.
        _PLA_log.exception("Unable to record portal login activity")
    return response


_pla_matches = [
    route for route in app.router.routes
    if getattr(route, "path", None) == "/login"
    and "POST" in (getattr(route, "methods", set()) or set())
]
if len(_pla_matches) != 1:
    raise RuntimeError("Portal /login route changed; refusing activity recorder")

app.router.routes[:] = [route for route in app.router.routes if route not in _pla_matches]
app.add_api_route("/login", _pla_login_with_activity, methods=["POST"])
