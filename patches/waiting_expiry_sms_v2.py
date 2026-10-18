# HESAB_WAITING_EXPIRY_SMS_V2
# Operator-only update to the existing waiting reminders.
# The customer's actual earliest waiting due date replaces the sample "۶ مهر".
# This never pays, marks followup, changes subscriptions, or sends SMS.
from fastapi import Request as _ews_Request, Form as _ews_Form, Depends as _ews_Depends
from fastapi.responses import JSONResponse as _ews_JSON
from sqlalchemy.orm import Session as _ews_Session

_EWS_MONTHS = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
)
_EWS_FA_NUMBERS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_EWS_DOMAIN = "https://hesab.filmjadiid.ir"

def _ews_jalali_parts(value):
    # Standalone Gregorian -> Jalali conversion, same algorithm as date_edit.py.
    # Avoid installing a new dependency in the production admin image.
    gy, gm, gd = value.year, value.month, value.day
    gdays = [0,31,59,90,120,151,181,212,243,273,304,334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (365*gy+(gy2+3)//4-(gy2+99)//100
            +(gy2+399)//400-80+gd+gdays[gm-1])
    jy += 33*(days//12053)
    days %= 12053
    jy += 4*(days//1461)
    days %= 1461
    if days > 365:
        jy += (days-1)//365
        days = (days-1)%365
    if days < 186:
        jm = 1+days//31
        jd = 1+days%31
    else:
        jm = 7+(days-186)//30
        jd = 1+(days-186)%30
    return jy,jm,jd

def _ews_expiry_label(expiry):
    if expiry is None:
        raise ValueError("expiry date missing; refuse misleading SMS")
    _,jm,jd = _ews_jalali_parts(expiry)
    return str(jd).translate(_EWS_FA_NUMBERS)+" "+_EWS_MONTHS[jm-1]

def _ews_message(expiry):
    return (
        "سلام اکانت شما "+_ews_expiry_label(expiry)+" تمام شده.\n"
        "برای تمدید با شماره همراه خودتون وارد این سایت بشید و نسبت به پرداخت اقدام فرمایید.\n\n"
        "usersmanager.ir"
    )

def _ews_queue_impl(request,phone,db):
    # The admin login middleware already protects the dashboard.
    # Additionally refuse a cross-origin POST to avoid CSRF-like queue floods.
    origin=request.headers.get("origin","")
    referer=request.headers.get("referer","")
    fetch_site=request.headers.get("sec-fetch-site","")
    if (origin!=_EWS_DOMAIN or
        not referer.startswith(_EWS_DOMAIN+"/") or
        fetch_site not in ("","same-origin")):
        return _ews_JSON({"ok":False,"code":"ORIGIN_DENIED"},status_code=403)

    normalized=_ns_clean_phone(phone)
    if not normalized:
        return _ews_JSON({"ok":False,"code":"INVALID_PHONE"},status_code=400)
    states=_followup_states(db)
    now=today_local()
    candidates=db.query(Subscription).filter(
        Subscription.phone==normalized,
        Subscription.is_free.is_(False),
    ).all()
    eligible=[
        s for s in candidates
        if states.get(int(s.id))=="waiting"
        and s.expiry_date is not None
        and s.expiry_date<=now
        and current_debt_for(s,now)>0
    ]
    if not eligible:
        return _ews_JSON({"ok":False,"code":"NOT_IN_WAITING"},status_code=409)
    expiry=min(s.expiry_date for s in eligible)
    message=_ews_message(expiry)
    # A manual draft only; the V4 app opens Google Messages for human Send.
    job_id,error=_ns_enqueue(db,normalized,"manual",message)
    if error:
        return _ews_JSON({"ok":False,"code":error},status_code=409)
    return {"ok":True,"job_id":job_id,"status":"queued",
            "message":message,"sent":False,"followup_state_unchanged":True}

def _ews_queue_header(request: _ews_Request,phone: str=_ews_Form(""),
                      db: _ews_Session=_ews_Depends(get_db)):
    return _ews_queue_impl(request,phone,db)

def _ews_queue_box(request: _ews_Request,phone: str=_ews_Form(""),
                   db: _ews_Session=_ews_Depends(get_db)):
    return _ews_queue_impl(request,phone,db)

# Replace ONLY the two older waiting reminder endpoints, preserving their URLs.
_EWS_PATHS={"/sms/waiting-renewal","/followups/sms-reminder"}
app.router.routes[:]=[
    r for r in app.router.routes
    if not (getattr(r,"path",None) in _EWS_PATHS and
            "POST" in (getattr(r,"methods",set()) or set()))
]
app.add_api_route("/sms/waiting-renewal",_ews_queue_header,methods=["POST"])
app.add_api_route("/followups/sms-reminder",_ews_queue_box,methods=["POST"])

env.filters["ews_message"]=_ews_message
_env_globals = getattr(env, "globals", None)
if _env_globals is not None:
    _env_globals["ews_message"]=_ews_message

_ews_tpl=TEMPLATES.get("followups.html","")
if not _ews_tpl or "data-waiting-renewal-form" not in _ews_tpl:
    raise RuntimeError("Waiting SMS V2: original group reminder button not installed")
_ews_title='title="سلام وقت بخیر، اکانتتون تمدید بشه؟"'
_ews_tpl=_ews_tpl.replace(_ews_title,'title="ثبت پیامک یادآوری انقضا در صف گوشی"')
if "data-waiting-sms-reminder-box" in _ews_tpl:
    # The optional details box should preview the same dynamically generated
    # message as the server, not the stale old one.
    _old_preview='<div class="waiting-sms-reminder-text">سلام وقت بخیر، اکانتتون تمدید بشه؟</div>'
    _new_preview='<div class="waiting-sms-reminder-text">{{ g.first_expiry|ews_message }}</div>'
    if _old_preview not in _ews_tpl:
        raise RuntimeError("Waiting SMS V2: details-box template differs")
    _ews_tpl=_ews_tpl.replace(_old_preview,_new_preview,1)
    _ews_tpl=_ews_tpl.replace(
        ".waiting-sms-reminder-text{",
        ".waiting-sms-reminder-text{white-space:pre-line;",
        1
    )
# Add a convenient hover-preview to the header button for the chosen payer.
_ews_tpl=_ews_tpl.replace(
    'title="ثبت پیامک یادآوری انقضا در صف گوشی"',
    'title="{{ g.first_expiry|ews_message }}"',
    1
)
TEMPLATES["followups.html"]=_ews_tpl
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)
