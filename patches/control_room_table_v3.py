# HESAB_CONTROL_ROOM_TABLE_V3
# Late overlay: restore properly styled table, per-server search/sort, read-only
# abnormal-usage detection and details dialog. Existing CSRF/toggle/mapping kept.
import sqlite3 as _c3_sqlite
from datetime import timedelta as _c3_timedelta
from jinja2 import Environment as _c3_Environment

_C3_GIB = 1024 ** 3
_C3_ORIGINAL_ONE = _cr2_one

def _cr2_one(server, db):
    report = _C3_ORIGINAL_ONE(server, db)
    # This is sampled usage, not lifetime XUI usage and not provider quota.
    for row in report.get("rows", []):
        row.update({"anomaly": False, "baseline_days": 0,
                    "baseline_avg_bytes": None, "anomaly_threshold_bytes": None})
    if not report.get("rows") or not _CR2_DB.is_file():
        return report
    today = _cr2_datetime.now(_CR2_TZ).date()
    start = (today - _c3_timedelta(days=7)).isoformat()
    previous_end = (today - _c3_timedelta(days=1)).isoformat()
    current = today.isoformat()
    history = {}
    try:
        with _c3_sqlite.connect("file:" + str(_CR2_DB) + "?mode=ro",
                                uri=True, timeout=3) as conn:
            for email, day, up, down, samples in conn.execute("""
                SELECT email, local_day, up, down, sample_count
                FROM daily_usage
                WHERE server=? AND local_day>=? AND local_day<=?
            """, (server, start, current)):
                key = str(email or "").strip().casefold()
                if not key:continue
                # At least 24 five-minute observations per reference day.
                if (start <= day <= previous_end and int(samples or 0) >= 24):
                    history.setdefault(key, []).append(max(0, int(up or 0))+
                                                       max(0, int(down or 0)))
    except (_c3_sqlite.Error, ValueError, TypeError, OSError):
        return report  # No false anomalous users when history is unavailable.
    for row in report["rows"]:
        days = history.get(str(row.get("email") or "").strip().casefold(), [])
        row["baseline_days"] = len(days)
        if len(days) < 3 or not row.get("usage_sampled"):
            continue
        avg = sum(days) / len(days)
        threshold = max(2 * _C3_GIB, 3 * avg)
        row["baseline_avg_bytes"] = int(avg)
        row["anomaly_threshold_bytes"] = int(threshold)
        row["anomaly"] = bool(int(row.get("today_bytes", 0)) > threshold)
    return report

_C3_TEMPLATE = TEMPLATES.get("control_room.html", "")
if not all(x in _C3_TEMPLATE for x in (
    'id="p1-ops-root"', 'id="p1-monitor"',
    'id="c2-search"', 'id="c2-scroll"', 'id="c2-users"',
    'const state={active:null,latest:{},query:"",loading:false,mutating:false};',
    'const y=scroll.scrollTop;', 'for(const item of data.rows){',
    'const controls=create("td",undefined,tr);',
    'search.oninput=()=>{state.query=search.value;renderDetails();};'
)):
    raise RuntimeError("Control room V3 requires the deployed Phase1/V2 DOM and scripts")
if "c3-table-controls" in _C3_TEMPLATE:
    raise RuntimeError("Control room V3 already installed")

