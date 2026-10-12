# PORTAL_LOGIN_REPORT_ADMIN_V1
# Read-only customer portal login report for authenticated admin.
# Source table is recorded by customer_portal/login_activity.py.
from datetime import datetime as _pla_datetime, timedelta as _pla_timedelta
from zoneinfo import ZoneInfo as _pla_ZoneInfo
from fastapi import Request as _pla_Request, Depends as _pla_Depends
from sqlalchemy import text as _pla_text
from sqlalchemy.orm import Session as _pla_Session

_PLA_TZ = _pla_ZoneInfo("Asia/Tehran")


def _pla_when(value):
    if value is None:
        return "—"
    # SQL TIMESTAMPTZ normally arrives aware. Handle naive UTC defensively.
    from datetime import timezone as _tz
    if value.tzinfo is None:
        value = value.replace(tzinfo=_tz.utc)
    local = value.astimezone(_PLA_TZ)
    if "_g2j" in globals():
        jy, jm, jd = _g2j(local.year, local.month, local.day)
        return f"{jy:04d}/{jm:02d}/{jd:02d} · {local:%H:%M}"
    return local.strftime("%Y-%m-%d · %H:%M")


_PLA_ADMIN_TEMPLATE = r'''{% extends "base.html" %}
{% block title %}ورودهای پنل مشتریان · حساب VPN{% endblock %}
{% block heading %}ورودهای پنل مشتریان{% endblock %}
{% block subheading %}سوابق ثبت‌شده در usersmanager.ir از زمان فعال‌سازی این گزارش{% endblock %}
{% block content %}
<style>
.pla-root{display:flex;flex-direction:column;gap:18px}
.pla-notice{border:1px solid rgba(125,156,202,.20);border-radius:12px;
 padding:13px 16px;line-height:2;color:#a6b8d0;
 background:linear-gradient(115deg,rgba(27,48,77,.46),rgba(16,24,36,.5));font-size:12px}
.pla-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.pla-kpi{padding:18px;border-radius:16px;border:1px solid rgba(255,255,255,.08);
 background:linear-gradient(148deg,rgba(22,34,51,.94),rgba(13,20,32,.96))}
.pla-kpi span{display:block;font-size:11px;color:#9aaec8;margin-bottom:8px}
.pla-kpi strong{font-weight:850;font-size:27px;letter-spacing:-.03em;color:#f1f7ff}
.pla-kpi small{display:block;font-size:10px;color:#6f879f;margin-top:6px}
.pla-panel{background:linear-gradient(145deg,rgba(15,23,38,.98),rgba(10,16,26,.98));
 border:1px solid rgba(255,255,255,.08);border-radius:18px;overflow:hidden}
.pla-panel header{display:flex;justify-content:space-between;align-items:center;
 gap:12px;padding:19px 19px 16px;border-bottom:1px solid rgba(255,255,255,.07);flex-wrap:wrap}
.pla-panel h2{font-size:15px;font-weight:850;color:#eef4ff;margin:0}
.pla-panel header small{font-size:10px;color:#8093aa}
.pla-search{display:flex;gap:9px;flex-wrap:wrap}
.pla-search input,.pla-search select{background:#0c1422;border:1px solid rgba(137,163,199,.23);
 color:#eaf0fa;padding:9px 13px;border-radius:10px;font:inherit;font-size:12px;min-width:160px}
.pla-search input{width:min(270px,100%)}.pla-search button{border:0;background:#dbe8fb;
 color:#17243a;border-radius:10px;padding:9px 18px;cursor:pointer;font-weight:850;font:inherit;font-size:12px}
.pla-tablewrap{overflow-x:auto}
.pla-table{border-collapse:collapse;width:100%;min-width:685px;text-align:right}
.pla-table th{font-size:10px;font-weight:700;color:#7e92ae;background:rgba(255,255,255,.018)}
.pla-table th,.pla-table td{border-bottom:1px solid rgba(255,255,255,.055);padding:13px 16px}
.pla-table td{font-size:12px;color:#b6c6d9}.pla-table tr:last-child td{border-bottom:0}
.pla-name{color:#edf4ff;font-weight:750}.pla-number{direction:ltr;unicode-bidi:isolate;
 display:inline-block;font-family:Tahoma,Arial,sans-serif;letter-spacing:.025em;color:#b5d4ff}
.pla-ip{direction:ltr;unicode-bidi:isolate;display:inline-block;color:#8098b4;font-size:11px}
.pla-pill{border-radius:99px;padding:4px 9px;display:inline-block;font-size:10px}
.pla-pill.success{background:rgba(44,176,115,.12);color:#8ee9b6}
.pla-pill.failed{background:rgba(239,93,102,.11);color:#f4b0b8}
.pla-empty{padding:40px 18px;color:#8294ac;text-align:center;font-size:12px}
@media(max-width:950px){.pla-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:540px){.pla-kpis{grid-template-columns:1fr 1fr;gap:8px}
 .pla-kpi{padding:12px}.pla-kpi strong{font-size:21px}
 .pla-panel header{padding:14px}.pla-search input{width:100%}}
</style>
<div class="pla-root">
  <div class="pla-notice">این گزارش از زمان نصب فعال است و ورودهای گذشته را بازسازی نمی‌کند.
    در شیوه ورود فعلی، «موفق» یعنی شماره ثبت‌شده وارد شده؛ مالکیت سیم‌کارت تأیید نشده است.
    IP ممکن است به‌دلیل VPN یا پروکسی با موقعیت واقعی متفاوت باشد.</div>
  <section class="pla-kpis">
    <div class="pla-kpi"><span>شماره‌های واردشده امروز</span>
      <strong>{{ metrics.today_unique|fa }}</strong><small>شماره یکتا · ورود موفق</small></div>
    <div class="pla-kpi"><span>شماره‌های ۷ روز اخیر</span>
      <strong>{{ metrics.week_unique|fa }}</strong><small>شماره یکتا · ورود موفق</small></div>
    <div class="pla-kpi"><span>مجموع شماره‌های ثبت‌شده</span>
      <strong>{{ metrics.all_unique|fa }}</strong><small>از زمان راه‌اندازی گزارش</small></div>
    <div class="pla-kpi"><span>تلاش‌های ناموفق امروز</span>
      <strong>{{ metrics.today_failed|fa }}</strong><small>شماره نامعتبر یا ثبت‌نشده</small></div>
  </section>
  <section class="pla-panel">
    <header>
      <div><h2>آخرین ورود هر شماره</h2>
       <small>حداکثر ۲۰۰ شماره؛ جست‌وجو در کل سوابق</small></div>
      <form method="get" action="/portal-logins" class="pla-search">
        <input name="q" type="search" value="{{ query }}" placeholder="جست‌وجو نام یا شماره…" autocomplete="off">
        <button type="submit">جست‌وجو</button>
      </form>
    </header>
    <div class="pla-tablewrap">
      <table class="pla-table">
        <thead><tr><th>نام مشتری / اکانت</th><th>شماره همراه</th>
          <th>آخرین ورود (تهران)</th><th>دفعات ورود</th><th>آخرین IP ثبت‌شده</th></tr></thead>
        <tbody>
          {% for row in phones %}
          <tr><td><span class="pla-name">{{ row.display_name or 'بدون نام ثبت‌شده' }}</span></td>
            <td><span class="pla-number">{{ row.phone }}</span></td>
            <td>{{ row.last_text }}</td><td>{{ row.entries|fa }}</td>
            <td><span class="pla-ip">{{ row.ip_address or '—' }}</span></td></tr>
          {% else %}
          <tr><td colspan="5"><div class="pla-empty">
          {% if query %}موردی برای این جست‌وجو پیدا نشد.{% else %}هنوز ورود موفقی ثبت نشده است.{% endif %}
          </div></td></tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </section>
  <section class="pla-panel">
    <header><div><h2>رویدادهای اخیر ورود</h2><small>۱۰۰ رویداد آخر؛ شامل تلاش‌های ناموفق</small></div>
    <form class="pla-search" method="get" action="/portal-logins">
      <input type="hidden" name="q" value="{{ query }}">
      <select name="status">
        <option value="all" {{ 'selected' if status=='all' else '' }}>همه وضعیت‌ها</option>
        <option value="success" {{ 'selected' if status=='success' else '' }}>موفق</option>
        <option value="not_found" {{ 'selected' if status=='not_found' else '' }}>شماره ثبت‌نشده</option>
        <option value="invalid" {{ 'selected' if status=='invalid' else '' }}>نامعتبر</option>
      </select><button type="submit">فیلتر</button>
    </form></header>
    <div class="pla-tablewrap">
      <table class="pla-table">
        <thead><tr><th>زمان (تهران)</th><th>شماره واردشده</th><th>نام مشتری</th><th>نتیجه</th><th>IP</th></tr></thead>
        <tbody>
          {% for row in events %}
          <tr><td>{{ row.when_text }}</td><td><span class="pla-number">{{ row.phone or '—' }}</span></td>
            <td>{{ row.display_name or '—' }}</td>
            <td><span class="pla-pill {{ 'success' if row.result=='success' else 'failed' }}">
              {{ 'موفق' if row.result=='success' else ('شماره ثبت‌نشده' if row.result=='not_found' else 'شماره نامعتبر') }}
            </span></td>
            <td><span class="pla-ip">{{ row.ip_address or '—' }}</span></td></tr>
          {% else %}
          <tr><td colspan="5"><div class="pla-empty">هنوز رویدادی ثبت نشده است.</div></td></tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </section>
</div>
{% endblock %}'''

