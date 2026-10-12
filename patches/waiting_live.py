# Progressive enhancement for the waiting inbox. Appended after all legacy patches.
# Keeps existing settlement and audit routes authoritative.
from fastapi import Form
from fastapi.responses import RedirectResponse
import re as _waiting_live_re


def waiting_restore_group(
    phone: str = Form(""),
    sid: int = Form(0),
    db: Session = Depends(get_db),
):
    """Restore only currently waiting, indebted children of the selected payer."""
    refresh_billing(db)
    states = _followup_states(db)
    if phone:
        candidates = (
            db.query(Subscription)
            .filter(Subscription.phone == phone, Subscription.is_free.is_(False))
            .order_by(Subscription.id.asc())
            .all()
        )
    else:
        s = db.get(Subscription, int(sid or 0))
        candidates = [s] if s is not None else []

    restored = []
    for s in candidates:
        if (
            s is None
            or bool(s.is_free)
            or states.get(int(s.id)) != "waiting"
            or current_debt_for(s, today_local()) <= 0
        ):
            continue
        _followup_set(db, int(s.id), None, "group restored to debt inbox")
        restored.append(int(s.id))

    if restored:
        db.add(AuditEvent(
            kind="followup_group_restore",
            message=f"Restored waiting group; count={len(restored)}; ids={restored}",
        ))
        db.commit()
    return RedirectResponse("/followups?restored=1", 303)


app.add_api_route("/followups/restore-group", waiting_restore_group, methods=["POST"])


_WAITING_LIVE_STYLE = r"""
<style>
.waiting-group-restore-form{margin:0;flex:0 0 auto}
.waiting-group-restore-btn{
  min-height:38px;border:1px solid rgba(148,166,194,.33);border-radius:10px;
  background:rgba(126,147,179,.10);color:#e0e7f5;padding:0 10px;
  font:700 11px/1.3 var(--site-font),Tahoma,sans-serif;cursor:pointer;white-space:nowrap
}
.waiting-group-restore-btn:hover{border-color:rgba(173,198,237,.70);background:rgba(126,147,179,.20)}
.waiting-pay-tools{flex-wrap:wrap!important;justify-content:flex-end!important}
.waiting-head{grid-template-columns:minmax(135px,1fr) minmax(120px,.8fr) minmax(110px,.65fr) minmax(120px,.7fr) minmax(315px,1.65fr) 22px!important}
.waiting-live-toast{position:fixed;bottom:22px;right:22px;z-index:2000;max-width:min(450px,calc(100vw - 44px));padding:13px 17px;
  background:#152b23;border:1px solid #448e68;border-radius:12px;box-shadow:0 18px 50px #0007;color:#d5ffe6;
  font:700 12px/1.9 var(--site-font),Tahoma,sans-serif}
.waiting-live-toast.error{background:#3b1923;border-color:#a84459;color:#ffd6df}
.waiting-list.is-updating{opacity:.58;pointer-events:none;transition:opacity .18s}
.waiting-list form button:disabled,.waiting-head form button:disabled{opacity:.5;cursor:wait}
@media(max-width:1200px){
 .waiting-head{grid-template-columns:repeat(2,minmax(0,1fr))!important}
 .waiting-head-pay{grid-column:1/-1!important}
 .waiting-pay-tools{justify-content:flex-start!important}
}
@media(max-width:600px){
 .waiting-head{grid-template-columns:1fr!important}
 .waiting-pay-tools{display:flex!important;gap:7px!important}
 .waiting-group-restore-btn{width:100%}
}
@media(prefers-reduced-motion:reduce){.waiting-list.is-updating{transition:none}}
</style>
"""

