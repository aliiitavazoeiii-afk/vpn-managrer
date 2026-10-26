# HESAB_CUSTOMER_SERVICES_V2 — additive customer-facing route overlay
# Read-only ledger history, no modifications to payment, X-UI or billing flow.
from pathlib import Path as _sv2_Path
from fastapi.responses import Response as _sv2_Response
from fastapi.responses import HTMLResponse as _sv2_HTML, RedirectResponse as _sv2_Redirect
import re as _sv2_re

_SV2_ROOT = _sv2_Path(__file__).resolve().parent
_SV2_HTML = (_SV2_ROOT / "services_ui_v2.html").read_text(encoding="utf-8")
_SV2_CSS = (_SV2_ROOT / "services_ui_v2.css").read_text(encoding="utf-8")
_SV2_JS = (_SV2_ROOT / "services_ui_v2.js").read_text(encoding="utf-8")

def _sv2_whatsapp():
    # Only trust explicit, validated E.164 digits. Do not expose a guess.
    raw = str(os.environ.get("HESAB_SUPPORT_WHATSAPP", "") or "").strip()
    digits = raw.lstrip("+")
    if not digits.isascii() or not digits.isdecimal() or not 8 <= len(digits) <= 15:
        return None
    return "https://wa.me/" + digits

def _sv2_phone():
    raw = str(os.environ.get("HESAB_SUPPORT_PHONE", "") or "").strip()
    if not _sv2_re.fullmatch(r"\+?[0-9]{8,15}", raw):
        return None
    return "tel:" + raw

@app.get("/assets/services-v2.css", include_in_schema=False)
def _sv2_css():
    return _sv2_Response(_SV2_CSS, media_type="text/css; charset=utf-8",
                         headers={"Cache-Control":"public,max-age=3600"})

@app.get("/assets/services-v2.js", include_in_schema=False)
def _sv2_js():
    return _sv2_Response(_SV2_JS, media_type="text/javascript; charset=utf-8",
                         headers={"Cache-Control":"public,max-age=3600", "X-Content-Type-Options":"nosniff"})

@app.get("/payments/history", response_class=_sv2_HTML, include_in_schema=False)
def _sv2_payment_history(request: Request):
    phone = _v2_session_phone(request)
    if not phone:
        return _sv2_Redirect("/", status_code=303)
    # Preserve historical rows for archived accounts: ownership derives from
    # subscriptions.phone, not a visitor-supplied subscription identifier.
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.amount_toman,p.paid_at,s.display_name,s.id AS subscription_id
                FROM payments p JOIN subscriptions s ON s.id=p.subscription_id
                WHERE s.phone=%s
                ORDER BY p.paid_at DESC,p.id DESC LIMIT 100
            """, (phone,))
            rows = cur.fetchall()
    output = []
    for row in rows:
        when = row["paid_at"]
        output.append({
          "display_name": row["display_name"],
          "subscription_id": int(row["subscription_id"]),
          "date": jalali_text(when.date()) if when else "—",
          "amount": money(row["amount_toman"]),
        })
    template = """<!doctype html><html lang="fa" dir="rtl"><head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>سوابق پرداخت | حساب من</title>
    <link rel="stylesheet" href="/assets/v2.css"><link rel="stylesheet" href="/assets/v2_polish.css">
    <link rel="stylesheet" href="/assets/services-v2.css"></head>
    <body class="sv2"><main class="sv-shell">
      <header class="sv-top"><div class="sv-brand"><div class="sv-logo"><img src="/assets/logo.png" alt="لوگو"></div><div><b>سوابق پرداخت</b><small>فقط پرداخت‌های ثبت‌شده</small></div></div>
      <a class="sv-line-button" href="/" style="margin-top:0">بازگشت به حساب من ←</a></header>
      <section class="sv-box"><div class="sv-heading"><div><h2>تاریخچه پرداخت‌های شما</h2><p>آخرین ۱۰۰ پرداخت ثبت‌شده در حسابداری</p></div></div>
        {% if rows %}<div class="sv-history-list">
        {% for p in rows %}<div class="sv-history-row">
          <div><b>{{ p.display_name }}</b><small>اکانت {{ p.subscription_id|fa }} · {{ p.date }}</small></div>
          <strong>{{ p.amount }} تومان</strong></div>{% endfor %}</div>
        {% else %}<p class="sv-info">هنوز پرداختی برای این شماره ثبت نشده است.</p>{% endif %}
        <a class="sv-main-button" href="/?view=payments" style="margin-top:24px">تمدید یا پرداخت اشتراک ←</a>
      </section></main>
      <style>.sv-history-list{margin-top:20px}.sv-history-row{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:15px 3px;border-bottom:1px solid #e7e9ed}.sv-history-row b{font-size:14px}.sv-history-row small{display:block;color:#8b8f98;font-size:11px;margin-top:7px}.sv-history-row strong{font-size:14px;white-space:nowrap}@media(max-width:470px){.sv-history-row b,.sv-history-row strong{font-size:12px}}</style>
    </body></html>"""
    return _sv2_HTML(jinja.from_string(template).render(rows=output),
                     headers={"Cache-Control":"private,no-store"})

def _sv2_landing(request: Request):
    if request.query_params.get("view") == "payments" or any(\n        key in request.query_params for key in ("payment_error", "payment_pending", "disabled", "welcome")\n    ):\n        return v2_home(request)
    phone = _v2_session_phone(request)
    if not phone:
        return v2_home(request)
    # Checkout cookie requires original verified-payment redirect/reconciliation.
    if request.cookies.get("moshtarakin_checkout"):
        return v2_home(request)
    with db_conn() as conn:
        accounts = active_subscriptions(conn, phone)
    exp = [a["expiry_date"] for a in accounts if a.get("expiry_date")]
    total = sum(int(a.get("debt") or 0) for a in accounts)
    page = jinja.from_string(_SV2_HTML).render(
        masked_phone=masked(phone), account_count=len(accounts),
        expiry=jalali_text(min(exp)) if exp else "ثبت نشده",
        debt=money(total),
        whatsapp_url=_sv2_whatsapp(), phone_url=_sv2_phone()
    )
    return _sv2_HTML(page, headers={"Cache-Control":"private,no-store"})

# This legacy portal registers GET '/' during v2.py execution.
# Update its APIRoute callable without registering a duplicate "/" path.
_sv2_found=False
for _sv2_route in app.router.routes:
    if getattr(_sv2_route,"path",None)=="/" and "GET" in (getattr(_sv2_route,"methods",set()) or set()):
        if getattr(_sv2_route,"endpoint",None) not in (v2_home,globals().get("_svc_home")):
            continue
        _sv2_route.endpoint = _sv2_landing
        _sv2_route.dependant.call = _sv2_landing
        _sv2_found=True
        break
if not _sv2_found:
    raise RuntimeError("Expected previous V2 home route missing: refusing services dashboard patch")
