# SMS_GATEWAY_PATCH_V1
# Admin queue UI for the Hesab SMS Gateway. Loaded last at container start.
from datetime import datetime as _sms_datetime, timezone as _sms_timezone
from fastapi import Form as _SmsForm, Depends as _SmsDepends, Request as _SmsRequest
from fastapi.responses import RedirectResponse as _SmsRedirectResponse
from sqlalchemy import text as _sms_text
from sqlalchemy.orm import Session as _SmsSession


_SMS_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS sms_jobs (
        id BIGSERIAL PRIMARY KEY,
        phone VARCHAR(32) NOT NULL,
        message TEXT NOT NULL,
        status VARCHAR(24) NOT NULL DEFAULT 'queued',
        source VARCHAR(64) NOT NULL DEFAULT 'dashboard',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        claimed_at TIMESTAMPTZ,
        dispatching_at TIMESTAMPTZ,
        sent_at TIMESTAMPTZ,
        delivered_at TIMESTAMPTZ,
        failed_at TIMESTAMPTZ,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        device_id VARCHAR(128),
        sim_subscription_id INTEGER,
        attempts INTEGER NOT NULL DEFAULT 0,
        error TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sms_jobs_queue ON sms_jobs(status, id)",
    "CREATE INDEX IF NOT EXISTS idx_sms_jobs_phone ON sms_jobs(phone, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS sms_devices (
        device_id VARCHAR(128) PRIMARY KEY,
        device_name VARCHAR(160),
        app_version VARCHAR(64),
        android_version VARCHAR(64),
        sim_subscription_id INTEGER,
        last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
)


def _sms_ensure_schema(db):
    for stmt in _SMS_SCHEMA:
        db.execute(_sms_text(stmt))
    db.commit()


def _sms_normalize_phone(value):
    if "_normalize_phone" in globals():
        return _normalize_phone(value)
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    raw = str(value or "").translate(table).strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits.startswith("0098"):
        digits = "0" + digits[4:]
    elif digits.startswith("98") and len(digits) == 12:
        digits = "0" + digits[2:]
    elif digits.startswith("9") and len(digits) == 10:
        digits = "0" + digits
    return digits


