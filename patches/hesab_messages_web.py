# HESAB_MESSAGES_HOSTED_WEB_V1
# Mobile-first web work-SMS control surface; integrates with existing admin session.
# This patch is APP-only, does not touch finance, customer portal or SMS dispatcher.
import json as _hm_json
import secrets as _hm_secrets
from datetime import datetime as _hm_datetime, timezone as _hm_timezone
from fastapi import Request as _hm_Request, Depends as _hm_Depends, Form as _hm_Form
from fastapi.responses import RedirectResponse as _hm_Redirect, Response as _hm_Response, JSONResponse as _hm_Json
from sqlalchemy.orm import Session as _hm_Session
from sqlalchemy import text as _hm_text

_HM_HTML = r'''<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#10192b">
<meta name="referrer" content="same-origin">
<meta http-equiv="Cache-Control" content="no-store">
<link rel="manifest" href="/messages/manifest.webmanifest">
<link rel="icon" href="/messages/icon.svg" type="image/svg+xml">
<title>Hesab Messages · پیامک‌های کاری</title>
<style>
:root{color-scheme:dark;--bg:#080f1e;--panel:#101b2d;--panel2:#17263e;--line:rgba(178,203,248,.12);--text:#f3f7ff;--muted:#a5b3cb;--blue:#96baff;--mint:#77e6bc;--orange:#ffc78a;--red:#ffa6b2;font-family:Tahoma,"Noto Sans Arabic","Vazirmatn",sans-serif}
*{box-sizing:border-box}html{background:#080f1e;scroll-behavior:smooth}body{margin:0;background:radial-gradient(ellipse 90% 35% at 80% 0%,#203d74 0%,transparent 85%),radial-gradient(ellipse 60% 32% at 0% 23%,#242052 0%,transparent 87%),#080f1e;color:var(--text);min-height:100svh;font-size:13px}
main{width:min(950px,100%);margin:auto;padding:27px 17px 110px}.eyebrow{letter-spacing:2.6px;font-size:10px;color:var(--blue);font-family:system-ui;text-transform:uppercase;font-weight:750}
header{display:flex;align-items:center;justify-content:space-between;gap:13px;flex-wrap:wrap;margin-bottom:22px}h1{font-size:28px;margin:5px 0 4px;letter-spacing:-.5px}h2{font-size:16px;margin:0 0 12px}.sub{color:var(--muted);line-height:2;margin:0}
.brand{display:flex;align-items:center;gap:13px}.logo{height:49px;width:49px;background:linear-gradient(135deg,#8ab5ff,#bdaaff);border-radius:15px;display:grid;place-items:center;color:#07142c;box-shadow:0 9px 36px #7199ff2b}.logo svg{width:27px;height:27px}
a{color:inherit;text-decoration:none}a:hover{text-decoration:underline}
.online{border:1px solid #75d7b365;background:#20574359;color:#b4f8d9;border-radius:25px;padding:8px 12px;font-size:11px;font-weight:700}
.statics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:20px}
.stat,.panel{background:linear-gradient(135deg,rgba(25,42,68,.96),rgba(13,24,40,.96));border:1px solid var(--line);box-shadow:0 15px 33px #0206113d;border-radius:18px}
.stat{padding:17px 15px;min-height:97px}.stat span{display:block;color:var(--muted);font-size:11px}.stat strong{display:block;margin-top:12px;font-family:system-ui;font-size:27px;letter-spacing:-1px;direction:ltr;text-align:right;font-weight:800}
.stat.sent strong{color:var(--blue)}.stat.ok strong{color:var(--mint)}.stat.error strong{color:var(--red)}
.layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,.86fr);align-items:start;gap:16px}.panel{padding:20px}.panel p{color:var(--muted);line-height:2;margin:2px 0 12px}.chips{display:flex;gap:8px;flex-wrap:wrap}.chip{background:#2841638a;color:#d8e9ff;border:1px solid #739bdb4a;padding:10px 13px;border-radius:11px;font-size:12px;font-weight:700}
.chip.primary{background:linear-gradient(135deg,#9ebeff,#c0abff);color:#08162a;border:0}.muted{color:var(--muted);font-size:11px}
label{display:block;color:#c9d9f0;font-weight:700;margin:13px 0 7px;font-size:12px}input,textarea{font:inherit;width:100%;padding:12px 13px;background:#091525;color:#fff;border:1px solid #405477;border-radius:11px;outline:0;direction:rtl}input:focus,textarea:focus{border-color:#9cbcff;box-shadow:0 0 0 3px #6a9cff18}
input[type=tel]{direction:ltr;text-align:left;font-family:system-ui;letter-spacing:1px}textarea{min-height:127px;resize:vertical;line-height:1.9}button{font:inherit;cursor:pointer;border:0}.send{width:100%;background:linear-gradient(135deg,#93b7ff,#b0aaff);border-radius:12px;padding:12px;color:#0b1930;font-weight:850;margin-top:13px}
.alert{padding:12px 15px;border-radius:12px;font-size:12px;line-height:2;margin:0 0 16px;border:1px solid #ebba7c50;background:#53392344;color:#ffdfb2}.alert.success{color:#b7ffda;border-color:#6ed9a450;background:#1d5b3b33}
.jobs{margin-top:16px}.job{display:flex;gap:12px;align-items:center;justify-content:space-between;padding:15px 0;border-top:1px solid var(--line)}.job:first-of-type{border-top:0}.job .info{min-width:0;flex:1}.job b{display:block;direction:ltr;text-align:right;font-family:system-ui;font-size:13px;letter-spacing:.6px}.job small{color:var(--muted);font-size:10px;display:block;margin-top:6px}.status{font-size:10px;border:1px solid #6e84a14d;border-radius:999px;padding:7px 10px;white-space:nowrap}.status.delivered{color:var(--mint);border-color:#69dba45c}.status.sent{color:var(--blue)}.status.failed{color:var(--red);border-color:#d66b705c}.status.queued,.status.claimed,.status.dispatching{color:var(--orange)}.status.operator_confirmed{color:#b1d8b9}
.footer-nav{position:fixed;bottom:0;left:0;right:0;display:flex;justify-content:center;padding:11px 12px max(11px,env(safe-area-inset-bottom));background:#0a1525ed;backdrop-filter:blur(18px);border-top:1px solid #455d833b;gap:7px;z-index:40}
.footer-nav a{width:min(215px,33.3%);text-align:center;border-radius:12px;padding:12px 7px;color:#bbcae3;font-weight:700;font-size:11px;background:#ffffff08}
.footer-nav a.selected{color:#17273e;background:linear-gradient(135deg,#a9c8ff,#bcaaff)}
.divline{height:1px;background:var(--line);margin:16px 0}
.countpill{font:600 11px system-ui;color:#cee3ff;background:#789cef28;border-radius:14px;padding:5px 9px}
@media(max-width:680px){main{padding:21px 14px 103px}.statics{grid-template-columns:repeat(2,minmax(0,1fr))}.layout{grid-template-columns:1fr}.stat{min-height:84px;padding:14px 16px}.stat strong{font-size:25px}header h1{font-size:26px}.panel{padding:16px}.online{font-size:10px}.footer-nav a{font-size:10px}}
</style>
</head>
<body>
<main>
<header>
<div class="brand"><div class="logo"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="m4 7 8 6 8-6"/></svg></div>
<div><div class="eyebrow">HESAB MESSAGES</div><h1>مرکز پیامک</h1><p class="sub">پنل پیامک‌های کاری · نسخه آنلاین</p></div></div>
{% if hm.device_online %}<div class="online">● گوشی متصل است</div>{% else %}<div class="online" style="border-color:#ddac6c72;background:#51321d69;color:#ffd5a1">○ گوشی آفلاین / نامشخص</div>{% endif %}
</header>
{% if request.query_params.get('sent') %}<div class="alert success">درخواست پیامک در صف ثبت شد. این به معنی ارسال یا تحویل نیست؛ وضعیت را در فهرست پیگیری کن.</div>{% endif %}
{% if request.query_params.get('duplicate') %}<div class="alert">برای این شماره و متن، اخیراً یک پیامک ثبت شده است. برای جلوگیری از ارسال تکراری، پیام جدیدی ساخته نشد.</div>{% endif %}
{% if request.query_params.get('error') %}<div class="alert">درخواست ثبت نشد. شماره، طول پیام یا وضعیت سامانه را بررسی کن.</div>{% endif %}
<section class="statics" aria-label="وضعیت پیامک‌ها در ۲۴ ساعت اخیر">
<div class="stat"><span>در صف / در حال ارسال</span><strong>{{hm.queued}}</strong></div>
<div class="stat sent"><span>ارسال‌شده به شبکه</span><strong>{{hm.sent}}</strong></div>
<div class="stat ok"><span>گزارش تحویل</span><strong>{{hm.delivered}}</strong></div>
<div class="stat error"><span>ناموفق</span><strong>{{hm.failed}}</strong></div>
</section>
<div class="layout">
<section class="panel">
<h2>عملیات سریع</h2>
<p>یادآوری بدهی را از «وصول بدهی» بفرست تا همان روند پیگیری حسابداری حفظ شود. هیچ پیامکی از این صفحه خودکار ارسال نمی‌شود.</p>
<div class="chips">
<a class="chip primary" href="/debts">وصول بدهی ←</a>
<a class="chip" href="/sms">تاریخچه کامل پیامک‌ها</a>
<a class="chip" href="/followups">در انتظار</a>
{% if hm.native %}<a class="chip" href="hesab://local/inbox">پیام‌های گوشی</a>{% else %}<span class="muted">پیام‌های شخصی فقط در اپ اندروید قابل مشاهده‌اند.</span>{% endif %}
</div>
<div class="divline"></div>
<h2>ارسال پیامک دستی</h2>
<p>فقط برای پیامک مستقل از وصول بدهی؛ ثبت پیام، وضعیت مالی مشتری را تغییر نمی‌دهد.</p>
<form action="/messages/send" method="post" id="hmForm" autocomplete="off">
<input type="hidden" name="csrf" value="{{ hm.csrf }}">
<label for="hmPhone">شماره موبایل گیرنده</label><input id="hmPhone" type="tel" name="phone" required inputmode="tel" placeholder="09xxxxxxxxx" maxlength="18">
<label for="hmBody">متن پیامک</label><textarea id="hmBody" name="message" maxlength="1000" required placeholder="متن پیامک..."></textarea>
<div class="muted" id="hmLength">۰ نویسه · برای متن فارسی بلند، پیام به چند بخش تقسیم می‌شود.</div>
<button class="send" type="submit" id="hmSubmit">ثبت در صف ارسال</button>
</form>
</section>
<section class="panel jobs">
<div style="display:flex;align-items:center;justify-content:space-between;gap:8px"><h2>آخرین پیامک‌های کاری</h2><span class="countpill">۳۰ مورد آخر</span></div>
<p>نتیجه‌های شبکه ممکن است با تأخیر برسند؛ «ارسال‌شده» الزاماً «تحویل‌شده» نیست.</p>
<div id="hmJobs">
{% for j in hm.jobs %}
<div class="job"><div class="info"><b>••• {{j.last4}}</b><small>#{{j.id}} · {{j.time}} · {{j.source}}</small></div><span class="status {{j.status_class}}">{{j.label}}</span></div>
{% else %}
<p>هنوز پیامکی در سامانه ثبت نشده است.</p>
{% endfor %}
</div>
</section>
</div>
</main>
<nav class="footer-nav">
<a class="selected" href="/messages/">پیام‌های کاری</a>
<a href="/debts">وصول بدهی</a>
{% if hm.native %}<a href="hesab://local/inbox">پیام‌های گوشی</a>{% else %}<a href="/sms">پیامک‌ها</a>{% endif %}
</nav>
<script>
(function(){
"use strict";
const input=document.getElementById("hmBody"), length=document.getElementById("hmLength"), form=document.getElementById("hmForm"), submit=document.getElementById("hmSubmit");
function update(){length.textContent=String(input.value.length)+" نویسه · متن فارسی بلند ممکن است چند بخش SMS شود."}
input.addEventListener("input",update);
form.addEventListener("submit",function(e){
  if(!confirm("این پیامک با سیم‌کارت گوشی به شماره واردشده ارسال شود؟")){e.preventDefault();return}
  submit.disabled=true;submit.textContent="در حال ثبت...";
});
if("serviceWorker" in navigator){navigator.serviceWorker.register("/messages/sw.js",{scope:"/messages/"}).catch(function(){})}
})();
</script>
</body></html>'''

