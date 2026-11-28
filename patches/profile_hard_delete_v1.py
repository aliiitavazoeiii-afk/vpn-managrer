# HESAB_PROFILE_HARD_DELETE_GUARDED_V1
# Adds a distinct permanent-delete action to the existing profile.
# NEVER changes existing archive routes. Financial / gateway-linked users
# are blocked until manual reconciliation; no XUI/Shahan/VPN deletions.
import os as _hd_os
import re as _hd_re
import html as _hd_html
import hmac as _hd_hmac
import time as _hd_time
import hashlib as _hd_hashlib
from fastapi import Request as _hd_Request, Depends as _hd_Depends
from fastapi.responses import HTMLResponse as _hd_HTML, RedirectResponse as _hd_Redirect
from sqlalchemy import text as _hd_text
from sqlalchemy.orm import Session as _hd_Session

_HD_MARKER = "HESAB_PROFILE_HARD_DELETE_GUARDED_V1"
_HD_DOMAIN = "https://" + _hd_os.environ.get("APP_DOMAIN", "hesab.filmjadiid.ir").strip().lower()
_HD_SIGNATURE_KEY = _hd_os.environ.get("APP_SECRET_KEY", "").encode("utf-8")
if len(_HD_SIGNATURE_KEY) < 24:
    raise RuntimeError("Hard-delete protection requires APP_SECRET_KEY")

_hd_profile = TEMPLATES.get("user_detail.html", "")
_hd_inject = """<section id="hd-erase-user" style="margin:22px 0;padding:16px;border:1px solid #6b3336;border-radius:14px;background:#201b22">
 <div style="font-weight:850;font-size:15px;color:#fecaca;margin-bottom:8px">مدیریت دائمی اکانت</div>
 <p style="font-size:12px;line-height:2;color:#decbd1">بایگانی با حذف دائمی فرق دارد. اگر این اکانت سابقهٔ پرداخت، پیام یا وابستگی مشترک داشته باشد، حذف دائمی به‌صورت ایمن مسدود می‌شود.</p>
 <a href="/users/{{ request.path_params['sid'] }}/permanent-delete" style="display:inline-block;background:#7f1d1d;color:white;padding:10px 15px;border-radius:10px;text-decoration:none;font-weight:bold">بررسی حذف دائمی از سامانه</a>
</section>
"""
if not _hd_profile or "hd-erase-user" in _hd_profile:
    raise RuntimeError("Unexpected profile template for hard-delete UI")
_hd_begin = _hd_profile.find("{% block content %}")
_hd_end = _hd_profile.find("{% endblock %}", _hd_begin + 17)
if _hd_begin < 0 or _hd_end < 0:
    raise RuntimeError("Profile content block missing; refusing blind modification")
_hd_profile = _hd_profile[:_hd_end] + _hd_inject + _hd_profile[_hd_end:]
TEMPLATES["user_detail.html"] = _hd_profile
_hd_users = TEMPLATES.get("user_status.html", "")
if _hd_users and 'hard_deleted' not in _hd_users:
    _hd_users = _hd_users.replace(
        '<div class="lc-searchbar">',
        '''{% if request.query_params.get("hard_deleted") %}
<div style="padding:12px 16px;margin-bottom:16px;background:#123d32;
border:1px solid #32826c;border-radius:12px;color:#c4f6e8">
اکانت انتخاب‌شده از دیتابیس مدیریتی حذف شد؛ اطلاعات مالی، پیام‌ها
و دیگر وابستگی‌های محافظت‌شده قبلاً بررسی شده‌اند.</div>
{% endif %}
<div class="lc-searchbar">''', 1)
    TEMPLATES["user_status.html"] = _hd_users
if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)


def _hd_page(title, body, status=200):
    return _hd_HTML("""<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>""" + _hd_html.escape(title) + """</title><style>
body{background:#101b2c;color:#eef3f8;font:15px/2 Tahoma,Arial,sans-serif;padding:24px}
main{max-width:680px;margin:auto;background:#18263b;border:1px solid #34445a;
border-radius:18px;padding:24px}h1{font-size:20px;margin-top:0}
a{color:#9bcfff}.warn{color:#ffc7c7}.muted{color:#a7b6c8}
label{display:block;margin:10px 0}input[type=text]{box-sizing:border-box;width:100%;
background:#0b1524;color:white;border:1px solid #718197;border-radius:10px;padding:12px;font:inherit}
button{background:#8c2228;color:white;border:0;border-radius:10px;
padding:11px 16px;font:inherit;font-weight:bold;cursor:pointer}
li{margin:4px 0}
</style><main><h1>""" + _hd_html.escape(title) + """</h1>""" + body +
            """</main></html>""", status_code=status,
            headers={"Cache-Control": "no-store"})