_SMS_TEMPLATE = r'''{% extends "base.html" %}
{% block title %}پیامک · حساب VPN{% endblock %}
{% block heading %}پیامک از خط شخصی{% endblock %}
{% block subheading %}درخواست را اینجا ثبت کن؛ گوشی Android از سیم‌کارت انتخابی ارسال می‌کند{% endblock %}
{% block content %}
<div class="sms-page">
  {% if request.query_params.get("queued") %}
    <div class="sms-banner ok">✓ پیامک در صف قرار گرفت و گوشی آن را دریافت می‌کند.</div>
  {% endif %}
  {% if request.query_params.get("retried") %}
    <div class="sms-banner ok">↻ پیام ناموفق دوباره در صف قرار گرفت.</div>
  {% endif %}
  {% if request.query_params.get("cancelled") %}
    <div class="sms-banner">پیامِ در صف لغو شد.</div>
  {% endif %}
  {% if request.query_params.get("error") %}
    <div class="sms-banner bad">اطلاعات پیام معتبر نیست؛ شماره و متن را بررسی کن.</div>
  {% endif %}

  <section class="sms-grid">
    <article class="sms-card sms-compose">
      <header>
        <div><span class="sms-icon">✉</span><div><h2>ارسال پیامک</h2><p>پیام از همان سیم‌کارت گوشی تو ارسال می‌شود.</p></div></div>
      </header>

      <form method="post" action="/sms/send" id="sms-form">
        <label>انتخاب کاربر</label>
        <select id="sms-user">
          <option value="">— انتخاب اختیاری —</option>
          {% for u in users %}
          <option value="{{ u.phone }}" data-name="{{ u.name }}">{{ u.name }} · {{ u.phone }}</option>
          {% endfor %}
        </select>

        <label>شماره موبایل</label>
        <input id="sms-phone" name="phone" type="tel" inputmode="tel" autocomplete="off" placeholder="0912..." required>

        <label>متن پیام</label>
        <textarea id="sms-message" name="message" rows="7" maxlength="1000" required placeholder="متن پیامک را بنویس…"></textarea>

        <div class="sms-presets">
          <button type="button" data-preset="سلام، زمان تمدید اشتراک شما رسیده. لطفاً برای تمدید اقدام کنید.">یادآوری تمدید</button>
          <button type="button" data-preset="سلام، پرداخت تمدید اشتراک شما هنوز ثبت نشده. لطفاً پس از واریز اطلاع دهید.">پیگیری پرداخت</button>
        </div>

        <div class="sms-compose-foot">
          <small><span id="sms-count">۰</span> کاراکتر</small>
          <button class="sms-send" type="submit">قرار دادن در صف ارسال ←</button>
        </div>
      </form>
    </article>

    <aside class="sms-card sms-device">
      <header><h2>وضعیت گوشی</h2><span class="sms-live-dot"></span></header>
      {% if devices %}
        {% for d in devices %}
        <div class="sms-device-row">
          <div><b>{{ d.name }}</b><small>{{ d.device_id }}</small></div>
          <span class="{{ 'online' if d.online else 'offline' }}">{{ 'آنلاین' if d.online else 'آفلاین' }}</span>
        </div>
        <div class="sms-device-meta">
          <span>Android {{ d.android_version or '—' }}</span>
          <span>App {{ d.app_version or '—' }}</span>
          <span>SIM {{ d.sim_subscription_id if d.sim_subscription_id is not none else 'پیش‌فرض' }}</span>
        </div>
        {% endfor %}
      {% else %}
        <div class="sms-empty-device">هنوز هیچ گوشی به Gateway متصل نشده. APK را نصب و Gateway را Start کن.</div>
      {% endif %}
      <div class="sms-security-note"><b>امنیت</b><span>API گوشی با توکن مستقل محافظت می‌شود و امکان ساخت پیام جدید از API گوشی وجود ندارد.</span></div>
    </aside>
  </section>

  <section class="sms-card sms-history">
    <header><div><h2>تاریخچه پیامک‌ها</h2><p>۵۰ درخواست اخیر</p></div></header>
    <div class="sms-table-wrap">
      <table>
        <thead><tr><th>#</th><th>شماره</th><th>متن</th><th>وضعیت</th><th>گوشی / SIM</th><th>عملیات</th></tr></thead>
        <tbody>
        {% for j in jobs %}
          <tr>
            <td>{{ j.id }}</td>
            <td class="ltr">{{ j.phone }}</td>
            <td class="sms-msg-cell">{{ j.message }}</td>
            <td><span class="sms-status status-{{ j.status }}">{{ status_labels.get(j.status, j.status) }}</span>{% if j.error %}<small class="sms-error">{{ j.error }}</small>{% endif %}</td>
            <td><small>{{ j.device_id or '—' }}{% if j.sim_subscription_id is not none %}<br>SIM {{ j.sim_subscription_id }}{% endif %}</small></td>
            <td>
              {% if j.status == 'failed' %}
              <form method="post" action="/sms/{{ j.id }}/retry"><button class="sms-mini" type="submit">ارسال دوباره</button></form>
              {% elif j.status == 'queued' %}
              <form method="post" action="/sms/{{ j.id }}/cancel"><button class="sms-mini muted" type="submit">لغو</button></form>
              {% else %}—{% endif %}
            </td>
          </tr>
        {% else %}
          <tr><td colspan="6"><div class="sms-empty">هنوز پیامکی ثبت نشده.</div></td></tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </section>
</div>

<style>
.sms-page{display:flex;flex-direction:column;gap:18px}.sms-banner{border:1px solid rgba(148,163,184,.18);background:rgba(30,41,59,.55);padding:12px 14px;border-radius:13px;color:#dbe3ef}.sms-banner.ok{border-color:rgba(34,197,94,.25);background:rgba(34,197,94,.08);color:#bff6cf}.sms-banner.bad{border-color:rgba(248,113,113,.25);background:rgba(239,68,68,.08);color:#ffc4c9}
.sms-grid{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(280px,.75fr);gap:18px}.sms-card{border:1px solid rgba(255,255,255,.08);background:linear-gradient(180deg,rgba(16,23,36,.94),rgba(10,15,24,.92));border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,.18);overflow:hidden}.sms-card>header{display:flex;justify-content:space-between;align-items:center;padding:18px 20px;border-bottom:1px solid rgba(255,255,255,.07)}.sms-card h2{margin:0;color:#f8fafc;font-size:17px}.sms-card header p{margin:4px 0 0;color:#7f8ba0;font-size:11px}.sms-compose header>div{display:flex;gap:12px;align-items:center}.sms-icon{width:44px;height:44px;border-radius:14px;display:grid;place-items:center;background:rgba(59,130,246,.12);color:#93c5fd;font-size:20px}
.sms-compose form{padding:20px;display:flex;flex-direction:column;gap:9px}.sms-compose label{font-size:11px;color:#96a1b2;margin-top:5px}.sms-compose input,.sms-compose select,.sms-compose textarea{width:100%;box-sizing:border-box;border:1px solid rgba(255,255,255,.11);background:#0b111c;color:#f5f7fb;border-radius:11px;padding:11px 12px;font:inherit;outline:none}.sms-compose input:focus,.sms-compose select:focus,.sms-compose textarea:focus{border-color:rgba(96,165,250,.55)}.sms-compose textarea{resize:vertical;line-height:1.9}.sms-presets{display:flex;gap:8px;flex-wrap:wrap}.sms-presets button,.sms-mini{border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.04);color:#bdc7d6;border-radius:9px;padding:7px 10px;font:inherit;font-size:10px;cursor:pointer}.sms-presets button:hover,.sms-mini:hover{background:rgba(255,255,255,.08);color:#fff}.sms-compose-foot{display:flex;justify-content:space-between;align-items:center;margin-top:8px}.sms-compose-foot small{color:#778397}.sms-send{border:0;border-radius:11px;background:#eef2f7;color:#111827;padding:11px 16px;font:inherit;font-weight:850;cursor:pointer}
.sms-device{padding-bottom:18px}.sms-device header{border-bottom:0}.sms-live-dot{width:9px;height:9px;border-radius:50%;background:#22c55e;box-shadow:0 0 0 6px rgba(34,197,94,.08)}.sms-device-row{margin:0 18px;padding:14px;border:1px solid rgba(255,255,255,.08);border-radius:13px;display:flex;justify-content:space-between;align-items:center;background:rgba(255,255,255,.025)}.sms-device-row b{display:block;color:#eef2f7}.sms-device-row small{display:block;color:#69758a;font-size:9px;margin-top:4px;direction:ltr;text-align:left}.sms-device-row span{font-size:10px;border-radius:999px;padding:5px 8px}.sms-device-row .online{color:#9ef0b4;background:rgba(34,197,94,.09)}.sms-device-row .offline{color:#f5b2b7;background:rgba(239,68,68,.08)}.sms-device-meta{display:flex;flex-wrap:wrap;gap:6px;margin:9px 18px 0}.sms-device-meta span{font-size:9px;color:#7f8ba0;padding:5px 7px;border-radius:7px;background:rgba(255,255,255,.03)}.sms-empty-device{margin:0 18px;color:#8894a6;font-size:11px;line-height:1.9;padding:14px;border:1px dashed rgba(255,255,255,.09);border-radius:12px}.sms-security-note{margin:18px 18px 0;padding:12px;border-radius:12px;background:rgba(59,130,246,.06);border:1px solid rgba(59,130,246,.12)}.sms-security-note b{display:block;color:#a9ccff;font-size:11px}.sms-security-note span{display:block;color:#748097;font-size:9px;line-height:1.8;margin-top:3px}
.sms-history header{padding-bottom:14px}.sms-table-wrap{overflow:auto}.sms-history table{width:100%;border-collapse:collapse;min-width:800px}.sms-history th,.sms-history td{padding:12px 14px;text-align:right;border-top:1px solid rgba(255,255,255,.055);font-size:11px;color:#b9c2d0;vertical-align:top}.sms-history th{color:#69758a;font-size:9px;font-weight:650}.sms-msg-cell{max-width:360px;line-height:1.75}.sms-status{display:inline-block;border-radius:999px;padding:5px 8px;font-size:9px}.status-queued{background:rgba(148,163,184,.1);color:#cbd5e1}.status-claimed,.status-dispatching{background:rgba(59,130,246,.1);color:#a9ccff}.status-sent{background:rgba(168,85,247,.1);color:#d8b4fe}.status-delivered{background:rgba(34,197,94,.1);color:#a7f3bd}.status-failed{background:rgba(239,68,68,.1);color:#fecaca}.status-cancelled{background:rgba(100,116,139,.1);color:#94a3b8}.sms-error{display:block;color:#fca5a5;font-size:8px;margin-top:5px}.sms-mini{white-space:nowrap}.sms-mini.muted{color:#8893a3}.sms-empty{text-align:center;padding:25px;color:#6f7a8c}
@media(max-width:900px){.sms-grid{grid-template-columns:1fr}}@media(max-width:560px){.sms-compose-foot{align-items:stretch;flex-direction:column;gap:10px}.sms-send{width:100%}}
</style>

<script>
(function(){
  const sel=document.getElementById('sms-user');
  const phone=document.getElementById('sms-phone');
  const msg=document.getElementById('sms-message');
  const count=document.getElementById('sms-count');
  const fa=n=>String(n).replace(/\d/g,d=>'۰۱۲۳۴۵۶۷۸۹'[d]);
  if(sel) sel.addEventListener('change',()=>{ if(sel.value) phone.value=sel.value; });
  document.querySelectorAll('[data-preset]').forEach(b=>b.addEventListener('click',()=>{msg.value=b.dataset.preset||'';msg.dispatchEvent(new Event('input'));msg.focus();}));
  if(msg){const upd=()=>count.textContent=fa(msg.value.length);msg.addEventListener('input',upd);upd();}
})();
</script>
{% endblock %}'''