_WAITING_LIVE_SCRIPT = r"""
<script>
(function(){
  'use strict';
  const root=document.querySelector('.waiting-list');
  if(!root)return;
  const search=document.getElementById('waiting-search');
  const count=document.getElementById('waiting-search-count');
  const noResults=document.getElementById('waiting-no-results');
  const fa=n=>String(n).replace(/\d/g,d=>'۰۱۲۳۴۵۶۷۸۹'[d]);
  const interactive=el=>!!el.closest('button,a,form,input,select,textarea,details,summary');
  let busy=false;
  let toastTimer;

  function groups(){return [...root.querySelectorAll('[data-waiting-group]')]}
  function applySearch(){
    const term=(search?.value||'').trim().toLowerCase();
    let total=0;
    for(const g of groups()){
      const visible=!term||(g.dataset.search||'').toLowerCase().includes(term);
      g.hidden=!visible;
      if(visible)total++;
    }
    if(count)count.textContent=fa(total)+' نتیجه';
    if(noResults)noResults.hidden=total!==0;
  }
  function toggle(head){
    const parent=head.closest('[data-waiting-group]');
    const panel=parent?.querySelector('.waiting-services');
    if(!panel)return;
    const opening=panel.hasAttribute('hidden');
    panel.hidden=!opening;
    head.classList.toggle('open',opening);
    head.setAttribute('aria-expanded',String(opening));
  }
  function openKeys(){
    return new Set(groups().filter(g=>!g.querySelector('.waiting-services')?.hidden).map(g=>g.dataset.waitingKey));
  }
  function toast(message,error=false){
    let el=document.getElementById('waiting-live-feedback');
    if(!el){
      el=document.createElement('div');
      el.id='waiting-live-feedback';
      el.className='waiting-live-toast';
      el.setAttribute('role','status');
      el.setAttribute('aria-live','polite');
      document.body.append(el);
    }
    el.textContent=message;el.classList.toggle('error',error);
    clearTimeout(toastTimer);
    toastTimer=setTimeout(()=>el.remove(),4200);
  }
  async function copy(value){
    try{
      await navigator.clipboard.writeText(value);
      toast('شماره کپی شد');
    }catch(_){
      toast('کپی خودکار ممکن نشد؛ شماره را به‌صورت دستی کپی کن.',true);
    }
  }

  root.addEventListener('click',e=>{
    const copyButton=e.target.closest('[data-copy]');
    if(copyButton){
      e.preventDefault();e.stopPropagation();
      copy(copyButton.dataset.copy||copyButton.textContent.trim());
      return;
    }
    const head=e.target.closest('[data-waiting-toggle]');
    if(head && !interactive(e.target))toggle(head);
  });
  root.addEventListener('keydown',e=>{
    const head=e.target.closest('[data-waiting-toggle]');
    if(head && (e.key==='Enter'||e.key===' ') && !interactive(e.target)){
      e.preventDefault();toggle(head);
    }
  });
  search?.addEventListener('input',applySearch);
  applySearch();

  document.addEventListener('submit',async e=>{
    const form=e.target;
    if(!form.matches('.waiting-list form'))return;
    if(e.defaultPrevented)return; // Preserve cancellation by existing onsubmit/confirm.
    if((form.method||'').toUpperCase()!=='POST')return;
    if(busy){e.preventDefault();return}
    e.preventDefault();
    const scrollY=window.scrollY;
    const expanded=openKeys();
    const focusGroup=form.closest('[data-waiting-group]')?.dataset.waitingKey;
    const submitter=e.submitter||form.querySelector('button[type="submit"],button:not([type])');
    busy=true;root.classList.add('is-updating');
    root.querySelectorAll('button').forEach(b=>b.disabled=true);
    try{
      const payload=new FormData(form);
      if(submitter?.name)payload.append(submitter.name,submitter.value);
      const response=await fetch(form.action,{
        method:'POST',body:payload,credentials:'same-origin',redirect:'follow',
        headers:{'X-Requested-With':'XMLHttpRequest'}
      });
      if(!response.ok)throw new Error('POST status '+response.status);
      if(new URL(response.url).origin!==location.origin)throw new Error('unexpected origin');

      // A rejected financial input must stay editable; never clear the form.
      const redirect=new URL(response.url);
      if(redirect.searchParams.has('amount_error') ||
         redirect.searchParams.has('manage_error') ||
         redirect.searchParams.has('phone_error')){
        toast('عملیات انجام نشد؛ مقادیر یا تاریخ را بررسی کن.',true);
        return;
      }
      // Keep the actual database-driven GET authoritative: no optimistic payment state.
      const latest=await fetch('/followups',{credentials:'same-origin',cache:'no-store'});
      if(!latest.ok)throw new Error('GET status '+latest.status);
      const html=await latest.text();
      const doc=new DOMParser().parseFromString(html,'text/html');
      const updatedList=doc.querySelector('.waiting-list');
      const updatedSummary=doc.querySelector('.waiting-summary');
      const currentSummary=document.querySelector('.waiting-summary');
      if(!updatedList||!updatedSummary||!currentSummary)throw new Error('unexpected response page');

      root.innerHTML=updatedList.innerHTML;
      currentSummary.innerHTML=updatedSummary.innerHTML;
      for(const g of groups()){
        const shouldOpen=expanded.has(g.dataset.waitingKey)||
          (focusGroup===g.dataset.waitingKey);
        if(shouldOpen){
          const panel=g.querySelector('.waiting-services'),head=g.querySelector('[data-waiting-toggle]');
          if(panel){panel.hidden=false}
          if(head){head.classList.add('open');head.setAttribute('aria-expanded','true')}
        }
      }
      applySearch();
      window.scrollTo(0,scrollY);
      let message='تغییرات ثبت شد و لیست به‌روز شد.';
      const path=new URL(form.action).pathname;
      if(path.endsWith('/restore')||path.endsWith('/restore-group'))message='به وصول بدهی برگردانده شد.';
      else if(path.endsWith('/cut'))message='اکانت به حذفی‌ها منتقل شد.';
      else if(path.endsWith('/pay')||path.endsWith('/pay-group'))message='پرداخت ثبت شد.';
      else if(path.endsWith('/pay-amount'))message='مبلغ واقعی ثبت شد.';
      toast(message);
    }catch(err){
      toast('وضعیت عملیات قطعی نیست. پیش از تلاش دوباره، لیست و سابقه پرداخت را بررسی کن.',true);
      // Never auto-retry a financial POST.
    }finally{
      busy=false;root.classList.remove('is-updating');
      root.querySelectorAll('button').forEach(b=>b.disabled=false);
    }
  });
})();
</script>
"""