if "portal_logins.html" in TEMPLATES:
    raise RuntimeError("Duplicate customer-login admin report patch")
TEMPLATES["portal_logins.html"] = _PLA_ADMIN_TEMPLATE

_pla_base = TEMPLATES.get("base.html", "")
if not _pla_base or _pla_base.count("</nav>") != 1:
    raise RuntimeError("Missing admin navigation slot")
_pla_nav = '''<a href="/portal-logins" class="{{ 'active' if request.url.path.startswith('/portal-logins') else '' }}"><i>◉</i><span>ورودهای مشتریان</span></a>
'''
if 'href="/portal-logins"' not in _pla_base:
    _pla_base = _pla_base.replace("</nav>", _pla_nav + "</nav>", 1)
    TEMPLATES["base.html"] = _pla_base

_pla_dash = TEMPLATES.get("ref_dashboard.html", "")
if _pla_dash and 'href="/portal-logins"' not in _pla_dash:
    _pla_dash_link = '''<section style="margin-top:18px;padding:19px 22px;border-radius:16px;
 background:linear-gradient(120deg,rgba(25,43,67,.85),rgba(12,22,36,.93));
 border:1px solid rgba(135,170,215,.16)">
 <a href="/portal-logins" style="display:flex;align-items:center;justify-content:space-between;
 gap:12px;flex-wrap:wrap;text-decoration:none;color:#dceaff;font-weight:800;font-size:14px">
 <span>◉ گزارش ورودهای پنل مشتریان</span><span>شماره‌ها، آمار امروز و زمان آخرین ورود ←</span></a>
 </section>
'''
    _before,_after=_pla_dash.rsplit("{% endblock %}",1)
    TEMPLATES["ref_dashboard.html"]=_before+_pla_dash_link+"\n{% endblock %}"+_after