TEMPLATES["sms.html"] = _SMS_TEMPLATE


_SMS_STATUS_LABELS = {
    "queued": "در صف",
    "claimed": "دریافت توسط گوشی",
    "dispatching": "در حال ارسال",
    "sent": "ارسال شد",
    "delivered": "تحویل شد",
    "failed": "خطا",
    "cancelled": "لغو شد",
}


def sms_admin_page(request: _SmsRequest, db: _SmsSession = _SmsDepends(get_db)):
    _sms_ensure_schema(db)

    grouped = {}
    for s in db.query(Subscription).filter(Subscription.phone.isnot(None)).order_by(Subscription.display_name.asc()).all():
        phone = str(s.phone or "").strip()
        if not phone:
            continue
        if phone not in grouped:
            grouped[phone] = {"phone": phone, "names": []}
        grouped[phone]["names"].append(str(s.display_name or "کاربر"))

    users = []
    for phone, item in grouped.items():
        names = item["names"]
        label = names[0] if len(names) == 1 else f"{names[0]} + {len(names)-1} اکانت"
        users.append({"phone": phone, "name": label})
    users.sort(key=lambda x: x["name"].lower())

    jobs = db.execute(_sms_text(
        """
        SELECT id, phone, message, status, created_at, device_id,
               sim_subscription_id, attempts, error
        FROM sms_jobs
        ORDER BY id DESC
        LIMIT 50
        """
    )).mappings().all()

    raw_devices = db.execute(_sms_text(
        """
        SELECT device_id, device_name, app_version, android_version,
               sim_subscription_id, last_seen
        FROM sms_devices
        ORDER BY last_seen DESC
        LIMIT 5
        """
    )).mappings().all()

    now = _sms_datetime.now(_sms_timezone.utc)
    devices = []
    for d in raw_devices:
        last_seen = d["last_seen"]
        if last_seen and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=_sms_timezone.utc)
        online = bool(last_seen and (now - last_seen).total_seconds() < 90)
        devices.append({
            "device_id": d["device_id"],
            "name": d["device_name"] or "Android Gateway",
            "app_version": d["app_version"],
            "android_version": d["android_version"],
            "sim_subscription_id": d["sim_subscription_id"],
            "last_seen": d["last_seen"],
            "online": online,
        })

    return render(
        "sms.html",
        request,
        users=users,
        jobs=jobs,
        devices=devices,
        status_labels=_SMS_STATUS_LABELS,
    )


