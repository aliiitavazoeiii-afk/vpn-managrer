# Hesab VPN phone editor: change each subscription phone and regroup automatically.
from fastapi import Form

_phone_style = r'''
<style>
.phone-editor{border:1px solid rgba(255,255,255,.09);border-radius:10px;background:rgba(255,255,255,.02);overflow:hidden}
.phone-editor summary{list-style:none;cursor:pointer;padding:7px 10px;font-size:10px;color:#aeb7c6;text-align:center;user-select:none}
.phone-editor summary::-webkit-details-marker{display:none}
.phone-editor[open] summary{border-bottom:1px solid rgba(255,255,255,.07);color:#fff}
.phone-edit-form{padding:9px;display:flex;flex-direction:column;gap:7px}.phone-edit-form label{font-size:10px;color:#8e99aa}
.phone-edit-row{display:grid;grid-template-columns:1fr 78px;gap:7px}.phone-edit-row input{min-width:0;height:36px;background:#0c1320;color:#fff;border:1px solid rgba(255,255,255,.13);border-radius:8px;padding:0 9px;font:inherit;font-size:12px;direction:ltr;text-align:left}.phone-edit-row button{border:0;border-radius:8px;background:#eef2f6;color:#131820;font:inherit;font-size:11px;font-weight:800;cursor:pointer}.phone-edit-form small{font-size:9px;color:#768295;line-height:1.55}
@media(max-width:640px){.phone-edit-row{grid-template-columns:1fr 74px}}
</style>
'''

_phone_focus_script = r'''
<script>
window.addEventListener('load',()=>{
  const p=new URLSearchParams(location.search);
  if(!p.has('phone_updated')) return;
  const sid=p.get('sid');
  if(!sid) return;
  setTimeout(()=>{
    const service=document.querySelector(`[data-service-id="${CSS.escape(sid)}"]`);
    if(!service) return;
    const group=service.closest('[data-debt-group]');
    if(group){
      group.hidden=false;
      const panel=group.querySelector('[data-debt-panel]');
      const btn=group.querySelector('[data-debt-toggle]');
      if(panel) panel.removeAttribute('hidden');
      if(btn) btn.classList.add('open');
    }
    service.scrollIntoView({behavior:'instant',block:'center'});
  },120);
});
</script>
'''

_phone_ui = r'''
<details class="phone-editor">
  <summary>ویرایش شماره</summary>
  <form method="post" action="/manage/users/{{ s.id }}/phone" class="phone-edit-form" data-preserve-position data-service-sid="{{ s.id }}">
    <label>شماره همراه این اکانت</label>
    <div class="phone-edit-row">
      <input name="phone" type="text" inputmode="tel" autocomplete="off" value="{{ s.phone or '' }}" placeholder="0912...">
      <button type="submit">ذخیره</button>
    </div>
    <small>اگر شماره از قبل وجود داشته باشد، این اکانت خودکار زیر همان سرگروه منتقل می‌شود.</small>
  </form>
</details>
'''

_tpl = TEMPLATES.get("debts.html", "")
if _tpl:
    _tpl = _tpl.replace("{% block content %}", "{% block content %}" + _phone_style + _phone_focus_script, 1)

    # Mark each service so the browser can find it after a phone change moves it to another group.
    service_anchor = '<div class="debt-service-v3">'
    if service_anchor in _tpl:
        _tpl = _tpl.replace(service_anchor, '<div class="debt-service-v3" data-service-id="{{ s.id }}">', 1)

    # Insert phone editor before the per-account delete button.
    action_anchor = '''        <div class="service-actions">\n          <form method="post" action="/manage/users/{{ s.id }}/delete"'''
    action_replacement = '''        <div class="service-actions">\n''' + _phone_ui + '''          <form method="post" action="/manage/users/{{ s.id }}/delete"'''
    if action_anchor in _tpl:
        _tpl = _tpl.replace(action_anchor, action_replacement, 1)

    banner_anchor = '{% if request.query_params.get("manage_error") %}<div class="manage-banner error">عملیات انجام نشد؛ اطلاعات ورودی را بررسی کن.</div>{% endif %}'
    phone_banner = r'''
{% if request.query_params.get("phone_updated") %}<div class="manage-banner">✓ شماره همراه اصلاح شد و گروه‌بندی کاربران دوباره انجام شد.</div>{% endif %}
'''
    if banner_anchor in _tpl:
        _tpl = _tpl.replace(banner_anchor, banner_anchor + phone_banner, 1)

    for old in ("v=2", "v=3", "v=4", "v=5", "v=6", "v=7"):
        _tpl = _tpl.replace(old, "v=8")

    TEMPLATES["debts.html"] = _tpl
    if hasattr(env.loader, "mapping"):
        env.loader.mapping.update(TEMPLATES)


def update_user_phone(sid: int, phone: str = Form(""), db: Session = Depends(get_db)):
    s = db.get(Subscription, sid)
    if not s:
        return RedirectResponse("/debts?manage_error=1", 303)

    old_phone = s.phone
    new_phone = _normalize_phone(phone)
    s.phone = new_phone
    if hasattr(s, "payment_method"):
        # Keep card-only rows as card; otherwise phone/none follows the edited number.
        current_method = getattr(s, "payment_method", None)
        if current_method != "card":
            s.payment_method = "phone" if new_phone else "none"

    db.add(AuditEvent(
        kind="phone_edit",
        message=f"Phone changed for {s.display_name} (sid={s.id}): {old_phone} -> {new_phone}",
    ))
    db.commit()
    return RedirectResponse(f"/debts?phone_updated=1&sid={s.id}", 303)


app.add_api_route("/manage/users/{sid}/phone", update_user_phone, methods=["POST"])