def _hd_auth(request):
    # Existing app-level auth middleware protects all /users routes. In
    # addition require a nonempty signed login session and same-site POST.
    try:
        session = request.session
    except Exception:
        return False
    return isinstance(session, dict) and bool(session)


def _hd_identity_signature(sid, name, created_at):
    raw = f"{sid}|{created_at}|{name}".encode("utf-8")
    return _hd_hmac.new(_HD_SIGNATURE_KEY, raw, _hd_hashlib.sha256).hexdigest()


def _hd_token(s):
    issued = str(int(_hd_time.time()))
    return issued + "." + _hd_identity_signature(s.id, s.display_name or "", issued)


def _hd_valid_token(s, raw):
    try:
        issued, sign = str(raw or "").split(".", 1)
        when = int(issued)
    except (ValueError, TypeError):
        return False
    now = int(_hd_time.time())
    return (0 <= now-when <= 600 and len(sign) == 64 and
            _hd_hmac.compare_digest(sign, _hd_identity_signature(
                s.id, s.display_name or "", issued)))


def _hd_valid_origin(request):
    origin = (request.headers.get("origin") or "").rstrip("/")
    referer = request.headers.get("referer") or ""
    site = request.headers.get("sec-fetch-site") or ""
    return ((origin == _HD_DOMAIN or
             (not origin and referer.startswith(_HD_DOMAIN + "/"))) and
            site in ("", "same-origin"))


def _hd_existing(db, table):
    return db.execute(_hd_text("SELECT to_regclass(:name)"), {"name": "public."+table}).scalar() is not None


def _hd_simple_count(db, table, column, value):
    if not (_hd_re.fullmatch(r"[a-z_][a-z0-9_]*", table) and
            _hd_re.fullmatch(r"[a-z_][a-z0-9_]*", column)):
        raise ValueError("invalid database identifier")
    if not _hd_existing(db, table):
        return 0
    return int(db.execute(_hd_text(
        f'SELECT COUNT(*) FROM public."{table}" WHERE "{column}"=:value'
    ), {"value": value}).scalar() or 0)