def sms_queue(
    phone: str = _SmsForm(...),
    message: str = _SmsForm(...),
    db: _SmsSession = _SmsDepends(get_db),
):
    _sms_ensure_schema(db)
    normalized = _sms_normalize_phone(phone)
    body = str(message or "").strip()
    if not normalized or len(normalized) < 10 or len(normalized) > 15 or not body or len(body) > 1000:
        return _SmsRedirectResponse("/sms?error=1", 303)

    row = db.execute(
        _sms_text(
            """
            INSERT INTO sms_jobs(phone, message, status, source)
            VALUES (:phone, :message, 'queued', 'dashboard')
            RETURNING id
            """
        ),
        {"phone": normalized, "message": body},
    ).first()
    try:
        if "AuditEvent" in globals():
            db.add(AuditEvent(
                kind="sms_queue",
                message=f"SMS queued; job={row[0] if row else '?'}; phone={normalized}; chars={len(body)}",
            ))
    except Exception:
        pass
    db.commit()
    return _SmsRedirectResponse(f"/sms?queued=1&job={row[0] if row else ''}", 303)


def sms_retry(job_id: int, db: _SmsSession = _SmsDepends(get_db)):
    _sms_ensure_schema(db)
    result = db.execute(
        _sms_text(
            """
            UPDATE sms_jobs
            SET status='queued', claimed_at=NULL, dispatching_at=NULL,
                sent_at=NULL, delivered_at=NULL, failed_at=NULL,
                updated_at=NOW(), device_id=NULL, sim_subscription_id=NULL, error=NULL
            WHERE id=:id AND status='failed'
            """
        ),
        {"id": job_id},
    )
    db.commit()
    if not result.rowcount:
        return _SmsRedirectResponse("/sms?error=retry", 303)
    return _SmsRedirectResponse("/sms?retried=1", 303)


def sms_cancel(job_id: int, db: _SmsSession = _SmsDepends(get_db)):
    _sms_ensure_schema(db)
    db.execute(
        _sms_text(
            """
            UPDATE sms_jobs
            SET status='cancelled', updated_at=NOW()
            WHERE id=:id AND status='queued'
            """
        ),
        {"id": job_id},
    )
    db.commit()
    return _SmsRedirectResponse("/sms?cancelled=1", 303)


app.add_api_route("/sms", sms_admin_page, methods=["GET"])
app.add_api_route("/sms/send", sms_queue, methods=["POST"])
app.add_api_route("/sms/{job_id}/retry", sms_retry, methods=["POST"])
app.add_api_route("/sms/{job_id}/cancel", sms_cancel, methods=["POST"])


# Point the existing dashboard "ارسال پیام" quick action at the real SMS workspace.
_sms_dash = TEMPLATES.get("ref_dashboard.html", "")
if _sms_dash:
    _sms_dash = _sms_dash.replace(
        '<a class="focus-action focus-action-blue" href="/debts">',
        '<a class="focus-action focus-action-blue" href="/sms">',
        1,
    )
    TEMPLATES["ref_dashboard.html"] = _sms_dash


# Add one navigation entry without replacing the existing navigation structure.
_sms_base = TEMPLATES.get("base.html", "")
if _sms_base and 'href="/sms"' not in _sms_base:
    _sms_nav = r'''  <a href="/sms" class="{{ 'active' if request.url.path.startswith('/sms') else '' }}"><i>✉</i><span>پیامک</span></a>
'''
    _sms_base = _sms_base.replace("</nav>", _sms_nav + "</nav>", 1)
    TEMPLATES["base.html"] = _sms_base

if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)


# ---------------------------------------------------------------------------
# Debt desk one-click SMS
# ---------------------------------------------------------------------------
# Keep the workflow explicit:
#   SMS -> visible sent status -> operator manually moves the group to "waiting".
# Sending an SMS never changes billing/follow-up state by itself.
import re as _sms_debt_re

_SMS_DEBT_DEFAULT_TEXT = "سلام، وقت بخیر. برای مشاهده وضعیت اشتراک و تمدید آنلاین وارد پنل خود شوید:\\nhttps://hesab.filmjadiid.ir/my/"


_SMS_DEBT_STYLE = r'''
<style>
.debt-sms-form{margin:0}
.debt-sms-btn{border:1px solid rgba(96,165,250,.36);background:rgba(59,130,246,.09);color:#b9d8ff;border-radius:8px;padding:5px 9px;font:inherit;font-size:10px;font-weight:850;cursor:pointer;white-space:nowrap;transition:.15s ease}
.debt-sms-btn:hover{background:rgba(59,130,246,.16);border-color:rgba(96,165,250,.58);color:#e4f0ff}
.debt-sms-btn:disabled{cursor:default;opacity:1}
.debt-sms-btn.sms-pending{border-color:rgba(250,204,21,.30);background:rgba(250,204,21,.07);color:#f8df82}
.debt-sms-btn.sms-sent{border-color:rgba(34,197,94,.34);background:rgba(34,197,94,.09);color:#adf3c0}
.debt-sms-btn.sms-failed{border-color:rgba(248,113,113,.34);background:rgba(239,68,68,.08);color:#ffc0c5}
.debt-sms-btn.sms-no-phone{border-color:rgba(148,163,184,.14);background:rgba(148,163,184,.04);color:#697487}
</style>
'''

