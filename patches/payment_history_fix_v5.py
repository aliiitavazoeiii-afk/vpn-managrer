# HESAB_PAYMENT_HISTORY_SAFE_V5_1
# Emergency fix for V5 payment-page HTTP 500: fall back to proven payment rows
# and the original undo-safe backend. Group dates/search client-side only.
from datetime import datetime as _pf_datetime, timezone as _pf_timezone
from fastapi import Request as _pf_Request, Depends as _pf_Depends
from sqlalchemy.orm import Session as _pf_Session

_PF_TEMPLATE = r'''{% extends "base.html" %}
{% block title %}پرداختی‌ها · حساب VPN{% endblock %}
{% block heading %}پرداختی‌ها{% endblock %}
{% block subheading %}تاریخچه واقعی پرداخت‌ها بر اساس امروز، دیروز و تاریخ شمسی{% endblock %}
{% block content %}
<style>
.pf-search{width:100%;box-sizing:border-box;border:1px solid #425773;background:#101a29;
 color:#fff;border-radius:12px;padding:13px;font:inherit;margin-bottom:12px}
.pf-day{border:1px solid #344054;border-radius:14px;overflow:hidden;margin:12px 0 18px}
.pf-day-head{background:#19283c;padding:12px 15px;color:#d5e8ff;font-weight:850;font-size:14px}
.pf-row{display:grid;grid-template-columns:minmax(150px,1.4fr) minmax(100px,.8fr)
 minmax(150px,1fr) minmax(125px,.8fr);gap:13px;align-items:center;
 padding:12px 15px;border-top:1px solid #2f4155;font-size:12px}
.pf-row a{color:#badfff;text-decoration:none;font-weight:800}.pf-row strong{color:#b3f59b}
.pf-row small{display:block;color:#9ab0c7;font-size:11px;margin-top:3px}
.pf-row button{width:100%;border-radius:9px;border:1px solid #91545c;background:#412b35;
 color:#ffdbdf;font:inherit;padding:9px;cursor:pointer}
.pf-row button:disabled{opacity:.45;cursor:not-allowed}
.pf-info{color:#a9bfd5;font-size:12px}
@media(max-width:720px){.pf-row{grid-template-columns:1fr 1fr}.pf-row>div:last-child{grid-column:1/-1}}
</style>
{% if request.query_params.get('undone') %}<p class="pf-info">✓ پرداخت اشتباهی برگشت داده شد.</p>{% endif %}
{% if request.query_params.get('undo_error') %}<p class="pf-info">این پرداخت قابل برگشت نیست.</p>{% endif %}
<input id="pf-search" class="pf-search" type="search" placeholder="جست‌وجوی نام، شماره همراه، شناسه یا مبلغ پرداخت" autocomplete="off">
<p class="pf-info" id="pf-count"></p>
<div id="pf-rows" hidden>
{% for item in rows %}{% set p=item.p %}{% set s=item.s %}
<div class="pf-row" data-pf-row
     data-when="{{ p.paid_at.isoformat() if p.paid_at else '' }}"
     data-search="{{ (((s.display_name or '') ~ ' ' ~ (s.phone or '') ~ ' ' ~ s.id) if s else ('حذف شده ' ~ p.subscription_id) }} {{ p.amount_toman }} {{ p.note or '' }}">
<div>{% if s %}<a href="/users/{{ s.id }}">{{ s.display_name }}</a>
<small>{{ s.phone or 'بدون شماره' }} · شناسه {{ s.id|fa }}</small>{% else %}اکانت حذف‌شده{% endif %}
<small>{{ p.note or '' }}</small></div>
<div><strong>{{ p.amount_toman|money }} تومان</strong><small data-pf-time>زمان ثبت</small></div>
<div>انقضای قبل: {{ p.previous_expiry|jdate }}<small>انقضای بعد: {{ p.new_expiry|jdate }}</small></div>
<div>{% if item.undoable %}<form method="post" action="/payments/{{ p.id }}/undo"
 onsubmit="return confirm('پرداخت اشتباهی برگردانده شود؟')">
 <button type="submit">↶ لغو پرداخت</button></form>
 {% else %}<button type="button" disabled>قابل برگشت نیست</button>{% endif %}</div>
</div>
{% endfor %}
</div>
<div id="pf-days"></div>
<div id="pf-empty" class="pf-info" hidden>پرداختی با این مشخصات پیدا نشد.</div>
<script>
(function(){
"use strict";
const source=document.getElementById("pf-rows"),output=document.getElementById("pf-days");
const input=document.getElementById("pf-search"),count=document.getElementById("pf-count"),empty=document.getElementById("pf-empty");
const rows=[...source.querySelectorAll("[data-pf-row]")],tz="Asia/Tehran";
const localKey=date=>{
  const parts=new Intl.DateTimeFormat("en-US",{timeZone:tz,year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(date);
  const obj=Object.fromEntries(parts.map(x=>[x.type,x.value]));
  return obj.year+"-"+obj.month+"-"+obj.day;
};
const persianDate=d=>new Intl.DateTimeFormat("fa-IR-u-ca-persian",{timeZone:tz,year:"numeric",month:"long",day:"numeric"}).format(d);
const today=localKey(new Date()),yesterday=localKey(new Date(Date.now()-86400000));
const timeFormatter=new Intl.DateTimeFormat("fa-IR",{timeZone:tz,hour:"2-digit",minute:"2-digit",hour12:false});
const groups=new Map();
for(const row of rows){
 const text=row.dataset.when||"";
 const dt=new Date(text && !/[Zz]|[+-]\d\d:\d\d$/.test(text)?text+"Z":text);
 const valid=!isNaN(dt.getTime());
 const key=valid?localKey(dt):"unknown";
 const label=valid?(key===today?"امروز":key===yesterday?"دیروز":persianDate(dt)):"تاریخ نامشخص";
 const stamp=row.querySelector("[data-pf-time]");
 if(valid && stamp)stamp.textContent="ساعت "+timeFormatter.format(dt);
 row.dataset.pfSearchNorm=row.dataset.search||"";
 if(!groups.has(key))groups.set(key,{label,rows:[]});
 groups.get(key).rows.push(row);
}
const order=[...groups].sort((a,b)=>b[0].localeCompare(a[0]));
const sections=[];
for(const [key,group] of order){
 const section=document.createElement("section");section.className="pf-day";
 const header=document.createElement("div");header.className="pf-day-head";
 section.append(header);
 group.rows.sort((a,b)=>(b.dataset.when||"").localeCompare(a.dataset.when||""));
 group.rows.forEach(row=>section.append(row));
 output.append(section);sections.push({group,section,header});
}
source.remove();
const norm=s=>String(s||"").toLowerCase().replace(/ي/g,"ی").replace(/ك/g,"ک")
 .replace(/[۰-۹]/g,c=>"۰۱۲۳۴۵۶۷۸۹".indexOf(c))
 .replace(/[٠-٩]/g,c=>"٠١٢٣٤٥٦٧٨٩".indexOf(c))
 .replace(/[,٬،\s]/g,"");
const apply=()=>{
 const q=norm(input.value);let n=0;
 for(const x of sections){
  let shown=0;
  for(const row of x.group.rows){
   const show=!q||norm(row.dataset.pfSearchNorm).includes(q);
   row.hidden=!show;
   if(show){shown++;n++;}
  }
  x.section.hidden=shown===0;
  x.header.textContent=x.group.label+" · "+shown+" پرداخت";
 }
 count.textContent=n+" پرداخت در تاریخچه";
 empty.hidden=n!==0;
};
input.addEventListener("input",apply);apply();
})();
</script>
{% endblock %}'''
TEMPLATES["payments.html"]=_PF_TEMPLATE
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)

def _pf_payments_safe(request:_pf_Request,db:_pf_Session=_pf_Depends(get_db)):
    # Same ORM query and undo decision as the working V4 payments history.
    payments=db.query(Payment).order_by(Payment.id.desc()).all()
    seen=set()
    rows=[]
    for p in payments:
        s=db.get(Subscription,p.subscription_id)
        is_latest=p.subscription_id not in seen
        seen.add(p.subscription_id)
        undoable=bool(
            is_latest and s is not None and p.previous_expiry is not None
            and p.new_expiry is not None and s.expiry_date==p.new_expiry)
        rows.append({"p":p,"s":s,"undoable":undoable})
    return render("payments.html",request,rows=rows)

app.router.routes[:]=[r for r in app.router.routes
    if not (getattr(r,"path",None)=="/payments" and "GET" in (getattr(r,"methods",set()) or set()))]
app.add_api_route("/payments",_pf_payments_safe,methods=["GET"])
