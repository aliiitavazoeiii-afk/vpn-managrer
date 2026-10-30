# HESAB_ADMIN_PHONE_SUGGESTIONS_V1
# Read-only optional number suggestions on both admin add-user forms.
# Loaded AFTER HESAB_OPERATOR_WORKSPACE_V5 in the mounted sms_native_v2.py.
# No change to customer registration POST, billing, SMS or authentication.
import logging as _aps_logging
from collections import OrderedDict as _aps_OrderedDict

_aps_logger = _aps_logging.getLogger("hesab.admin_phone_suggestions")

def _aps_phone_directory():
    """Read existing phone/name associations for authenticated admin pages only."""
    provider = get_db()
    try:
        db = next(provider)
        groups = _aps_OrderedDict()
        for display_name, raw_phone in db.query(
            Subscription.display_name, Subscription.phone
        ).order_by(Subscription.id.desc()).all():
            phone = _normalize_phone(raw_phone)
            if not (phone and len(phone) == 11 and phone.isascii()
                    and phone.isdecimal() and phone.startswith("09")):
                continue
            name = str(display_name or "").strip()
            if not name:
                continue
            if phone not in groups:
                groups[phone] = {"phone": phone, "names": [], "count": 0}
            group = groups[phone]
            group["count"] += 1
            if name not in group["names"] and len(group["names"]) < 40:
                group["names"].append(name[:140])
        return list(groups.values())
    except Exception:
        # Suggestions must never break financial pages or user creation.
        _aps_logger.exception("Read-only phone suggestion directory unavailable")
        return []
    finally:
        provider.close()

env.globals["admin_phone_suggestion_directory"] = _aps_phone_directory