TEMPLATES["hm_messages.html"] = _HM_HTML
if hasattr(env.loader, "mapping"):
    env.loader.mapping["hm_messages.html"] = _HM_HTML

_HM_STATUS = {
    "queued": "در صف", "claimed": "دریافت گوشی",
    "dispatching": "در حال ارسال", "sent": "ارسال شد",
    "delivered": "تحویل شد", "failed": "ناموفق",
    "operator_confirmed": "تأیید دستی", "cancelled": "لغوشده",
}

def _hm_token(request):
    token = request.session.get("hesab_messages_csrf")
    if not isinstance(token, str) or len(token) < 28:
        token = _hm_secrets.token_urlsafe(32)
        request.session["hesab_messages_csrf"] = token
    return token

def _hm_data(db):
    now = _hm_datetime.now(_hm_timezone.utc)
    raw = db.execute(_hm_text("""
        SELECT id, right(phone,4) AS last4, source, status,
               created_at AT TIME ZONE 'Asia/Tehran' AS local_created
        FROM sms_jobs ORDER BY id DESC LIMIT 30
    """)).mappings().all()
    counts = db.execute(_hm_text("""
        SELECT
          count(*) FILTER(WHERE status IN('queued','claimed','dispatching')) AS queued,
          count(*) FILTER(WHERE status='sent') AS sent,
          count(*) FILTER(WHERE status='delivered') AS delivered,
          count(*) FILTER(WHERE status='failed') AS failed
        FROM sms_jobs WHERE created_at >= NOW() - interval '24 hours'
    """)).mappings().one()
    last_device = db.execute(_hm_text("""
        SELECT last_seen FROM sms_devices ORDER BY last_seen DESC LIMIT 1
    """)).scalar()
    online = bool(last_device and
                  (now - (last_device.replace(tzinfo=_hm_timezone.utc)
                        if last_device.tzinfo is None else last_device)).total_seconds() < 95)
    jobs = []
    for item in raw:
        state = str(item["status"])
        jobs.append({
            "id": item["id"], "last4": item["last4"], "source": str(item["source"] or "")[:32],
            "time": item["local_created"].strftime("%m/%d %H:%M") if item["local_created"] else "—",
            "status_class": state if state in _HM_STATUS else "unknown",
            "label": _HM_STATUS.get(state, "نامشخص"),
        })
    return {
        "queued": counts["queued"] or 0, "sent": counts["sent"] or 0,
        "delivered": counts["delivered"] or 0, "failed": counts["failed"] or 0,
        "jobs": jobs, "device_online": online,
    }