_SMS_DEBT_FORM = r'''
      <form method="post" action="/sms/debt-send" data-preserve-position class="debt-sms-form"
            data-debt-sms-form
            data-sms-phone="{{ g.phone or '' }}"
            data-sms-cycle="{{ g.first_expiry or '' }}">
        <input type="hidden" name="phone" value="{{ g.phone or '' }}">
        <input type="hidden" name="cycle" value="{{ g.first_expiry or '' }}">
        {% if g.phone %}
          <button type="submit" class="debt-sms-btn" data-debt-sms-btn>✉ ارسال پیامک</button>
        {% else %}
          <button type="button" class="debt-sms-btn sms-no-phone" disabled>بدون شماره</button>
        {% endif %}
      </form>
'''

_SMS_DEBT_SCRIPT = r'''
<script>
(function(){
  const forms=[...document.querySelectorAll('[data-debt-sms-form]')];
  if(!forms.length) return;

  const keyOf=f=>(f.dataset.smsPhone||'')+'|'+(f.dataset.smsCycle||'');

  function paint(form,status){
    const btn=form.querySelector('[data-debt-sms-btn]');
    if(!btn) return;
    btn.classList.remove('sms-pending','sms-sent','sms-failed');
    btn.disabled=false;

    if(status==='queued'){
      btn.classList.add('sms-pending');
      btn.textContent='… پیامک در صف';
      btn.disabled=true;
    }else if(status==='claimed' || status==='dispatching'){
      btn.classList.add('sms-pending');
      btn.textContent='… در حال ارسال';
      btn.disabled=true;
    }else if(status==='sent' || status==='delivered'){
      btn.classList.add('sms-sent');
      btn.textContent='✓ پیامک ارسال شد';
      btn.disabled=true;
    }else if(status==='failed'){
      btn.classList.add('sms-failed');
      btn.textContent='↻ خطا؛ ارسال دوباره';
      btn.disabled=false;
    }else{
      btn.textContent='✉ ارسال پیامک';
    }
  }

  async function refresh(){
    try{
      const res=await fetch('/sms/debt-status',{headers:{'Accept':'application/json'},cache:'no-store'});
      if(!res.ok) return;
      const data=await res.json();
      const states=(data&&data.states)||{};
      forms.forEach(f=>paint(f,states[keyOf(f)]||''));
    }catch(_e){}
  }

  forms.forEach(form=>{
    form.addEventListener('submit',()=>{
      const btn=form.querySelector('[data-debt-sms-btn]');
      if(btn){
        btn.disabled=true;
        btn.classList.add('sms-pending');
        btn.textContent='… در حال ثبت';
      }
    });
  });

  refresh();
  let rounds=0;
  const timer=setInterval(()=>{
    rounds++;
    refresh();
    if(rounds>=15) clearInterval(timer);
  },4000);
})();
</script>
'''

_sms_debt_tpl = TEMPLATES.get("debts.html", "")
if _sms_debt_tpl and "/sms/debt-send" not in _sms_debt_tpl:
    _sms_debt_tpl = _sms_debt_tpl.replace(
        "{% block content %}",
        "{% block content %}" + _SMS_DEBT_STYLE,
        1,
    )

    _sms_track_pattern = _sms_debt_re.compile(
        r'(<form\s+method="post"\s+action="/followups/track-group".*?</form>)',
        flags=_sms_debt_re.S,
    )
    _sms_match = _sms_track_pattern.search(_sms_debt_tpl)
    if _sms_match:
        _sms_debt_tpl = (
            _sms_debt_tpl[:_sms_match.start()]
            + _SMS_DEBT_FORM
            + _sms_debt_tpl[_sms_match.start():]
        )

    _sms_last_endblock = _sms_debt_tpl.rfind("{% endblock %}")
    if _sms_last_endblock >= 0:
        _sms_debt_tpl = (
            _sms_debt_tpl[:_sms_last_endblock]
            + _SMS_DEBT_SCRIPT
            + _sms_debt_tpl[_sms_last_endblock:]
        )

    TEMPLATES["debts.html"] = _sms_debt_tpl


def _sms_debt_source(cycle):
    raw = str(cycle or "").strip()
    if not _sms_debt_re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raw = "unknown"
    return "debt:" + raw


