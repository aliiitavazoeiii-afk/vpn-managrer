import hashlib
import hmac
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import escape
from typing import Optional

import jdatetime
import psycopg
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from jinja2 import Environment
from psycopg.rows import dict_row


DATABASE_DSN = os.environ["DATABASE_DSN"]
PORTAL_SECRET = os.environ["CUSTOMER_PORTAL_SECRET"].strip()
AYRIA_API_BASE = (os.environ.get("AYRIA_API_BASE") or "https://api.ayriaclub.ir").rstrip("/")
AYRIA_API_KEY = (os.environ.get("AYRIA_APG_API_KEY") or "").strip()
AYRIA_WALLET_ID = (os.environ.get("AYRIA_APG_WALLET_ID") or "").strip()
AYRIA_REFERRAL_CODE = (os.environ.get("AYRIA_REFERRAL_CODE") or "").strip()
PUBLIC_PREFIX = "/my"

if len(PORTAL_SECRET) < 32:
    raise RuntimeError("CUSTOMER_PORTAL_SECRET must be at least 32 characters")

app = FastAPI(title="Hesab Customer Portal", docs_url=None, redoc_url=None)
jinja = Environment(autoescape=True)
session_signer = URLSafeTimedSerializer(PORTAL_SECRET, salt="hesab-customer-session")
pending_signer = URLSafeTimedSerializer(PORTAL_SECRET, salt="hesab-customer-pending")


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS customer_login_codes (
    id BIGSERIAL PRIMARY KEY,
    phone VARCHAR(32) NOT NULL,
    code_hash VARCHAR(128) NOT NULL,
    request_ip VARCHAR(96),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_customer_login_codes_phone
    ON customer_login_codes(phone, created_at DESC);

CREATE TABLE IF NOT EXISTS ayria_payment_requests (
    id BIGSERIAL PRIMARY KEY,
    phone VARCHAR(32) NOT NULL,
    cycle_key VARCHAR(96) NOT NULL,
    amount_toman BIGINT NOT NULL,
    amount_rial BIGINT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'creating',
    reference_code VARCHAR(160),
    tracking_number VARCHAR(160),
    payment_url TEXT,
    sms_job_id BIGINT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(phone, cycle_key)
);
CREATE INDEX IF NOT EXISTS idx_ayria_requests_phone
    ON ayria_payment_requests(phone, created_at DESC);
"""


BASE_CSS = r"""
:root{
  color-scheme:dark;
  --bg:#070b12;--panel:#0e1521;--panel2:#111a28;--line:rgba(255,255,255,.08);
  --text:#f4f7fb;--muted:#8d99aa;--blue:#76a9ff;--green:#79e29a;--red:#ff9aa4;
  --violet:#c7a7ff;
}
*{box-sizing:border-box}
html,body{margin:0;background:
radial-gradient(900px 440px at 85% -10%,rgba(88,101,242,.14),transparent 60%),
radial-gradient(700px 430px at -10% 20%,rgba(37,99,235,.10),transparent 60%),
var(--bg);color:var(--text);font-family:Tahoma,Arial,sans-serif;min-height:100%}
body{direction:rtl}
a{color:inherit}
.wrap{width:min(980px,calc(100% - 28px));margin:0 auto;padding:26px 0 48px}
.top{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:22px}
.brand{display:flex;align-items:center;gap:11px}
.logo{width:42px;height:42px;border-radius:14px;display:grid;place-items:center;
background:linear-gradient(145deg,#1b2941,#111927);border:1px solid var(--line);font-weight:900}
.brand b{display:block;font-size:15px}.brand small{display:block;color:var(--muted);font-size:10px;margin-top:4px}
.logout{border:1px solid var(--line);background:rgba(255,255,255,.03);color:#c9d2df;border-radius:10px;padding:8px 11px;font:inherit;font-size:10px;cursor:pointer}
.hero{border:1px solid var(--line);border-radius:24px;padding:24px;background:
linear-gradient(135deg,rgba(24,34,52,.96),rgba(10,15,24,.96));box-shadow:0 24px 70px rgba(0,0,0,.25)}
.hero-kicker{color:#9dbcf7;font-size:10px;letter-spacing:.08em}
.hero h1{font-size:26px;margin:10px 0 8px}.hero p{margin:0;color:var(--muted);font-size:12px;line-height:1.9}
.card{margin-top:16px;border:1px solid var(--line);border-radius:19px;background:rgba(14,21,33,.93);overflow:hidden}
.card-head{padding:16px 18px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:12px}
.card-head h2{margin:0;font-size:15px}.card-head small{color:var(--muted);font-size:10px}
.login-card{width:min(480px,100%);margin:70px auto 0;padding:24px;border:1px solid var(--line);border-radius:24px;background:rgba(14,21,33,.96);box-shadow:0 28px 80px rgba(0,0,0,.3)}
.login-card h1{margin:14px 0 7px;font-size:24px}.login-card p{color:var(--muted);font-size:11px;line-height:1.9;margin:0 0 19px}
.field{display:flex;flex-direction:column;gap:7px;margin-top:12px}.field label{font-size:10px;color:#a6b1c1}
.field input{height:48px;border:1px solid rgba(255,255,255,.11);border-radius:12px;background:#090f19;color:#fff;padding:0 13px;font:inherit;font-size:14px;outline:none}
.field input:focus{border-color:rgba(118,169,255,.55)}
.btn{width:100%;height:48px;border:0;border-radius:12px;background:#edf2f8;color:#111821;font:inherit;font-weight:900;margin-top:16px;cursor:pointer}
.note{margin-top:13px;color:#707d90;font-size:9px;line-height:1.8}
.flash{margin:14px 0 0;padding:11px 12px;border-radius:11px;border:1px solid rgba(255,255,255,.08);font-size:10px;line-height:1.8}
.flash.ok{background:rgba(34,197,94,.07);border-color:rgba(34,197,94,.18);color:#b8f4c8}
.flash.bad{background:rgba(239,68,68,.07);border-color:rgba(239,68,68,.18);color:#ffc0c6}
.summary{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:16px}
.summary>div{border:1px solid var(--line);background:rgba(14,21,33,.86);border-radius:16px;padding:14px}
.summary small{color:var(--muted);font-size:9px;display:block}.summary strong{display:block;margin-top:8px;font-size:17px}.summary span{color:#a8b4c4;font-size:9px}
.accounts{padding:0 16px}
.account{display:grid;grid-template-columns:1.3fr 1fr 1fr 1fr;gap:12px;align-items:center;padding:15px 2px;border-bottom:1px solid rgba(255,255,255,.055)}
.account:last-child{border-bottom:0}.account small{display:block;color:#78869a;font-size:9px;margin-bottom:5px}.account b{font-size:12px}.account .money{color:#dbe8ff}.pill{display:inline-flex;padding:5px 8px;border-radius:999px;font-size:9px}
.pill.active{background:rgba(34,197,94,.09);color:#a9efbc}.pill.due{background:rgba(239,68,68,.08);color:#ffb4bb}
.paybox{padding:18px;display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center}
.paybox h3{margin:0 0 6px;font-size:14px}.paybox p{margin:0;color:var(--muted);font-size:10px;line-height:1.8}
.paybtn{border:0;border-radius:12px;background:linear-gradient(135deg,#8ab4ff,#b6ccff);color:#0b1320;padding:12px 18px;font:inherit;font-size:11px;font-weight:900;cursor:pointer;white-space:nowrap}
.paybtn:disabled{opacity:.45;cursor:not-allowed}.ltr{direction:ltr;text-align:left}
.footer{margin-top:18px;color:#5f6d80;font-size:9px;text-align:center;line-height:1.9}
@media(max-width:700px){
  .wrap{width:min(100% - 20px,980px);padding-top:16px}
  .hero{padding:19px}.hero h1{font-size:22px}
  .summary{grid-template-columns:1fr}
  .account{grid-template-columns:1fr 1fr}
  .paybox{grid-template-columns:1fr}.paybtn{width:100%}
  .login-card{margin-top:28px;padding:20px}
}
"""


LOGIN_HTML = r"""
<!doctype html><html lang="fa" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>ورود به حساب اشتراک</title><style>{{ css }}</style></head><body>
<div class="wrap">
  <div class="login-card">
    <div class="brand"><div class="logo">H</div><div><b>Hesab</b><small>پنل اشتراک من</small></div></div>
    <h1>ورود با شماره موبایل</h1>
    <p>شماره‌ای را وارد کن که اشتراک با آن ثبت شده. کد یک‌بارمصرف از طریق پیامک برای همان شماره ارسال می‌شود.</p>
    {% if error %}<div class="flash bad">{{ error }}</div>{% endif %}
    {% if info %}<div class="flash ok">{{ info }}</div>{% endif %}
    <form method="post" action="{{ prefix }}/request-code">
      <div class="field"><label>شماره موبایل</label>
        <input name="phone" inputmode="tel" autocomplete="tel" dir="ltr" placeholder="0912..." required>
      </div>
      <button class="btn" type="submit">ارسال کد ورود</button>
    </form>
    <div class="note">برای امنیت، ورود فقط با داشتن سیم‌کارت ثبت‌شده امکان‌پذیر است.</div>
  </div>
</div></body></html>
"""


VERIFY_HTML = r"""
<!doctype html><html lang="fa" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>تأیید شماره موبایل</title><style>{{ css }}</style></head><body>
<div class="wrap">
  <div class="login-card">
    <div class="brand"><div class="logo">H</div><div><b>Hesab</b><small>تأیید ورود</small></div></div>
    <h1>کد پیامک را وارد کن</h1>
    <p>کد ۶ رقمی برای شماره <span dir="ltr">{{ masked_phone }}</span> ارسال شده و ۵ دقیقه اعتبار دارد.</p>
    {% if error %}<div class="flash bad">{{ error }}</div>{% endif %}
    <form method="post" action="{{ prefix }}/verify">
      <div class="field"><label>کد یک‌بارمصرف</label>
        <input name="code" inputmode="numeric" autocomplete="one-time-code" dir="ltr" maxlength="6" placeholder="••••••" required autofocus>
      </div>
      <button class="btn" type="submit">ورود به حساب</button>
    </form>
    <form method="get" action="{{ prefix }}/"><button class="logout" type="submit" style="margin-top:12px">تغییر شماره</button></form>
  </div>
</div></body></html>
"""


DASHBOARD_HTML = r"""
<!doctype html><html lang="fa" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>اشتراک من</title><style>{{ css }}</style></head><body>
<div class="wrap">
  <div class="top">
    <div class="brand"><div class="logo">H</div><div><b>Hesab</b><small>پنل اشتراک من</small></div></div>
    <form method="post" action="{{ prefix }}/logout"><button class="logout" type="submit">خروج</button></form>
  </div>

  <section class="hero">
    <div class="hero-kicker">MY SUBSCRIPTION</div>
    <h1>وضعیت اشتراک شما</h1>
    <p>شماره ثبت‌شده: <span dir="ltr">{{ phone }}</span> · تاریخ‌ها، بدهی و تمدید همه اکانت‌های این شماره اینجا نمایش داده می‌شود.</p>
  </section>

  <section class="summary">
    <div><small>تعداد اکانت</small><strong>{{ accounts|length|fa }}</strong><span>زیر همین شماره</span></div>
    <div><small>جمع بدهی فعلی</small><strong>{{ total_debt|money }}</strong><span>تومان</span></div>
    <div><small>نزدیک‌ترین سررسید</small><strong>{{ nearest_expiry }}</strong><span>شمسی</span></div>
  </section>

  <section class="card">
    <div class="card-head"><h2>اکانت‌ها</h2><small>اطلاعات به‌روز اشتراک</small></div>
    <div class="accounts">
      {% for a in accounts %}
      <div class="account">
        <div><small>نام اکانت</small><b>{{ a.display_name }}</b></div>
        <div><small>تاریخ انقضا</small><b>{{ a.expiry_jalali }}</b></div>
        <div><small>مبلغ ماهانه</small><b class="money">{{ a.monthly_fee|money }} تومان</b></div>
        <div><small>وضعیت</small>
          {% if a.debt > 0 %}<span class="pill due">نیازمند تمدید · {{ a.debt|money }} تومان</span>
          {% else %}<span class="pill active">فعال</span>{% endif %}
        </div>
      </div>
      {% endfor %}
    </div>
  </section>

  <section class="card">
    <div class="paybox">
      <div>
        <h3>{% if total_debt > 0 %}تمدید و پرداخت آنلاین{% else %}اشتراک شما بدهی ندارد{% endif %}</h3>
        <p>{% if total_debt > 0 %}با زدن دکمه، درگاه Ayria برای مبلغ دقیق بدهی ساخته می‌شود و به صفحه پرداخت منتقل می‌شوی.{% else %}در حال حاضر پرداختی برای این شماره لازم نیست.{% endif %}</p>
      </div>
      {% if total_debt > 0 %}
      <form method="post" action="{{ prefix }}/pay">
        <input type="hidden" name="csrf" value="{{ csrf }}">
        <button class="paybtn" type="submit">پرداخت {{ total_debt|money }} تومان ←</button>
      </form>
      {% else %}
      <button class="paybtn" disabled>پرداخت لازم نیست</button>
      {% endif %}
    </div>
  </section>

  {% if message %}<div class="flash {{ 'bad' if message_is_error else 'ok' }}">{{ message }}</div>{% endif %}
  <div class="footer">برای ورود مجدد فقط شماره موبایل و کد پیامکی لازم است.</div>
</div></body></html>
"""


def db_conn():
    return psycopg.connect(DATABASE_DSN, row_factory=dict_row)


def ensure_schema():
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()


@app.on_event("startup")
def startup():
    ensure_schema()


def fa_digits(value):
    return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def money(value):
    try:
        return fa_digits(f"{int(value or 0):,}")
    except Exception:
        return "۰"


jinja.filters["fa"] = fa_digits
jinja.filters["money"] = money


def render(source, **ctx):
    return HTMLResponse(jinja.from_string(source).render(css=BASE_CSS, prefix=PUBLIC_PREFIX, **ctx))


def normalize_phone(value):
    raw = str(value or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits.startswith("0098"):
        digits = "0" + digits[4:]
    elif digits.startswith("98") and len(digits) == 12:
        digits = "0" + digits[2:]
    elif digits.startswith("9") and len(digits) == 10:
        digits = "0" + digits
    if len(digits) != 11 or not digits.startswith("09"):
        return ""
    return digits


def masked(phone):
    if len(phone) < 8:
        return phone
    return phone[:4] + "•••" + phone[-4:]


def code_hash(phone, code):
    return hmac.new(
        PORTAL_SECRET.encode(),
        f"{phone}:{code}".encode(),
        hashlib.sha256,
    ).hexdigest()


def client_ip(request: Request):
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()[:96]
    return (request.client.host if request.client else "")[:96]


def session_phone(request: Request) -> Optional[str]:
    token = request.cookies.get("hesab_customer", "")
    if not token:
        return None
    try:
        data = session_signer.loads(token, max_age=60 * 60 * 24 * 30)
    except (BadSignature, SignatureExpired):
        return None
    phone = normalize_phone(data.get("phone", ""))
    return phone or None


def csrf_for(phone):
    return hmac.new(
        PORTAL_SECRET.encode(),
        f"csrf:{phone}".encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_csrf(phone, token):
    return hmac.compare_digest(csrf_for(phone), str(token or ""))


def add_jalali_months(g_date: date, months: int) -> date:
    jd = jdatetime.date.fromgregorian(date=g_date)
    total = jd.year * 12 + (jd.month - 1) + months
    jy = total // 12
    jm = total % 12 + 1
    day = jd.day
    while day > 27:
        try:
            next_j = jdatetime.date(jy, jm, day)
            return next_j.togregorian()
        except ValueError:
            day -= 1
    return jdatetime.date(jy, jm, day).togregorian()


def debt_periods(expiry: Optional[date], today: date) -> int:
    if not expiry or expiry > today:
        return 0
    cursor = expiry
    periods = 0
    while cursor <= today and periods < 240:
        periods += 1
        cursor = add_jalali_months(cursor, 1)
    return periods


def jalali_text(value: Optional[date]) -> str:
    if not value:
        return "—"
    jd = jdatetime.date.fromgregorian(date=value)
    return fa_digits(f"{jd.year:04d}/{jd.month:02d}/{jd.day:02d}")


def active_subscriptions(conn, phone):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, display_name, phone, expiry_date, monthly_fee_toman,
                   debt_toman, payment_status, is_free
            FROM subscriptions
            WHERE phone=%s
            ORDER BY expiry_date ASC NULLS LAST, id ASC
            """,
            (phone,),
        )
        rows = cur.fetchall()

        cur.execute(
            """
            SELECT kind, message
            FROM audit_events
            WHERE kind IN ('followup_waiting','followup_cut','followup_clear')
            ORDER BY id DESC
            """
        )
        events = cur.fetchall()

    states = {}
    for ev in events:
        m = re.search(r"\bsid=(\d+)\b", str(ev["message"] or ""))
        if not m:
            continue
        sid = int(m.group(1))
        if sid in states:
            continue
        if ev["kind"] == "followup_cut":
            states[sid] = "cut"
        elif ev["kind"] == "followup_waiting":
            states[sid] = "waiting"
        else:
            states[sid] = None

    today = date.today()
    result = []
    for row in rows:
        if states.get(int(row["id"])) == "cut":
            continue
        fee = int(row["monthly_fee_toman"] or 0)
        live_debt = 0 if row["is_free"] else debt_periods(row["expiry_date"], today) * fee
        item = dict(row)
        item["monthly_fee"] = fee
        item["debt"] = live_debt
        item["expiry_jalali"] = jalali_text(row["expiry_date"])
        item["followup_state"] = states.get(int(row["id"]))
        result.append(item)
    return result


def phone_exists(conn, phone):
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM subscriptions WHERE phone=%s LIMIT 1", (phone,))
        return cur.fetchone() is not None


def queue_sms(conn, phone, message, source):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sms_jobs(phone, message, status, source)
            VALUES (%s, %s, 'queued', %s)
            RETURNING id
            """,
            (phone, message, source),
        )
        return int(cur.fetchone()["id"])


def ayria_create(payload):
    if not AYRIA_API_KEY or not AYRIA_WALLET_ID or not AYRIA_REFERRAL_CODE:
        raise RuntimeError("Ayria APG is not configured")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        AYRIA_API_BASE + "/apg/v1/create",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "Accept": "application/json",
            "APG-API-KEY": AYRIA_API_KEY,
            "APG-WALLET-ID": AYRIA_WALLET_ID,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            detail = ""
        raise RuntimeError(f"Ayria HTTP {exc.code}: {detail}") from exc
    data = json.loads(raw)
    if not data.get("paymentUrl") or not data.get("referenceCode"):
        raise RuntimeError("Ayria response missing payment URL")
    return data


@app.get("/health")
def health():
    return {"ok": True, "service": "Hesab Customer Portal"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    phone = session_phone(request)
    if not phone:
        return render(LOGIN_HTML, error=None, info=None)

    with db_conn() as conn:
        accounts = active_subscriptions(conn, phone)

    if not accounts:
        response = RedirectResponse(PUBLIC_PREFIX + "/", status_code=303)
        response.delete_cookie("hesab_customer", path=PUBLIC_PREFIX)
        return response

    total_debt = sum(int(a["debt"] or 0) for a in accounts)
    expiries = [a["expiry_date"] for a in accounts if a["expiry_date"]]
    nearest = jalali_text(min(expiries)) if expiries else "—"

    q = request.query_params
    message = None
    message_is_error = False
    if q.get("payment_error"):
        message = "ساخت درگاه انجام نشد. چند لحظه بعد دوباره تلاش کن."
        message_is_error = True

    return render(
        DASHBOARD_HTML,
        phone=phone,
        accounts=accounts,
        total_debt=total_debt,
        nearest_expiry=nearest,
        csrf=csrf_for(phone),
        message=message,
        message_is_error=message_is_error,
    )


@app.post("/request-code")
def request_code(request: Request, phone: str = Form(...)):
    normalized = normalize_phone(phone)
    generic = "اگر این شماره در سیستم ثبت شده باشد، کد ورود برای آن ارسال می‌شود."

    if not normalized:
        return render(LOGIN_HTML, error="شماره موبایل معتبر نیست.", info=None)

    now = datetime.now(timezone.utc)
    ip = client_ip(request)

    with db_conn() as conn:
        exists = phone_exists(conn, normalized)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT created_at
                FROM customer_login_codes
                WHERE phone=%s
                ORDER BY id DESC
                LIMIT 1
                """,
                (normalized,),
            )
            last = cur.fetchone()

            cur.execute(
                """
                SELECT COUNT(*) AS n
                FROM customer_login_codes
                WHERE phone=%s
                  AND created_at > NOW() - INTERVAL '1 hour'
                """,
                (normalized,),
            )
            hourly = int(cur.fetchone()["n"])

        too_soon = bool(last and last["created_at"] and (now - last["created_at"]).total_seconds() < 60)
        limited = hourly >= 5

        if exists and not too_soon and not limited:
            code = f"{secrets.randbelow(900000) + 100000:06d}"
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO customer_login_codes(
                        phone, code_hash, request_ip, expires_at
                    )
                    VALUES (%s, %s, %s, NOW() + INTERVAL '5 minutes')
                    """,
                    (normalized, code_hash(normalized, code), ip),
                )
                queue_sms(
                    conn,
                    normalized,
                    f"کد ورود به پنل اشتراک Hesab: {code}\nاعتبار: ۵ دقیقه",
                    "portal-otp",
                )
            conn.commit()

    pending = pending_signer.dumps({"phone": normalized})
    response = RedirectResponse(PUBLIC_PREFIX + "/verify", status_code=303)
    response.set_cookie(
        "hesab_pending",
        pending,
        max_age=600,
        httponly=True,
        secure=True,
        samesite="lax",
        path=PUBLIC_PREFIX,
    )
    return response


@app.get("/verify", response_class=HTMLResponse)
def verify_page(request: Request):
    pending = request.cookies.get("hesab_pending", "")
    try:
        data = pending_signer.loads(pending, max_age=600)
        phone = normalize_phone(data.get("phone", ""))
    except Exception:
        phone = ""
    if not phone:
        return RedirectResponse(PUBLIC_PREFIX + "/", status_code=303)
    return render(VERIFY_HTML, masked_phone=masked(phone), error=None)


@app.post("/verify")
def verify_code(request: Request, code: str = Form(...)):
    pending = request.cookies.get("hesab_pending", "")
    try:
        data = pending_signer.loads(pending, max_age=600)
        phone = normalize_phone(data.get("phone", ""))
    except Exception:
        phone = ""

    clean_code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if not phone or len(clean_code) != 6:
        return render(VERIFY_HTML, masked_phone=masked(phone or "—"), error="کد واردشده معتبر نیست.")

    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, code_hash, attempts, expires_at
                FROM customer_login_codes
                WHERE phone=%s
                  AND used_at IS NULL
                ORDER BY id DESC
                LIMIT 1
                FOR UPDATE
                """,
                (phone,),
            )
            row = cur.fetchone()

            if not row:
                return render(VERIFY_HTML, masked_phone=masked(phone), error="کد معتبر پیدا نشد. دوباره درخواست کد بده.")

            cur.execute(
                "UPDATE customer_login_codes SET attempts=attempts+1 WHERE id=%s",
                (row["id"],),
            )

            valid = (
                int(row["attempts"] or 0) < 5
                and row["expires_at"] > datetime.now(timezone.utc)
                and hmac.compare_digest(row["code_hash"], code_hash(phone, clean_code))
            )

            if valid:
                cur.execute(
                    "UPDATE customer_login_codes SET used_at=NOW() WHERE id=%s",
                    (row["id"],),
                )
            conn.commit()

    if not valid:
        return render(VERIFY_HTML, masked_phone=masked(phone), error="کد اشتباه یا منقضی شده است.")

    token = session_signer.dumps({"phone": phone})
    response = RedirectResponse(PUBLIC_PREFIX + "/", status_code=303)
    response.set_cookie(
        "hesab_customer",
        token,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        secure=True,
        samesite="lax",
        path=PUBLIC_PREFIX,
    )
    response.delete_cookie("hesab_pending", path=PUBLIC_PREFIX)
    return response


@app.post("/logout")
def logout():
    response = RedirectResponse(PUBLIC_PREFIX + "/", status_code=303)
    response.delete_cookie("hesab_customer", path=PUBLIC_PREFIX)
    response.delete_cookie("hesab_pending", path=PUBLIC_PREFIX)
    return response


@app.post("/pay")
def pay(request: Request, csrf: str = Form(...)):
    phone = session_phone(request)
    if not phone or not verify_csrf(phone, csrf):
        return RedirectResponse(PUBLIC_PREFIX + "/", status_code=303)

    with db_conn() as conn:
        accounts = active_subscriptions(conn, phone)
        actionable = [a for a in accounts if int(a["debt"] or 0) > 0]

        if not actionable:
            return RedirectResponse(PUBLIC_PREFIX + "/", status_code=303)

        amount_toman = sum(int(a["debt"]) for a in actionable)
        amount_rial = amount_toman * 10
        expiries = [a["expiry_date"] for a in actionable if a["expiry_date"]]
        first_expiry = min(expiries).isoformat() if expiries else "no-expiry"
        cycle_key = f"{first_expiry}:{amount_toman}"

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status, payment_url, reference_code
                FROM ayria_payment_requests
                WHERE phone=%s AND cycle_key=%s
                LIMIT 1
                """,
                (phone, cycle_key),
            )
            existing = cur.fetchone()

        if existing and existing["payment_url"] and existing["reference_code"]:
            payment_url = str(existing["payment_url"])
            reference = str(existing["reference_code"])
            request_id = int(existing["id"])
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

            names = [str(a["display_name"] or "").strip() for a in actionable if str(a["display_name"] or "").strip()]
            payment_number = f"portal-{request_id}-{int(time.time())}"

            payload = {
                "referralCode": int(AYRIA_REFERRAL_CODE),
                "amount": amount_rial,
                "payerMobile": phone,
                "payerName": ("، ".join(names[:3]) or "کاربر")[:255],
                "description": "تمدید اشتراک",
                "paymentNumber": payment_number,
                "extraData": json.dumps(
                    {
                        "source": "hesab-customer-portal",
                        "requestId": request_id,
                        "phone": phone,
                        "subscriptionIds": [int(a["id"]) for a in actionable],
                        "amountToman": amount_toman,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "issuerMustVerifyPayment": False,
            }

            try:
                response = ayria_create(payload)
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
                return RedirectResponse(PUBLIC_PREFIX + "/?payment_error=1", status_code=303)

            payment_url = str(response["paymentUrl"]).strip()
            reference = str(response["referenceCode"]).strip()
            tracking = str(response.get("trackingNumber") or "").strip()

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
            for a in actionable:
                cur.execute(
                    """
                    INSERT INTO audit_events(kind, message, created_at)
                    VALUES ('followup_waiting', %s, NOW())
                    """,
                    (
                        f"sid={int(a['id'])}; customer portal payment opened; "
                        f"reference={reference}; phone={phone}",
                    ),
                )
            cur.execute(
                """
                INSERT INTO audit_events(kind, message, created_at)
                VALUES ('customer_portal_payment', %s, NOW())
                """,
                (
                    f"Portal payment opened; request={request_id}; reference={reference}; "
                    f"phone={phone}; amount_toman={amount_toman}",
                ),
            )
        conn.commit()

    return RedirectResponse(payment_url, status_code=303)
