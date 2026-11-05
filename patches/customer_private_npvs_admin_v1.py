# HESAB_PRIVATE_NPVS_ADMIN_V1
# Additive admin-only management page, uploaded .npvs content in dedicated
# PostgreSQL table. Never touches subscriptions, payment or XUI records.
from fastapi import Request as _nf_Request, Depends as _nf_Depends
from fastapi import Form as _nf_Form, File as _nf_File, UploadFile as _nf_UploadFile
from fastapi import HTTPException as _nf_HTTPException
from fastapi.responses import RedirectResponse as _nf_Redirect
from sqlalchemy import text as _nf_text
from sqlalchemy.orm import Session as _nf_Session
import hashlib as _nf_hashlib
import secrets as _nf_secrets
import re as _nf_re

_NF_LIMIT=1048576  # 1 MiB per customer; configurations should be small.
_NF_ORIGIN="https://hesab.filmjadiid.ir"
_NF_TRANSLATE=str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
                             "01234567890123456789")

def _nf_phone(value):
    # Same normalization as the existing customer-portal login flow.
    digits="".join(c for c in str(value or "").translate(_NF_TRANSLATE) if c.isdigit())
    if digits.startswith("0098"):
        digits="0"+digits[4:]
    elif digits.startswith("98") and len(digits)==12:
        digits="0"+digits[2:]
    elif digits.startswith("9") and len(digits)==10:
        digits="0"+digits
    return digits if _nf_re.fullmatch(r"09[0-9]{9}",digits) else None

def _nf_filename(original):
    value=str(original or "")
    value=value.replace("\\","/").split("/")[-1].strip()
    if (not value or len(value)>120 or
        any(ord(ch)<32 or ord(ch)==127 for ch in value) or
        not value.lower().endswith(".npvs") or value.lower()==".npvs"):
        return None
    return value

def _nf_check(request, token):
    origin=request.headers.get("origin")
    # Require the exact admin domain for state-changing form posts.
    if origin!=_NF_ORIGIN:
        raise _nf_HTTPException(status_code=403,detail="Origin check failed")
    known=request.session.get("npvs_admin_csrf")
    if not (isinstance(token,str) and isinstance(known,str)
            and len(known)>=30 and _nf_secrets.compare_digest(token,known)):
        raise _nf_HTTPException(status_code=403,detail="CSRF check failed")

