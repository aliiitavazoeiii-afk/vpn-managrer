# MAYA1_CONTROL_VIEW_V1
# Read-only dashboard view for SSH-pulled maya1 x-ui snapshot. No billing or x-ui writes.
import json as _mc_json
from pathlib import Path as _mc_Path
from datetime import datetime as _mc_datetime, timezone as _mc_timezone, timedelta as _mc_timedelta
from zoneinfo import ZoneInfo as _mc_ZoneInfo
from fastapi import Request as _mc_Request, Depends as _mc_Depends
from sqlalchemy.orm import Session as _mc_Session

_MC_FOLDER = _mc_Path("/srv/maya1-sync")
_MC_TEHRAN = _mc_ZoneInfo("Asia/Tehran")

def _mc_stamp(ms):
    try:
        val = int(ms or 0)
        if val <= 0:
            return "—"
        return _mc_datetime.fromtimestamp(val / 1000, _mc_timezone.utc).astimezone(
            _MC_TEHRAN).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError, OverflowError, OSError):
        return "—"

def _mc_read_json(path):
    if not path.is_file() or path.stat().st_size > 3000000:
        return None
    return _mc_json.loads(path.read_text(encoding="utf-8"))

def _mc_gb(value):
    try:
        return f"{int(value or 0)/1073741824:,.2f} GB"
    except (ValueError, TypeError):
        return "—"

_MC_PANEL = r"""
<section class="mc-root">
<style>
.mc-root{margin-top:24px;direction:rtl;color:#e8f0fa}
.mc-header{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:15px}
.mc-header h2{font-weight:850;font-size:22px;margin:0}
.mc-header p{color:#90a4bc;font-size:12px;margin:6px 0}
.mc-pill{border:1px solid rgba(90,217,175,.4);padding:7px 13px;border-radius:999px;color:#77dfb5;font-size:12px}
.mc-warn{padding:14px 18px;border:1px solid #ba8046;border-radius:12px;color:#f2cda7;background:rgba(150,100,38,.1);margin-bottom:16px}
.mc-cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:14px 0 18px}
.mc-card{border:1px solid rgba(151,176,218,.17);border-radius:16px;background:linear-gradient(135deg,#1a2940,#0e1827);padding:17px}
.mc-card small{color:#91a6c3;display:block;font-size:11px}
.mc-card strong{display:block;font-size:24px;margin-top:9px;color:#f4f8fe}
.mc-panel{border:1px solid rgba(151,176,218,.18);border-radius:16px;background:#0f1b2a;overflow:hidden}
.mc-tools{padding:15px 16px;display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap}
.mc-tools input{background:#091423;border:1px solid #34465d;border-radius:9px;padding:10px 12px;color:white;min-width:230px}
.mc-tools button{padding:10px 18px;border:0;border-radius:9px;background:#cadbf4;color:#12203a;font-weight:800}
.mc-scroll{overflow-x:auto}
.mc-table{width:100%;border-collapse:collapse;text-align:right;min-width:800px}
.mc-table th,.mc-table td{padding:13px 15px;border-top:1px solid rgba(150,175,205,.09);font-size:12px}
.mc-table th{color:#8eacc9;background:#121f30;font-size:11px}
.mc-table td{color:#d3dfec}
.mc-table a{color:#a6d3ff;text-decoration:none}
.mc-muted{color:#859ab4;font-size:11px}
.mc-ok{color:#83dfb5}.mc-off{color:#efa992}
@media(max-width:700px){.mc-cards{grid-template-columns:repeat(2,minmax(0,1fr))}.mc-card strong{font-size:20px}}
</style>
<div class="mc-header">
  <div><h2>maya1 · کاربران زنده x-ui</h2>
  <p>فقط‌خواندنی · تطبیق با شناسه داشبورد · به‌روزرسانی خودکار هر ۵ دقیقه</p></div>
  <span class="mc-pill">اتصال امن SSH</span>
</div>
{% if mc.error %}
  <div class="mc-warn">{{ mc.error }}</div>
{% else %}
  {% if mc.stale %}<div class="mc-warn">آخرین داده قدیمی است؛ وضعیت فعلی سرور تا دریافت گزارش جدید تأیید نشده.</div>{% endif %}
  <div class="mc-cards">
    <div class="mc-card"><small>کل کلاینت‌های maya1</small><strong>{{ mc.total|fa }}</strong></div>
    <div class="mc-card"><small>متصل به داشبورد</small><strong>{{ mc.linked|fa }}</strong></div>
    <div class="mc-card"><small>مستثنا از اتصال مالی</small><strong>{{ mc.excluded|fa }}</strong></div>
    <div class="mc-card"><small>فعال در x-ui</small><strong>{{ mc.enabled|fa }}</strong></div>
  </div>
  <div class="mc-panel">
    <div class="mc-tools">
      <div><b>فهرست کاربران</b><div class="mc-muted">آخرین سینک: {{ mc.synced }}</div></div>
      <form method="get" action="/control-room">
        <input name="q" type="search" value="{{ mc.query }}" placeholder="نام x-ui یا نام داشبورد یا ID">
        <button type="submit">جست‌وجو</button>
      </form>
    </div>
    <div class="mc-scroll">
      <table class="mc-table">
        <thead><tr><th>کلاینت x-ui</th><th>اکانت داشبورد</th><th>وضعیت</th><th>مصرف کل</th><th>آخرین اتصال</th><th>انقضای داشبورد</th></tr></thead>
        <tbody>
        {% for row in mc.rows %}
        <tr>
          <td><strong>{{ row.email }}</strong></td>
          <td>{% if row.sid %}<a href="/users/{{ row.sid }}">#{{ row.sid }} · {{ row.name }}</a>{% else %}<span class="mc-muted">مستثنا ({{ row.reason }})</span>{% endif %}</td>
          <td><span class="{{ 'mc-ok' if row.enabled else 'mc-off' }}">{{ 'فعال' if row.enabled else 'غیرفعال' }}</span>{% if row.dashboard_state %}<div class="mc-muted">داشبورد: {{ row.dashboard_state }}</div>{% endif %}</td>
          <td dir="ltr">{{ row.usage }}</td>
          <td dir="ltr">{{ row.last_online }}</td>
          <td>{% if row.expiry %}{{ row.expiry|jdate }}{% else %}—{% endif %}</td>
        </tr>
        {% else %}<tr><td colspan="6">کاربری مطابق این جست‌وجو پیدا نشد.</td></tr>{% endfor %}
        </tbody>
      </table>
    </div>
  </div>
{% endif %}
</section>
"""

