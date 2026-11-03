# HESAB_PAYMENT_TOTALS_V1
# READ-ONLY UI: all-time ledger sum + per-day deposits prominently in header.
# Appended LAST to mounted admin overlay after optional V5/V6 search fixes.
# Never changes Payment rows, undo POST, billing, customer portal or SMS.
from fastapi import Request as _pts_Request, Depends as _pts_Depends
from sqlalchemy.orm import Session as _pts_Session
from sqlalchemy import func as _pts_func

_PTS_TEMPLATE = TEMPLATES.get("payments.html", "")
if not _PTS_TEMPLATE or _PTS_TEMPLATE.count("{% block content %}") != 1:
    raise RuntimeError("Payment totals: current payments template unavailable")
if "pts-total-card" in _PTS_TEMPLATE:
    raise RuntimeError("Payment totals: duplicate UI patch")

_PTS_SUMMARY = r'''
<section class="pts-total-card" aria-label="جمع کل پرداخت‌های ثبت‌شده">
 <div class="pts-total-intro">
  <p>جمع کل پرداخت‌های ثبت‌شده</p>
  <small>از ابتدای سوابق موجود در حساب VPN</small>
 </div>
 <div class="pts-total-numbers">
  <strong>{{ request.state.pts_total|money }} <small>تومان</small></strong>
  <span>{{ request.state.pts_count|fa }} پرداخت ثبت‌شده</span>
 </div>
</section>
'''
_PTS_CSS = r'''
<style>
.pts-total-card{display:flex;direction:rtl;align-items:center;justify-content:space-between;gap:18px;
 padding:19px 22px;margin:0 0 18px;border:1px solid #3b5069;border-radius:16px;
 background:linear-gradient(110deg,#142338,#0f1929);color:#f7fbff;box-shadow:0 9px 22px #0002}
.pts-total-intro p{font-size:17px;font-weight:850;margin:0 0 7px}
.pts-total-intro small{font-size:11px;color:#9cb4cc;line-height:1.6}
.pts-total-numbers{text-align:left;direction:rtl}
.pts-total-numbers strong{font-size:clamp(23px,3vw,32px);font-weight:900;display:block;
 color:#b4f0ac;font-variant-numeric:tabular-nums;white-space:nowrap}
.pts-total-numbers strong small{font-size:13px;color:#c8e9c3}
.pts-total-numbers span{display:block;font-size:11px;color:#b7c8d9;margin-top:5px}
.op-pay-day h2.pts-day-heading{display:flex;align-items:center;justify-content:space-between;
 flex-wrap:wrap;gap:12px;line-height:1.6;padding:14px 16px}
.pts-day-date{font-size:15px;font-weight:850}
.pts-day-date small{display:block;font-size:11px;color:#aebfd0;font-weight:500}
.pts-day-value{text-align:left;direction:rtl}
.pts-day-value small{display:block;font-size:11px;color:#aebfd0}
.pts-day-value strong{font-size:18px;font-weight:850;color:#b4f0ac}
.pf-day-head{line-height:1.9;font-size:15px;padding:13px 16px}
@media(max-width:640px){
 .pts-total-card{padding:15px;align-items:flex-start;flex-direction:column;gap:13px}
 .pts-total-numbers{text-align:right}
 .op-pay-day h2.pts-day-heading{align-items:flex-start}
 .pts-day-value{text-align:right}
}
</style>
'''
_PTS_TEMPLATE = _PTS_TEMPLATE.replace(
    "{% block content %}", "{% block content %}\n" + _PTS_CSS + _PTS_SUMMARY, 1
)

if ('id="op-pay-query"' in _PTS_TEMPLATE
        and '<section class="op-pay-day">' in _PTS_TEMPLATE):
    _pts_old_heading = (
        '<h2>{{ day.label }} · {{ day.items|length|fa }} پرداخت · '
        '{{ day.total|money }} تومان</h2>'
    )
    _pts_new_heading = (
        '<h2 class="pts-day-heading">'
        '<span class="pts-day-date">{{ day.label }}'
        '<small>{{ day.items|length|fa }} پرداخت</small></span>'
        '<span class="pts-day-value"><small>جمع واریزی روز</small>'
        '<strong>{{ day.total|money }} تومان</strong></span>'
        '</h2>'
    )
    if _PTS_TEMPLATE.count(_pts_old_heading) != 1:
        raise RuntimeError("Payment totals: operator day heading changed")
    _PTS_TEMPLATE = _PTS_TEMPLATE.replace(
        _pts_old_heading, _pts_new_heading, 1
    )
    _PTS_LAYOUT = "operator-v5"