_tpl = TEMPLATES.get("followups.html", "")
if _tpl:
    # Put a single group restore action alongside the existing full settlement action.
    _anchor = '<div class="waiting-head-pay waiting-pay-tools">'
    if _anchor in _tpl and '/followups/restore-group' not in _tpl:
        _group_restore = r'''
        <form method="post" action="/followups/restore-group" class="waiting-group-restore-form"
              onsubmit="return confirm('همه زیرمجموعه‌های در انتظار این سرگروه به وصول بدهی برگردند؟')">
          <input type="hidden" name="phone" value="{{ g.phone or '' }}">
          <input type="hidden" name="sid" value="{% if not g.phone %}{{ g.rows[0].s.id }}{% else %}0{% endif %}">
          <button type="submit" class="waiting-group-restore-btn">برگردان همه</button>
        </form>
'''
        _tpl = _tpl.replace(_anchor, _anchor + _group_restore, 1)

    _tpl = _tpl.replace(
        '<section class="waiting-group" data-waiting-group',
        '<section class="waiting-group" data-waiting-key="{{ (\'phone:\' ~ g.phone) if g.phone else (\'sid:\' ~ g.rows[0].s.id) }}" data-waiting-group',
        1,
    )

    # Old per-node listeners cannot survive content swaps; replace with delegated listeners.
    _tpl, _removed = _waiting_live_re.subn(
        r'<script>\s*\(function\(\)\{[\s\S]*?\}\)\(\);\s*</script>',
        '', _tpl, count=1,
    )
    if _removed != 1:
        raise RuntimeError("Unexpected waiting dashboard script; refuse live patch")

    _tpl = _tpl.replace('{% block content %}', '{% block content %}' + _WAITING_LIVE_STYLE, 1)
    # The template contains title, heading, subheading and content blocks.
    # Inject at the LAST endblock (content), never into the page title.
    _before, _ending = _tpl.rsplit('{% endblock %}', 1)
    _tpl = _before + _WAITING_LIVE_SCRIPT + '\n{% endblock %}' + _ending
    TEMPLATES["followups.html"] = _tpl
    if hasattr(env.loader, "mapping"):
        env.loader.mapping.update(TEMPLATES)


