# HESAB_CUSTOMER_SERVICES_HOME_V1 — non-destructive customer home overlay
# Existing v2 payment page remains untouched at /?view=payments.
from fastapi.responses import HTMLResponse as _svc_html, RedirectResponse as _svc_redirect
from html import escape as _svc_escape
import json as _svc_json

_SVC_OLD_HOME = v2_home
_SVC_TEMPLATE = r'''<!doctype html><html lang="fa" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>حساب من | پنل مشترکین</title>
<link rel="stylesheet" href="/assets/v2.css"><link rel="stylesheet" href="/assets/v2_polish.css">
<style>
*{box-sizing:border-box}body{background:#f6f6f6!important;color:#141414;font-family:Estedad,Vazirmatn,Tahoma,sans-serif!important;margin:0}
.svc-shell{max-width:940px;margin:auto;padding:24px 18px 65px}
.svc-top{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:22px}
.svc-title{font-size:24px;font-weight:900}.svc-sub{font-size:12px;color:#888}
.svc-phone{font-size:12px;background:white;border:1px solid #ececec;padding:11px 15px;border-radius:14px}
.svc-card{background:#fff;border:1px solid #e8e8e8;box-shadow:0 16px 42px rgba(0,0,0,.035);border-radius:25px;padding:25px;margin-bottom:15px}
.svc-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}
.svc-heading h2{margin:0;font-size:21px;font-weight:900}
.svc-muted{color:#858585;font-size:12px}.svc-values{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:20px 0}
.svc-value{background:#f8f8f8;border:1px solid #eee;border-radius:16px;padding:17px}
.svc-value span{display:block;color:#818181;font-size:12px;margin-bottom:10px}
.svc-value strong{font-size:22px;color:#151515}.svc-btn{display:block;text-decoration:none;text-align:center;font-weight:800;padding:17px 16px;background:#111;color:#fff!important;border-radius:15px}
.svc-outline{display:block;text-decoration:none;color:#191919!important;text-align:center;padding:13px;border:1px solid #e8e8e8;border-radius:13px;margin-top:9px;font-weight:700;font-size:13px}
.svc-pills{display:flex;gap:7px;flex-wrap:wrap}.svc-pill{font-size:12px;border-radius:99px;background:#f0f0f0;padding:7px 11px;color:#666}
.svc-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px}
.svc-tile{background:#fff;border:1px solid #e8e8e8;border-radius:22px;min-height:134px;padding:22px;display:flex;flex-direction:column;justify-content:space-between;color:#141414!important;text-decoration:none;font-weight:850;cursor:pointer}
.svc-tile svg{width:27px;height:27px}.svc-note{font-size:11px;color:#888;line-height:1.9}
.svc-status{display:inline-flex;align-items:center;gap:8px;background:#f1f2f3;color:#60656b;padding:9px 12px;border-radius:30px;font-size:12px}
.svc-dot{width:8px;height:8px;background:#a5aab0;border-radius:50%}
.svc-tile:hover,.svc-outline:hover{border-color:#999}
.svc-results{display:none;border-top:1px solid #eee;margin-top:17px;padding-top:15px}
.svc-action{cursor:pointer;border:0;font:inherit;text-align:right}
@media(max-width:650px){.svc-shell{padding:18px 12px 50px}.svc-card{padding:19px;border-radius:22px}.svc-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.svc-tile{padding:17px;min-height:110px}.svc-heading h2{font-size:19px}.svc-value strong{font-size:18px}}
</style></head><body><main class="svc-shell">
<header class="svc-top"><div><div class="svc-title">حساب من</div><div class="svc-sub">پنل مشترکین VPN</div></div><span class="svc-phone">{{ phone }}</span></header>
<section class="svc-card"><div class="svc-heading"><h2>اشتراک VPN شما</h2><span class="svc-pill">{{ account_count }} اکانت</span></div>
<div class="svc-values"><div class="svc-value"><span>تاریخ تمدید</span><strong>{{ expiry }}</strong></div>
<div class="svc-value"><span>بدهی فعلی</span><strong>{{ debt }} <small style="font-size:12px">تومان</small></strong></div></div>
<a class="svc-btn" href="/?view=payments">تمدید یا پرداخت اشتراک</a>
<a class="svc-outline" href="/?view=payments#payment-history">سوابق پرداخت و جزئیات حساب</a></section>
<section class="svc-card"><div class="svc-heading"><h2>وضعیت سرور شما</h2><span class="svc-status"><span class="svc-dot"></span>در انتظار اتصال پایش</span></div>
<p class="svc-note">نمایش وضعیت پایدار، ناپایدار، در حال رسیدگی یا قطع پس از فعال‌شدن پایش تأییدشده تونل‌ها.</p>
<div class="svc-pills">{% for item in server_names %}<span class="svc-pill">{{ item }}</span>{% endfor %}</div></section>
<section class="svc-grid">
<button id="svc-speed-open" class="svc-tile svc-action" type="button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 17a9 9 0 1 1 16 0M12 16l5-7"/><circle cx="12" cy="16" r="2"/></svg><span>تست سرعت</span></button>
<a class="svc-tile" href="https://radar.cloudflare.com/traffic/ir" target="_blank" rel="noopener noreferrer"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c6 5 6 13 0 18M12 3c-6 5-6 13 0 18"/></svg><span>وضعیت اینترنت ایران</span></a>
<button class="svc-tile svc-action" type="button" onclick="document.getElementById('svc-support-note').hidden=false"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 13v-2a8 8 0 0 1 16 0v2M4 12h4v7H6a2 2 0 0 1-2-2zm12 0h4v5a2 2 0 0 1-2 2h-2z"/></svg><span>پشتیبانی</span></button>
</section>
<p id="svc-support-note" hidden class="svc-note">اطلاعات تماس پشتیبانی هنوز تنظیم نشده است.</p>
<section id="svc-speed-panel" class="svc-card" hidden style="margin-top:15px">
<div class="svc-heading"><h2>تست سرعت Cloudflare</h2><span class="svc-muted">تست از مرورگر شما</span></div>
<p class="svc-note">تست ممکن است حجم اینترنت مصرف کند. سرعت مسیر تا Cloudflare اندازه‌گیری می‌شود، نه الزاماً سرعت سرور VPN.</p>
<button class="svc-btn svc-action" id="svc-speed-start" type="button" style="width:100%;text-align:center">شروع تست سرعت</button>
<p id="svc-speed-state" class="svc-note" role="status"></p>
<div id="svc-speed-results" class="svc-results"><div class="svc-values">
<div class="svc-value"><span>دانلود</span><strong id="svc-down">—</strong></div>
<div class="svc-value"><span>آپلود</span><strong id="svc-up">—</strong></div>
<div class="svc-value"><span>پینگ</span><strong id="svc-ping">—</strong></div>
<div class="svc-value"><span>Jitter</span><strong id="svc-jitter">—</strong></div></div>
<button class="svc-outline svc-action" id="svc-copy" type="button" style="width:100%;text-align:center">کپی گزارش برای پشتیبانی</button>
</div></section></main>
<script type="module">
let report='';
const el=id=>document.getElementById(id);
el('svc-speed-open').onclick=()=>{el('svc-speed-panel').hidden=false;el('svc-speed-panel').scrollIntoView({behavior:'smooth'});};
el('svc-speed-start').onclick=async()=>{
 const btn=el('svc-speed-start');btn.disabled=true;el('svc-speed-state').textContent='در حال اتصال به موتور تست سرعت...';
 try {
   const {default:SpeedTest}=await import('https://esm.sh/@cloudflare/speedtest@1.15.0');
   const test=new SpeedTest({autoStart:false});
   test.onError=err=>{el('svc-speed-state').textContent='خطا در تست: '+String(err);btn.disabled=false;};
   test.onFinish=results=>{
     const v=results.getSummary();const fmt=(x,scale=1)=>Number.isFinite(Number(x))?(Number(x)/scale).toFixed(1):'—';
     const down=fmt(v.download,1000000),up=fmt(v.upload,1000000),ping=fmt(v.latency),jitter=fmt(v.jitter);
     el('svc-down').textContent=down+' Mbps';el('svc-up').textContent=up+' Mbps';
     el('svc-ping').textContent=ping+' ms';el('svc-jitter').textContent=jitter+' ms';
     report='تست سرعت Cloudflare\\nدانلود: '+down+' Mbps\\nآپلود: '+up+' Mbps\\nپینگ: '+ping+' ms\\nJitter: '+jitter+' ms\\nزمان: '+new Date().toLocaleString('fa-IR');
     el('svc-speed-results').style.display='block';el('svc-speed-state').textContent='تست تکمیل شد';btn.disabled=false;
   };
   el('svc-speed-state').textContent='در حال اندازه‌گیری...';test.play();
 } catch(e) {el('svc-speed-state').textContent='موتور تست در این مرورگر در دسترس نیست.';btn.disabled=false;}
};
el('svc-copy').onclick=()=>{if(report)navigator.clipboard.writeText(report).then(()=>el('svc-speed-state').textContent='گزارش کپی شد').catch(()=>el('svc-speed-state').textContent='امکان کپی خودکار وجود ندارد');};
</script></body></html>'''