_C3_CSS = r'''
<style id="c3-styles">
/* Undo ONLY the Phase1 card treatment for XUI users; keep three server cards and metrics. */
#c2-root .c2-table-wrap{width:100%;overflow-x:auto!important;overflow-y:visible!important;
 max-height:none!important;border:1px solid var(--c2-line, #363957)!important;
 border-radius:13px!important;scrollbar-width:thin}
#c2-root .c2-table-wrap table{display:table!important;table-layout:auto;
 min-width:785px!important;width:100%!important;border-collapse:collapse!important}
#c2-root .c2-table-wrap thead{display:table-header-group!important}
#c2-root .c2-table-wrap tbody{display:table-row-group!important}
#c2-root .c2-table-wrap thead tr,
#c2-root .c2-table-wrap tbody tr,
#c2-root .c2-table-wrap tbody tr:has(td[colspan]){display:table-row!important;
 border:0!important;border-radius:0!important;background:transparent!important;
 box-shadow:none!important;padding:0!important}
#c2-root .c2-table-wrap th{position:static!important;top:auto!important;
 z-index:auto!important;background:#242545!important;color:#e0daf9!important;
 font-size:11px!important;font-weight:800!important;white-space:nowrap!important}
#c2-root .c2-table-wrap td{display:table-cell!important;width:auto!important;
 white-space:normal!important;vertical-align:middle!important;
 text-align:right!important;padding:13px 10px!important;overflow-wrap:anywhere;
 font-size:12px!important;border-bottom:1px solid rgba(157,161,255,.11)!important}
#c2-root .c2-table-wrap td::before,
#c2-root .c2-table-wrap td:before{content:none!important;display:none!important}
#c2-root .c2-table-wrap tbody tr:hover{background:rgba(141,116,250,.095)!important}
#c2-root .c2-table-wrap th:nth-child(4),
#c2-root .c2-table-wrap td:nth-child(4),
#c2-root .c2-table-wrap th:nth-child(7),
#c2-root .c2-table-wrap td:nth-child(7){display:none!important}
#c2-root .c2-table-wrap td:first-child{font-weight:750}
#c2-root .c2-table-wrap td:nth-child(2){max-width:230px}
#c2-root .c2-table-wrap td:nth-child(8){min-width:126px}
#c2-root .c2-table-wrap td:nth-child(9){min-width:155px}
#c2-root .c2-table-wrap td:nth-child(9) button{width:auto!important;min-width:65px;
 min-height:34px!important;margin-inline-end:5px;padding:7px 9px;font-size:11px}
#c2-root .c2-table-wrap td:nth-child(9) .c3-detail-button{background:rgba(141,120,246,.22);
 border:1px solid rgba(169,150,255,.5);color:#f1eaff}
#c2-root .c2-reports{display:none!important}
#c2-root .c2-panel-top{margin-bottom:10px}
#c2-root .c2-panel-top .c2-search{display:none!important}
#c3-table-controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap;
 margin:12px 0 10px;direction:rtl}
#c3-table-controls label{font-size:11px;color:#bfc2e4;font-weight:700}
#c3-table-controls select,#c3-table-controls input{background:#12182f!important;
 color:#f5f4ff!important;border:1px solid rgba(176,155,255,.34)!important;
 border-radius:10px!important;min-height:43px;padding:0 12px!important;
 font:inherit!important;font-size:12px!important;max-width:100%}
#c3-table-controls input{width:min(310px,100%)!important;flex:1 1 195px;min-width:150px}
#c3-table-controls select{min-width:235px;flex:1 1 235px}
#c3-filter-info{font-size:11px;color:#aeb9db;line-height:1.7;margin:0 0 10px}
#c3-detail-backdrop{position:fixed;inset:0;z-index:9700;background:rgba(3,5,18,.83);
 display:grid;place-items:center;padding:14px;direction:rtl;overflow-y:auto}
#c3-detail-backdrop .c3-dialog{width:min(580px,100%);max-height:90vh;overflow-y:auto;
 background:linear-gradient(140deg,#232442,#151a2e);border:1px solid #696093;
 border-radius:19px;color:#f4f1ff;padding:20px;box-shadow:0 25px 75px #0009}
#c3-detail-backdrop h3{margin:0 0 5px;font-size:18px!important;color:#fff!important}
#c3-detail-backdrop .c3-caption{font-size:11px;color:#afb6d4;margin-bottom:12px}
#c3-detail-backdrop .c3-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
#c3-detail-backdrop .c3-metric{background:#ffffff0c;border:1px solid #ffffff17;
 border-radius:10px;padding:11px;min-width:0}
#c3-detail-backdrop .c3-metric small{display:block;font-size:10px;color:#aab6d1}
#c3-detail-backdrop .c3-metric strong{display:block;font-size:12px;
 margin-top:7px;overflow-wrap:anywhere}
#c3-detail-backdrop .c3-alert{font-size:12px;line-height:1.9;color:#ffd9a8;
 border:1px solid #785c38;background:#5a3b192e;border-radius:11px;padding:10px;margin-top:12px}
#c3-detail-backdrop .c3-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:15px}
#c3-detail-backdrop .c3-actions button,#c3-detail-backdrop .c3-actions a{font:inherit;
 font-size:12px;font-weight:750;border-radius:9px;padding:9px 15px;border:1px solid #8a7cba;
 background:#52477d;color:#fff;text-decoration:none;cursor:pointer}
#c3-detail-backdrop .c3-actions button:focus-visible{outline:2px solid white}
@media(max-width:700px){
 #c2-root .c2-table-wrap table{min-width:735px!important}
 #c3-table-controls{align-items:stretch}
 #c3-table-controls select{flex-basis:100%;width:100%}
 #c3-detail-backdrop .c3-dialog{padding:15px}
}
</style>
'''
_C3_TOOLBAR = r'''
<div id="c3-table-controls">
  <input id="c2-search" class="c2-search" type="search" autocomplete="off"
    aria-label="جست‌وجو در کاربران سرور انتخاب‌شده" placeholder="جست‌وجو در همین سرور: نام یا شناسه">
  <label for="c3-mode">نمایش و مرتب‌سازی</label>
  <select id="c3-mode" aria-label="فیلتر و مرتب‌سازی کاربران">
    <option value="normal">همه کاربران · ترتیب اصلی</option>
    <option value="today">پرمصرف‌ترین‌های امروز ↓</option>
    <option value="month">پرمصرف‌ترین‌های ۳۰ روز ↓</option>
    <option value="idle">بدون اتصال بیش از ۴۸ ساعت</option>
    <option value="unknown">زمان آخرین اتصال نامشخص</option>
    <option value="anomaly">مصرف غیرعادی امروز</option>
  </select>
</div>
<div id="c3-filter-info" role="status"></div>
'''
_C3_OLD_SEARCH = '<input id="c2-search" class="c2-search" type="search" autocomplete="off" placeholder="جست‌وجوی کاربر، نام، شناسه">'
_C3_OLD_SCROLL = '<div class="c2-table-wrap" id="c2-scroll">'
assert _C3_TEMPLATE.count(_C3_OLD_SEARCH)==1
assert _C3_TEMPLATE.count(_C3_OLD_SCROLL)==1
_C3_TEMPLATE = _C3_TEMPLATE.replace("{% block content %}", "{% block content %}"+_C3_CSS,1)
_C3_TEMPLATE = _C3_TEMPLATE.replace(_C3_OLD_SEARCH,"",1)
_C3_TEMPLATE = _C3_TEMPLATE.replace(_C3_OLD_SCROLL,_C3_TOOLBAR+_C3_OLD_SCROLL,1)