_APS_WIDGET = r'''
<style>
.aps-name-anchor{position:relative!important;min-width:0}
.aps-suggestion-panel{
 position:absolute;top:calc(100% + 6px);left:0;right:0;min-width:min(320px,85vw);
 z-index:700;background:#101b2a;color:#f5f9ff;border:1px solid #476382;
 border-radius:14px;padding:7px;box-shadow:0 20px 42px #0007;
 max-height:310px;overflow:auto;direction:rtl
}
.aps-suggestion-panel[hidden]{display:none!important}
.aps-heading{font-size:11px;font-weight:750;color:#9ebee1;padding:8px 9px}
.aps-choice{display:block;width:100%;border:0;border-bottom:1px solid #304055;
 padding:11px 9px;background:transparent;text-align:right;color:#f5f9ff;
 font:inherit;cursor:pointer;border-radius:8px}
.aps-choice:last-child{border-bottom:0}
.aps-choice:hover,.aps-choice:focus-visible{background:#233850;outline:2px solid #65a7ff}
.aps-choice-title{display:block;font-size:13px;font-weight:850;line-height:1.6;overflow-wrap:anywhere}
.aps-choice-meta{display:block;font-size:11px;line-height:1.8;color:#b6c8df;direction:rtl}
.aps-phone-ltr{direction:ltr;unicode-bidi:isolate;display:inline-block;font-family:Tahoma,sans-serif;
 font-size:13px;font-weight:850;letter-spacing:.035em}
.aps-description{padding:8px 9px;font-size:10px;color:#a6bbd2;line-height:1.8}
@media(max-width:600px){.aps-suggestion-panel{min-width:0;max-width:calc(100vw - 40px)}
 .aps-choice{min-height:53px}}
</style>
<script type="application/json" class="aps-directory">{{ admin_phone_suggestion_directory()|tojson }}</script>
<script>
(function(){
"use strict";
function init(){
  var data=document.querySelector(".aps-directory"), directory=[];
  if(!data || window.__hesabPhoneSuggestionsV1)return;
  try{directory=JSON.parse(data.textContent||"[]");}catch(e){return;}
  if(!Array.isArray(directory))return;
  window.__hesabPhoneSuggestionsV1=true;
  function norm(v){
    return String(v||"").normalize("NFKC").toLowerCase()
      .replace(/[يى]/g,"ی").replace(/ك/g,"ک").replace(/[\u200c\u200dـ]/g," ")
      .replace(/[^a-z0-9\u0600-\u06ff]+/gi," ").trim().replace(/\s+/g," ");
  }
  function score(query, candidate){
    var q=norm(query),n=norm(candidate);
    if(!q || !n)return 0;
    var qs=q.split(" ").filter(function(x){return x.length>=2;});
    var ns=n.split(" ").filter(Boolean), hits=0, points=0;
    for(var i=0;i<qs.length;i++){
      var best=0;
      for(var j=0;j<ns.length;j++){
        if(qs[i]===ns[j])best=Math.max(best,5);
        else if(qs[i].length>=3 && ns[j].indexOf(qs[i])===0)best=Math.max(best,3);
        else if(ns[j].length>=4 && qs[i].indexOf(ns[j])===0)best=Math.max(best,2.5);
        else if(qs[i].length>=4 && ns[j].indexOf(qs[i])>=0)best=Math.max(best,1.5);
      }
      if(best){hits++;points+=best;}
    }
    if(!hits)return 0;
    if(n===q)points+=15;
    if(n.indexOf(q)>=0)points+=8;
    if(hits>=2)points+=hits*5;
    return points;
  }
  var forms=Array.from(document.querySelectorAll("form")).filter(function(form){
    return form.querySelector('input[name="display_name"]')&&form.querySelector('input[name="phone"]');
  });
  forms.forEach(function(form,idx){
    var name=form.querySelector('input[name="display_name"]');
    var phone=form.querySelector('input[name="phone"]');
    var host=name.parentElement;
    if(!host||host.querySelector(".aps-suggestion-panel"))return;
    host.classList.add("aps-name-anchor");
    var menu=document.createElement("div");
    menu.className="aps-suggestion-panel";
    menu.hidden=true;
    menu.id="aps-options-"+idx;
    menu.setAttribute("role","listbox");
    name.setAttribute("aria-autocomplete","list");
    name.setAttribute("aria-controls",menu.id);
    name.setAttribute("aria-expanded","false");
    host.appendChild(menu);
    function close(){menu.hidden=true;name.setAttribute("aria-expanded","false");}
    function update(){
      var query=norm(name.value);
      menu.replaceChildren();
      if(query.length<3){close();return;}
      var matched=directory.map(function(group){
        var best=0,bestName="";
        (group.names||[]).forEach(function(n){
          var s=score(query,n);
          if(s>best){best=s;bestName=n;}
        });
        return {phone:group.phone,count:group.count,matchedName:bestName,score:best};
      }).filter(function(x){return x.score>0;})
        .sort(function(a,b){return b.score-a.score||b.count-a.count||a.phone.localeCompare(b.phone);})
        .slice(0,7);
      if(!matched.length){close();return;}
      var title=document.createElement("div");
      title.className="aps-heading";
      title.textContent="شماره‌های مرتبط با نام مشابه — انتخاب اختیاری";
      menu.appendChild(title);
      matched.forEach(function(item){
        var btn=document.createElement("button");
        btn.type="button";btn.className="aps-choice";btn.setAttribute("role","option");
        var label=document.createElement("span");
        label.className="aps-choice-title";label.textContent=item.matchedName;
        var sub=document.createElement("span");sub.className="aps-choice-meta";
        var tel=document.createElement("span");tel.className="aps-phone-ltr";tel.textContent=item.phone;
        sub.appendChild(tel);
        sub.appendChild(document.createTextNode(" · "+item.count+" اکانت در این شماره"));
        btn.appendChild(label);btn.appendChild(sub);
        btn.addEventListener("click",function(){
          phone.value=item.phone;
          phone.dispatchEvent(new Event("input",{bubbles:true}));
          close();phone.focus();
        });
        menu.appendChild(btn);
      });
      var note=document.createElement("div");
      note.className="aps-description";
      note.textContent="برای شماره جدید، کافی است آن را دستی وارد کنید. پیشنهادها هیچ شماره‌ای را خودکار انتخاب نمی‌کنند.";
      menu.appendChild(note);
      menu.hidden=false;name.setAttribute("aria-expanded","true");
    }
    name.addEventListener("input",update);
    name.addEventListener("focus",update);
    name.addEventListener("keydown",function(e){if(e.key==="Escape")close();});
    document.addEventListener("pointerdown",function(e){if(!host.contains(e.target))close();});
    form.addEventListener("submit",close);
  });
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init,{once:true});
else init();
})();
</script>
'''

for _aps_page in ("add_user_page.html", "debts.html"):
    _aps_template = TEMPLATES.get(_aps_page, "")
    if not (_aps_template and 'name="display_name"' in _aps_template
            and 'name="phone"' in _aps_template):
        raise RuntimeError("Phone suggestions: expected admin form missing in " + _aps_page)
    if "aps-directory" in _aps_template:
        raise RuntimeError("Phone suggestions: already installed in " + _aps_page)
    _aps_end = _aps_template.rfind("{% endblock %}")
    if _aps_end < 0:
        raise RuntimeError("Phone suggestions: no final content block in " + _aps_page)
    TEMPLATES[_aps_page] = (
        _aps_template[:_aps_end] + _APS_WIDGET + _aps_template[_aps_end:]
    )
if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)
