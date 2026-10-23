# HESAB_PAYMENTS_SEARCH_FIX_V6
# UI-only overlay for /payments. No ORM, payment rows, undo endpoints, or DB writes.
# Restore proper hidden behavior for CSS-grid payment rows and make Persian/Latin
# multi-word searches work on all displayed payment metadata.
import re as _pfs6_re

_pfs6_template = TEMPLATES.get("payments.html", "")
if not _pfs6_template:
    raise RuntimeError("Payments search v6: payment history template missing")
if _pfs6_template.count('id="pf-search"') != 1 or _pfs6_template.count('data-pf-row') != 1:
    raise RuntimeError("Payments search v6: unsupported payment template")
if 'id="pf-days"' not in _pfs6_template or '"/payments/{{ p.id }}/undo"' not in _pfs6_template:
    # Literal Jinja undo action is immutable.
    if 'action="/payments/{{ p.id }}/undo"' not in _pfs6_template:
        raise RuntimeError("Payments search v6: existing undo action missing")

_pfs6_css = """
/* Author CSS display:grid previously overrode the browser's [hidden] rule. */
#pf-days .pf-row[hidden],
#pf-days .pf-day[hidden],
#pf-empty[hidden],
#pf-rows[hidden] { display: none !important; }
"""
if _pfs6_template.count("</style>") != 1:
    raise RuntimeError("Payments search v6: stylesheet anchor not unique")
_pfs6_template = _pfs6_template.replace("</style>", _pfs6_css+"\n</style>", 1)
_pfs6_when = '''data-when="{{ p.paid_at.isoformat() if p.paid_at else '' }}"'''
if _pfs6_template.count(_pfs6_when) != 1:
    raise RuntimeError("Payments search v6: payment date dataset changed")
_pfs6_template = _pfs6_template.replace(
    _pfs6_when, _pfs6_when+'\n     data-pf-id="{{ p.id }}"', 1
)
_pfs6_old = r'''const norm=s=>String(s||"").toLowerCase().replace(/ي/g,"ی").replace(/ك/g,"ک")
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
input.addEventListener("input",apply);apply();'''
_pfs6_new = r'''// Robust Persian / Arabic / Latin text and number matching.
const norm=s=>String(s??"").toLowerCase()
 .replace(/ي/g,"ی").replace(/ك/g,"ک").replace(/[\u064b-\u065f\u0670]/g,"")
 .replace(/[۰-۹]/g,c=>String("۰۱۲۳۴۵۶۷۸۹".indexOf(c)))
 .replace(/[٠-٩]/g,c=>String("٠١٢٣٤٥٦٧٨٩".indexOf(c)))
 .replace(/[\u200c\u200d]/g," ")
 .replace(/[^0-9a-z\u0600-\u06ff]+/g," ")
 .trim().replace(/\s+/g," ");
const compact=s=>norm(s).replace(/\s/g,"");
const total=rows.length;
const apply=()=>{
 const needle=norm(input.value);
 const terms=needle?needle.split(" "):[];
 const noSpace=compact(input.value);
 let n=0;
 for(const x of sections){
  let shown=0;
  for(const row of x.group.rows){
   const haystack=norm([
      row.dataset.pfSearchNorm,row.dataset.pfId,
      row.dataset.when,row.textContent,x.group.label
   ].join(" "));
   const matches=!needle ||
      terms.every(word=>haystack.includes(word)) ||
      (noSpace && compact(haystack).includes(noSpace));
   row.hidden=!matches;
   if(matches){shown++;n++;}
  }
  x.section.hidden=shown===0;
  x.header.textContent=x.group.label+" · "+shown+" پرداخت";
 }
 count.textContent=n+" از "+total+" پرداخت";
 empty.hidden=n!==0;
};
input.addEventListener("input",apply);
input.addEventListener("search",apply);
input.addEventListener("change",apply);
apply();'''
if _pfs6_template.count(_pfs6_old) != 1:
    raise RuntimeError("Payments search v6: source search code differs; refusing blind edit")
_pfs6_template = _pfs6_template.replace(_pfs6_old, _pfs6_new, 1)
TEMPLATES["payments.html"] = _pfs6_template
if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)
