# Phone editing inside the waiting workflow, preserving follow-up state and page position.
from fastapi import Form

_WAITING_PHONE_STYLE = r'''
<style>
.waiting-phone-editor{border:1px solid rgba(255,255,255,.09);border-radius:9px;background:rgba(255,255,255,.02);overflow:hidden;min-width:185px}
.waiting-phone-editor summary{list-style:none;cursor:pointer;padding:6px 8px;font-size:10px;color:#aeb7c6;text-align:center;user-select:none}
.waiting-phone-editor summary::-webkit-details-marker{display:none}.waiting-phone-editor[open] summary{border-bottom:1px solid rgba(255,255,255,.07);color:#fff}
.waiting-phone-edit-form{padding:8px;display:flex;flex-direction:column;gap:6px}.waiting-phone-edit-row{display:grid;grid-template-columns:1fr 64px;gap:6px}
.waiting-phone-edit-row input{min-width:0;height:34px;background:#0c1320;color:#fff;border:1px solid rgba(255,255,255,.13);border-radius:8px;padding:0 8px;font:inherit;font-size:11px;direction:ltr;text-align:left}
.waiting-phone-edit-row button{border:0;border-radius:8px;background:#eef2f6;color:#131820;font:inherit;font-size:10px;font-weight:800;cursor:pointer}.waiting-phone-edit-form small{font-size:9px;color:#778295;line-height:1.5}
.waiting-actions{align-items:start}.waiting-actions .waiting-phone-editor{grid-column:1/-1}
@media(max-width:640px){.waiting-phone-editor{min-width:0;width:100%}}
</style>
'''

_WAITING_PHONE_SCRIPT = r'''
<script>
(function(){
  const prefix='hesab.followups.';
  const serviceKey=prefix+'service';
  const topKey=prefix+'top';
  const yKey=prefix+'y';

  function save(form){
    try{
      sessionStorage.setItem(yKey,String(window.scrollY));
      const service=form.closest('[data-service-id]');
      if(service){
        sessionStorage.setItem(serviceKey,service.dataset.serviceId||'');
        sessionStorage.setItem(topKey,String(service.getBoundingClientRect().top));
      }else{
        sessionStorage.removeItem(serviceKey);
        sessionStorage.removeItem(topKey);
      }
    }catch(_){ }
  }

  document.querySelectorAll('.waiting-list form').forEach(form=>{
    form.addEventListener('submit',()=>save(form));
  });

  try{
    const sid=sessionStorage.getItem(serviceKey)||new URLSearchParams(location.search).get('sid')||'';
    const oldTop=parseFloat(sessionStorage.getItem(topKey)||'NaN');
    const oldY=parseFloat(sessionStorage.getItem(yKey)||'0');
    requestAnimationFrame(()=>requestAnimationFrame(()=>{
      const target=sid?document.querySelector('[data-service-id="'+CSS.escape(String(sid))+'"]'):null;
      if(target && Number.isFinite(oldTop)){
        window.scrollBy(0,target.getBoundingClientRect().top-oldTop);
      }else if(target){
        target.scrollIntoView({block:'center'});
      }else if(Number.isFinite(oldY) && oldY>0){
        window.scrollTo(0,oldY);
      }
      sessionStorage.removeItem(serviceKey);sessionStorage.removeItem(topKey);sessionStorage.removeItem(yKey);
    }));
  }catch(_){ }
})();
</script>
'''

_waiting_tpl = TEMPLATES.get("followups.html", "")
if _waiting_tpl:
    _waiting_tpl = _waiting_tpl.replace("{% block content %}", "{% block content %}" + _WAITING_PHONE_STYLE, 1)

    # Identify each service independently so it can be found even after regrouping to a different phone.
    service_anchor = '<div class="waiting-service">'
    if service_anchor in _waiting_tpl:
        _waiting_tpl = _waiting_tpl.replace(service_anchor, '<div class="waiting-service" data-service-id="{{ s.id }}">', 1)

    # Phone editing is per subscription. If it matches another phone, regrouping happens automatically on reload.
    actions_anchor = '<div class="waiting-actions">'
    phone_editor = r'''
        <details class="waiting-phone-editor">
          <summary>ویرایش شماره تلفن</summary>
          <form method="post" action="/followups/{{ s.id }}/phone" class="waiting-phone-edit-form">
            <div class="waiting-phone-edit-row">
              <input name="phone" type="text" inputmode="tel" autocomplete="off" value="{{ s.phone or '' }}" placeholder="0912...">
              <button type="submit">ذخیره</button>
            </div>
            <small>شماره تکراری باشد، این اکانت خودکار زیر همان سرگروه می‌رود.</small>
          </form>
        </details>
'''
    if actions_anchor in _waiting_tpl and "/followups/{{ s.id }}/phone" not in _waiting_tpl:
        _waiting_tpl = _waiting_tpl.replace(actions_anchor, actions_anchor + phone_editor, 1)

    banner_anchor = '{% if request.query_params.get("restored") %}<div class="collect-success">✓ اکانت دوباره به صفحه بدهی‌ها برگشت.</div>{% endif %}'
    if banner_anchor in _waiting_tpl:
        _waiting_tpl = _waiting_tpl.replace(
            banner_anchor,
            banner_anchor + '\n{% if request.query_params.get("phone_updated") %}<div class="collect-success">✓ شماره تلفن اصلاح شد و گروه‌بندی دوباره انجام شد.</div>{% endif %}',
            1,
        )

    # Insert the script before the content block's final endblock, not before the title/heading blocks.
    end_idx = _waiting_tpl.rfind("{% endblock %}")
    if end_idx >= 0:
        _waiting_tpl = _waiting_tpl[:end_idx] + _WAITING_PHONE_SCRIPT + _waiting_tpl[end_idx:]

    TEMPLATES["followups.html"] = _waiting_tpl
    if hasattr(env.loader, "mapping"):
        env.loader.mapping.update(TEMPLATES)


def followup_update_phone(sid: int, phone: str = Form(""), db: Session = Depends(get_db)):
    s = db.get(Subscription, sid)
    if not s:
        return RedirectResponse("/followups", 303)

    old_phone = s.phone
    new_phone = _normalize_phone(phone)
    s.phone = new_phone
    if hasattr(s, "payment_method") and getattr(s, "payment_method", None) != "card":
        s.payment_method = "phone" if new_phone else "none"

    db.add(AuditEvent(
        kind="phone_edit",
        message=f"Waiting phone changed for {s.display_name} (sid={s.id}): {old_phone} -> {new_phone}",
    ))
    db.commit()
    return RedirectResponse(f"/followups?phone_updated=1&sid={s.id}", 303)


app.add_api_route("/followups/{sid}/phone", followup_update_phone, methods=["POST"])
