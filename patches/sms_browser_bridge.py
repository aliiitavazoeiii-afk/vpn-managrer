# HESAB_BROWSER_SMS_BRIDGE_V1
# Appended AFTER sms_admin, sms_aban_default, sms_nojump.
# Independent browser-send intents. NO Android queue, SMS gateway dispatch,
# payments, subscription edits, or delivery receipts.
import hashlib as _bs_hashlib
import hmac as _bs_hmac
import re as _bs_re
import secrets as _bs_secrets
from datetime import datetime as _bs_datetime, timezone as _bs_timezone, timedelta as _bs_timedelta
from fastapi import Request as _bs_Request, Depends as _bs_Depends, HTTPException as _bs_HTTPException
from fastapi.responses import JSONResponse as _bs_JSONResponse
from sqlalchemy import text as _bs_text
from sqlalchemy.orm import Session as _bs_Session

_BS_ORIGIN = "https://hesab.filmjadiid.ir"
_BS_PATTERN = _bs_re.compile(r"^09\d{9}$")
_BS_TTL_MINUTES = 8
_BS_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS sms_browser_intents (
      id BIGSERIAL PRIMARY KEY,
      phone VARCHAR(11) NOT NULL,
      body TEXT NOT NULL,
      body_sha256 VARCHAR(64) NOT NULL,
      source VARCHAR(12) NOT NULL,
      cycle_key VARCHAR(32),
      intent_token_hash VARCHAR(64) NOT NULL,
      status VARCHAR(30) NOT NULL DEFAULT 'pending',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      submitted_at TIMESTAMPTZ,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      moved_count INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS ix_sms_browser_debt_one
      ON sms_browser_intents(phone, cycle_key)
      WHERE source='debt'
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_sms_browser_phone_created
      ON sms_browser_intents(phone,created_at DESC)
    """,
)

def _bs_fail(code, status=409):
    return _bs_JSONResponse({"ok": False, "code": code}, status_code=status)


def _bs_local_only(request):
    # Auth is also enforced by the app's existing session middleware.
    # Require same-origin browser execution, not CORS or a third-party caller.
    origin = request.headers.get("origin", "")
    ref = request.headers.get("referer", "")
    if origin != _BS_ORIGIN or not ref.startswith(_BS_ORIGIN + "/"):
        raise _bs_HTTPException(status_code=403, detail="same_origin_required")
    if request.headers.get("x-hesab-browser-sms") != "v1":
        raise _bs_HTTPException(status_code=403, detail="bridge_header_required")
    fetch_site = request.headers.get("sec-fetch-site", "")
    if fetch_site and fetch_site != "same-origin":
        raise _bs_HTTPException(status_code=403, detail="cross_site_denied")


def _bs_norm(value):
    number = _sms_normalize_phone(value)
    return number if _BS_PATTERN.fullmatch(number or "") else ""


def _bs_init(db):
    for stmt in _BS_SCHEMA:
        db.execute(_bs_text(stmt))
    db.commit()


def _bs_lock(db, normalized):
    db.execute(
      _bs_text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
      {"k": "browser-sms|" + normalized},
    )


def _bs_existing_legacy_debt(db, phone, body):
    # A previous job in the current Jalali month is NOT evidence that the
    # CURRENT reminder was already sent. The old broad month check prevented
    # nearly every debtor from using the new browser flow.
    #
    # Block only when the same exact reminder body was previously recorded
    # as successfully submitted/confirmed by the old workflow. "Failed" may
    # have been delivered despite error (an old gateway failure mode), so
    # operators must still check the Google conversation before resending
    # a reminder they know was already received. No old job is ever replayed.
    found = db.execute(_bs_text("""
      SELECT id FROM sms_jobs
      WHERE phone=:phone AND source LIKE 'debt:%'
        AND message=:body
        AND status IN ('sent','delivered','operator_confirmed')
      ORDER BY id DESC LIMIT 1
    """), {"phone": phone, "body": body}).first()
    return found is not None


def _bs_debt_candidates(db, phone, now):
    states = _followup_states(db)
    candidates = db.query(Subscription).filter(
      Subscription.phone == phone,
      Subscription.is_free.is_(False)
    ).order_by(Subscription.id.asc()).all()
    return [
      s for s in candidates
      if s.expiry_date is not None and s.expiry_date <= now
      and current_debt_for(s, now) > 0
      and states.get(s.id) not in ("waiting", "cut")
    ]


async def _bs_begin(request: _bs_Request, db: _bs_Session = _bs_Depends(get_db)):
    _bs_local_only(request)
    try:
        data = await request.json()
    except (ValueError, TypeError):
        return _bs_fail("BAD_JSON", 400)
    if not isinstance(data, dict):
        return _bs_fail("BAD_JSON", 400)
    phone = _bs_norm(data.get("phone", ""))
    source = data.get("source")
    requested_body = data.get("message")
    if not phone or source not in ("manual", "debt"):
        return _bs_fail("INVALID_REQUEST", 400)
    if not isinstance(requested_body, str) or len(requested_body) > 1000:
        return _bs_fail("INVALID_MESSAGE", 400)
    if source == "manual" and not requested_body.strip():
        return _bs_fail("INVALID_MESSAGE", 400)

    _bs_init(db)
    _bs_lock(db, phone)
    now = today_local()
    cycle = None
    if source == "debt":
        if not callable(globals().get("_followup_set")):
            db.rollback()
            return _bs_fail("FOLLOWUP_UNAVAILABLE", 503)
        eligible = _bs_debt_candidates(db, phone, now)
        if not eligible:
            db.rollback()
            return _bs_fail("NO_ACTIONABLE_DEBT")
        cycle = min(s.expiry_date for s in eligible).isoformat()
        canonical = _ABAN_SMS_PATTERN.format(expiry=jdate(min(s.expiry_date for s in eligible)))
        if len(canonical) > 1000:
            db.rollback()
            return _bs_fail("CANONICAL_MESSAGE_TOO_LONG", 400)
        # Refuse a different on-screen reminder. The operator must not click
        # expecting one body while the server silently sends another.
        if requested_body.strip() != canonical.strip():
            db.rollback()
            return _bs_fail("DEBT_MESSAGE_CHANGED_REVIEW_REQUIRED")
        body = canonical
        if _bs_existing_legacy_debt(db, phone, body):
            db.rollback()
            return _bs_fail("EXISTING_IDENTICAL_CONFIRMED_SMS")
        older = db.execute(_bs_text("""
          SELECT id,status FROM sms_browser_intents
          WHERE phone=:phone AND source='debt' AND cycle_key=:cycle
          LIMIT 1
        """), {"phone": phone, "cycle": cycle}).mappings().first()
        if older:
            db.rollback()
            return _bs_fail("EXISTING_BROWSER_INTENT_" + older["status"].upper())
    else:
        body = requested_body.strip()
        earlier = db.execute(_bs_text("""
          SELECT id FROM sms_browser_intents
          WHERE phone=:phone AND source='manual' AND body_sha256=:hash
          AND created_at > now() - interval '5 minutes'
          ORDER BY id DESC LIMIT 1
        """), {"phone":phone,"hash":_bs_hashlib.sha256(body.encode("utf-8")).hexdigest()}).first()
        if earlier:
            db.rollback()
            return _bs_fail("DUPLICATE_RECENT_MANUAL_SMS")

    token = _bs_secrets.token_urlsafe(32)
    digest = _bs_hashlib.sha256(body.encode("utf-8")).hexdigest()
    intent_id = db.execute(_bs_text("""
      INSERT INTO sms_browser_intents
        (phone,body,body_sha256,source,cycle_key,intent_token_hash,status)
      VALUES (:phone,:body,:digest,:source,:cycle,:token_hash,'pending')
      RETURNING id
    """), {
      "phone":phone, "body":body, "digest":digest, "source":source,
      "cycle":cycle, "token_hash":_bs_hashlib.sha256(token.encode("ascii")).hexdigest(),
    }).scalar_one()
    db.add(AuditEvent(kind="browser_sms_intent",
      message=f"browser SMS prepared; intent={intent_id}; source={source}; phone={phone}; cycle={cycle or '-'}"))
    db.commit()
    return {"ok": True, "id":intent_id, "token":token, "source":source,
            "phone":"+98"+phone[1:], "message":body}


async def _bs_finish(request: _bs_Request, db: _bs_Session = _bs_Depends(get_db)):
    _bs_local_only(request)
    try:
        data = await request.json()
    except (ValueError, TypeError):
        return _bs_fail("BAD_JSON", 400)
    if not isinstance(data, dict) or type(data.get("id")) is not int:
        return _bs_fail("INVALID_RESULT", 400)
    token = data.get("token")
    code = data.get("result")
    if (not isinstance(token,str) or len(token) < 32 or
        code not in ("SUBMITTED", "UNKNOWN")):
        return _bs_fail("INVALID_RESULT", 400)

    _bs_init(db)
    row = db.execute(_bs_text("""
      SELECT id, phone, body, source, cycle_key, status,
             intent_token_hash, created_at, moved_count
      FROM sms_browser_intents WHERE id=:id FOR UPDATE
    """), {"id": data["id"]}).mappings().first()
    if not row or not _bs_hmac.compare_digest(
      row["intent_token_hash"],
      _bs_hashlib.sha256(token.encode("utf-8")).hexdigest()
    ):
        db.rollback()
        return _bs_fail("UNKNOWN_INTENT", 403)

    if row["status"] == "browser_submitted":
        db.commit()
        return {"ok":True,"status":"browser_submitted","moved":row["moved_count"],
                "duplicate":True}
    if row["status"] != "pending":
        db.rollback()
        return _bs_fail("INTENT_ALREADY_RESOLVED")
    created = row["created_at"]
    if created.tzinfo is None:
        created = created.replace(tzinfo=_bs_timezone.utc)
    if _bs_datetime.now(_bs_timezone.utc) > created + _bs_timedelta(minutes=_BS_TTL_MINUTES):
        db.rollback()
        return _bs_fail("INTENT_EXPIRED_REVIEW_REQUIRED")
    if code != "SUBMITTED":
        # Do NOT release a possibly-sent intent automatically.
        db.execute(_bs_text("""
          UPDATE sms_browser_intents SET status='uncertain',updated_at=now()
          WHERE id=:id
        """), {"id":row["id"]})
        db.commit()
        return {"ok":False,"status":"uncertain","code":"VERIFY_GOOGLE_MESSAGES"}

    moved = 0
    if row["source"] == "debt":
        now = today_local()
        _bs_lock(db,row["phone"])
        eligible = _bs_debt_candidates(db,row["phone"],now)
        if (not eligible or
            min(s.expiry_date for s in eligible).isoformat() != row["cycle_key"]):
            db.rollback()
            return _bs_fail("SUBMITTED_BUT_DEBT_CHANGED_REVIEW_REQUIRED")
        for s in eligible:
            _followup_set(db,s.id,"waiting",
              f"Google Messages browser UI submitted; unverified delivery; intent={row['id']}")
            moved += 1

    db.execute(_bs_text("""
      UPDATE sms_browser_intents SET status='browser_submitted',
        submitted_at=now(), updated_at=now(), moved_count=:moved
      WHERE id=:id
    """), {"moved":moved, "id":row["id"]})
    db.add(AuditEvent(kind="browser_sms_submitted",
      message=(f"Google Messages web UI submission (NOT delivered); "
               f"intent={row['id']}; phone={row['phone']}; moved={moved}")))
    db.commit()
    return {"ok":True,"status":"browser_submitted","moved":moved,
            "delivery_confirmed":False}


app.add_api_route("/sms/browser/begin", _bs_begin, methods=["POST"])
app.add_api_route("/sms/browser/finish", _bs_finish, methods=["POST"])


# Disable direct legacy gateway queueing from any browser/profile without the
# bridge, preventing accidental accounting transitions on stale forms.
def _bs_legacy_blocked():
    return _bs_fail("BROWSER_BRIDGE_REQUIRED_NO_GATEWAY_QUEUE")

app.router.routes[:] = [
    r for r in app.router.routes
    if not (
        getattr(r, "path", None) in ("/sms/send", "/sms/debt-send", "/sms/{job_id}/retry")
        and "POST" in (getattr(r, "methods", set()) or set())
    )
]
app.add_api_route("/sms/send", _bs_legacy_blocked, methods=["POST"])
app.add_api_route("/sms/debt-send", _bs_legacy_blocked, methods=["POST"])
app.add_api_route("/sms/{job_id}/retry", _bs_legacy_blocked, methods=["POST"])