# Targeted live follow-up from the DEBT inbox.
# Keep the original loaded debt cards/listeners intact: only remove a group that
# the authoritative server GET confirms was moved to "waiting".
_DEBT_TRACK_LIVE_SCRIPT = r"""
<script>
(function(){
  'use strict';
  const desk=document.querySelector('.debt-desk');
  if(!desk) return;
  const summary=document.querySelector('.debt-summary-clean');
  const search=document.getElementById('debt-search');
  const searchCount=document.getElementById('debt-search-count');
  const empty=document.getElementById('debt-no-results');
  let processing=false;
  let toastTimer=null;
  const fa=n=>String(n).replace(/\d/g,d=>'۰۱۲۳۴۵۶۷۸۹'[d]);

  function keyOf(group){return group && group.getAttribute('data-group-key')}
  function updateSearch(){
    const term=(search && search.value || '').trim().toLowerCase();
    let visible=0;
    desk.querySelectorAll('[data-debt-group]').forEach(g=>{
      const found=!term||(g.getAttribute('data-search')||'').toLowerCase().includes(term);
      g.hidden=!found;
      if(found)visible++;
    });
    if(searchCount)searchCount.textContent=fa(visible)+' نتیجه';
    if(empty)empty.hidden=visible!==0;
  }
  // app.js captures the original groups in a static array. After an async
  // removal, use fresh DOM queries for search so removed rows never reappear.
  if(search){
    search.addEventListener('input',event=>{
      event.stopImmediatePropagation();
      updateSearch();
    },true);
  }
  function flash(message,isError){
    let toast=document.getElementById('debt-live-feedback');
    if(!toast){
      toast=document.createElement('div');
      toast.id='debt-live-feedback';
      toast.style.cssText='position:fixed;bottom:22px;right:22px;z-index:3000;max-width:min(430px,calc(100vw - 44px));background:#172d23;color:#e2ffe9;border:1px solid #4b926c;border-radius:12px;padding:12px 17px;box-shadow:0 18px 45px #0007;font-size:13px;line-height:1.8';
      toast.setAttribute('role','status');
      document.body.appendChild(toast);
    }
    toast.textContent=message;
    toast.style.background=isError?'#401d28':'#172d23';
    toast.style.borderColor=isError?'#b55468':'#4b926c';
    toast.style.color=isError?'#ffe0e8':'#e2ffe9';
    clearTimeout(toastTimer);
    toastTimer=setTimeout(()=>toast.remove(),4800);
  }

  // Existing app.js owns expand, copy and search for the original cards.
  // Do not replace unrelated cards or their event listeners.
  document.addEventListener('submit',async event=>{
    const form=event.target;
    if(!(form instanceof HTMLFormElement))return;
    if(!form.matches('.debt-desk form.followup-track-form'))return;
    if(event.defaultPrevented)return; // An existing confirmation rejected the action.
    event.preventDefault();
    if(processing)return;
    processing=true;
    const button=event.submitter||form.querySelector('button[type=submit],button:not([type])');
    if(button)button.disabled=true;
    const group=form.closest('[data-debt-group]');
    const key=keyOf(group);
    const originalScroll=window.scrollY;
    try{
      if(!group||!key)throw new Error('missing group identifier');
      const res=await fetch(form.action,{
        method:'POST',body:new FormData(form),redirect:'follow',
        credentials:'same-origin',headers:{'X-Requested-With':'XMLHttpRequest'}
      });
      if(!res.ok)throw new Error('POST failed: '+res.status);
      const redirected=new URL(res.url);
      if(redirected.origin!==location.origin||redirected.pathname!=='/debts'||!redirected.searchParams.has('tracked')){
        throw new Error('unexpected follow-up response');
      }
      const latest=await fetch('/debts',{
        credentials:'same-origin',cache:'no-store',headers:{'X-Requested-With':'XMLHttpRequest'}
      });
      if(!latest.ok)throw new Error('GET failed: '+latest.status);
      const doc=new DOMParser().parseFromString(await latest.text(),'text/html');
      const incoming=doc.querySelector('.debt-desk');
      const incomingSummary=doc.querySelector('.debt-summary-clean');
      if(!incoming||!incomingSummary||!summary)throw new Error('unexpected debtor page');
      const stillThere=[...incoming.querySelectorAll('[data-debt-group]')]
        .some(item=>keyOf(item)===key);
      if(stillThere){
        flash('این گروه هنوز در وصول بدهی ثبت است؛ صفحه را بررسی کن.',true);
        return;
      }
      // The move is confirmed by the database-backed GET. Remove only this group.
      group.remove();
      if(!desk.querySelector('[data-debt-group]'))desk.innerHTML=incoming.innerHTML;
      summary.innerHTML=incomingSummary.innerHTML;
      updateSearch();
      // Legacy savePosition runs on form submit. Clear it after this AJAX action.
      ['open','group','groupTop','scrollY','search'].forEach(part=>{
        try{sessionStorage.removeItem('hesab.debts.'+part)}catch(_){}
      });
      window.scrollTo(0,originalScroll);
      flash('این سرگروه به «در انتظار» منتقل شد.',false);
    }catch(_){
      // A financial/state-changing POST must never be automatically retried.
      flash('نتیجه عملیات قطعی نیست؛ قبل از کلیک مجدد، فهرست در انتظار را بررسی کن.',true);
    }finally{
      processing=false;
      if(button&&button.isConnected)button.disabled=false;
    }
  });

  // New cards aren't inserted on this page, so existing app.js search handlers remain valid.
})();
</script>
"""

_debt_live_tpl=TEMPLATES.get("debts.html", "")
if _debt_live_tpl and 'id="debt-live-feedback"' not in _debt_live_tpl and 'followup-track-form' in _debt_live_tpl:
    if _debt_live_tpl.count("{% endblock %}") < 4 or 'class="debt-desk"' not in _debt_live_tpl:
        raise RuntimeError("Unexpected debt template; refuse to inject live action")
    _body, _tail = _debt_live_tpl.rsplit("{% endblock %}", 1)
    _debt_live_tpl = _body + _DEBT_TRACK_LIVE_SCRIPT + "\n{% endblock %}" + _tail
    TEMPLATES["debts.html"] = _debt_live_tpl
    if hasattr(env.loader, "mapping"):
        env.loader.mapping.update(TEMPLATES)
