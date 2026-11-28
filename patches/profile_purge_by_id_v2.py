# HESAB_PROFILE_PURGE_BY_ID_V2
# Optional operator-only irreversible purge of one subscription and its direct
# financial/linked rows. Other subscriptions with the same phone are untouched.
# Does not erase shared phone histories, backups or third-party VPN accounts.
from fastapi import Request as _hp2_Request, Depends as _hp2_Depends
from sqlalchemy.orm import Session as _hp2_Session
from sqlalchemy import text as _hp2_text

_HP2_ALLOWED_FK = frozenset(("payments", "billing_anchor", "ayria_payment_allocations"))
_HP2_PAID_SAFE_STATUS = frozenset(("paid", "failed", "canceled", "cancelled"))


def _hp2_plan(db, s):
    sid = int(s.id)
    phone = str(s.phone or "")
    reasons = []
    counts = {}

    # Any new/unknown FK may delete unrelated data through ON DELETE CASCADE.
    fks = db.execute(_hp2_text("""
      SELECT n.nspname AS ns,c.relname AS tbl,a.attname AS col,
             array_length(k.conkey,1) AS ncols
      FROM pg_constraint k
      JOIN pg_class c ON c.oid=k.conrelid
      JOIN pg_namespace n ON n.oid=c.relnamespace
      LEFT JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.conkey[1]
      WHERE k.contype='f' AND k.confrelid='public.subscriptions'::regclass
    """)).mappings().all()
    for fk in fks:
        tbl, col = str(fk["tbl"]),str(fk["col"])
        if fk["ns"] != "public" or fk["ncols"] != 1:
            reasons.append("ارتباط چندستونی یا خارج از public")
        elif tbl not in _HP2_ALLOWED_FK:
            if _hd_re.fullmatch(r"[a-z_][a-z0-9_]*",tbl) and _hd_re.fullmatch(r"[a-z_][a-z0-9_]*",col):
                if _hd_simple_count(db,tbl,col,sid)>0:
                    reasons.append("ارجاع ناشناخته از "+tbl)
            else:
                reasons.append("نام جدول وابسته نامعتبر است")

    # Validate non-FK subscription_id columns too.
    columns = db.execute(_hp2_text("""
      SELECT table_name FROM information_schema.columns
      WHERE table_schema='public' AND column_name='subscription_id'
        AND table_name NOT IN ('payments','billing_anchor',
                               'ayria_payment_allocations')
    """)).scalars().all()
    for table in columns:
        if _hd_re.fullmatch(r"[a-z_][a-z0-9_]*",str(table)):
            if _hd_simple_count(db,str(table),"subscription_id",sid):
                reasons.append("ارجاع ثبت‌شده در جدول "+str(table))
        else:
            reasons.append("ساختار نامعتبر جدول")

    for table in ("payments","ayria_payment_allocations","billing_anchor"):
        counts[table] = _hd_simple_count(db,table,"subscription_id",sid)

    # Never erase the allocation of a checkout that can still settle.
    if counts["ayria_payment_allocations"]:
        gateway = db.execute(_hp2_text("""
          SELECT r.status,r.paid_at,r.sync_status,a.applied_at
          FROM ayria_payment_allocations a
          JOIN ayria_payment_requests r ON r.id=a.request_id
          WHERE a.subscription_id=:sid
        """),{"sid":sid}).mappings().all()
        if len(gateway) != counts["ayria_payment_allocations"]:
            reasons.append("تخصیص پرداخت درگاه نامعتبر یا مفقود است")
        for row in gateway:
            status = str(row["status"] or "").lower()
            sync = str(row["sync_status"] or "").lower()
            if row["paid_at"] is None and status not in _HP2_PAID_SAFE_STATUS:
                reasons.append("درخواست پرداخت باز یا نامشخص در درگاه وجود دارد")
            if row["paid_at"] is not None and sync != "applied":
                reasons.append("پرداخت تأییدشده اما تسویه‌نشده در سامانه وجود دارد")

    # Preserve phone-only SMS data, but remove THIS subscription ID from
    # account_ids. The rest of an account group and its drafts are untouched.
    counts["native_linked"] = 0
    if _hd_existing(db,"native_sms_v2_jobs"):
        records = db.execute(_hp2_text("""
          SELECT id,status,account_ids
          FROM native_sms_v2_jobs
          WHERE :sid = ANY(account_ids)
          ORDER BY id
        """),{"sid":sid}).mappings().all()
        counts["native_linked"] = len(records)
        if any(str(r["status"]) in ("claimed","opened","attempting","dispatching") for r in records):
            reasons.append("پیامِ در حال ارسال یا بازشده؛ ابتدا تعیین وضعیت شود")

    # Phone-only rows and shared gateway requests cannot be attributed safely
    # to this subscription, so they are retained. Shared-phone does NOT block.
    counts["same_phone_other_accounts"] = (
        max(0,_hd_simple_count(db,"subscriptions","phone",phone)-1) if phone else 0
    )
    # Keep audit events if ambiguous; delete only exclusive and recognizable
    # direct references. No matching by name or phone.
    event_ids=[]
    events = db.execute(_hp2_text("""
      SELECT id,kind,message FROM audit_events
      WHERE message LIKE :sid OR message LIKE :add
         OR message LIKE :archived
      ORDER BY id LIMIT 2001
    """), {"sid":"%sid="+str(sid)+";%",
           "add":"%id="+str(sid)+";%",
           "archived":"%Archived accounts ["+str(sid)+"]%"}).mappings().all()
    if len(events)>2000:
        reasons.append("تعداد رویدادهای حساب بیش از حد مجاز است")
    for r in events[:2000]:
        message=str(r["message"] or "")
        kind=str(r["kind"] or "")
        sidrefs=_hd_re.findall(r"(?<![0-9])sid=([0-9]+);",message)
        idrefs=_hd_re.findall(r"(?<![0-9])id=([0-9]+);",message)
        safe=(
          (sidrefs == [str(sid)] and kind in
           ("followup_waiting","followup_cut","followup_clear","payment"))
          or (kind=="user_add" and idrefs==[str(sid)])
          or (kind=="user_archive" and message.startswith(
              "Archived accounts ["+str(sid)+"];"))
        )
        if safe and len(set(sidrefs))<=1:
            event_ids.append(int(r["id"]))
        else:
            reasons.append("رویداد مشترک یا غیرقابل‌تفکیک مرتبط با شناسه")

    counts["exclusive_audits"] = len(event_ids)
    return sorted(set(reasons)), counts, sorted(set(event_ids))


