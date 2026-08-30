# Hesab VPN follow-up workflow: debt inbox -> waiting -> paid/cut.
import re


def _followup_event_sid(message):
    m = re.search(r"\bsid=(\d+)\b", str(message or ""))
    return int(m.group(1)) if m else None


def _followup_states(db):
    states = {}
    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.kind.in_(["followup_waiting", "followup_cut", "followup_clear"]))
        .order_by(AuditEvent.id.desc())
        .all()
    )
    for ev in events:
        sid = _followup_event_sid(ev.message)
        if sid is None or sid in states:
            continue
        if ev.kind == "followup_waiting":
            states[sid] = "waiting"
        elif ev.kind == "followup_cut":
            states[sid] = "cut"
        else:
            states[sid] = None
    return states


def _followup_set(db, sid, state, extra=""):
    kind = {
        "waiting": "followup_waiting",
        "cut": "followup_cut",
        None: "followup_clear",
    }[state]
    db.add(AuditEvent(kind=kind, message=f"sid={int(sid)}; {extra}".strip()))


def _followup_autoclear_zero_debt(db):
    states = _followup_states(db)
    changed = False
    for sid, state in list(states.items()):
        if state != "waiting":
            continue
        s = db.get(Subscription, sid)
        if not s or current_debt_for(s, today_local()) <= 0:
            _followup_set(db, sid, None, "auto clear: no current debt")
            changed = True
    if changed:
        db.commit()
        states = _followup_states(db)
    return states


def _group_debt_rows(rows):
    grouped = {}
    for s in rows:
        periods = debt_periods_for(s)
        debt = current_debt_for(s)
        key = f"phone:{s.phone}" if s.phone else f"service:{s.id}"
        if key not in grouped:
            grouped[key] = {
                "phone": s.phone,
                "rows": [],
                "debt": 0,
                "services": 0,
                "first_expiry": s.expiry_date,
            }
        g = grouped[key]
        g["rows"].append({"s": s, "periods": periods, "debt": debt})
        g["debt"] += debt
        g["services"] += 1
        if s.expiry_date and (not g["first_expiry"] or s.expiry_date < g["first_expiry"]):
            g["first_expiry"] = s.expiry_date
    groups = list(grouped.values())
    for g in groups:
        names = [x["s"].display_name for x in g["rows"]]
        g["primary_name"] = names[0] if len(names) == 1 else "، ".join(names[:2]) + (f" +{len(names)-2}" if len(names) > 2 else "")
        g["search_text"] = ((g.get("phone") or "") + " " + " ".join(names)).lower()
    groups.sort(key=lambda g: (g["first_expiry"] or date.max, -(g["debt"] or 0)))
    return groups


# Add "در انتظار" after the debt nav item without depending on exact surrounding markup.
_base = TEMPLATES.get("base.html", "")
if _base and 'href="/followups"' not in _base:
    m = re.search(r'(<a[^>]+href="/debts"[^>]*>.*?</a>)', _base, flags=re.S)
    if m:
        _base = _base.replace(m.group(1), m.group(1) + '<a href="/followups"><span>⏳</span><b>در انتظار</b></a>', 1)
        TEMPLATES["base.html"] = _base


# Add the follow-up action to every collapsed debt group.
_debt_tpl = TEMPLATES.get("debts.html", "")
if _debt_tpl:
    track_button = r'''
      <form method="post" action="/followups/track-group" data-preserve-position class="followup-track-form">
        <input type="hidden" name="phone" value="{{ g.phone or '' }}">
        <input type="hidden" name="sid" value="{% if not g.phone %}{{ g.rows[0].s.id }}{% else %}0{% endif %}">
        <button type="submit" class="followup-track-btn" title="بعد از ارسال پیام بزن">✓ پیگیری شد</button>
      </form>
'''
    marker = '<div class="group-action-row">'
    if marker in _debt_tpl and "/followups/track-group" not in _debt_tpl:
        _debt_tpl = _debt_tpl.replace(marker, marker + track_button, 1)

    banner_anchor = '{% if request.query_params.get("phone_updated") %}<div class="manage-banner">✓ شماره همراه اصلاح شد و گروه‌بندی کاربران دوباره انجام شد.</div>{% endif %}'
    if banner_anchor in _debt_tpl:
        _debt_tpl = _debt_tpl.replace(
            banner_anchor,
            banner_anchor + '\n{% if request.query_params.get("tracked") %}<div class="manage-banner">✓ مورد به «در انتظار» منتقل شد.</div>{% endif %}\n{% if request.query_params.get("restored") %}<div class="manage-banner">✓ مورد به بدهی‌ها برگشت.</div>{% endif %}',
            1,
        )

    for old in ("v=2", "v=3", "v=4", "v=5", "v=6", "v=7", "v=8"):
        _debt_tpl = _debt_tpl.replace(old, "v=9")
    TEMPLATES["debts.html"] = _debt_tpl


