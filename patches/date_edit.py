# Hesab VPN date editor: Jalali expiry correction with immediate debt recalculation.
from fastapi import Form

_JALALI_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]

def _g2j(gy, gm, gd):
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

def _j2g(jy, jm, jd):
    original = (jy, jm, jd)
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
    month_days = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    while gm <= 12 and gd > month_days[gm]:
        gd -= month_days[gm]
        gm += 1
    if gm > 12:
        raise ValueError("invalid Jalali date")
    result = (gy, gm, gd)
    if _g2j(*result) != original:
        raise ValueError("invalid Jalali date")
    return result

def _jparts(value):
    if not value:
        return (1405, 1, 1)
    return _g2j(value.year, value.month, value.day)

def _jalali_years_around(year):
    year = int(year)
    return list(range(year - 2, year + 6))

env.filters["jparts"] = _jparts
env.globals["jalali_months"] = _JALALI_MONTHS
env.globals["jalali_years_around"] = _jalali_years_around

_date_editor = r'''
<details class="expiry-editor">
  <summary>ویرایش تاریخ</summary>
  {% set jp = s.expiry_date|jparts %}
  <form method="post" action="/debts/{{ s.id }}/expiry" class="expiry-edit-form">
    <div class="expiry-picker-title">تقویم شمسی</div>
    <div class="expiry-picker">
      <select name="jd" aria-label="روز">
        {% for d in range(1, 32) %}
          <option value="{{ d }}" {% if d == jp[2] %}selected{% endif %}>{{ d|fa }}</option>
        {% endfor %}
      </select>
      <select name="jm" aria-label="ماه">
        {% for month_name in jalali_months %}
          <option value="{{ loop.index }}" {% if loop.index == jp[1] %}selected{% endif %}>{{ month_name }}</option>
        {% endfor %}
      </select>
      <select name="jy" aria-label="سال">
        {% for y in jalali_years_around(jp[0]) %}
          <option value="{{ y }}" {% if y == jp[0] %}selected{% endif %}>{{ y|fa }}</option>
        {% endfor %}
      </select>
    </div>
    <small>با ذخیره تاریخ، بدهی همین اکانت فوراً دوباره محاسبه می‌شود.</small>
    <button type="submit">ذخیره تاریخ</button>
  </form>
</details>
'''

_date_anchor = '<span class="debt-expiry">انقضا: <b>{{ s.expiry_date|jdate }}</b></span>'
if _date_anchor in TEMPLATES.get("debts.html", ""):
    TEMPLATES["debts.html"] = TEMPLATES["debts.html"].replace(
        _date_anchor, _date_anchor + _date_editor
    )

_banner_anchor = '{% if adjust_error %}<div class="collect-error">مبلغ اصلاحی باید صفر یا مضربی از تعرفه ماهانه باشد و از بدهی محاسبه‌شده بیشتر نباشد.</div>{% endif %}'
_banner_extra = r'''
{% if request.query_params.get("date_updated") %}<div class="collect-success">✓ تاریخ اکانت اصلاح شد و بدهی دوباره محاسبه شد.</div>{% endif %}
{% if request.query_params.get("date_error") %}<div class="collect-error">تاریخ واردشده معتبر نیست.</div>{% endif %}
'''
if _banner_anchor in TEMPLATES.get("debts.html", ""):
    TEMPLATES["debts.html"] = TEMPLATES["debts.html"].replace(
        _banner_anchor, _banner_anchor + _banner_extra
    )

_inline_style = r'''
<style>
.expiry-editor{margin-top:7px;width:max-content;max-width:100%;border:1px solid rgba(255,255,255,.10);border-radius:10px;background:rgba(255,255,255,.025);overflow:hidden}
.expiry-editor summary{list-style:none;cursor:pointer;padding:6px 10px;font-size:11px;color:#b8c0ce;user-select:none}
.expiry-editor summary::-webkit-details-marker{display:none}
.expiry-editor[open] summary{color:#fff;border-bottom:1px solid rgba(255,255,255,.07)}
.expiry-edit-form{padding:10px;min-width:310px;max-width:100%;display:flex;flex-direction:column;gap:8px}
.expiry-picker-title{font-size:11px;color:#8f9bad}
.expiry-picker{display:grid;grid-template-columns:72px 1fr 88px;gap:7px;direction:rtl}
.expiry-picker select{height:38px;background:#0d1421;color:#f3f5f8;border:1px solid rgba(255,255,255,.13);border-radius:9px;padding:0 8px;font:inherit;font-size:12px;outline:none}
.expiry-edit-form small{font-size:10px;color:#7f8a9b;line-height:1.55}
.expiry-edit-form button{height:36px;border:0;border-radius:9px;background:#eef1f5;color:#141922;font:inherit;font-size:12px;font-weight:800;cursor:pointer}
.expiry-edit-form button:hover{background:#fff}
@media(max-width:640px){.expiry-edit-form{min-width:0;width:100%}.expiry-picker{grid-template-columns:66px 1fr 82px}}
</style>
'''
TEMPLATES["debts.html"] = TEMPLATES["debts.html"].replace(
    "{% block content %}", "{% block content %}" + _inline_style, 1
)

if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)

def update_expiry_date(sid: int, jy: int = Form(...), jm: int = Form(...), jd: int = Form(...), db: Session = Depends(get_db)):
    s = db.get(Subscription, sid)
    if not s:
        return RedirectResponse("/debts?date_error=1", 303)
    try:
        jy, jm, jd = int(jy), int(jm), int(jd)
        if jy < 1300 or jy > 1500 or jm < 1 or jm > 12 or jd < 1 or jd > 31:
            raise ValueError("out of range")
        gy, gm, gd = _j2g(jy, jm, jd)
        new_expiry = date(gy, gm, gd)
    except Exception:
        return RedirectResponse("/debts?date_error=1", 303)

    previous_expiry = s.expiry_date
    previous_debt = int(s.debt_toman or 0)
    s.expiry_date = new_expiry

    recalculated = 0 if s.is_free else current_debt_for(s, today_local())
    s.debt_toman = recalculated
    s.payment_status = "unpaid" if recalculated > 0 else "paid"
    s.billing_cursor_date = today_local()

    db.add(AuditEvent(
        kind="expiry_edit",
        message=(
            f"Expiry manually changed for {s.display_name}: "
            f"{previous_expiry} -> {new_expiry}; debt {previous_debt} -> {recalculated}"
        ),
    ))
    db.commit()
    return RedirectResponse("/debts?date_updated=1", 303)

app.add_api_route("/debts/{sid}/expiry", update_expiry_date, methods=["POST"])
app.add_api_route("/users/{sid}/expiry", update_expiry_date, methods=["POST"])
