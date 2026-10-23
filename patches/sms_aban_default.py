# SMS_DEBT_DEFAULT_ABAN_V1
# Installed after SMS + first-day billing patches. Only overrides default
# reminder template and its send route; other SMS and payment routes unchanged.
import re as _aban_re

# Operator-authorized, one-time SMS exception for three historic cases
# where Ayria payment links were canceled but the subscriptions remain due.
# Never sends automatically; never alters an Ayria payment or billing record.
_ABAN_MANUAL_ONCE_PHONES = frozenset({
    "09120758984",
    "09126260485",
    "09129743094",
})
_ABAN_MANUAL_ONCE_SUFFIX = ":manual-exception-aban1"

_ABAN_SMS_PATTERN = (
    "سلام امروز موعد تمدید اکانت شماست\n"
    "لطفا برای تمدید وارد پنل کاربری خودتون بشید و نسبت به پرداخت اقدام فرمایید\n"
    "\n"
    " ساعت 10 شب اکانت هایی که پرداخت نداشتن مسدود خواهند شد و تا فردا همچنان امکان پرداخت هست.فردا ساعت 12 ظهر اکانت های پرداخت نشده حذف خواهند شد.\n"
    "\n"
    "فعال یا غیرفعال شدن اکانت ها سیستمی بوده و امکان فعال سازی اکانت بدون واریز ممکن نیست"
)

# The canonical debt reminder is operator-authored and deliberately has no
# dynamic expiry placeholder. Other finance/SMS rules remain unchanged.
_aban_tpl = TEMPLATES.get("debts.html", "")
if not _aban_tpl:
    raise RuntimeError("Debt SMS template unavailable")
_aban_textarea = _aban_re.compile(
    r'(<textarea\s+id="debt-message-\{\{ loop\.index0 \}\}"[^>]*>).*?(</textarea>)',
    flags=_aban_re.S,
)
_aban_display_text = _ABAN_SMS_PATTERN.replace("{expiry}", "{{ g.first_expiry|jdate }}")
_aban_tpl, _aban_count = _aban_textarea.subn(
    lambda m: m.group(1) + _aban_display_text + m.group(2),
    _aban_tpl,
)
if _aban_count != 1:
    raise RuntimeError(f"Expected one debt reminder textarea, found {_aban_count}")
TEMPLATES["debts.html"] = _aban_tpl
if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)

# Distinguish gateway acknowledgement from an operator-confirmed recipient report.
# This status is terminal for the retry button; it is NOT a gateway delivery receipt.
_SMS_STATUS_LABELS["operator_confirmed"] = "ارسال طبق تأیید شما (بدون تکرار)"

_ab_sms_history = TEMPLATES.get("sms.html", "")
if _ab_sms_history:
    _ab_sms_history = _ab_sms_history.replace(
        "{% if j.error %}<small class=\"sms-error\">{{ j.error }}</small>{% endif %}",
        "{% if j.error and j.status != 'operator_confirmed' %}<small class=\"sms-error\">{{ j.error }}</small>{% endif %}",
    )
    # Debt reminders can have a false-negative Android result=0 while the
    # recipient still receives the SMS. Never offer one-click retry for these.
    _ab_sms_history = _ab_sms_history.replace(
        "{% if j.status == 'failed' %}",
        "{% if j.status == 'failed' and 'usersmanager.ir' not in j.message and 'moshtarakin.filmjadiid.ir' not in j.message %}",
        1,
    )
    TEMPLATES["sms.html"] = _ab_sms_history

_ab_sms_debt_template = TEMPLATES["debts.html"]
_ab_sms_debt_template = _ab_sms_debt_template.replace(
    "status==='sent' || status==='delivered'",
    "status==='sent' || status==='delivered' || status==='operator_confirmed'",
)
_ab_sms_debt_template = _ab_sms_debt_template.replace(
    "{% block content %}",
    "{% block content %}"
    "{% if request.query_params.get('sms_existing') %}"
    '<div class="manage-banner">برای این شماره و سررسید قبلاً پیامک ثبت شده است؛ '
    'برای جلوگیری از ارسال تکراری، پیامک جدیدی ساخته نشد.</div>'
    "{% endif %}",
    1,
)
TEMPLATES["debts.html"] = _ab_sms_debt_template
if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)


