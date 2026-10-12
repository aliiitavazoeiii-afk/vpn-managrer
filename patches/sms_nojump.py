# DEBT_SMS_LIVE_NOJUMP_V1
# Final override: two placement choices, same canonical SMS endpoint, AJAX only.
# This patch modifies templates/assets, NOT billing or ledger routes.
import re as _debt_sms_live_re

_debt_sms_live_tpl = TEMPLATES.get("debts.html", "")
if not _debt_sms_live_tpl:
    raise RuntimeError("Debt template unavailable for no-jump SMS")

# One button beside 'پیگیری شد' in each debtor group's header.
_debt_sms_header_form = r"""
<form method="post" action="/sms/debt-send"
      class="debt-sms-header-form" data-debt-sms-form
      data-sms-phone="{{ g.phone or '' }}" data-sms-cycle="{{ g.first_expiry or '' }}">
  <input type="hidden" name="phone" value="{{ g.phone or '' }}">
  <input type="hidden" name="cycle" value="{{ g.first_expiry or '' }}">
  {% if g.phone %}
  <button type="submit" class="debt-sms-btn debt-sms-header-btn"
          data-debt-sms-btn title="ارسال پیامک و انتقال مستقیم به در انتظار">✉ ارسال پیامک</button>
  {% else %}
  <button type="button" class="debt-sms-btn sms-no-phone" disabled>بدون شماره</button>
  {% endif %}
</form>
"""
if "debt-sms-header-form" not in _debt_sms_live_tpl:
    track_form = _debt_sms_live_re.compile(
        r'(<form\b[^>]*action="/followups/track-group"[^>]*>.*?</form>)',
        flags=_debt_sms_live_re.S,
    )
    _debt_sms_live_tpl, _count_header = track_form.subn(
        lambda m: m.group(1) + _debt_sms_header_form,
        _debt_sms_live_tpl,
        count=1,
    )
    if _count_header != 1:
        raise RuntimeError("Can't find 'پیگیری شد' header action; refusing to patch")