def _hp2_preview(sid:int, request:_hp2_Request,
                 db:_hp2_Session=_hp2_Depends(get_db)):
    if not _hd_auth(request):
        return _hd_page("دسترسی مجاز نیست","<p>ابتدا وارد پنل مدیریت شوید.</p>",403)
    s=db.get(Subscription,sid)
    if s is None:
        return _hd_page("کاربر پیدا نشد",
                        '<p><a href="/user-status">بازگشت به فهرست کاربران</a></p>',404)
    try:
        reasons,counts,_ = _hp2_plan(db,s)
    except Exception:
        db.rollback()
        return _hd_page("حذف قابل بررسی نیست",
              "<p class='warn'>ساختار دیتابیس تأیید نشد؛ هیچ تغییری انجام نشد.</p>",409)
    info=(f"<p>اکانت: <b>{_hd_html.escape(str(s.display_name))}</b> "
          f"— شناسه <b>{sid}</b><br>شماره: "
          f"{_hd_html.escape(str(s.phone or '—'))}</p>")
    info+=("<p>در این حالت تنها شناسهٔ انتخاب‌شده و رکوردهای اختصاصی آن "
           "حذف می‌شوند، نه همهٔ اکانت‌های یک شماره.</p><ul>"
           f"<li>پرداخت‌های مربوط به این شناسه: <b>{counts['payments']}</b></li>"
           f"<li>تخصیص‌های پرداخت درگاه: <b>{counts['ayria_payment_allocations']}</b></li>"
           f"<li>مبنای مالی: <b>{counts['billing_anchor']}</b></li>"
           f"<li>پیام‌های دارای پیوند مستقیم: <b>{counts['native_linked']}</b></li>"
           f"<li>سایر اکانت‌های همین شماره: <b>{counts['same_phone_other_accounts']}</b> (محفوظ)</li></ul>"
           "<p class='warn'><b>هشدار:</b> حذف پرداخت‌های اختصاصی، "
           "گزارش‌های مالی و جمع فروش تاریخی را تغییر می‌دهد. "
           "درخواست‌های پرداخت مشترک، لاگ‌های شمارهٔ همراه و سوابق بیرونی "
           "حذف نمی‌شوند. این حذف، پاک‌شدن کامل اطلاعات از تمام منابع نیست.</p>")
    if reasons:
        body=info+"<p class='warn'>حذف در شرایط فعلی متوقف است:</p><ul>"
        body+="".join("<li>"+_hd_html.escape(x)+"</li>" for x in reasons)+"</ul>"
    else:
        body=info+f"""
<form method="post" action="/users/{sid}/permanent-delete">
<input type="hidden" name="verification" value="{_hd_token(s)}">
<label>برای حذف غیرقابل‌بازگشت، دقیقاً <b>حذف {sid}</b> را بنویسید:</label>
<input name="confirm_text" type="text" placeholder="حذف {sid}" autocomplete="off" required>
<label><input type="checkbox" name="erase_finance" value="yes" required>
با حذف پرداخت‌ها و سوابق مالی اختصاصی این شناسه و تغییر جمع گزارش‌ها موافقم.</label>
<label><input type="checkbox" name="backup_confirmed" value="yes" required>
نسخهٔ پشتیبان معتبر دارم و تأیید می‌کنم این عملیات برگشت‌ناپذیر است.</label>
<button type="submit">حذف دائمی شناسه {sid} و سوابق اختصاصی</button>
</form>"""
    body+=f'<p><a href="/users/{sid}">بازگشت به پروفایل</a></p>'
    return _hd_page("حذف دائمی شناسه از دیتابیس مدیریت",body)


