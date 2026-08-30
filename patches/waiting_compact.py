# Compact waiting inbox: one row per payer/group, click to expand children, with search.

WAITING_COMPACT_TEMPLATE = r'''{% extends "base.html" %}
{% block title %}در انتظار · حساب VPN{% endblock %}
{% block heading %}در انتظار پرداخت{% endblock %}
{% block subheading %}هر پرداخت‌کننده یک ردیف؛ برای دیدن اکانت‌ها روی ردیف کلیک کن{% endblock %}
{% block content %}
{% if request.query_params.get("paid") %}<div class="collect-success">✓ پرداخت ثبت شد و اکانت از انتظار خارج شد.</div>{% endif %}
{% if request.query_params.get("cut") %}<div class="collect-error">اکانت به وضعیت «قطع شد» منتقل شد و دیگر در بدهی‌ها نمایش داده نمی‌شود.</div>{% endif %}
{% if request.query_params.get("restored") %}<div class="collect-success">✓ اکانت دوباره به صفحه بدهی‌ها برگشت.</div>{% endif %}
{% if request.query_params.get("undo") %}<div class="collect-success">✓ پرداخت لغو شد و اکانت دوباره به «در انتظار» برگشت.</div>{% endif %}

<section class="waiting-summary">
  <div><small>پرداخت‌کننده در انتظار</small><strong>{{ groups|length|fa }}</strong></div>
  <div><small>اکانت در انتظار</small><strong>{{ service_count|fa }}</strong></div>
  <div><small>جمع بدهی در انتظار</small><strong>{{ total|money }} <em>تومان</em></strong></div>
</section>

<div class="waiting-searchbar">
  <span>⌕</span>
  <input id="waiting-search" type="search" autocomplete="off" placeholder="جستجو با نام یا شماره همراه…">
  <small id="waiting-search-count">{{ groups|length|fa }} نتیجه</small>
</div>

<div class="waiting-list">
{% for g in groups %}
  <section class="waiting-group" data-waiting-group data-search="{{ g.search_text }}">
    <div class="waiting-head waiting-toggle" data-waiting-toggle="{{ loop.index0 }}" role="button" tabindex="0" aria-expanded="false">
      <div class="waiting-head-name">
        <small>نام</small>
        <strong>{{ g.primary_name }}</strong>
        {% if g.services > 1 %}<span>{{ g.services|fa }} اکانت</span>{% endif %}
      </div>
      <div class="waiting-head-phone">
        <small>شماره همراه</small>
        {% if g.phone %}<button type="button" class="waiting-phone" data-copy="{{ g.phone }}">{{ g.phone }}</button>{% else %}<strong>بدون شماره</strong>{% endif %}
      </div>
      <div class="waiting-head-expiry">
        <small>قدیمی‌ترین سررسید</small>
        <strong>{{ g.first_expiry|jdate }}</strong>
      </div>
      <div class="waiting-head-debt">
        <small>جمع بدهی</small>
        <strong>{{ g.debt|money }} <em>تومان</em></strong>
      </div>
      <span class="waiting-chevron">⌄</span>
    </div>

    <div class="waiting-services" data-waiting-panel="{{ loop.index0 }}" hidden>
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
<div id="waiting-no-results" class="empty debt-empty" hidden>موردی با این نام یا شماره پیدا نشد.</div>
<div id="copy-toast" class="copy-toast">کپی شد</div>

<script>
(function(){
  const interactive = el => el.closest('button,a,form,input,select,textarea,details,summary');
  document.querySelectorAll('[data-waiting-toggle]').forEach(head=>{
    const toggle=()=>{
      const id=head.dataset.waitingToggle;
      const panel=document.querySelector('[data-waiting-panel="'+id+'"]');
      if(!panel) return;
      const opening=panel.hasAttribute('hidden');
      if(opening){panel.removeAttribute('hidden');head.classList.add('open');head.setAttribute('aria-expanded','true');}
      else{panel.setAttribute('hidden','');head.classList.remove('open');head.setAttribute('aria-expanded','false');}
    };
    head.addEventListener('click',e=>{if(interactive(e.target)) return;toggle();});
    head.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ') && !interactive(e.target)){e.preventDefault();toggle();}});
  });

  const search=document.getElementById('waiting-search');
  if(search){
    const groups=[...document.querySelectorAll('[data-waiting-group]')];
    const count=document.getElementById('waiting-search-count');
    const empty=document.getElementById('waiting-no-results');
    const fa=n=>String(n).replace(/\d/g,d=>'۰۱۲۳۴۵۶۷۸۹'[d]);
    const apply=()=>{
      const term=search.value.trim().toLowerCase();
      let visible=0;
      groups.forEach(g=>{const show=!term||(g.dataset.search||'').toLowerCase().includes(term);g.hidden=!show;if(show)visible++;});
      if(count) count.textContent=fa(visible)+' نتیجه';
      if(empty) empty.hidden=visible!==0;
    };
    search.addEventListener('input',apply);
  }
})();
</script>
{% endblock %}'''

TEMPLATES["followups.html"] = WAITING_COMPACT_TEMPLATE

# Defensive: keep the debt-page search available even if a future patch replaces the debt template.
_debt_tpl = TEMPLATES.get("debts.html", "")
if _debt_tpl and 'id="debt-search"' not in _debt_tpl and '<div class="debt-desk">' in _debt_tpl:
    _debt_search = r'''
<div class="debt-searchbar">
  <span>⌕</span>
  <input id="debt-search" type="search" autocomplete="off" placeholder="جستجو با نام یا شماره همراه…">
  <small id="debt-search-count">{{ groups|length|fa }} نتیجه</small>
</div>
'''
    TEMPLATES["debts.html"] = _debt_tpl.replace('<div class="debt-desk">', _debt_search + '<div class="debt-desk">', 1)

# Force a fresh static bundle because waiting_compact.css is appended to app.css.
_base_tpl = TEMPLATES.get("base.html", "")
if _base_tpl:
    for _v in range(2, 12):
        _base_tpl = _base_tpl.replace(f'/static/app.css?v={_v}', '/static/app.css?v=11')
        _base_tpl = _base_tpl.replace(f'/static/app.js?v={_v}', '/static/app.js?v=11')
    TEMPLATES["base.html"] = _base_tpl

if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)