_NF_PAGE=r'''{% extends "base.html" %}
{% block title %}مدیریت فایل کاربران · حساب VPN{% endblock %}
{% block heading %}مدیریت فایل کاربران{% endblock %}
{% block subheading %}ارسال اختصاصی فایل NPV Tunnel برای شماره‌های مشترکین{% endblock %}
{% block content %}
<style>
.nf-wrap{direction:rtl;display:grid;gap:16px;max-width:1000px}
.nf-panel{border-radius:18px;border:1px solid rgba(156,183,218,.17);
 background:linear-gradient(135deg,#152239,#0c1524);padding:20px}
.nf-panel h2{font-size:17px;color:#edf5ff;margin:0 0 8px}
.nf-muted{font-size:12px;color:#a2b5ce;line-height:2;margin-bottom:18px}
.nf-form{display:flex;gap:12px;flex-wrap:wrap;align-items:end}
.nf-form label{display:grid;gap:8px;min-width:210px;flex:1;color:#bdcce2;font-size:12px}
.nf-form input{width:100%;box-sizing:border-box;border:1px solid #41516c;
 color:#ebf2fe;background:#101d30;border-radius:10px;padding:12px;font:inherit}
.nf-button{background:#5f76dc;color:white;border:0;border-radius:10px;
 font:inherit;padding:12px 19px;cursor:pointer}
.nf-delete{background:#51303a;color:#ffb8c4;border:1px solid #85505b;
 border-radius:8px;cursor:pointer;font:inherit;padding:8px 11px}
.nf-table{width:100%;border-collapse:collapse;font-size:12px}
.nf-table th,.nf-table td{padding:13px 9px;border-bottom:1px solid #ffffff16;text-align:right}
.nf-table th{color:#aac0d9}.nf-table td{color:#e9edfa}
.nf-rows{overflow-x:auto}
.nf-feedback{padding:12px;border-radius:10px;background:#203d36;color:#afeecb}
.nf-alert{background:#44302e;color:#ffd3bd}
@media(max-width:640px){.nf-panel{padding:14px}.nf-form{display:grid}.nf-table{min-width:570px}}
</style>
<div class="nf-wrap">
 <section class="nf-panel">
  <h2>بارگذاری فایل .npvs</h2>
  <p class="nf-muted">برای هر شماره یک فایل اختصاصی ذخیره می‌شود. فایل جدید جایگزین فایل قبلی همان شماره خواهد شد.
  حداکثر حجم: ۱ مگابایت.</p>
  {% if result=='uploaded' %}<p class="nf-feedback">فایل با موفقیت برای کاربر ثبت شد.</p>
  {% elif result=='deleted' %}<p class="nf-feedback">فایل این شماره حذف شد.</p>
  {% elif result=='invalid_phone' %}<p class="nf-feedback nf-alert">شماره موبایل معتبر نیست.</p>
  {% elif result=='unknown_phone' %}<p class="nf-feedback nf-alert">این شماره در اشتراک‌های ثبت‌شده وجود ندارد.</p>
  {% elif result=='invalid_file' %}<p class="nf-feedback nf-alert">فقط فایل معتبر با پسوند .npvs پذیرفته می‌شود.</p>
  {% elif result=='too_large' %}<p class="nf-feedback nf-alert">حجم فایل بیشتر از ۱ مگابایت است.</p>{% endif %}
  <form class="nf-form" method="post" action="/customer-files/upload" enctype="multipart/form-data">
   <input type="hidden" name="csrf" value="{{ csrf }}">
   <label>شماره موبایل مشترک
    <input type="tel" name="phone" placeholder="0912..." inputmode="tel" required maxlength="18">
   </label>
   <label>فایل NPV Tunnel
    <input type="file" name="upload" accept=".npvs" required>
   </label>
   <button class="nf-button" type="submit">ثبت فایل برای کاربر</button>
  </form>
 </section>
 <section class="nf-panel">
  <h2>فایل‌های اختصاص‌یافته</h2>
  <p class="nf-muted">فقط کاربری که با شماره ثبت‌شده وارد پنل مشترکین شود، فایل مربوط به همان شماره را دریافت می‌کند.</p>
  <div class="nf-rows"><table class="nf-table">
   <thead><tr><th>شماره</th><th>نام فایل</th><th>حجم</th><th>آخرین بروزرسانی</th><th>عملیات</th></tr></thead>
   <tbody>
   {% for f in files %}
   <tr><td dir="ltr">{{ f.phone }}</td><td>{{ f.filename }}</td>
    <td>{{ f.size }} بایت</td><td>{{ f.updated }}</td>
    <td><form method="post" action="/customer-files/delete">
     <input type="hidden" name="csrf" value="{{ csrf }}">
     <input type="hidden" name="phone" value="{{ f.phone }}">
     <button class="nf-delete" type="submit" onclick="return confirm('فایل این شماره حذف شود؟')">حذف فایل</button>
    </form></td></tr>
   {% else %}<tr><td colspan="5">هنوز فایلی بارگذاری نشده است.</td></tr>{% endfor %}
   </tbody></table></div>
 </section>
</div>
{% endblock %}'''

if "private_npvs_admin.html" in TEMPLATES:
    raise RuntimeError("Private NPV admin patch already installed")
TEMPLATES["private_npvs_admin.html"]=_NF_PAGE

_nf_nav=TEMPLATES.get("base.html","")
_nf_link='''<a href="/customer-files" class="{{ 'active' if request.url.path.startswith('/customer-files') else '' }}"><i>▣</i><span>فایل کاربران</span></a>
'''
if _nf_nav.count("</nav>")!=1 or 'href="/customer-files"' in _nf_nav:
    raise RuntimeError("Unexpected admin sidebar; refusing NPV patch")