FOLLOWUPS_TEMPLATE = r'''{% extends "base.html" %}
{% block title %}در انتظار · حساب VPN{% endblock %}
{% block heading %}در انتظار پرداخت{% endblock %}
{% block subheading %}فقط کاربرهایی که پیام سررسید برایشان ارسال شده اینجا می‌مانند{% endblock %}
{% block content %}
{% if request.query_params.get("paid") %}<div class="collect-success">✓ پرداخت ثبت شد و اکانت از انتظار خارج شد.</div>{% endif %}
{% if request.query_params.get("cut") %}<div class="collect-error">اکانت به وضعیت «قطع شد» منتقل شد و دیگر در بدهی‌ها نمایش داده نمی‌شود.</div>{% endif %}
{% if request.query_params.get("restored") %}<div class="collect-success">✓ اکانت دوباره به صفحه بدهی‌ها برگشت.</div>{% endif %}

<section class="waiting-summary">
  <div><small>پرداخت‌کننده در انتظار</small><strong>{{ groups|length|fa }}</strong></div>
  <div><small>اکانت در انتظار</small><strong>{{ service_count|fa }}</strong></div>
  <div><small>جمع بدهی در انتظار</small><strong>{{ total|money }} <em>تومان</em></strong></div>
</section>

<div class="waiting-list">
{% for g in groups %}
  <section class="waiting-group">
    <header class="waiting-head">
      <div><small>نام</small><strong>{{ g.primary_name }}</strong></div>
      <div><small>شماره همراه</small>{% if g.phone %}<button type="button" class="waiting-phone" data-copy="{{ g.phone }}">{{ g.phone }}</button>{% else %}<strong>بدون شماره</strong>{% endif %}</div>
      <div><small>جمع بدهی</small><strong>{{ g.debt|money }} تومان</strong></div>
    </header>
    <div class="waiting-services">
      {% for item in g.rows %}{% set s=item.s %}
      <div class="waiting-service">
        <div class="waiting-identity">
          <a href="/users/{{ s.id }}">{{ s.display_name }}</a>
          <span>انقضا {{ s.expiry_date|jdate }}</span>
        </div>
        <div class="waiting-debt"><small>بدهی</small><b>{{ item.debt|money }} تومان</b></div>
        <div class="waiting-actions">
          <form method="post" action="/followups/{{ s.id }}/pay" onsubmit="return confirm('پرداخت {{ item.debt|money }} تومان ثبت شود؟')"><button class="waiting-pay">پرداخت شد</button></form>
          <form method="post" action="/followups/{{ s.id }}/cut" onsubmit="return confirm('این اکانت از لیست انتظار خارج و به حالت قطع‌شده منتقل شود؟')"><button class="waiting-cut">قطع شد</button></form>
          <form method="post" action="/followups/{{ s.id }}/restore"><button class="waiting-restore">برگردان</button></form>
        </div>
      </div>
      {% endfor %}
    </div>
  </section>
{% else %}
  <div class="empty debt-empty">فعلاً هیچ کاربری در انتظار پرداخت نیست.</div>
{% endfor %}
</div>
<div id="copy-toast" class="copy-toast">کپی شد</div>
{% endblock %}'''

TEMPLATES["followups.html"] = FOLLOWUPS_TEMPLATE
if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)


def debts_followup(request: Request, paid: int = 0, adjusted: int = 0, adjust_error: int = 0, db: Session = Depends(get_db)):
    refresh_billing(db)
    states = _followup_autoclear_zero_debt(db)
    rows = db.query(Subscription).filter(
        Subscription.is_free.is_(False), Subscription.debt_toman > 0
    ).order_by(Subscription.expiry_date.asc().nullslast(), Subscription.display_name.asc()).all()
    rows = [s for s in rows if states.get(s.id) not in ("waiting", "cut")]
    groups = _group_debt_rows(rows)
    return render(
        "debts.html",
        request,
        groups=groups,
        total=sum(g["debt"] for g in groups),
        service_count=len(rows),
        paid=bool(paid),
        adjusted=bool(adjusted),
        adjust_error=bool(adjust_error),
    )


