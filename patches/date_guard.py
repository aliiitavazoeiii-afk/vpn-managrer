# Canonical Jalali date guard.
# Loaded last so every billing/date route uses one tested conversion/arithmetic implementation.
from datetime import date as _date_cls, datetime as _datetime_cls
import re as _date_re

_DATE_GUARD_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]
_DATE_GUARD_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_DATE_GUARD_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _date_guard_g2j(gy, gm, gd):
    gy, gm, gd = int(gy), int(gm), int(gd)
    gdm = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        - 80
        + gd
        + gdm[gm - 1]
    )
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def _date_guard_j2g(jy, jm, jd):
    jy, jm, jd = int(jy), int(jm), int(jd)
    original = (jy, jm, jd)
    if not (1 <= jm <= 12 and 1 <= jd <= 31):
        raise ValueError("invalid Jalali date")
    if jy > 979:
        gy = 1600
        jy -= 979
    else:
        gy = 621
    days = 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + 78 + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += (jm - 7) * 30 + 186
    gy += 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        gy += 100 * ((days - 1) // 36524)
        days = (days - 1) % 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = gy % 4 == 0 and (gy % 100 != 0 or gy % 400 == 0)
    mdays = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    while gm <= 12 and gd > mdays[gm]:
        gd -= mdays[gm]
        gm += 1
    if gm > 12:
        raise ValueError("invalid Jalali date")
    result = (gy, gm, gd)
    if _date_guard_g2j(*result) != original:
        raise ValueError("invalid Jalali date")
    return result


def _date_guard_month_length(jy, jm):
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    try:
        _date_guard_j2g(jy, 12, 30)
        return 30
    except Exception:
        return 29


def _date_guard_add_months(value, months):
    if value is None:
        return None
    if isinstance(value, _datetime_cls):
        value = value.date()
    jy, jm, jd = _date_guard_g2j(value.year, value.month, value.day)
    absolute = jy * 12 + (jm - 1) + int(months)
    new_jy, new_zero_month = divmod(absolute, 12)
    new_jm = new_zero_month + 1
    new_jd = min(jd, _date_guard_month_length(new_jy, new_jm))
    gy, gm, gd = _date_guard_j2g(new_jy, new_jm, new_jd)
    return _date_cls(gy, gm, gd)


def _date_guard_add_one_month(value):
    return _date_guard_add_months(value, 1)


def _date_guard_parse(value):
    if isinstance(value, _datetime_cls):
        return value.date()
    if isinstance(value, _date_cls):
        return value
    raw = str(value or "").translate(_DATE_GUARD_DIGITS).strip()
    parts = [p for p in _date_re.split(r"[^0-9]+", raw) if p]
    if len(parts) != 3:
        raise ValueError("invalid Jalali date")
    jy, jm, jd = map(int, parts)
    if not (1300 <= jy <= 1500):
        raise ValueError("invalid Jalali year")
    gy, gm, gd = _date_guard_j2g(jy, jm, jd)
    return _date_cls(gy, gm, gd)


def _date_guard_jparts(value):
    if not value:
        return None
    if isinstance(value, _datetime_cls):
        value = value.date()
    return _date_guard_g2j(value.year, value.month, value.day)


def _date_guard_jdate(value):
    if not value:
        return "—"
    try:
        jy, jm, jd = _date_guard_jparts(value)
        try:
            _today = today_local()
        except Exception:
            _today = _date_cls.today()
        current_jy = _date_guard_g2j(_today.year, _today.month, _today.day)[0]
        day_fa = str(jd).translate(_DATE_GUARD_FA)
        text = f"{day_fa} {_DATE_GUARD_MONTHS[jm - 1]}"
        if jy != current_jy:
            text += " " + str(jy).translate(_DATE_GUARD_FA)
        return text
    except Exception:
        return str(value)


def _date_guard_jinput(value):
    if not value:
        return ""
    jy, jm, jd = _date_guard_jparts(value)
    return f"{jy:04d}/{jm:02d}/{jd:02d}"


# Hard self-test for the exact month boundary that previously regressed.
assert _date_guard_j2g(1405, 5, 9) == (2026, 7, 31)
assert _date_guard_g2j(2026, 7, 31) == (1405, 5, 9)
assert _date_guard_add_one_month(_date_cls(2026, 7, 31)) == _date_cls(2026, 8, 31)

# Replace all date primitives used by billing/profile/edit routes.
_g2j = _date_guard_g2j
_j2g = _date_guard_j2g
gregorian_to_jalali = _date_guard_g2j
parse_jalali_date = _date_guard_parse
add_jalali_months = _date_guard_add_months
add_one_jalali_month = _date_guard_add_one_month
jdate = _date_guard_jdate
jinput = _date_guard_jinput

# Keep Jinja display/editing on the same canonical implementation.
env.filters["jdate"] = _date_guard_jdate
env.filters["jinput"] = _date_guard_jinput
env.filters["jparts"] = _date_guard_jparts
env.globals["jalali_months"] = _DATE_GUARD_MONTHS

# Refresh template mapping in case an earlier patch cached filters/templates.
if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)