_C3_JS = r'''
const c3Mode=document.getElementById("c3-mode");
const c3Info=document.getElementById("c3-filter-info");
const c3Modes={
  normal:"همه کاربران",today:"پرمصرف‌ترین‌های امروز",
  month:"پرمصرف‌ترین‌های ۳۰ روز",idle:"بیش از ۴۸ ساعت بدون اتصال",
  unknown:"بدون زمان ثبت‌شده",anomaly:"مصرف غیرعادی"
};
const c3LastMs=x=>{
  let n=Number(x||0);if(!Number.isFinite(n)||n<=0)return null;
  if(n<1e11)n*=1000;
  if(n>Date.now()+5*60000)return null;
  return n;
};
function c3VisibleRows(rows,server){
  const q=normal(state.query);
  const mode=c3Mode.value;
  let filtered=rows.filter(item=>
    normal([item.email,item.name,item.sid||""].join(" ")).includes(q)
  );
  if(mode==="idle")filtered=filtered.filter(item=>{
    const ms=c3LastMs(item.last_online);
    return ms!==null && Date.now()-ms>48*3600*1000;
  });
  else if(mode==="unknown")filtered=filtered.filter(item=>
    c3LastMs(item.last_online)===null
  );
  else if(mode==="anomaly")filtered=filtered.filter(item=>item.anomaly===true);
  else if(mode==="today"||mode==="month"){
    const field=mode==="today"?"today_bytes":"last30_bytes";
    filtered=filtered.map((item,index)=>({item,index})).sort((a,b)=>{
      const av=a.item.usage_sampled?Number(a.item[field]||0):-1;
      const bv=b.item.usage_sampled?Number(b.item[field]||0):-1;
      return bv-av||a.index-b.index;
    }).map(x=>x.item);
  }
  const eligibleHistory=rows.filter(x=>x.baseline_days>=3&&x.usage_sampled).length;
  c3Info.textContent=count(filtered.length)+" از "+count(rows.length)+" اکانت · "+c3Modes[mode]+
    (mode==="anomaly"?" · دارای تاریخچه کافی: "+count(eligibleHistory)+
      " · معیار: بیش از ۳ برابر میانگین ۷ روز و حداقل ۲ گیگابایت":"")+
    (mode==="idle"?" · زمان اتصال نامشخص در این فیلتر نیست":"");
  return filtered;
}
function c3Details(server,item){
  document.getElementById("c3-detail-backdrop")?.remove();
  const overlay=create("div",undefined,document.body);
  overlay.id="c3-detail-backdrop";overlay.setAttribute("role","dialog");
  overlay.setAttribute("aria-modal","true");overlay.setAttribute("aria-label","جزئیات اکانت");
  const sheet=create("div",undefined,overlay,"c3-dialog");
  create("h3",item.name||item.email,sheet);
  create("div",(names[server]||server)+" · "+item.email,sheet,"c3-caption");
  const grid=create("div",undefined,sheet,"c3-grid");
  function metric(label,value){
    const card=create("div",undefined,grid,"c3-metric");
    create("small",label,card);create("strong",value,card);
  }
  metric("شناسه حساب",item.sid?"#"+item.sid:"تطبیق نشده");
  metric("وضعیت X-UI",item.client_enabled?"فعال":"غیرفعال");
  metric("وضعیت حساب",item.finance_state||"نامشخص");
  metric("تاریخ انقضا",item.expiry||"نامشخص");
  metric("شناسه تطبیق",item.reason||"نامشخص");
  metric("سهمیه داخل X-UI",item.quota?bytes(item.quota):"نامحدود/ثبت نشده");
  metric("مصرف کل اکانت",bytes(Number(item.up||0)+Number(item.down||0)));
  metric("آپلود کل",bytes(item.up));
  metric("دانلود کل",bytes(item.down));
  metric("مصرف امروز",item.usage_sampled?bytes(item.today_bytes):"بدون نمونه کافی");
  metric("مصرف ۳۰ روز",item.usage_sampled?bytes(item.last30_bytes):"بدون نمونه کافی");
  metric("نرخ میانگین نمونه",rate(item.rate_bps));
  metric("آخرین اتصال",last(item.last_online));
  metric("میانگین روزهای قبلی",item.baseline_days>=3?bytes(item.baseline_avg_bytes)+" در روز":"تاریخچه کافی نیست");
  metric("روزهای معتبر مبنا",count(item.baseline_days||0)+" از ۷ روز");
  metric("مصرف غیرعادی",item.anomaly===true?"بله · نیازمند بررسی":
    item.baseline_days>=3?"خیر":"قابل ارزیابی نیست");
  if(item.anomaly===true)create("div",
    "مصرف امروز از آستانه مقایسه با هفته قبل گذشته است. این هشدار آماری است و به معنای تخلف یا اشتراک‌گذاری اکانت نیست.",
    sheet,"c3-alert");
  const actions=create("div",undefined,sheet,"c3-actions");
  let restoreFocus=document.activeElement;
  if(item.sid){
    const link=create("a","پروفایل حساب",actions);
    link.href="/users/"+encodeURIComponent(item.sid);
  }
  const close=create("button","بستن",actions);close.type="button";
  function dismiss(){
    document.removeEventListener("keydown",onEscape);
    overlay.remove();
    if(restoreFocus?.isConnected)restoreFocus.focus();
  }
  function onEscape(e){if(e.key==="Escape")dismiss();}
  document.addEventListener("keydown",onEscape);
  close.onclick=dismiss;
  overlay.onclick=e=>{if(e.target===overlay)dismiss();};
  close.focus();
}
'''
_C3_STATE_OLD='const state={active:null,latest:{},query:"",loading:false,mutating:false};'
_C3_STATE_NEW='const state={active:null,latest:{},query:"",queries:{},modes:{},loading:false,mutating:false};'
assert _C3_TEMPLATE.count(_C3_STATE_OLD)==1
_C3_TEMPLATE=_C3_TEMPLATE.replace(_C3_STATE_OLD,_C3_STATE_NEW,1)
_C3_LAST='function renderCards(){'
assert _C3_TEMPLATE.count(_C3_LAST)==1
_C3_TEMPLATE=_C3_TEMPLATE.replace(_C3_LAST,_C3_JS+'\n'+_C3_LAST,1)
_C3_SWITCH_OLD='state.active=state.active===id?null:id;\n    notice.textContent="";'
_C3_SWITCH_NEW='''state.active=state.active===id?null:id;
    state.query=state.queries[id]||"";
    search.value=state.query;
    c3Mode.value=state.modes[id]||"normal";
    notice.textContent="";'''