def _hd_inspection(db, s):
    """Fail closed on financial, SMS, linked accounts and uncertain schema.

    Only account-specific followup and account-creation audit entries are
    eligible for deletion, never an ambiguous/shared audit entry.
    """
    sid = int(s.id)
    phone = str(s.phone or "").strip()
    blockers = []
    audit_ids = []

    for table in ("payments", "ayria_payment_allocations"):
        count = _hd_simple_count(db, table, "subscription_id", sid)
        if count:
            blockers.append(f"{table}: {count} ردیف مالی مرتبط")

    # Discover ANY unknown FK to subscriptions, not just ones we expect.
    fkrows = db.execute(_hd_text("""
        SELECT cls.relname AS table_name, n.nspname AS schema_name,
               a.attname AS column_name, c.confdeltype AS on_delete,
               array_length(c.conkey,1) AS column_count
        FROM pg_constraint c
        JOIN pg_class cls ON cls.oid=c.conrelid
        JOIN pg_namespace n ON n.oid=cls.relnamespace
        LEFT JOIN pg_attribute a ON a.attrelid=c.conrelid
          AND a.attnum=c.conkey[1]
        WHERE c.contype='f' AND c.confrelid='public.subscriptions'::regclass
    """)).mappings().all()
    for fk in fkrows:
        table, schema, column = fk["table_name"],fk["schema_name"],fk["column_name"]
        if schema != "public" or fk["column_count"] != 1 or not column:
            blockers.append("ارتباط ناشناختهٔ چندستونی در دیتابیس")
            continue
        if not (_hd_re.fullmatch(r"[a-z_][a-z0-9_]*", table) and
                _hd_re.fullmatch(r"[a-z_][a-z0-9_]*", column)):
            blockers.append("ساختار جدول وابسته قابل تأیید نیست")
            continue
        count = _hd_simple_count(db, table, column, sid)
        if table == "billing_anchor":
            if fk["on_delete"] != "c":
                blockers.append("billing_anchor: حذف آبشاری تأیید نشده")
        elif count and table not in ("payments", "ayria_payment_allocations"):
            blockers.append(f"{table}: {count} ارجاع دیگر به کاربر")

    # Additional non-FK subscription_id columns cannot be assumed safe.
    non_fk = db.execute(_hd_text("""
        SELECT table_name
        FROM information_schema.columns
        WHERE table_schema='public' AND column_name='subscription_id'
          AND table_name NOT IN ('payments','billing_anchor',
                                 'ayria_payment_allocations')
        GROUP BY table_name
    """)).scalars().all()
    for table in non_fk:
        if _hd_re.fullmatch(r"[a-z_][a-z0-9_]*", table):
            n = _hd_simple_count(db, table, "subscription_id", sid)
            if n:
                blockers.append(f"{table}: {n} ارجاع بدون کنترل حذف")

    if _hd_existing(db, "native_sms_v2_jobs"):
        count = db.execute(_hd_text(
            "SELECT count(*) FROM native_sms_v2_jobs WHERE :sid = ANY(account_ids)"
        ), {"sid":sid}).scalar()
        if count:
            blockers.append(f"پیام‌های متصل به شناسهٔ اکانت: {int(count)} مورد")

    if phone:
        siblings = _hd_simple_count(db, "subscriptions", "phone", phone)
        if siblings != 1:
            blockers.append("شمارهٔ مشترک بین چند اکانت؛ حذف مستقل امن نیست")
        # Any operational record with the phone may be evidence of a payment,
        # sent message or another service; never erase it indiscriminately.
        phone_tables = db.execute(_hd_text("""
            SELECT table_name,column_name
            FROM information_schema.columns
            WHERE table_schema='public' AND column_name IN ('phone','mobile')
              AND table_name <> 'subscriptions'
              AND data_type IN ('text','character varying','character')
            ORDER BY table_name
        """)).all()
        for table, field in phone_tables:
            if _hd_re.fullmatch(r"[a-z_][a-z0-9_]*", table):
                n = _hd_simple_count(db, table, field, phone)
                if n:
                    blockers.append(f"{table}: {n} رکورد مرتبط با شمارهٔ همراه")

    # Account-specific audit rows; preserve/deny anything ambiguous.
    conditions = ["message LIKE :sid_pat", "message LIKE :id_pat"]
    params = {"sid_pat":"%sid="+str(sid)+"%","id_pat":"%id="+str(sid)+"%"}
    if phone:
        conditions.append("message LIKE :phone_pat")
        params["phone_pat"] = "%" + phone + "%"
    name = str(s.display_name or "").strip()
    if len(name) >= 5:
        conditions.append("message LIKE :name_pat")
        params["name_pat"] = "%" + name + "%"
    events = db.execute(_hd_text(
        "SELECT id,kind,message FROM audit_events WHERE ("+" OR ".join(conditions)+
        ") ORDER BY id LIMIT 3001"
    ), params).mappings().all()
    if len(events)>3000:
        blockers.append("تعداد رویدادهای مرتبط زیاد است؛ بررسی دستی لازم است")
    for ev in events[:3000]:
        msg = str(ev["message"] or "")
        kind = str(ev["kind"] or "")
        safe_sid = bool(_hd_re.search(r"(?<![0-9])sid="+str(sid)+r";", msg))
        safe_add = kind=="user_add" and bool(_hd_re.search(
            r"(?<![0-9])id="+str(sid)+r";",msg))
        safe_archive = kind=="user_archive" and bool(_hd_re.fullmatch(
            r"Archived accounts \["+str(sid)+r"\]; source=.*",msg))
        if safe_sid or safe_add or safe_archive:
            audit_ids.append(int(ev["id"]))
        else:
            blockers.append("رویداد سیستمی غیرقابل‌تفکیک؛ نیازمند بررسی دستی")

    return sorted(set(blockers)), sorted(set(audit_ids))


