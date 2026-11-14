# HESAB_CONTROL_ROOM_USER_ROWS_V13
# Presentation and client-side filtering ONLY. No DB, API, SSH, XUI, tunnel,
# user toggle, billing, or daily-usage calculation changes.
from jinja2 import Environment as _r13_Jinja

_R13_OLD=TEMPLATES.get("control_room.html","")
_R13_EXPECTED=(
  'id="c2-users"',
  'id="c3-mode"',
  'id="c3-table-controls"',
  'function c3VisibleRows(rows,server){',
  'for(const item of c3VisibleRows(data.rows,server)){',
  'const controls=create("td",undefined,tr);',
  'detailsButton.onclick=()=>c3Details(server,item);',
  '<th>مصرف کل</th><th>امروز</th><th>۳۰ روز</th>',
  '<th>نرخ ۲۰ ثانیه‌ای</th><th>آخرین اتصال</th><th>کنترل</th>',
  'id="t10-compact-css"',
)
if not isinstance(_R13_OLD,str) or not all(x in _R13_OLD for x in _R13_EXPECTED):
    raise RuntimeError("CONTROL_ROOM_ROWS_V13_EXPECTED_V3_V10_MISSING")
if 'id="r13-compact-list-style"' in _R13_OLD:
    raise RuntimeError("CONTROL_ROOM_ROWS_V13_ALREADY_LOADED")

_R13_UPDATED=_R13_OLD
def _r13_replace_one(old,new):
    global _R13_UPDATED
    if _R13_UPDATED.count(old)!=1:
        raise RuntimeError("CONTROL_ROOM_ROWS_V13_AMBIGUOUS_ANCHOR: "+old[:65])
    _R13_UPDATED=_R13_UPDATED.replace(old,new,1)

# Keep all existing modes and reordering state per Maya; add explicit unmatched.
_r13_replace_one(
    '    <option value="today">پرمصرف‌ترین‌های امروز ↓</option>',
    '    <option value="unmatched">فقط تطبیق‌نشده‌ها</option>\n'
    '    <option value="today">پرمصرف‌ترین‌های امروز ↓</option>')
_r13_replace_one(
    '  normal:"همه کاربران",today:"پرمصرف‌ترین‌های امروز",',
    '  normal:"همه کاربران",unmatched:"فقط تطبیق‌نشده‌ها",today:"پرمصرف‌ترین‌های امروز",')
_r13_replace_one(
    '''  if(mode==="idle")filtered=filtered.filter(item=>{
    const ms=c3LastMs(item.last_online);
    return ms!==null && Date.now()-ms>48*3600*1000;
  });''',
    '''  if(mode==="unmatched"){
    filtered=filtered.filter(item=>!item.sid||item.control_ambiguous===true);
  }else if(mode==="idle"){
    filtered=filtered.filter(item=>{
      const ms=c3LastMs(item.last_online);
      return ms!==null&&Date.now()-ms>48*3600*1000;
    }).sort((a,b)=>{
      const diff=c3LastMs(a.last_online)-c3LastMs(b.last_online);
      return diff||String(a.email||"").localeCompare(String(b.email||""));
    });
  }''')
# Make unknown daily measurements visible as unmeasured, never as numeric zero.
_r13_replace_one(
    '  return filtered;\n}\nfunction c3Details(server,item){',
    '''  const noDaily=filtered.filter(item=>item.usage_sampled!==true).length;
  if(noDaily>0)c3Info.textContent+=" · مصرف امروز برای "+count(noDaily)+
      " اکانت اندازه‌گیری نشده";
  return filtered;
}
function c3Details(server,item){''')

# Only six essential columns in the list; keep the underlying 9-column DOM
# and the full details modal so toggles, profile links, security controls and
# the 30-day/rate evidence are not removed or rewritten.
_r13_replace_one(
    '<th>نرخ ۲۰ ثانیه‌ای</th><th>آخرین اتصال</th><th>کنترل</th>',
    '<th>نرخ ۲۰ ثانیه‌ای</th><th>آخرین اتصال</th><th>جزئیات / کنترل</th>')
_r13_replace_one(
    'create("td",item.usage_sampled?bytes(item.today_bytes):"—",tr,"c2-ltr");',
    '''const todayCell=create("td",item.usage_sampled?bytes(item.today_bytes):
         "اندازه‌گیری نشده",tr,"c2-ltr");
   todayCell.title=item.usage_sampled?
       "مصرف ثبت‌شده امروز بر اساس نمونه‌های سامانه، نه لزوماً کل مصرف روز":
       "هنوز نمونه معتبر مصرف امروز برای این اکانت دریافت نشده است";''')