TEMPLATES["base.html"]=_nf_nav.replace("</nav>",_nf_link+"</nav>",1)
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)

def _nf_list(request:_nf_Request,db:_nf_Session=_nf_Depends(get_db)):
    token=request.session.get("npvs_admin_csrf")
    if not isinstance(token,str) or len(token)<30:
        token=_nf_secrets.token_urlsafe(32)
        request.session["npvs_admin_csrf"]=token
    rows=db.execute(_nf_text("""
      SELECT phone,filename,octet_length(content) AS size,updated_at
      FROM customer_private_npvs ORDER BY updated_at DESC LIMIT 250
    """)).mappings().all()
    output=[{"phone":r["phone"],"filename":r["filename"],
             "size":int(r["size"]),
             "updated":r["updated_at"].strftime("%Y-%m-%d %H:%M")}
            for r in rows]
    status=request.query_params.get("result","")
    return render("private_npvs_admin.html",request,csrf=token,files=output,
                  result=status if status in ("uploaded","deleted","invalid_phone",
                  "unknown_phone","invalid_file","too_large") else "")

async def _nf_upload(request:_nf_Request,
                     phone:str=_nf_Form(...),csrf:str=_nf_Form(...),
                     upload:_nf_UploadFile=_nf_File(...),
                     db:_nf_Session=_nf_Depends(get_db)):
    _nf_check(request,csrf)
    normalized=_nf_phone(phone)
    if not normalized:
        return _nf_Redirect("/customer-files?result=invalid_phone",status_code=303)
    filename=_nf_filename(upload.filename)
    if not filename:
        return _nf_Redirect("/customer-files?result=invalid_file",status_code=303)
    contents=await upload.read(_NF_LIMIT+1)
    await upload.close()
    if len(contents)>_NF_LIMIT:
        return _nf_Redirect("/customer-files?result=too_large",status_code=303)
    if not contents:
        return _nf_Redirect("/customer-files?result=invalid_file",status_code=303)
    exists=db.execute(_nf_text("SELECT 1 FROM subscriptions WHERE phone=:phone LIMIT 1"),
                      {"phone":normalized}).first()
    if not exists:
        return _nf_Redirect("/customer-files?result=unknown_phone",status_code=303)
    db.execute(_nf_text("""
      INSERT INTO customer_private_npvs(phone,filename,content,sha256,updated_at)
      VALUES (:phone,:filename,:content,:digest,NOW())
      ON CONFLICT(phone) DO UPDATE
      SET filename=EXCLUDED.filename,content=EXCLUDED.content,
          sha256=EXCLUDED.sha256,updated_at=NOW()
    """),{"phone":normalized,"filename":filename,"content":contents,
          "digest":_nf_hashlib.sha256(contents).hexdigest()})
    db.commit()
    return _nf_Redirect("/customer-files?result=uploaded",status_code=303)

def _nf_delete(request:_nf_Request,
               phone:str=_nf_Form(...),csrf:str=_nf_Form(...),
               db:_nf_Session=_nf_Depends(get_db)):
    _nf_check(request,csrf)
    normalized=_nf_phone(phone)
    if not normalized:
        return _nf_Redirect("/customer-files?result=invalid_phone",status_code=303)
    db.execute(_nf_text("DELETE FROM customer_private_npvs WHERE phone=:phone"),
               {"phone":normalized})
    db.commit()
    return _nf_Redirect("/customer-files?result=deleted",status_code=303)

for _nf_route in ("/customer-files","/customer-files/upload","/customer-files/delete"):
    if any(getattr(route,"path",None)==_nf_route for route in app.router.routes):
        raise RuntimeError("Private NPV admin route collision")
app.add_api_route("/customer-files",_nf_list,methods=["GET"])
app.add_api_route("/customer-files/upload",_nf_upload,methods=["POST"])
app.add_api_route("/customer-files/delete",_nf_delete,methods=["POST"])