def sms_debt_send(
    phone: str = _SmsForm(...),
    cycle: str = _SmsForm(""),
    db: _SmsSession = _SmsDepends(get_db),
):
    _sms_ensure_schema(db)
    normalized = _sms_normalize_phone(phone)
    if not normalized:
        return _SmsRedirectResponse("/debts?sms_error=phone", 303)

    states = _followup_states(db) if "_followup_states" in globals() else {}
    candidates = (
        db.query(Subscription)
        .filter(
            Subscription.phone == normalized,
            Subscription.is_free.is_(False),
        )
        .order_by(Subscription.id.asc())
        .all()
    )
    actionable = [
        s for s in candidates
        if current_debt_for(s, today_local()) > 0
        and states.get(s.id) not in ("waiting", "cut")
    ]
    if not actionable:
        return _SmsRedirectResponse("/debts?sms_error=not_actionable", 303)

    source = _sms_debt_source(cycle)
    row = db.execute(
        _sms_text(
            """
            INSERT INTO sms_jobs(phone, message, status, source)
            VALUES (:phone, :message, 'queued', :source)
            RETURNING id
            """
        ),
        {
            "phone": normalized,
            "message": _SMS_DEBT_DEFAULT_TEXT,
            "source": source,
        },
    ).first()

    try:
        if "AuditEvent" in globals():
            db.add(AuditEvent(
                kind="sms_queue",
                message=(
                    f"Debt SMS queued; job={row[0] if row else '?'}; "
                    f"phone={normalized}; source={source}; "
                    f"accounts={','.join(str(s.id) for s in actionable)}"
                ),
            ))
    except Exception:
        pass

    db.commit()
    return _SmsRedirectResponse(
        f"/debts?sms_queued=1&job={row[0] if row else ''}",
        303,
    )


def sms_debt_status(db: _SmsSession = _SmsDepends(get_db)):
    _sms_ensure_schema(db)
    rows = db.execute(
        _sms_text(
            """
            SELECT DISTINCT ON (phone, source)
                   phone, source, status, id
            FROM sms_jobs
            WHERE source LIKE 'debt:%'
            ORDER BY phone, source, id DESC
            """
        )
    ).mappings().all()

    states = {}
    for row in rows:
        cycle = str(row["source"] or "")[5:]
        states[f"{row['phone']}|{cycle}"] = row["status"]

    return {"ok": True, "states": states}


app.add_api_route("/sms/debt-send", sms_debt_send, methods=["POST"])
app.add_api_route("/sms/debt-status", sms_debt_status, methods=["GET"])

if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)


# ---------------------------------------------------------------------------
# Ayria APG: create a payment from the debt desk, enqueue returned payment URL
# through the existing personal-SIM SMS gateway, then move the group to waiting.
# ---------------------------------------------------------------------------
import json as _ayria_json
import os as _ayria_os
import time as _ayria_time
import urllib.error as _ayria_urlerror
import urllib.request as _ayria_urlrequest


_AYRIA_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS ayria_payment_requests (
        id BIGSERIAL PRIMARY KEY,
        phone VARCHAR(32) NOT NULL,
        cycle_key VARCHAR(96) NOT NULL,
        amount_toman BIGINT NOT NULL,
        amount_rial BIGINT NOT NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'creating',
        reference_code VARCHAR(160),
        tracking_number VARCHAR(160),
        payment_url TEXT,
        sms_job_id BIGINT,
        error TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(phone, cycle_key)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_ayria_requests_phone ON ayria_payment_requests(phone, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_ayria_requests_reference ON ayria_payment_requests(reference_code)",
)


def _ayria_ensure_schema(db):
    for stmt in _AYRIA_SCHEMA:
        db.execute(_sms_text(stmt))
    db.commit()


def _ayria_settings():
    base = (_ayria_os.environ.get("AYRIA_API_BASE") or "https://api.ayriaclub.ir").rstrip("/")
    api_key = (_ayria_os.environ.get("AYRIA_APG_API_KEY") or "").strip()
    wallet_id = (_ayria_os.environ.get("AYRIA_APG_WALLET_ID") or "").strip()
    referral_raw = (_ayria_os.environ.get("AYRIA_REFERRAL_CODE") or "").strip()

    if not api_key or not wallet_id or not referral_raw:
        raise RuntimeError("Ayria APG environment is incomplete")

    try:
        referral = int(referral_raw)
    except Exception as exc:
        raise RuntimeError("AYRIA_REFERRAL_CODE is invalid") from exc

    return base, api_key, wallet_id, referral


def _ayria_create_payment(payload):
    base, api_key, wallet_id, _referral = _ayria_settings()
    body = _ayria_json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = _ayria_urlrequest.Request(
        base + "/apg/v1/create",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "Accept": "application/json",
            "APG-API-KEY": api_key,
            "APG-WALLET-ID": wallet_id,
        },
    )
    try:
        with _ayria_urlrequest.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            code = int(getattr(resp, "status", 200) or 200)
    except _ayria_urlerror.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        raise RuntimeError(f"Ayria HTTP {exc.code}: {raw[:500]}") from exc
    except Exception as exc:
        raise RuntimeError(f"Ayria connection error: {type(exc).__name__}") from exc

    if code < 200 or code >= 300:
        raise RuntimeError(f"Ayria HTTP {code}")

    try:
        data = _ayria_json.loads(raw)
    except Exception as exc:
        raise RuntimeError("Ayria returned invalid JSON") from exc

    payment_url = str(data.get("paymentUrl") or "").strip()
    reference_code = str(data.get("referenceCode") or "").strip()
    if not payment_url or not reference_code:
        raise RuntimeError("Ayria response is missing paymentUrl/referenceCode")

    return data


_AYRIA_DEBT_STYLE = r'''
<style>
.ayria-pay-form{margin:0}
.ayria-pay-btn{border:1px solid rgba(168,85,247,.38);background:rgba(168,85,247,.09);color:#dfc4ff;border-radius:8px;padding:5px 9px;font:inherit;font-size:10px;font-weight:850;cursor:pointer;white-space:nowrap;transition:.15s ease}
.ayria-pay-btn:hover{background:rgba(168,85,247,.17);border-color:rgba(192,132,252,.58);color:#f1e4ff}
.ayria-pay-btn:disabled{opacity:.58;cursor:wait}
</style>
'''