_mc_old_template = TEMPLATES.get("control_room.html", "")
if not _mc_old_template or _mc_old_template.count("{% endblock %}") < 1:
    raise RuntimeError("MAYA1: cannot find control-room template")
_mc_before, _mc_end = _mc_old_template.rsplit("{% endblock %}", 1)
TEMPLATES["control_room.html"] = _mc_before + _MC_PANEL + "\n{% endblock %}" + _mc_end
if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)

def _mc_control_room(request: _mc_Request, db: _mc_Session = _mc_Depends(get_db)):
    iran_servers, foreign_servers = _ref_servers()
    mc = {"error": "", "rows": [], "query": (request.query_params.get("q") or "").strip()[:80]}
    try:
        snapshot = _mc_read_json(_MC_FOLDER / "snapshot.json")
        raw_map = _mc_read_json(_MC_FOLDER / "mapping.json")
        if (not snapshot or not raw_map or
            snapshot.get("format") != "MAYA1_CONTROL_SNAPSHOT_V1" or
            raw_map.get("format") != "MAYA1_CONTROL_MAPPING_V1"):
            raise ValueError("هنوز گزارش معتبر maya1 دریافت نشده است.")
        clients = snapshot["clients"]
        mapping = raw_map["mapping"]
        if len(clients) != 145 or len(mapping) != 145:
            raise ValueError("تعداد کلاینت‌های گزارش با نقشه تأییدشده برابر نیست.")
        ids = [int(v["id"]) for v in mapping.values() if v.get("id") is not None]
        if len(ids) != 141 or len(set(ids)) != 141:
            raise ValueError("شناسه‌های نقشه اتصال معتبر نیستند.")
        subs = {s.id: s for s in db.query(Subscription).filter(Subscription.id.in_(ids)).all()}
        if len(subs) != 141:
            raise ValueError("یک یا چند اکانت داشبورد دیگر موجود نیست.")
        states = _followup_states(db)
        now = _mc_datetime.now(_mc_timezone.utc)
        last = _mc_datetime.fromisoformat(snapshot["synced_at"].replace("Z","+00:00"))
        mc["stale"] = not last.tzinfo or now-last > _mc_timedelta(minutes=15)
        mc["synced"] = last.astimezone(_MC_TEHRAN).strftime("%Y-%m-%d %H:%M")
        mc["total"] = len(clients)
        mc["linked"] = len(ids)
        mc["excluded"] = 4
        mc["enabled"] = sum(bool(c["enabled"]) for c in clients)
        rows = []
        for c in clients:
            email = str(c["email"])
            link = mapping[email.casefold()]
            sid = link.get("id")
            sub = subs.get(int(sid)) if sid else None
            name = sub.display_name if sub else ""
            row = {
                "email": email, "sid": sid, "name": name,
                "reason": link.get("reason", ""),
                "enabled": bool(c["enabled"]),
                "usage": _mc_gb(int(c["up_bytes"])+int(c["down_bytes"])),
                "last_online": _mc_stamp(c.get("last_online_ms")),
                "expiry": sub.expiry_date if sub else None,
                "dashboard_state": (states.get(sub.id) or "normal") if sub else "",
            }
            if mc["query"].casefold() in (email + " " + name + " " + str(sid or "")).casefold():
                rows.append(row)
        mc["rows"] = rows
    except Exception as ex:
        # Do not expose internal exceptions or customer data in error responses.
        mc["error"] = "گزارش زنده maya1 در دسترس نیست یا اعتبارسنجی آن ناموفق بود؛ اتصال قبلی تغییر نکرده است."
        print("MAYA1_VIEW_ERROR:", type(ex).__name__, str(ex)[:250])
    return render("control_room.html", request,
                  iran_servers=iran_servers, foreign_servers=foreign_servers, mc=mc)

app.router.routes[:] = [
    route for route in app.router.routes
    if not (getattr(route, "path", None) == "/control-room"
            and "GET" in (getattr(route, "methods", set()) or set()))
]
app.add_api_route("/control-room", _mc_control_room, methods=["GET"])