async def _hp2_execute(sid:int,request:_hp2_Request,
                       db:_hp2_Session=_hp2_Depends(get_db)):
    if not _hd_auth(request) or not _hd_valid_origin(request):
        return _hd_page("عدم دسترسی","<p>جلسه یا مبدأ درخواست نامعتبر است.</p>",403)
    data=await request.form()
    if (str(data.get("confirm_text") or "").strip() != "حذف "+str(sid) or
        data.get("erase_finance") != "yes" or
        data.get("backup_confirmed") != "yes"):
        return _hd_page("تأیید ناقص","<p>اطلاعات حذف تکمیل نشده است.</p>",409)
    try:
        db.execute(_hp2_text("SET LOCAL lock_timeout='3s'"))
        db.execute(_hp2_text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                   {"key":"hard-delete-subscription|"+str(sid)})
        s=db.query(Subscription).filter(Subscription.id==sid).with_for_update().one_or_none()
        if s is None or not _hd_valid_token(s,str(data.get("verification") or "")):
            db.rollback()
            return _hd_page("درخواست منقضی شده","<p>فرم را دوباره از پروفایل باز کنید.</p>",409)
        reasons,counts,event_ids=_hp2_plan(db,s)
        if reasons:
            db.rollback()
            return _hd_page("حذف متوقف شد",
                 "<p class='warn'>وابستگی جدید یا درخواست باز پیدا شد. هیچ ردیفی حذف نشد.</p>",409)

        # Only this subscription's rows. Gateway requests themselves and
        # phone-only tables MUST remain unchanged, especially shared phones.
        if counts["native_linked"]:
            db.execute(_hp2_text("""
              UPDATE native_sms_v2_jobs
              SET account_ids = array_remove(account_ids,:sid),
                  status = CASE
                    WHEN status='queued' AND cardinality(account_ids)=1
                    THEN 'cancelled' ELSE status END,
                  error = CASE
                    WHEN status='queued' AND cardinality(account_ids)=1
                    THEN 'Owner removed last linked subscription before dispatch'
                    ELSE error END,
                  updated_at=NOW()
              WHERE :sid = ANY(account_ids)
            """),{"sid":sid})

        if counts["ayria_payment_allocations"]:
            db.execute(_hp2_text(
                "DELETE FROM ayria_payment_allocations WHERE subscription_id=:sid"),
                {"sid":sid})
        if counts["payments"]:
            db.execute(_hp2_text(
                "DELETE FROM payments WHERE subscription_id=:sid"),
                {"sid":sid})
        if counts["billing_anchor"]:
            db.execute(_hp2_text(
                "DELETE FROM billing_anchor WHERE subscription_id=:sid"),
                {"sid":sid})
        if event_ids:
            db.query(AuditEvent).filter(AuditEvent.id.in_(event_ids)).delete(
                synchronize_session=False)
        db.delete(s)
        db.flush()
        left=_hd_simple_count(db,"subscriptions","id",sid)
        if left:
            raise RuntimeError("subscription still exists")
        db.commit()
    except Exception:
        db.rollback()
        return _hd_page("حذف انجام نشد",
               "<p class='warn'>تراکنش حذف برگشت خورد؛ داده‌ها تغییر نکردند. "
               "جزئیات خطا را در لاگ امن سرور بررسی کنید.</p>",409)
    return _hd_Redirect("/user-status?hard_deleted=1",status_code=303)


# Replace ONLY the two V1 /permanent-delete handlers; archive stays intact.
app.router.routes[:]=[
 r for r in app.router.routes
 if not (getattr(r,"path",None)=="/users/{sid}/permanent-delete" and
         bool(set(("GET","POST")) & set(getattr(r,"methods",set()) or set())))
]
app.add_api_route("/users/{sid}/permanent-delete",_hp2_preview,methods=["GET"])
app.add_api_route("/users/{sid}/permanent-delete",_hp2_execute,methods=["POST"])

_hp2_profile=TEMPLATES.get("user_detail.html","")
if "hd-erase-user" not in _hp2_profile:
    raise RuntimeError("V1 hard-delete profile link not installed")
_hp2_profile=_hp2_profile.replace(
  "اگر این اکانت سابقهٔ پرداخت، پیام یا وابستگی مشترک داشته باشد، حذف دائمی به‌صورت ایمن مسدود می‌شود.",
  "حذف فقط با شناسهٔ همین اکانت انجام می‌شود؛ پرداخت‌ها و سوابق اختصاصی آن پس از تأیید حذف و سوابق مشترک محافظت می‌شوند.")
_hp2_profile=_hp2_profile.replace(
  "بررسی حذف دائمی از سامانه","حذف دائمی این شناسه")
TEMPLATES["user_detail.html"]=_hp2_profile
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)