_AYRIA_DEBT_FORM = r'''
      <form method="post" action="/ayria/debt-create" data-preserve-position class="ayria-pay-form"
            onsubmit="const b=this.querySelector('button'); if(b){b.disabled=true;b.textContent='… ساخت درگاه';} return confirm('درگاه پرداخت {{ g.debt|money }} تومان در Ayria ساخته و لینک آن برای {{ g.phone or 'این کاربر' }} ارسال شود؟');">
        <input type="hidden" name="phone" value="{{ g.phone or '' }}">
        {% if g.phone %}
          <button type="submit" class="ayria-pay-btn" title="مبلغ: {{ g.debt|money }} تومان">◆ ارسال لینک پرداخت</button>
        {% else %}
          <button type="button" class="ayria-pay-btn" disabled>بدون شماره</button>
        {% endif %}
      </form>
'''

_ayria_debt_tpl = TEMPLATES.get("debts.html", "")
if _ayria_debt_tpl and "/ayria/debt-create" not in _ayria_debt_tpl:
    _ayria_debt_tpl = _ayria_debt_tpl.replace(
        "{% block content %}",
        "{% block content %}" + _AYRIA_DEBT_STYLE,
        1,
    )

    _ayria_sms_pattern = _sms_debt_re.compile(
        r'(<form\s+method="post"\s+action="/sms/debt-send".*?</form>)',
        flags=_sms_debt_re.S,
    )
    _ayria_match = _ayria_sms_pattern.search(_ayria_debt_tpl)
    if _ayria_match:
        _ayria_debt_tpl = (
            _ayria_debt_tpl[:_ayria_match.end()]
            + _AYRIA_DEBT_FORM
            + _ayria_debt_tpl[_ayria_match.end():]
        )

    _ayria_banner_anchor = "{% block content %}"
    _ayria_banners = r'''
{% if request.query_params.get("ayria_error") == "config" %}<div class="manage-banner error">اتصال Ayria هنوز روی سرور تنظیم نشده است.</div>{% endif %}
{% if request.query_params.get("ayria_error") == "phone" %}<div class="manage-banner error">شماره همراه این سرگروه معتبر نیست.</div>{% endif %}
{% if request.query_params.get("ayria_error") == "api" %}<div class="manage-banner error">ساخت درگاه در Ayria ناموفق بود؛ هیچ کاربری به «در انتظار» منتقل نشد.</div>{% endif %}
{% if request.query_params.get("ayria_error") == "duplicate" %}<div class="manage-banner error">برای همین دوره قبلاً یک درخواست Ayria ساخته شده است.</div>{% endif %}
'''
    _ayria_debt_tpl = _ayria_debt_tpl.replace(
        _ayria_banner_anchor,
        _ayria_banner_anchor + _ayria_banners,
        1,
    )
    TEMPLATES["debts.html"] = _ayria_debt_tpl


_ayria_wait_tpl = TEMPLATES.get("followups.html", "")
if _ayria_wait_tpl and "ayria_link_sent" not in _ayria_wait_tpl:
    _ayria_wait_banner = r'''
{% if request.query_params.get("ayria_link_sent") %}<div class="collect-success">✓ درگاه Ayria ساخته شد، لینک پرداخت در صف SMS قرار گرفت و سرگروه به «در انتظار» منتقل شد.</div>{% endif %}
{% if request.query_params.get("ayria_existing") %}<div class="collect-success">برای این دوره قبلاً درگاه Ayria ساخته شده بود؛ سرگروه در «در انتظار» نگه داشته شد.</div>{% endif %}
'''
    _ayria_wait_tpl = _ayria_wait_tpl.replace(
        "{% block content %}",
        "{% block content %}" + _ayria_wait_banner,
        1,
    )
    TEMPLATES["followups.html"] = _ayria_wait_tpl