_R13_STYLE=r'''
<style id="r13-compact-list-style">
/* One clean X-UI user per HORIZONTAL row on desktop. No visual mini-cards. */
#c2-root #c2-scroll.c2-table-wrap{
 width:100%!important;max-height:none!important;overflow-x:auto!important;
 overflow-y:visible!important;border:1px solid rgba(128,140,188,.18)!important;
 border-radius:13px!important;background:rgba(13,18,38,.54)!important;
 box-shadow:none!important;
}
#c2-root #c2-scroll table{
 display:table!important;width:100%!important;min-width:855px!important;
 table-layout:fixed!important;border-collapse:collapse!important;
 background:transparent!important
}
#c2-root #c2-scroll thead{display:table-header-group!important}
#c2-root #c2-scroll tbody{display:table-row-group!important}
#c2-root #c2-scroll thead tr,
#c2-root #c2-scroll tbody tr{
 display:table-row!important;background:transparent!important;
 border:0!important;box-shadow:none!important;border-radius:0!important;
 padding:0!important;grid-template-columns:none!important;
}
#c2-root #c2-scroll thead th{
 display:table-cell!important;padding:13px 11px!important;
 background:#1b2540!important;color:#dbe3f6!important;
 font-weight:800!important;font-size:11px!important;text-align:right!important;
 border-bottom:1px solid rgba(160,180,226,.2)!important;
 white-space:nowrap!important;
}
#c2-root #c2-scroll tbody td{
 display:table-cell!important;vertical-align:middle!important;
 padding:12px 11px!important;width:auto!important;max-width:none!important;
 font-size:12px!important;font-weight:500!important;
 background:transparent!important;line-height:1.65!important;
 color:#e5eaf4!important;border:0!important;
 border-bottom:1px solid rgba(159,179,223,.12)!important;
 overflow-wrap:anywhere!important;white-space:normal!important;
 text-align:right!important;
}
#c2-root #c2-scroll tbody tr:hover{background:rgba(112,145,205,.075)!important}
#c2-root #c2-scroll tbody tr:nth-child(even){background:rgba(255,255,255,.017)!important}
#c2-root #c2-scroll th:nth-child(6),
#c2-root #c2-scroll td:nth-child(6),
#c2-root #c2-scroll th:nth-child(7),
#c2-root #c2-scroll td:nth-child(7){display:none!important}
#c2-root #c2-scroll th:nth-child(1){width:20%}
#c2-root #c2-scroll th:nth-child(2){width:17%}
#c2-root #c2-scroll th:nth-child(3){width:9%}
#c2-root #c2-scroll th:nth-child(4){width:12%}
#c2-root #c2-scroll th:nth-child(5){width:12%}
#c2-root #c2-scroll th:nth-child(8){width:17%}
#c2-root #c2-scroll th:nth-child(9){width:13%}
#c2-root #c2-scroll td:nth-child(1) b{
 display:block!important;font-size:12px!important;font-weight:800!important;
 overflow-wrap:anywhere!important;color:#f3f5ff!important;
}
#c2-root #c2-scroll td:nth-child(2) a{
 display:inline-block!important;color:#a9c9fc!important;
 font-weight:750!important;font-size:11px!important;text-decoration:none;
}
#c2-root #c2-scroll td:nth-child(2) a:hover{text-decoration:underline}
#c2-root #c2-scroll td:nth-child(2) small{
 display:inline-block!important;padding:3px 7px!important;
 color:#f6c4a3!important;background:rgba(184,112,43,.12)!important;
 border:1px solid rgba(193,126,80,.19)!important;border-radius:7px!important;
 font-weight:700!important;
}
#c2-root #c2-scroll td:nth-child(4),
#c2-root #c2-scroll td:nth-child(5){font-variant-numeric:tabular-nums;direction:ltr;unicode-bidi:isolate}
#c2-root #c2-scroll td:nth-child(8){color:#bbc9df!important;font-size:11px!important}
#c2-root #c2-scroll td:nth-child(9){
 white-space:normal!important;min-width:0!important;
}
#c2-root #c2-scroll td:nth-child(9) button{
 width:auto!important;min-width:0!important;min-height:32px!important;
 font-size:10px!important;padding:6px 8px!important;margin:2px 2px!important;
 border-radius:8px!important;
}
#c2-root #c2-scroll td::before,
#c2-root #c2-scroll td:before{content:none!important;display:none!important}
#c2-root #c3-table-controls{margin:14px 0 8px!important}
#c2-root #c3-filter-info{
 color:#a8bad2!important;margin:0 0 12px!important;
 padding:7px 1px!important;font-size:11px!important
}
/* Phone: one full-width, orderly user row after another, never tiled cards
   or horizontally overflowing nine-column spreadsheets. */
@media(max-width:720px){
 html body #c2-root #c2-scroll.c2-table-wrap{
   overflow:visible!important;border:0!important;background:none!important;
   border-radius:0!important
 }
 html body #c2-root #c2-scroll table{
   display:block!important;width:100%!important;min-width:0!important;
   max-width:100%!important;table-layout:auto!important
 }
 html body #c2-root #c2-scroll thead{display:none!important}
 html body #c2-root #c2-scroll tbody{
   display:block!important;width:100%!important;min-width:0!important;
 }
 html body #c2-root #c2-scroll tbody tr{
   display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;
   gap:8px 10px!important;align-items:start!important;
   padding:12px 0!important;
   border:0!important;border-bottom:1px solid rgba(151,167,206,.22)!important;
   border-radius:0!important;background:transparent!important;box-shadow:none!important;
 }
 html body #c2-root #c2-scroll tbody td{
   display:block!important;width:auto!important;max-width:none!important;
   min-width:0!important;padding:2px 0!important;border:0!important;
   font-size:11px!important;line-height:1.65!important;
   white-space:normal!important;overflow-wrap:anywhere!important;
 }
 html body #c2-root #c2-scroll tbody td:nth-child(1){
   grid-column:1/-1;grid-row:1;
 }
 html body #c2-root #c2-scroll tbody td:nth-child(1) b{
   font-size:13px!important;direction:ltr;text-align:left!important;
 }
 html body #c2-root #c2-scroll tbody td:nth-child(2){grid-column:1;grid-row:2}
 html body #c2-root #c2-scroll tbody td:nth-child(3){grid-column:2;grid-row:2;text-align:left!important}
 html body #c2-root #c2-scroll tbody td:nth-child(4){grid-column:1;grid-row:3;text-align:right!important;direction:rtl}
 html body #c2-root #c2-scroll tbody td:nth-child(5){grid-column:2;grid-row:3;text-align:right!important;direction:rtl}
 html body #c2-root #c2-scroll tbody td:nth-child(8){grid-column:1;grid-row:4}
 html body #c2-root #c2-scroll tbody td:nth-child(9){grid-column:2;grid-row:4;text-align:left!important}
 html body #c2-root #c2-scroll tbody td:nth-child(4)::before,
 html body #c2-root #c2-scroll tbody td:nth-child(5)::before,
 html body #c2-root #c2-scroll tbody td:nth-child(8)::before{
   display:block!important;font-size:10px!important;line-height:1.8!important;
   color:#9eacc8!important;padding-bottom:3px!important;
 }
 html body #c2-root #c2-scroll tbody td:nth-child(4)::before{content:"مصرف کل X-UI"!important}
 html body #c2-root #c2-scroll tbody td:nth-child(5)::before{content:"مصرف امروز"!important}
 html body #c2-root #c2-scroll tbody td:nth-child(8)::before{content:"آخرین اتصال"!important}
 html body #c2-root #c2-scroll tbody td:nth-child(6),
 html body #c2-root #c2-scroll tbody td:nth-child(7){display:none!important}
 html body #c2-root #c2-scroll tbody tr:has(td[colspan]){
   display:block!important;text-align:center!important;
 }
 html body #c2-root #c2-scroll tbody tr:has(td[colspan]) td{
   display:block!important;text-align:center!important
 }
 html body #c2-root #c2-scroll td:nth-child(9) button{min-height:38px!important}
}
/* The final mobile V12 rule had higher specificity; override only this table. */
@media(max-width:720px){
 html body.hm12-ready #c2-root #c2-scroll.c2-table-wrap table{
   display:block!important;width:100%!important;min-width:0!important;
 }
 html body.hm12-ready #c2-root #c2-scroll.c2-table-wrap td{
   white-space:normal!important;min-width:0!important;
 }
}
</style>
'''
# Jinja page has a title block as well as content; only append to the
# LAST (content) endblock. Never add CSS into the page-title block.
if _R13_UPDATED.count("{% endblock %}")<2:
    raise RuntimeError("CONTROL_ROOM_ROWS_V13_CONTENT_END_MISSING")
_r13_head,_r13_sep,_r13_tail=_R13_UPDATED.rpartition("{% endblock %}")
if 'id="c2-users"' not in _r13_head:
    raise RuntimeError("CONTROL_ROOM_ROWS_V13_CONTENT_LOCATION_INVALID")
_R13_UPDATED=_r13_head+_R13_STYLE+"\n"+_r13_sep+_r13_tail
_r13_Jinja().parse(_R13_UPDATED)
# No route, financial row, toggle callback or usage source changes.
TEMPLATES["control_room.html"]=_R13_UPDATED
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)
