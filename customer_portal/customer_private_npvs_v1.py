# HESAB_PRIVATE_NPVS_CUSTOMER_V1
# Additive to the existing mounted login_activity.py AFTER the services V4 route.
# Only a signed customer session's normalized phone can download its own file.
# No public file URL, no upload endpoint on the customer-facing domain.
from fastapi import Request as _npc_Request
from fastapi.responses import Response as _npc_Response
from fastapi.responses import RedirectResponse as _npc_Redirect
from fastapi.responses import HTMLResponse as _npc_HTML
from urllib.parse import quote as _npc_quote
import hashlib as _npc_hashlib
import re as _npc_re

_NPC_LIMIT=1048576
_NPC_BUTTON=r'''
<style>
.sv-private-file{margin-bottom:16px!important;display:flex;align-items:center;gap:18px;
 justify-content:space-between;background:linear-gradient(110deg,#fff 65%,#f1f6ff)}
.sv-file-heading{display:flex;align-items:center;gap:14px;min-width:0}
.sv-file-icon{display:grid;place-items:center;background:#e9f0ff;color:#3a6ad6;
 width:58px;height:58px;border-radius:17px;font-size:26px;flex:none}
.sv-private-file h2{font-size:22px;margin:0;color:#1d2432;font-weight:900}
.sv-private-file p{font-size:12px;line-height:1.9;color:#798394;margin:5px 0 0}
.sv-private-file .sv-file-action{display:inline-flex;align-items:center;justify-content:center;
 text-decoration:none;white-space:nowrap;color:white;background:#171c2a;
 border-radius:14px;padding:15px 20px;font-weight:850;font-size:13px}
.sv-private-file .sv-file-action:hover{background:#313c56}
@media(max-width:630px){.sv-private-file{flex-direction:column;align-items:stretch;
 padding:20px}.sv-private-file h2{font-size:19px}
.sv-private-file .sv-file-action{width:100%}}
</style>
<section id="sv-private-file" class="sv-box sv-private-file">
  <div class="sv-file-heading">
    <span class="sv-file-icon" aria-hidden="true">⇩</span>
    <div><h2>دریافت فایل</h2>
      <p>دریافت فایل اختصاصی NPV Tunnel از حساب کاربری شما</p></div>
  </div>
  <a class="sv-file-action" href="/my-file/download">دریافت فایل .npvs ←</a>
</section>
'''
def _npc_place_download_before_support(page):
    """Match the *live* customer template, not a frozen class attribute order.
    Fail closed unless a single actual customer-support block is located.
    """
    if not isinstance(page,str) or not page:
        raise RuntimeError("Customer landing template not available")
    if 'id="sv-private-file"' in page:
        raise RuntimeError("Private file card already installed")
    # Existing known support card may reorder classes or add attributes.
    candidate=[]
    for match in _npc_re.finditer(r"<section\b[^>]*>",page,flags=_npc_re.IGNORECASE):
        if _npc_re.search(r"(?<![\w-])sv-support(?![\w-])",match.group(),flags=_npc_re.IGNORECASE):
            candidate.append(match.start())
    if len(candidate)==1:
        idx=candidate[0]
    elif len(candidate)==0:
        # Newer production layouts might rename the support card class.
        # Locate the unique support heading, then its enclosing section.
        headings=list(_npc_re.finditer(
            r"<h[1-6]\b[^>]*>\s*(?:<[^>]+>\s*)*پشتیبانی\s*</h[1-6]\s*>",
            page,flags=_npc_re.IGNORECASE))
        if len(headings)!=1:
            raise RuntimeError("Support heading not uniquely identified")
        before=page[:headings[0].start()]
        sections=list(_npc_re.finditer(r"<section\b[^>]*>",before,
                                      flags=_npc_re.IGNORECASE))
        if not sections or headings[0].start()-sections[-1].end()>1500:
            raise RuntimeError("Support card container not safely located")
        idx=sections[-1].start()
    else:
        raise RuntimeError("Multiple support cards found; refusing ambiguous insertion")
    # Require the heading in this card, and do not insert into a similarly
    # named unrelated container.
    closing=page.find("</section>",idx)
    segment=page[idx:(closing+10 if closing!=-1 else idx+2200)]
    if (closing==-1 or "پشتیبانی" not in segment
        or not _npc_re.search(r"<h[1-6]\b",segment,flags=_npc_re.IGNORECASE)):
        raise RuntimeError("Support target did not validate")
    updated=page[:idx]+_NPC_BUTTON+page[idx:]
    if updated.count('id="sv-private-file"')!=1:
        raise RuntimeError("Unexpected private-file card duplication")
    return updated

_SV2_HTML=_npc_place_download_before_support(_SV2_HTML)

def _npc_download(request:_npc_Request):
    phone=_v2_session_phone(request)
    if not phone:
        return _npc_Redirect("/",status_code=303)
    # Recheck that phone is still associated with at least one subscription.
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT filename,content,sha256
                FROM customer_private_npvs
                WHERE phone=%s AND EXISTS(
                  SELECT 1 FROM subscriptions WHERE phone=%s
                )
            """,(phone,phone))
            row=cur.fetchone()
    if not row:
        return _npc_HTML("""<!doctype html><html lang="fa" dir="rtl">
        <head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
        <body style="font-family:Tahoma,Arial,sans-serif;background:#f7f8fc;color:#1c2534;
        text-align:center;padding:65px 20px">
        <h2>فایلی برای شما ثبت نشده است</h2>
        <p>در صورت نیاز با پشتیبانی تماس بگیرید.</p>
        <a href="/" style="color:#345fc1">بازگشت به حساب من</a></body></html>""",
         status_code=404,headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})
    data=bytes(row["content"])
    filename=str(row["filename"])
    if (not 0<len(data)<=_NPC_LIMIT or
        not 1<len(filename)<=120 or not filename.lower().endswith(".npvs") or
        "/" in filename or "\\" in filename or
        any(ord(c)<32 or ord(c)==127 for c in filename) or
        _npc_hashlib.sha256(data).hexdigest()!=row["sha256"]):
        return _npc_HTML("File unavailable",status_code=503,
                         headers={"Cache-Control":"no-store"})
    # Fixed ASCII fallback; UTF-8 original is RFC 5987 percent-encoded.
    disposition="attachment; filename=\"configuration.npvs\"; filename*=UTF-8''"+_npc_quote(filename,safe="")
    return _npc_Response(
      content=data,media_type="application/octet-stream",
      headers={
        "Content-Disposition":disposition,
        "Cache-Control":"private, no-store, max-age=0",
        "Pragma":"no-cache",
        "X-Content-Type-Options":"nosniff",
        "X-Robots-Tag":"noindex, nofollow, noarchive"
      })

if any(getattr(r,"path",None)=="/my-file/download" for r in app.router.routes):
    raise RuntimeError("Private .npvs download route collision")
app.add_api_route("/my-file/download",_npc_download,methods=["GET"])