assert _C3_TEMPLATE.count(_C3_SWITCH_OLD)==1
_C3_TEMPLATE=_C3_TEMPLATE.replace(_C3_SWITCH_OLD,_C3_SWITCH_NEW,1)
assert _C3_TEMPLATE.count('for(const item of data.rows){')==1
_C3_TEMPLATE=_C3_TEMPLATE.replace('for(const item of data.rows){','for(const item of c3VisibleRows(data.rows,server)){',1)
_C3_ACTION_OLD='const controls=create("td",undefined,tr);'
_C3_ACTION_NEW='''const controls=create("td",undefined,tr);
   const detailsButton=create("button","جزئیات",controls,"c2-btn c3-detail-button");
   detailsButton.type="button";
   detailsButton.onclick=()=>c3Details(server,item);'''
assert _C3_TEMPLATE.count(_C3_ACTION_OLD)==1
_C3_TEMPLATE=_C3_TEMPLATE.replace(_C3_ACTION_OLD,_C3_ACTION_NEW,1)
_C3_SEARCH_OLD='search.oninput=()=>{state.query=search.value;renderDetails();};'
_C3_SEARCH_NEW='''search.oninput=()=>{
  state.query=search.value;
  if(state.active)state.queries[state.active]=state.query;
  renderDetails();
};
c3Mode.onchange=()=>{
  if(state.active)state.modes[state.active]=c3Mode.value;
  renderDetails();
};'''
assert _C3_TEMPLATE.count(_C3_SEARCH_OLD)==1
_C3_TEMPLATE=_C3_TEMPLATE.replace(_C3_SEARCH_OLD,_C3_SEARCH_NEW,1)
_C3_TEMPLATE=_C3_TEMPLATE.replace(
    '<div class="c2-reports">','<div class="c2-reports" hidden>',1)
_C3_TEMPLATE=_C3_TEMPLATE.replace(
    '<th>مصرف کل</th><th>امروز</th><th>۳۰ روز</th>',
    '<th>مصرف کل</th><th>امروز</th><th>۳۰ روز</th>',1)

# Jinja2 recognizes a literal "{#" in CSS/JS as the start of a template comment.
if "{#" in _C3_TEMPLATE:
    raise RuntimeError("Unsafe Jinja comment opener in phase1 table template")
_c3_Environment().parse(_C3_TEMPLATE)
TEMPLATES["control_room.html"]=_C3_TEMPLATE
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)