def followups_page(request: Request, db: Session = Depends(get_db)):
    refresh_billing(db)
    states = _followup_autoclear_zero_debt(db)
    waiting_ids = [sid for sid, state in states.items() if state == "waiting"]
    if waiting_ids:
        rows = db.query(Subscription).filter(Subscription.id.in_(waiting_ids)).all()
    else:
        rows = []
    rows = [s for s in rows if not s.is_free and current_debt_for(s) > 0]
    groups = _group_debt_rows(rows)
    return render(
        "followups.html",
        request,
        groups=groups,
        service_count=len(rows),
        total=sum(g["debt"] for g in groups),
    )


def track_followup_group(phone: str = Form(""), sid: int = Form(0), db: Session = Depends(get_db)):
    refresh_billing(db)
    states = _followup_states(db)
    if phone:
        candidates = db.query(Subscription).filter(Subscription.phone == phone, Subscription.is_free.is_(False)).all()
    else:
        s = db.get(Subscription, int(sid or 0))
        candidates = [s] if s else []
    marked = 0
    for s in candidates:
        if not s or current_debt_for(s) <= 0 or states.get(s.id) in ("waiting", "cut"):
            continue
        _followup_set(db, s.id, "waiting", f"phone={s.phone or ''}; name={s.display_name}")
        marked += 1
    if marked:
        db.commit()
    return RedirectResponse("/debts?tracked=1", 303)


def followup_pay(sid: int, db: Session = Depends(get_db)):
    refresh_billing(db)
    s = db.get(Subscription, sid)
    if not s or s.is_free:
        return RedirectResponse("/followups", 303)
    periods = debt_periods_for(s)
    amount = current_debt_for(s)
    if periods <= 0 or amount <= 0:
        _followup_set(db, sid, None, "payment route: no debt")
        db.commit()
        return RedirectResponse("/followups", 303)
    prev = s.expiry_date
    s.expiry_date = add_jalali_months(s.expiry_date, periods)
    s.debt_toman = 0
    s.payment_status = "paid"
    s.billing_cursor_date = today_local()
    db.add(Payment(
        subscription_id=s.id,
        amount_toman=amount,
        periods=periods,
        previous_expiry=prev,
        new_expiry=s.expiry_date,
        note="ثبت واریز از صفحه در انتظار",
    ))
    db.add(AuditEvent(kind="payment", message=f"Waiting payment {amount}; sid={s.id}; name={s.display_name}"))
    _followup_set(db, sid, None, "paid from waiting page")
    db.commit()
    return RedirectResponse("/followups?paid=1", 303)


def followup_cut(sid: int, db: Session = Depends(get_db)):
    s = db.get(Subscription, sid)
    if s:
        _followup_set(db, sid, "cut", f"marked cut; phone={s.phone or ''}; name={s.display_name}; debt={int(s.debt_toman or 0)}")
        db.commit()
    return RedirectResponse("/followups?cut=1", 303)


def followup_restore(sid: int, db: Session = Depends(get_db)):
    s = db.get(Subscription, sid)
    if s:
        _followup_set(db, sid, None, f"restored to debt inbox; name={s.display_name}")
        db.commit()
    return RedirectResponse("/debts?restored=1", 303)


# Replace debt GET once more so waiting/cut accounts stay out of the inbox.
app.router.routes[:] = [
    r for r in app.router.routes
    if not (getattr(r, "path", None) == "/debts" and "GET" in (getattr(r, "methods", set()) or set()))
]
app.add_api_route("/debts", debts_followup, methods=["GET"])
app.add_api_route("/followups", followups_page, methods=["GET"])
app.add_api_route("/followups/track-group", track_followup_group, methods=["POST"])
app.add_api_route("/followups/{sid}/pay", followup_pay, methods=["POST"])
app.add_api_route("/followups/{sid}/cut", followup_cut, methods=["POST"])
app.add_api_route("/followups/{sid}/restore", followup_restore, methods=["POST"])