def _hm_page(request: _hm_Request, db: _hm_Session = _hm_Depends(get_db)):
    data = _hm_data(db)
    data["csrf"] = _hm_token(request)
    data["native"] = "HesabNative/" in request.headers.get("user-agent", "")
    result = render("hm_messages.html", request, hm=data)
    result.headers["Cache-Control"] = "no-store, private"
    result.headers["X-Content-Type-Options"] = "nosniff"
    result.headers["Referrer-Policy"] = "same-origin"
    return result

def _hm_send(
    request: _hm_Request,
    phone: str = _hm_Form(...),
    message: str = _hm_Form(...),
    csrf: str = _hm_Form(...),
    db: _hm_Session = _hm_Depends(get_db),
):
    origin = request.headers.get("origin")
    if origin and origin != "https://hesab.filmjadiid.ir":
        return _hm_Response("Invalid origin", status_code=403)
    stored = request.session.get("hesab_messages_csrf")
    if not isinstance(stored, str) or not _hm_secrets.compare_digest(stored, csrf):
        return _hm_Response("Invalid control token", status_code=403)
    normalized = _sms_normalize_phone(phone)
    body = str(message or "").strip()
    if (not normalized or len(normalized) not in (11, 12, 13) or
        len(body) < 1 or len(body) > 1000):
        return _hm_Redirect("/messages/?error=invalid", status_code=303)
    db.execute(_hm_text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
               {"k": "messages-manual|" + normalized})
    existed = db.execute(_hm_text("""
        SELECT id FROM sms_jobs
        WHERE phone=:phone AND message=:message AND
        created_at > NOW() - interval '2 hours' AND
        status NOT IN ('failed','cancelled')
        ORDER BY id DESC LIMIT 1
    """), {"phone": normalized, "message": body}).first()
    if existed:
        return _hm_Redirect("/messages/?duplicate=1", status_code=303)
    db.execute(_hm_text("""
        INSERT INTO sms_jobs(phone,message,status,source)
        VALUES(:phone,:message,'queued','messages-mobile')
    """), {"phone": normalized, "message": body})
    db.commit()
    return _hm_Redirect("/messages/?sent=1", status_code=303)

