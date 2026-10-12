# SMS_DEBT_DEFAULT_ABAN_V1
# Installed after SMS + first-day billing patches. Only overrides default
# reminder template and its send route; other SMS and payment routes unchanged.
import re as _aban_re

_ABAN_SMS_PATTERN = (
    "⏳اکانت شما {expiry} تمام شده\n\n"
    "برای تمدید وارد پنل کاربری خودتون بشید به نشانی زیر\n\n"
    "usersmanager.ir\n\n"
    "ازین پس پرداخت فقط از طریق پنل کاربری انجام میشه و نیاز به ارسال لینک پرداخت نیست\n\n"
    "📱با شماره همراه خودتون وارد بشید.\n\n"
    "🗓️تمامی اکانت ها تا تاریخ ۱ آبان محاسبه شدن لذا سر رسید جدید تمامی اکانت ها یکم هر ماه هست"
)

# Single account expiry date for an entire phone group: oldest actual due
# account (the one for which we first started collection). No account names.
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

_aban_previous_sms_sender = sms_debt_send


def _aban_debt_send(
    phone: str = _SmsForm(...),
    cycle: str = _SmsForm(""),
    message: str = _SmsForm(""),
    db: _SmsSession = _SmsDepends(get_db),
):
    normalized = _sms_normalize_phone(phone)
    if not normalized:
        return _SmsRedirectResponse("/debts?sms_error=phone", 303)

    _aban_states = _followup_states(db)
    _aban_items = (
        db.query(Subscription)
        .filter(
            Subscription.phone == normalized,
            Subscription.is_free.is_(False),
        )
        .all()
    )
    _aban_eligible = [
        s for s in _aban_items
        if s.expiry_date
        and s.expiry_date <= today_local()
        and current_debt_for(s, today_local()) > 0
        and _aban_states.get(s.id) not in ("waiting", "cut")
    ]
    if not _aban_eligible:
        return _SmsRedirectResponse("/debts?sms_error=not_actionable", 303)

    earliest = min(s.expiry_date for s in _aban_eligible)
    canonical_message = _ABAN_SMS_PATTERN.format(expiry=jdate(earliest))
    if len(canonical_message) > 1000:
        raise RuntimeError("Canonical debt reminder too long")

    # Reuse the existing SMS job creation and followup transition logic.
    return _aban_previous_sms_sender(
        phone=normalized, cycle=cycle, message=canonical_message, db=db
    )


app.router.routes[:] = [
    r for r in app.router.routes
    if not (getattr(r, "path", None) == "/sms/debt-send"
            and "POST" in (getattr(r, "methods", set()) or set()))
]
app.add_api_route("/sms/debt-send", _aban_debt_send, methods=["POST"])