def ayria_debt_create(
    phone: str = _SmsForm(...),
    db: _SmsSession = _SmsDepends(get_db),
):
    _sms_ensure_schema(db)
    _ayria_ensure_schema(db)

    normalized = _sms_normalize_phone(phone)
    if not normalized:
        return _SmsRedirectResponse("/debts?ayria_error=phone", 303)

    try:
        _base, _api_key, _wallet_id, referral = _ayria_settings()
    except Exception:
        return _SmsRedirectResponse("/debts?ayria_error=config", 303)

    refresh_billing(db)
    states = _followup_states(db) if "_followup_states" in globals() else {}
    candidates = (
        db.query(Subscription)
        .filter(
            Subscription.phone == normalized,
            Subscription.is_free.is_(False),
        )
        .order_by(Subscription.expiry_date.asc().nullslast(), Subscription.id.asc())
        .all()
    )
    actionable = [
        s for s in candidates
        if current_debt_for(s, today_local()) > 0
        and states.get(s.id) not in ("waiting", "cut")
    ]
    if not actionable:
        return _SmsRedirectResponse("/debts?ayria_error=duplicate", 303)

    amount_toman = sum(int(current_debt_for(s, today_local()) or 0) for s in actionable)
    if amount_toman <= 0:
        return _SmsRedirectResponse("/debts?ayria_error=duplicate", 303)

    amount_rial = amount_toman * 10
    expiries = [s.expiry_date for s in actionable if s.expiry_date]
    first_expiry = min(expiries).isoformat() if expiries else "no-expiry"
    cycle_key = f"{first_expiry}:{amount_toman}"

    existing = db.execute(
        _sms_text(
            """
            SELECT id, status, payment_url, reference_code
            FROM ayria_payment_requests
            WHERE phone=:phone AND cycle_key=:cycle
            LIMIT 1
            """
        ),
        {"phone": normalized, "cycle": cycle_key},
    ).mappings().first()

    if existing:
        if existing["status"] in ("created", "sms_queued", "waiting"):
            for s in actionable:
                _followup_set(
                    db,
                    s.id,
                    "waiting",
                    f"Ayria existing payment; reference={existing['reference_code'] or ''}; phone={normalized}",
                )
            db.commit()
            return _SmsRedirectResponse("/followups?ayria_existing=1", 303)
        return _SmsRedirectResponse("/debts?ayria_error=duplicate", 303)

    reserve = db.execute(
        _sms_text(
            """
            INSERT INTO ayria_payment_requests(
                phone, cycle_key, amount_toman, amount_rial, status
            )
            VALUES (:phone, :cycle, :toman, :rial, 'creating')
            RETURNING id
            """
        ),
        {
            "phone": normalized,
            "cycle": cycle_key,
            "toman": amount_toman,
            "rial": amount_rial,
        },
    ).first()
    request_id = int(reserve[0])
    db.commit()

    names = [str(s.display_name or "").strip() for s in actionable if str(s.display_name or "").strip()]
    payer_name = ("، ".join(names[:3]) or "کاربر")[:255]
    subscription_ids = [int(s.id) for s in actionable]
    payment_number = f"hesab-{request_id}-{int(_ayria_time.time())}"

    payload = {
        "referralCode": referral,
        "amount": amount_rial,
        "payerMobile": normalized,
        "payerName": payer_name,
        "description": "تمدید اشتراک",
        "paymentNumber": payment_number,
        "extraData": _ayria_json.dumps(
            {
                "source": "hesab",
                "requestId": request_id,
                "phone": normalized,
                "subscriptionIds": subscription_ids,
                "amountToman": amount_toman,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "issuerMustVerifyPayment": False,
    }

    try:
        response = _ayria_create_payment(payload)
    except Exception as exc:
        db.execute(
            _sms_text(
                """
                UPDATE ayria_payment_requests
                SET status='failed', error=:error, updated_at=NOW()
                WHERE id=:id
                """
            ),
            {"id": request_id, "error": str(exc)[:1000]},
        )
        try:
            if "AuditEvent" in globals():
                db.add(AuditEvent(
                    kind="ayria_payment_error",
                    message=f"Ayria create failed; request={request_id}; phone={normalized}; amount_toman={amount_toman}",
                ))
        except Exception:
            pass
        db.commit()
        return _SmsRedirectResponse("/debts?ayria_error=api", 303)

    payment_url = str(response.get("paymentUrl") or "").strip()
    reference_code = str(response.get("referenceCode") or "").strip()
    tracking_number = str(response.get("trackingNumber") or "").strip()

    sms_text = (
        "سلام، لینک پرداخت تمدید اشتراک شما:\n"
        + payment_url
        + "\nمبلغ: "
        + f"{amount_toman:,}"
        + " تومان"
    )

    sms_row = db.execute(
        _sms_text(
            """
            INSERT INTO sms_jobs(phone, message, status, source)
            VALUES (:phone, :message, 'queued', :source)
            RETURNING id
            """
        ),
        {
            "phone": normalized,
            "message": sms_text,
            "source": "ayria:" + reference_code,
        },
    ).first()
    sms_job_id = int(sms_row[0])

    db.execute(
        _sms_text(
            """
            UPDATE ayria_payment_requests
            SET status='sms_queued',
                reference_code=:reference,
                tracking_number=:tracking,
                payment_url=:url,
                sms_job_id=:sms_job,
                error=NULL,
                updated_at=NOW()
            WHERE id=:id
            """
        ),
        {
            "id": request_id,
            "reference": reference_code,
            "tracking": tracking_number,
            "url": payment_url,
            "sms_job": sms_job_id,
        },
    )

    for s in actionable:
        _followup_set(
            db,
            s.id,
            "waiting",
            (
                f"Ayria payment link queued; reference={reference_code}; "
                f"request={request_id}; sms_job={sms_job_id}; phone={normalized}"
            ),
        )

    try:
        if "AuditEvent" in globals():
            db.add(AuditEvent(
                kind="ayria_payment_create",
                message=(
                    f"Ayria payment created; request={request_id}; reference={reference_code}; "
                    f"phone={normalized}; amount_toman={amount_toman}; sms_job={sms_job_id}; "
                    f"subscriptions={subscription_ids}"
                ),
            ))
    except Exception:
        pass

    db.execute(
        _sms_text(
            "UPDATE ayria_payment_requests SET status='waiting', updated_at=NOW() WHERE id=:id"
        ),
        {"id": request_id},
    )
    db.commit()

    return _SmsRedirectResponse(
        f"/followups?ayria_link_sent=1&request={request_id}",
        303,
    )


app.add_api_route("/ayria/debt-create", ayria_debt_create, methods=["POST"])

if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)