if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)


def _pla_admin_login_report(
    request: _pla_Request,
    db: _pla_Session = _pla_Depends(get_db),
):
    now = _pla_datetime.now(_PLA_TZ)
    today = now.replace(hour=0,minute=0,second=0,microsecond=0)
    seven_days = today - _pla_timedelta(days=6)
    query = (request.query_params.get("q") or "").strip()[:65]
    status = (request.query_params.get("status") or "all").strip()
    if status not in ("all","success","not_found","invalid"):
        status = "all"
    pattern = "%" + query.replace("%","\\%").replace("_","\\_") + "%"
    metrics_row = db.execute(_pla_text("""
        SELECT
            count(DISTINCT phone) FILTER (
                WHERE result='success' AND created_at >= :today) AS today_unique,
            count(DISTINCT phone) FILTER (
                WHERE result='success' AND created_at >= :seven) AS week_unique,
            count(DISTINCT phone) FILTER (
                WHERE result='success') AS all_unique,
            count(*) FILTER (
                WHERE result<>'success' AND created_at >= :today) AS today_failed
        FROM customer_portal_login_events
    """),{"today":today, "seven":seven_days}).mappings().one()

    rows = db.execute(_pla_text("""
        SELECT phone, display_name, ip_address, created_at AS last_login, entries
        FROM (
            SELECT phone, display_name, ip_address, created_at, id,
                   row_number() OVER (
                       PARTITION BY phone ORDER BY created_at DESC, id DESC) AS rn,
                   count(*) OVER (PARTITION BY phone) AS entries
            FROM customer_portal_login_events
            WHERE result='success'
              AND (:query = '' OR phone ILIKE :pattern
                   OR COALESCE(display_name,'') ILIKE :pattern)
        ) grouped
        WHERE rn=1 ORDER BY last_login DESC LIMIT 200
    """), {"query":query, "pattern":pattern}).mappings().all()

    events = db.execute(_pla_text("""
        SELECT phone, display_name, ip_address, result, created_at
        FROM customer_portal_login_events
        WHERE (:query = '' OR phone ILIKE :pattern
               OR COALESCE(display_name,'') ILIKE :pattern)
          AND (:status='all' OR result=:status)
        ORDER BY created_at DESC, id DESC LIMIT 100
    """),{"query":query, "pattern":pattern, "status":status}).mappings().all()

    phones=[{**dict(r), "last_text":_pla_when(r["last_login"])} for r in rows]
    history=[{**dict(r), "when_text":_pla_when(r["created_at"])} for r in events]

    return render(
        "portal_logins.html", request,
        metrics=dict(metrics_row),
        phones=phones, events=history, query=query, status=status,
    )


app.add_api_route("/portal-logins", _pla_admin_login_report, methods=["GET"])