# The existing copy-area button and the new header button share the same route.
# Capture the submit BEFORE any legacy bubble handler can trigger navigation,
# preserving scroll, expanded groups, search and every unrelated group.
_DEBT_SMS_NOJUMP_UI = r"""
<style>
.debt-sms-header-form{display:inline-flex;margin:0;align-items:center}
.debt-sms-header-btn{min-height:34px;padding:6px 12px;white-space:nowrap}
[data-debt-sms-form].sms-busy{opacity:.7;pointer-events:none}
[data-debt-sms-form] [data-debt-sms-btn]:disabled{cursor:wait;opacity:.7}
#debt-sms-live-toast{position:fixed;inset:auto 16px 20px auto;z-index:100000;
  max-width:min(430px,calc(100vw - 32px));padding:13px 17px;border-radius:12px;
  font:700 12px/1.9 var(--site-font),Tahoma,sans-serif;
  color:#dfffea;background:#163327;border:1px solid #318760;
  box-shadow:0 16px 45px rgba(0,0,0,.3)}
#debt-sms-live-toast.error{color:#ffe1e5;background:#41212b;border-color:#aa5166}
</style>
<script>
(function(){
  "use strict";
  if(window.__hesabSmsNoJumpV1)return;
  window.__hesabSmsNoJumpV1=true;
  let busy=false;
  let toastTimer=0;
  const prefix="hesab.debts.";
  function notice(text,error){
    let el=document.getElementById("debt-sms-live-toast");
    if(!el){el=document.createElement("div");el.id="debt-sms-live-toast";
      el.setAttribute("role","status");document.body.append(el);}
    el.textContent=text;el.classList.toggle("error",!!error);
    clearTimeout(toastTimer);
    toastTimer=setTimeout(()=>el.remove(),5200);
  }
  function setPending(group,on){
    for(const f of group.querySelectorAll('form[data-debt-sms-form]')){
      f.classList.toggle("sms-busy",on);
      const b=f.querySelector("[data-debt-sms-btn]");
      if(!b)continue;
      b.disabled=on;
      b.textContent=on?"… در حال ثبت و انتقال":"✉ ارسال پیامک";
    }
  }
  function clearLegacyScroll(){
    for(const key of ["open","group","groupTop","scrollY","search"]){
      try{sessionStorage.removeItem(prefix+key)}catch(_){}
    }
  }
  function refreshSearch(root){
    const field=document.getElementById("debt-search");
    const counter=document.getElementById("debt-search-count");
    const empty=document.getElementById("debt-no-results");
    let n=0;
    for(const g of root.querySelectorAll("[data-debt-group]")){
      const found=!(field&&field.value.trim())||
        (g.getAttribute("data-search")||"").toLowerCase().includes(field.value.trim().toLowerCase());
      g.hidden=!found;
      if(found)n++;
    }
    if(counter)counter.textContent=String(n).replace(/\d/g,d=>"۰۱۲۳۴۵۶۷۸۹"[d])+" نتیجه";
    if(empty)empty.hidden=n!==0;
  }
  document.addEventListener("submit",async function(e){
    const form=e.target;
    if(!(form instanceof HTMLFormElement)||
       !form.matches('.debt-desk form[data-debt-sms-form]'))return;
    // Block all default submissions and older bubble listeners, including
    // scroll-position-saving listeners that caused the jump to top.
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    if(busy)return;
    const group=form.closest("[data-debt-group]");
    const desk=document.querySelector(".debt-desk");
    if(!group||!desk){notice("گروه مربوط به پیامک پیدا نشد؛ هیچ پیامی نفرستادیم.",true);return}
    const key=group.getAttribute("data-group-key");
    if(!key){notice("شناسه گروه نامعتبر است؛ ارسال لغو شد.",true);return}
    busy=true;setPending(group,true);
    const y=window.scrollY;
    const rect=group.getBoundingClientRect();
    const beforeBottom=rect.bottom;
    const groupHeight=rect.height;
    const oldAnchor=document.documentElement.style.overflowAnchor;
    document.documentElement.style.overflowAnchor="none";
    let successful=false;
    try{
      const res=await fetch(form.action,{
        method:"POST",body:new FormData(form),credentials:"same-origin",
        cache:"no-store",redirect:"follow",headers:{"X-Requested-With":"XMLHttpRequest"}
      });
      if(!res.ok)throw Error("SMS request HTTP "+res.status);
      const url=new URL(res.url,location.href);
      if(url.origin!==location.origin||url.pathname!=="/debts"||
         !url.searchParams.has("sms_queued")||!url.searchParams.has("tracked")){
         notice("ارسال جدید ثبت نشد یا قبلاً ثبت شده؛ وضعیت پیامک را بررسی کن.",true);
         return;
      }
      // The redirect itself isn't enough: ask the authoritative page again
      // and remove a group only if it is actually gone from the debt list.
      const latest=await fetch("/debts",{credentials:"same-origin",cache:"no-store",
        headers:{"X-Requested-With":"XMLHttpRequest"}});
      if(!latest.ok)throw Error("Refresh verification HTTP "+latest.status);
      const doc=new DOMParser().parseFromString(await latest.text(),"text/html");
      const updatedDesk=doc.querySelector(".debt-desk");
      const updatedSummary=doc.querySelector(".debt-summary-clean");
      const summary=document.querySelector(".debt-summary-clean");
      if(!updatedDesk||!updatedSummary||!summary)throw Error("Unexpected debtor page");
      const remaining=[...updatedDesk.querySelectorAll("[data-debt-group]")];
      if(remaining.some(g=>g.getAttribute("data-group-key")===key)){
        notice("پیام ثبت شد اما گروه هنوز در وصول دیده می‌شود؛ در انتظار را بررسی کن.",true);
        return;
      }
      const active=document.activeElement;
      if(active instanceof HTMLElement && group.contains(active))active.blur();
      group.remove();
      if(!desk.querySelector("[data-debt-group]"))desk.innerHTML=updatedDesk.innerHTML;
      summary.innerHTML=updatedSummary.innerHTML;
      refreshSearch(desk);
      clearLegacyScroll();
      // Reflow above the viewport must not visually push the user away.
      // If this card was above the screen, compensate its removed height.
      const targetY=beforeBottom<=0?Math.max(0,y-groupHeight):y;
      window.scrollTo({top:targetY,behavior:"instant"});
      requestAnimationFrame(()=>window.scrollTo({top:targetY,behavior:"instant"}));
      successful=true;
      notice("پیامک در صف ارسال ثبت شد و کاربر به «در انتظار» منتقل شد.",false);
    }catch(err){
      // Never replay an SMS POST: Android may have received the first job.
      notice("وضعیت ثبت پیامک قطعی نیست؛ پیش از اقدام دوباره سوابق پیامک را بررسی کن.",true);
    }finally{
      busy=false;
      document.documentElement.style.overflowAnchor=oldAnchor;
      if(!successful&&group.isConnected)setPending(group,false);
    }
  },true);
})();
</script>
"""
if "window.__hesabSmsNoJumpV1" not in _debt_sms_live_tpl:
    if "{% endblock %}" not in _debt_sms_live_tpl:
        raise RuntimeError("Debt template content terminator missing")
    _head,_tail=_debt_sms_live_tpl.rsplit("{% endblock %}",1)
    _debt_sms_live_tpl=_head+_DEBT_SMS_NOJUMP_UI+"\n{% endblock %}"+_tail

TEMPLATES["debts.html"]=_debt_sms_live_tpl
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)