elif ('id="pf-search"' in _PTS_TEMPLATE
      and 'id="pf-days"' in _PTS_TEMPLATE):
    # This legacy safe layout builds the day headings in JS. Add an immutable
    # per-payment amount to each row and display the full day's total regardless
    # of which rows are shown by the search filter.
    _pts_row = '''data-when="{{ p.paid_at.isoformat() if p.paid_at else '' }}"'''
    _pts_group = 'if(!groups.has(key))groups.set(key,{label,rows:[]});'
    _pts_append = 'groups.get(key).rows.push(row);'
    _pts_count = 'x.header.textContent=x.group.label+" · "+shown+" پرداخت";'
    for label,anchor in (
        ("safe payment date",_pts_row),
        ("safe day group",_pts_group),
        ("safe day rows",_pts_append),
        ("safe search heading",_pts_count),
    ):
        if _PTS_TEMPLATE.count(anchor) != 1:
            raise RuntimeError("Payment totals: " + label + " differs")
    _PTS_TEMPLATE = _PTS_TEMPLATE.replace(
        _pts_row, _pts_row + '\n     data-pf-amount="{{ p.amount_toman or 0 }}"', 1
    )
    _PTS_TEMPLATE = _PTS_TEMPLATE.replace(
        _pts_group, 'if(!groups.has(key))groups.set(key,{label,rows:[],total:0});', 1
    )
    _PTS_TEMPLATE = _PTS_TEMPLATE.replace(
        _pts_append, _pts_append + '\n  groups.get(key).total+=Number(row.dataset.pfAmount||0);', 1
    )
    _PTS_TEMPLATE = _PTS_TEMPLATE.replace(
        _pts_count,
        'x.header.textContent=x.group.label+" · "+shown+" پرداخت · جمع واریزی روز: "+'
        'new Intl.NumberFormat("fa-IR",{maximumFractionDigits:0}).format(x.group.total)+" تومان";',
        1
    )
    _PTS_LAYOUT = "safe-v5"

else:
    raise RuntimeError("Payment totals: unsupported live payment layout")

if 'action="/payments/{{' not in _PTS_TEMPLATE or '/undo"' not in _PTS_TEMPLATE:
    raise RuntimeError("Payment totals: undo action missing, refusing modification")
TEMPLATES["payments.html"] = _PTS_TEMPLATE
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)

_pts_routes = [
    r for r in app.router.routes
    if getattr(r,"path",None) == "/payments"
    and "GET" in (getattr(r,"methods",set()) or set())
]
if len(_pts_routes) != 1:
    raise RuntimeError("Payment totals: expected exactly one current GET /payments route")
_pts_original_handler = _pts_routes[0].endpoint
if getattr(_pts_original_handler,"__name__","") not in (
    "_op_payments_page", "_pf_payments_safe", "payments_with_undo"
):
    raise RuntimeError("Payment totals: unfamiliar payment handler")

def _pts_payments_page(
    request: _pts_Request,
    db: _pts_Session = _pts_Depends(get_db)
):
    # Sum exactly the surviving ledger entries. An undone payment is removed
    # from Payment and therefore automatically excluded. No writes.
    count,total = db.query(
        _pts_func.count(Payment.id),
        _pts_func.coalesce(_pts_func.sum(Payment.amount_toman),0),
    ).one()
    request.state.pts_count = int(count or 0)
    request.state.pts_total = int(total or 0)
    return _pts_original_handler(request,db)

app.router.routes[:] = [
    r for r in app.router.routes if r is not _pts_routes[0]
]
app.add_api_route("/payments",_pts_payments_page,methods=["GET"])