def _svc_home(request: Request):
    if request.query_params.get("view") == "payments":
        return _SVC_OLD_HOME(request)
    phone = _v2_session_phone(request)
    if not phone:
        return _SVC_OLD_HOME(request)
    # Retain the pre-existing Ayria checkout return/receipt flow unchanged.
    if request.cookies.get("moshtarakin_checkout"):
        return _SVC_OLD_HOME(request)
    with db_conn() as conn:
        accounts = active_subscriptions(conn, phone)
    total = sum(int(a.get("debt") or 0) for a in accounts)
    expiries = [a.get("expiry_date") for a in accounts if a.get("expiry_date")]
    expiry = jalali_text(min(expiries)) if expiries else "ثبت نشده"
    html = jinja.from_string(_SVC_TEMPLATE).render(
        phone=phone, account_count=len(accounts),
        expiry=expiry, debt=f"{total:,}", server_names=[]
    )
    return _svc_html(html, headers={"Cache-Control":"private, no-store"})

# Replace only the existing GET / endpoint, preserving POST payments and all v2 routes.
for _svc_route in app.router.routes:
    if getattr(_svc_route, "path", None)=="/" and "GET" in (getattr(_svc_route,"methods",set()) or set()):
        if getattr(_svc_route,"endpoint",None) is v2_home:
            _svc_route.endpoint=_svc_home
            _svc_route.dependant.call=_svc_home
            break
else:
    raise RuntimeError("Expected customer V2 home route missing; refusing overlay")