def _hm_root():
    return _hm_Redirect("/messages/", status_code=307)

_HM_MANIFEST = _hm_json.dumps({
    "name": "Hesab Messages", "short_name": "Hesab",
    "description": "پنل پیامک‌های کاری حساب",
    "id": "/messages/", "start_url": "/messages/", "scope": "/messages/",
    "display": "standalone", "background_color": "#080f1e",
    "theme_color": "#10192b", "lang": "fa", "dir": "rtl",
    "icons": [{"src":"/messages/icon.svg","sizes":"any",
               "type":"image/svg+xml","purpose":"any maskable"}]
}, ensure_ascii=False)

_HM_ICON = """<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
<defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="#89b7ff"/><stop offset="1" stop-color="#b9a1ff"/></linearGradient></defs>
<rect width="512" height="512" rx="116" fill="#10192b"/>
<rect x="85" y="119" width="342" height="275" rx="60" fill="url(#g)"/>
<rect x="127" y="166" width="258" height="171" rx="28" fill="none" stroke="#172944" stroke-width="26"/>
<path d="m141 193 115 88 115-88" stroke="#172944" stroke-width="25" stroke-linecap="round" fill="none"/>
</svg>"""

def _hm_manifest():
    return _hm_Response(_HM_MANIFEST, media_type="application/manifest+json",
                        headers={"Cache-Control":"public, max-age=3600"})

def _hm_icon():
    return _hm_Response(_HM_ICON, media_type="image/svg+xml",
                        headers={"Cache-Control":"public, max-age=86400",
                                 "X-Content-Type-Options":"nosniff"})

def _hm_sw():
    # Cache no customer data. Registration just permits an installable shell.
    source = """self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));"""
    return _hm_Response(source, media_type="application/javascript",
                        headers={"Cache-Control":"no-store","Service-Worker-Allowed":"/messages/"})

app.add_api_route("/messages", _hm_root, methods=["GET"])
app.add_api_route("/messages/", _hm_page, methods=["GET"])
app.add_api_route("/messages/send", _hm_send, methods=["POST"])
app.add_api_route("/messages/manifest.webmanifest", _hm_manifest, methods=["GET"])
app.add_api_route("/messages/icon.svg", _hm_icon, methods=["GET"])
app.add_api_route("/messages/sw.js", _hm_sw, methods=["GET"])
