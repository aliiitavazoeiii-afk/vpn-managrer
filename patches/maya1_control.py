# MAYA1_CONTROL_VIEW_V1
# Read-only dashboard view for SSH-pulled maya1 x-ui snapshot. No billing or x-ui writes.
import json as _mc_json
from pathlib import Path as _mc_Path
from datetime import datetime as _mc_datetime, timezone as _mc_timezone, timedelta as _mc_timedelta
from zoneinfo import ZoneInfo as _mc_ZoneInfo
from fastapi import Request as _mc_Request, Depends as _mc_Depends
from sqlalchemy.orm import Session as _mc_Session
from fastapi import Form as _mc_Form, HTTPException as _mc_HTTPException
from fastapi.responses import RedirectResponse as _mc_RedirectResponse
import secrets as _mc_secrets
import socket as _mc_socket
from urllib.parse import quote as _mc_quote

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
.mc-toggle{border:0;border-radius:9px;padding:8px 13px;cursor:pointer;font-weight:850;font-size:12px}
.mc-toggle-stop{background:#622b32;color:#ffe0df;border:1px solid #b85b66}
.mc-toggle-go{background:#155942;color:#dbffee;border:1px solid #318f71}
.mc-result{margin:12px 0;padding:13px 16px;border:1px solid #6882a4;border-radius:12px;color:#d5e4f8;background:#182a40}
.mc-history{margin-top:18px}

.mc-leaders{margin:18px 0;border:1px solid rgba(151,176,218,.18);border-radius:16px;background:#101c2c;overflow:hidden}
.mc-leaders h3{font-size:15px;margin:0;padding:15px 17px}
.mc-leaders .mc-scroll table{min-width:570px}
.mc-notice{margin:14px 0;font-size:12px;color:#a1b3c8;line-height:2}
@media(max-width:700px){.mc-cards{grid-template-columns:repeat(2,minmax(0,1fr))}.mc-card strong{font-size:20px}}
</style>
{% if mc.action_feedback %}<div class="mc-result">{{ mc.action_feedback }}</div>{% endif %}
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
  <div class="mc-notice">
    مصرف «امروز» از اختلاف نمونه‌های پنج‌دقیقه‌ای x-ui محاسبه می‌شود؛
    برای ساعات قبل از شروع پایش، قطعی مانیتورینگ یا ریست شمارنده‌ها عددی تخمین زده نمی‌شود.
    {% if mc.usage_available %}
      <strong> مجموع ثبت‌شده امروز: {{ mc.today_total }}</strong>
      · پوشش: {{ mc.today_samples|fa }} نمونه
    {% else %}
      <strong>ثبت نمونه‌های مصرف امروز هنوز آغاز نشده است.</strong>
    {% endif %}
  </div>
  {% if mc.usage_available %}
  <div class="mc-leaders">
    <h3>۱۰ کاربر پرمصرف امروز (تا آخرین نمونه)</h3>
    <div class="mc-scroll"><table class="mc-table">
      <thead><tr><th>رتبه</th><th>کاربر</th><th>مصرف امروز</th><th>دانلود</th><th>آپلود</th></tr></thead>
      <tbody>{% for row in mc.leaders %}
      <tr><td>{{ loop.index|fa }}</td>
        <td>{{ row.email }}{% if row.sid %}<div class="mc-muted">#{{ row.sid }} · {{ row.name }}</div>{% endif %}</td>
        <td dir="ltr">{{ row.today_usage }}</td>
        <td dir="ltr">{{ row.today_down }}</td><td dir="ltr">{{ row.today_up }}</td>
      </tr>
      {% else %}<tr><td colspan="5">هنوز مصرفی ثبت نشده است.</td></tr>{% endfor %}</tbody>
    </table></div>
  </div>
  {% endif %}
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
        <thead><tr><th>کلاینت x-ui</th><th>اکانت داشبورد</th><th>وضعیت</th><th>مصرف امروز</th><th>مصرف کل</th><th>آخرین اتصال</th><th>انقضای داشبورد</th><th>کنترل کاربر</th></tr></thead>
        <tbody>
        {% for row in mc.rows %}
        <tr>
          <td><strong>{{ row.email }}</strong></td>
          <td>{% if row.sid %}<a href="/users/{{ row.sid }}">#{{ row.sid }} · {{ row.name }}</a>{% else %}<span class="mc-muted">مستثنا ({{ row.reason }})</span>{% endif %}</td>
          <td><span class="{{ 'mc-ok' if row.enabled else 'mc-off' }}">{{ 'فعال' if row.enabled else 'غیرفعال' }}</span>{% if row.dashboard_state %}<div class="mc-muted">داشبورد: {{ row.dashboard_state }}</div>{% endif %}</td>
          <td dir="ltr">{{ row.today_usage }}</td>
          <td dir="ltr">{{ row.usage }}</td>
          <td dir="ltr">{{ row.last_online }}</td>
          <td>{% if row.expiry %}{{ row.expiry|jdate }}{% else %}—{% endif %}</td>
          <td>
          {% if row.sid and not mc.stale %}
            <form method="post" action="/control-room/maya1/toggle"
                  onsubmit="return confirm('آیا از تغییر وضعیت همین اکانت در maya1 مطمئن هستی؟');">
              <input type="hidden" name="email" value="{{ row.email }}">
              <input type="hidden" name="sid" value="{{ row.sid }}">
              <input type="hidden" name="expected" value="{{ 1 if row.enabled else 0 }}">
              <input type="hidden" name="target" value="{{ 0 if row.enabled else 1 }}">
              <input type="hidden" name="token" value="{{ mc.csrf_token }}">
              <button class="mc-toggle {{ 'mc-toggle-stop' if row.enabled else 'mc-toggle-go' }}"
                      type="submit">{{ 'قطع VPN' if row.enabled else 'وصل VPN' }}</button>
            </form>
          {% else %}<span class="mc-muted">غیرفعال / نیازمند به‌روزرسانی</span>{% endif %}
          </td>
        </tr>
        {% else %}<tr><td colspan="8">کاربری مطابق این جست‌وجو پیدا نشد.</td></tr>{% endfor %}
        </tbody>
      </table>
    </div>
  </div>
  {% if mc.history %}
  <div class="mc-panel mc-history">
    <div class="mc-tools"><b>۱۵ عملیات اخیر قطع و وصل</b></div>
    <div class="mc-scroll"><table class="mc-table">
      <thead><tr><th>زمان</th><th>اکانت</th><th>عملیات</th><th>نتیجه</th></tr></thead>
      <tbody>{% for item in mc.history %}
        <tr><td dir="ltr">{{ item.at }}</td><td>{{ item.email }}</td>
          <td>{{ 'وصل' if item.target else 'قطع' }}</td>
          <td>{{ 'تأییدشده' if item.result == 'confirmed' else 'ناموفق / نامطمئن' }}</td></tr>
      {% endfor %}</tbody>
    </table></div>
  </div>
  {% endif %}
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
    token = request.session.get("maya1_control_csrf")
    if not isinstance(token, str) or len(token) < 30:
        token = _mc_secrets.token_urlsafe(32)
        request.session["maya1_control_csrf"] = token
    mc = {"error": "", "rows": [], "query": (request.query_params.get("q") or "").strip()[:80],
          "csrf_token": token, "history": [], "action_feedback": ""}
    status = request.query_params.get("action", "")
    if status == "success":
        mc["action_feedback"] = "تغییر وضعیت در x-ui تأیید شد؛ وضعیت جدید از سرور خوانده می‌شود."
    elif status == "failed":
        mc["action_feedback"] = "عملیات تأیید نشد. قبل از تلاش دوباره وضعیت کاربر را در x-ui بررسی کن."
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
        usage = _mc_read_json(_MC_FOLDER / "daily_usage.json")
        today = _mc_datetime.now(_MC_TEHRAN).date().isoformat()
        counts = {}
        mc["usage_available"] = bool(usage and usage.get("format") == "MAYA1_USAGE_DAILY_V1"
                                     and today in usage.get("days", {}))
        if mc["usage_available"]:
            counts = usage["days"][today]
        mc["today_total"] = _mc_gb(sum(int(d.get("up", 0))+int(d.get("down", 0))
                                     for d in counts.values()))
        mc["today_samples"] = max((int(d.get("samples", 0)) for d in counts.values()), default=0)
        rows = []
        leaders = []
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
                "today_usage": _mc_gb(int(counts.get(email.casefold(), {}).get("up", 0))+
                                      int(counts.get(email.casefold(), {}).get("down", 0))) if mc["usage_available"] else "—",
                "today_up": _mc_gb(counts.get(email.casefold(), {}).get("up", 0)),
                "today_down": _mc_gb(counts.get(email.casefold(), {}).get("down", 0)),
                "today_bytes": int(counts.get(email.casefold(), {}).get("up", 0))+
                               int(counts.get(email.casefold(), {}).get("down", 0)),

                "last_online": _mc_stamp(c.get("last_online_ms")),
                "expiry": sub.expiry_date if sub else None,
                "dashboard_state": (states.get(sub.id) or "normal") if sub else "",
            }
            leaders.append(row)
            if mc["query"].casefold() in (email + " " + name + " " + str(sid or "")).casefold():
                rows.append(row)
        mc["leaders"] = sorted((r for r in leaders if r["today_bytes"] > 0),
                                key=lambda r: (-r["today_bytes"], r["email"].casefold()))[:10]
        mc["rows"] = rows
        history_path = _MC_FOLDER / "actions.jsonl"
        if history_path.is_file() and history_path.stat().st_size < 1000000:
            history = []
            for line in history_path.read_text(encoding="utf8").splitlines()[-15:]:
                try:
                    item = _mc_json.loads(line)
                    history.append({
                        "at": str(item.get("at", ""))[:19].replace("T", " "),
                        "email": str(item.get("email", ""))[:180],
                        "target": bool(item.get("target", False)),
                        "result": str(item.get("result", "")),
                    })
                except (ValueError, TypeError):
                    continue
            mc["history"] = list(reversed(history))
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

# MAYA1_CONTROL_WRITE_V1
def _mc_toggle(
    request: _mc_Request,
    email: str = _mc_Form(...),
    sid: int = _mc_Form(...),
    target: int = _mc_Form(...),
    expected: int = _mc_Form(...),
    token: str = _mc_Form(...),
    db: _mc_Session = _mc_Depends(get_db),
):
    origin = request.headers.get("origin")
    if origin and origin != "https://hesab.filmjadiid.ir":
        raise _mc_HTTPException(status_code=403, detail="Origin not allowed")
    csrf = request.session.get("maya1_control_csrf", "")
    if not isinstance(csrf, str) or not _mc_secrets.compare_digest(csrf, token):
        raise _mc_HTTPException(status_code=403, detail="Invalid control token")
    if target not in (0, 1) or expected not in (0, 1) or target == expected:
        raise _mc_HTTPException(status_code=400, detail="Invalid target status")
    if sid <= 0 or not email or len(email) > 180:
        raise _mc_HTTPException(status_code=400, detail="Invalid account")
    if db.get(Subscription, sid) is None or _followup_states(db).get(sid) == "cut":
        raise _mc_HTTPException(status_code=409, detail="Dashboard account unavailable")
    outcome = "failed"
    try:
        snap = _mc_read_json(_MC_FOLDER / "snapshot.json")
        links = _mc_read_json(_MC_FOLDER / "mapping.json")
        if (not snap or not links or
            links.get("expected_sha") != "8e1509674cf0c06d1e8015064c8c3b69b76931311bce4489b1bbda49d50f37fb"):
            raise ValueError("Missing verified mapping")
        key = email.strip().casefold()
        link = links["mapping"].get(key, {})
        if (link.get("id") != sid or
            link.get("reason") not in ("confirmed", "exact_approved")):
            raise ValueError("Account not approved for control")
        matches = [c for c in snap["clients"] if str(c.get("email") or "").strip().casefold() == key]
        when = _mc_datetime.fromisoformat(snap["source_generated_at"].replace("Z","+00:00"))
        if (len(matches) != 1 or matches[0].get("enabled") is not bool(expected) or
            not when.tzinfo or
            abs((_mc_datetime.now(_mc_timezone.utc)-when).total_seconds()) > 900):
            raise ValueError("Maya1 snapshot stale or changed")
        payload = _mc_json.dumps({
            "email": email.strip(), "sid": sid,
            "target": bool(target), "expected": bool(expected)
        }, ensure_ascii=False).encode() + b"\\n"
        with _mc_socket.socket(_mc_socket.AF_UNIX, _mc_socket.SOCK_STREAM) as sock:
            sock.settimeout(110)
            sock.connect(str(_MC_FOLDER / "control.sock"))
            sock.sendall(payload)
            sock.shutdown(_mc_socket.SHUT_WR)
            result = b""
            while not result.endswith(b"\\n") and len(result) < 8192:
                packet = sock.recv(8192-len(result))
                if not packet:
                    break
                result += packet
            answer = _mc_json.loads(result)
        if answer.get("ok") is True and answer.get("enabled") is bool(target):
            outcome = "success"
    except Exception as ex:
        print("MAYA1_TOGGLE_ERROR", type(ex).__name__, str(ex)[:180])
    return _mc_RedirectResponse(
        url="/control-room?q=" + _mc_quote(email.strip(), safe="") + "&action=" + outcome,
        status_code=303,
    )

app.add_api_route("/control-room/maya1/toggle", _mc_toggle, methods=["POST"])
