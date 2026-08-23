from datetime import date, datetime
from zoneinfo import ZoneInfo
from .config import settings

TZ = ZoneInfo(settings.timezone)

_BREAKS = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178]

def _div(a, b): return int(a / b)
def _mod(a, b): return a - int(a / b) * b

def _jal_cal(jy):
    bl = len(_BREAKS); gy = jy + 621; leap_j = -14; jp = _BREAKS[0]
    if jy < jp or jy >= _BREAKS[-1]: raise ValueError("سال شمسی خارج از محدوده")
    jump = 0
    for i in range(1, bl):
        jm = _BREAKS[i]; jump = jm - jp
        if jy < jm: break
        leap_j += _div(jump, 33) * 8 + _div(_mod(jump, 33), 4); jp = jm
    n = jy - jp
    leap_j += _div(n, 33) * 8 + _div(_mod(n, 33) + 3, 4)
    if _mod(jump, 33) == 4 and jump - n == 4: leap_j += 1
    leap_g = _div(gy, 4) - _div((_div(gy, 100) + 1) * 3, 4) - 150
    march = 20 + leap_j - leap_g
    if jump - n < 6: n = n - jump + _div(jump + 4, 33) * 33
    leap = _mod(_mod(n + 1, 33) - 1, 4)
    if leap == -1: leap = 4
    return leap, gy, march

def _g2d(gy, gm, gd):
    d = _div((gy + _div(gm - 8, 6) + 100100) * 1461, 4) + _div(153 * _mod(gm + 9, 12) + 2, 5) + gd - 34840408
    d = d - _div(_div(gy + 100100 + _div(gm - 8, 6), 100) * 3, 4) + 752
    return d

def _d2g(jdn):
    j = 4 * jdn + 139361631
    j = j + _div(_div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908
    i = _div(_mod(j, 1461), 4) * 5 + 308
    gd = _div(_mod(i, 153), 5) + 1
    gm = _mod(_div(i, 153), 12) + 1
    gy = _div(j, 1461) - 100100 + _div(8 - gm, 6)
    return gy, gm, gd

def _j2d(jy, jm, jd):
    _, gy, march = _jal_cal(jy)
    return _g2d(gy, 3, march) + (jm - 1) * 31 - _div(jm, 7) * (jm - 7) + jd - 1

def _d2j(jdn):
    gy, _, _ = _d2g(jdn); jy = gy - 621; leap, gy2, march = _jal_cal(jy)
    jdn1f = _g2d(gy2, 3, march); k = jdn - jdn1f
    if k >= 0:
        if k <= 185: return jy, 1 + _div(k, 31), _mod(k, 31) + 1
        k -= 186
    else:
        jy -= 1; k += 179
        if leap == 1: k += 1
    return jy, 7 + _div(k, 30), _mod(k, 30) + 1

def gregorian_to_jalali(d: date): return _d2j(_g2d(d.year, d.month, d.day))
def jalali_to_gregorian(jy: int, jm: int, jd: int) -> date:
    gy, gm, gd = _d2g(_j2d(jy, jm, jd)); return date(gy, gm, gd)
def is_leap_jalali(jy: int) -> bool:
    leap, _, _ = _jal_cal(jy); return leap == 0

def now_local() -> datetime: return datetime.now(TZ)
def today_local() -> date: return now_local().date()
def fa_digits(value) -> str: return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))

def jalali_date(value: date | datetime | None) -> str:
    if not value: return "—"
    if isinstance(value, datetime): value = value.date()
    y,m,d = gregorian_to_jalali(value); return fa_digits(f"{y:04d}/{m:02d}/{d:02d}")

def jalali_datetime(value: datetime | None) -> str:
    if not value: return "—"
    if value.tzinfo is None: value = value.replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
    y,m,d = gregorian_to_jalali(value.date()); return fa_digits(f"{y:04d}/{m:02d}/{d:02d} {value.hour:02d}:{value.minute:02d}")

def parse_jalali_date(text: str | None) -> date | None:
    if not text: return None
    normalized = str(text).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")).replace("-", "/").strip()
    parts = normalized.split("/")
    if len(parts) != 3: raise ValueError("تاریخ باید به شکل 1405/06/01 باشد")
    y,m,d = [int(x) for x in parts]
    if m < 1 or m > 12: raise ValueError("ماه شمسی نامعتبر است")
    max_day = 31 if m <= 6 else (30 if m <= 11 else (30 if is_leap_jalali(y) else 29))
    if d < 1 or d > max_day: raise ValueError("روز شمسی نامعتبر است")
    return jalali_to_gregorian(y,m,d)

def add_one_jalali_month(gregorian_date: date | None) -> date:
    base = gregorian_date or today_local(); y,m,d = gregorian_to_jalali(base); m += 1
    if m == 13: m=1; y+=1
    max_day = 31 if m <= 6 else (30 if m <= 11 else (30 if is_leap_jalali(y) else 29))
    return jalali_to_gregorian(y,m,min(d,max_day))

def money(value: int | float | None) -> str: return fa_digits(f"{int(value or 0):,}")
def bytes_human(n: int | float | None) -> str:
    n=float(n or 0); units=["B","KB","MB","GB","TB","PB"]
    for unit in units:
        if abs(n)<1024 or unit==units[-1]: return f"{n:.1f} {unit}" if unit!="B" else f"{int(n)} B"
        n/=1024

def percent(current,total): return round((float(current or 0)/float(total or 1))*100,1)
def due_meta(user) -> dict:
    today=today_local()
    if user.payment_status=="paid": return {"key":"paid","label":"پرداخت شده","class":"success","days":0}
    if not user.due_date: return {"key":"unknown","label":"بدون تاریخ","class":"muted","days":0}
    delta=(user.due_date-today).days
    if delta<0: return {"key":"overdue","label":f"{abs(delta)} روز گذشته","class":"danger","days":delta}
    if delta==0: return {"key":"today","label":"امروز","class":"warning","days":0}
    if delta<=3: return {"key":"soon","label":f"{delta} روز دیگر","class":"warning","days":delta}
    return {"key":"active","label":f"{delta} روز دیگر","class":"info","days":delta}