def _aban_debt_send(
    phone: str = _SmsForm(...),
    cycle: str = _SmsForm(""),
    message: str = _SmsForm(""),
    db: _SmsSession = _SmsDepends(get_db),
):
    """One canonical SMS per phone and actual due cycle; transfer due accounts atomically."""
    normalized = _sms_normalize_phone(phone)
    if not normalized:
        return _SmsRedirectResponse("/debts?sms_error=phone", 303)
    if not callable(globals().get("_followup_set")):
        raise RuntimeError("Followup state writer unavailable; refusing to queue SMS")

    # Serialize concurrent submit clicks for the same phone. Prevent double queue
    # even when both POSTs arrive within the same millisecond.
    db.execute(
        _sms_text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": "debt-sms|" + normalized},
    )
    now = today_local()
    states = _followup_states(db)
    candidates = (
        db.query(Subscription)
        .filter(
            Subscription.phone == normalized,
            Subscription.is_free.is_(False),
        ).order_by(Subscription.id.asc()).all()
    )
    eligible = [
        s for s in candidates
        if s.expiry_date is not None
        and s.expiry_date <= now
        and current_debt_for(s, now) > 0
        and states.get(s.id) not in ("waiting", "cut")
    ]
    if not eligible:
        return _SmsRedirectResponse("/debts?sms_error=not_actionable", 303)

    earliest = min(s.expiry_date for s in eligible)
    source = _sms_debt_source(earliest.isoformat())  # never trust submitted cycle
    previous = db.execute(
        _sms_text(
            """
            SELECT id, status FROM sms_jobs
            WHERE phone=:phone AND source LIKE 'debt:%'
              AND status <> 'cancelled'
              AND (source=:source OR created_at >= :current_jalali_month_start)
            ORDER BY id DESC LIMIT 1
            """
        ),
        {
            "phone": normalized,
            "source": source,
            "current_jalali_month_start": _b_month_start(now),
        },
    ).mappings().first()
    if previous and previous["status"] == "failed":
        # Owner-authorized one-time manual resend for prior failed SMS only.
        # Preserve the old failed job and its evidence; create a NEW job.
        # A distinct source prevents repeated sends of this exception.
        retry_source = source + ":manual-resend-20261013"
        used = db.execute(
            _sms_text("""
                SELECT id FROM sms_jobs
                WHERE phone=:phone AND source=:retry_source
                LIMIT 1
            """),
            {"phone": normalized, "retry_source": retry_source},
        ).first()
        if used:
            return _SmsRedirectResponse("/debts?sms_existing=1", 303)
        source = retry_source
        previous = None
    if previous:
        # One explicit operator-authorized follow-up for these three phones.
        # Prior canceled AYRIA payment requests and prior SMS delivery results
        # are unrelated; we do NOT treat canceled checkout as failed SMS.
        # We also never restart a failed old job: only a fresh manual click
        # may queue one new canonical reminder for an actually due account.
        if normalized not in _ABAN_MANUAL_ONCE_PHONES:
            return _SmsRedirectResponse("/debts?sms_existing=1", 303)

        exception_source = source + _ABAN_MANUAL_ONCE_SUFFIX
        already_used = db.execute(
            _sms_text(
                """
                SELECT id FROM sms_jobs
                WHERE phone=:phone AND source=:exception_source
                LIMIT 1
                """
            ),
            {"phone": normalized, "exception_source": exception_source},
        ).first()
        if already_used:
            return _SmsRedirectResponse("/debts?sms_existing=1", 303)
        source = exception_source

    body = _ABAN_SMS_PATTERN.format(expiry=jdate(earliest))
    if not body or len(body) > 1000:
        raise RuntimeError("Canonical reminder length invalid")

    inserted = db.execute(
        _sms_text(
            """
            INSERT INTO sms_jobs(phone,message,status,source)
            VALUES(:phone,:message,'queued',:source)
            RETURNING id
            """
        ),
        {"phone": normalized, "message": body, "source": source},
    ).scalar_one()

    db.add(AuditEvent(
        kind="sms_queue",
        message=(
            f"Debt SMS queued; job={int(inserted)}; phone={normalized}; "
            f"source={source}; accounts={','.join(str(s.id) for s in eligible)}"
        ),
    ))
    for account in eligible:
        _followup_set(
            db, account.id, "waiting",
            f"SMS reminder queued; phone={normalized}; job={int(inserted)}; source={source}",
        )
    db.commit()
    return _SmsRedirectResponse(
        f"/debts?sms_queued=1&tracked=1&moved={len(eligible)}&job={int(inserted)}",
        303,
    )


app.router.routes[:] = [
    r for r in app.router.routes
    if not (getattr(r, "path", None) == "/sms/debt-send"
            and "POST" in (getattr(r, "methods", set()) or set()))
]
app.add_api_route("/sms/debt-send", _aban_debt_send, methods=["POST"])


# Fail closed for ALL legacy/new debt reminders, even if the generic SMS
# dashboard is used to click "Retry". The operator must verify the handset and
# recipient first; debt reminders are not safe to automatically resend.
_aban_original_retry = sms_retry


def _aban_guarded_retry(job_id: int, db: _SmsSession = _SmsDepends(get_db)):
    row = db.execute(
        _sms_text("SELECT source FROM sms_jobs WHERE id=:id"),
        {"id": int(job_id)},
    ).mappings().first()
    if row and str(row["source"] or "").startswith("debt:"):
        return _SmsRedirectResponse("/sms?error=debt_retry_blocked", 303)
    return _aban_original_retry(job_id, db)


app.router.routes[:] = [
    r for r in app.router.routes
    if not (getattr(r, "path", None) == "/sms/{job_id}/retry"
            and "POST" in (getattr(r, "methods", set()) or set()))
]
app.add_api_route("/sms/{job_id}/retry", _aban_guarded_retry, methods=["POST"])