def _hd_preview(sid:int, request:_hd_Request, db:_hd_Session=_hd_Depends(get_db)):
    if not _hd_auth(request):
        return _hd_page("دسترسی مجاز نیست", "<p>ابتدا وارد پنل مدیریت شوید.</p>",403)
    s = db.get(Subscription, sid)
    if s is None:
        return _hd_page("اکانت پیدا نشد", '<p><a href="/user-status">بازگشت به کاربران</a></p>',404)
    try:
        blockers, audit_ids = _hd_inspection(db, s)
    except Exception:
        db.rollback()
        return _hd_page("حذف قابل بررسی نیست",
            '<p class="warn">ساختار دیتابیس یا ارتباطات کاربر قابل تأیید نیست. هیچ تغییری انجام نشد.</p>',409)
    label = _hd_html.escape(str(s.display_name or "—"))
    phone = _hd_html.escape(str(s.phone or "—"))
    details = (f"<p>اکانت: <b>{label}</b> (شناسه {sid})"
               f"<br>شماره: {phone}</p>")
    details += ("<p class='muted'>این عملیات فقط دیتابیس حساب VPN را بررسی می‌کند. "
                "اکانت روی X-UI/شاهان، لاگ‌های خارجی و بکاپ‌های قبلی "
                "به‌طور خودکار پاک نمی‌شوند.</p>")
    if blockers:
        body = details + '<p class="warn"><b>حذف دائمی فعلاً مسدود است:</b></p><ul>'
        body += "".join("<li>"+_hd_html.escape(v)+"</li>" for v in blockers)
        body += '</ul><p>برای جلوگیری از حذف اشتباهی سوابق مالی یا پیام‌ها، هیچ داده‌ای حذف نشده است.</p>'
    else:
        body = details + f"""<p>بررسی ایمنی انجام شد. {len(audit_ids)} رویداد اختصاصی
        اکانت نیز همراه با رکورد آن از دیتابیس حذف می‌شود. حساب‌های دیگر تغییری نمی‌کنند.</p>
        <p class="warn"><b>این کار در دیتابیس قابل بازگشت نیست.</b> فقط در صورتی
        ادامه دهید که نسخهٔ پشتیبان مستقل و معتبر دارید.</p>
        <form method="post" action="/users/{sid}/permanent-delete">
          <input type="hidden" name="verification" value="{_hd_token(s)}">
          <label>برای تأیید، عبارت <b>حذف {sid}</b> را دقیق تایپ کنید:</label>
          <input name="confirm_text" type="text" autocomplete="off" required
              placeholder="حذف {sid}">
          <label><input name="backup_confirmed" type="checkbox" value="yes" required>
          تأیید می‌کنم نسخهٔ پشتیبان جداگانه دارم و حذف دائمی را می‌خواهم.</label>
          <button type="submit">حذف دائمی این اکانت از دیتابیس</button>
        </form>"""
    body += f'<p><a href="/users/{sid}">بازگشت به پروفایل بدون تغییر</a></p>'
    return _hd_page("بررسی حذف دائمی کاربر",body)


async def _hd_execute(sid:int,request:_hd_Request,db:_hd_Session=_hd_Depends(get_db)):
    if not _hd_auth(request) or not _hd_valid_origin(request):
        return _hd_page("درخواست رد شد", "<p>احراز هویت یا مبدأ درخواست معتبر نیست.</p>",403)
    form = await request.form()
    token = str(form.get("verification") or "")
    confirmed = str(form.get("confirm_text") or "").strip()
    backup_confirmed = form.get("backup_confirmed") == "yes"
    if confirmed != "حذف "+str(sid) or not backup_confirmed:
        return _hd_page("تأیید ناقص", "<p>حذف انجام نشد؛ متن تأیید یا شرط بکاپ درست نیست.</p>",409)
    try:
        db.execute(_hd_text("SET LOCAL lock_timeout='3s'"))
        db.execute(_hd_text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                   {"key":"hard-delete-subscription|"+str(sid)})
        s = db.query(Subscription).filter(Subscription.id==sid).with_for_update().one_or_none()
        if s is None or not _hd_valid_token(s,token):
            db.rollback()
            return _hd_page("تأیید منقضی شد",
                            "<p>شناسه یا تأیید اعتبار ندارد. حذف انجام نشد.</p>",409)
        blockers, audit_ids = _hd_inspection(db,s)
        if blockers:
            db.rollback()
            return _hd_page("حذف مسدود شد",
                '<p class="warn">در فاصلهٔ بررسی تا تأیید، وابستگی پیدا شد یا قبلاً موجود بوده است. هیچ رکوردی حذف نشد.</p>',409)
        if audit_ids:
            db.query(AuditEvent).filter(AuditEvent.id.in_(audit_ids)).delete(synchronize_session=False)
        db.delete(s)
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        return _hd_page("حذف انجام نشد",
             "<p class='warn'>در بررسی وابستگی‌ها یا تراکنش پایگاه داده خطا رخ داد. "
             "تمام تغییرات همان تراکنش برگشت خوردند.</p>",409)
    return _hd_Redirect("/user-status?hard_deleted=1",status_code=303)


if not any(getattr(r,"path",None)=="/users/{sid}" and
           "GET" in (getattr(r,"methods",set()) or set()) for r in app.routes):
    raise RuntimeError("Existing user profile route not found")
if any(getattr(r,"path",None) in ("/users/{sid}/permanent-delete",) for r in app.routes):
    raise RuntimeError("Duplicate permanent-delete profile route")
app.add_api_route("/users/{sid}/permanent-delete",_hd_preview,methods=["GET"])
app.add_api_route("/users/{sid}/permanent-delete",_hd_execute,methods=["POST"])
