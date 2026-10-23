# HESAB_WAITING_VPN_RESTORE_RESILIENCE_V2
# Only explicitly operator-cut waiting clients (waiting_vpn_controls journal).
# NO scheduled disabling, NO Shahan, NO financial/payment record changes.
# Resolve uncertain manual cut through fresh XUI state; after a later verified
# full payment, restore with a CAS claim, readback and bounded retry cadence.
from sqlalchemy import text as _wvr_text
import asyncio as _wvr_asyncio

_WVR_ORIGINAL_DISABLE_ONE=_wvc_disable_one
_WVR_INTERVAL=30
_WVR_BACKOFF=(30,90,240,600,1200,3600)
_WVR_STALE_ACTIVATING_SECONDS=240

def _wvr_journal_audit(db,sid,server,email,kind,result):
    db.add(AuditEvent(kind=kind,
      message=f"sid={sid}; server={server}; client={email}; result={result}"))

def _wvr_promote_uncertain_disable(sid,db):
    """After a real operator click, confirm changed-off state by fresh readback.

    The original handler wrote a durable 'disabling' marker before calling the
    broker and set 'needs_review' after an ambiguous broker response. We only
    inspect those markers for this very click; NEVER discover unrelated users.
    """
    controls=db.execute(_wvr_text("""
      SELECT id,server,email FROM waiting_vpn_controls
      WHERE subscription_id=:sid AND state='needs_review'
        AND disabled_at IS NULL AND activated_at IS NULL
    """),{"sid":int(sid)}).mappings().all()
    confirmed=[]
    for row in controls:
        server=row["server"];email=row["email"]
        try:
            live=_ml_one(server,db)       # one read-only fresh XUI snapshot
            client=_wvc_match(live,server,int(sid))
            if client["email"].casefold()!=email.casefold():
                raise RuntimeError("Changed XUI identity")
            if client.get("client_enabled") is not False:
                # Do not pretend the client was disabled if still on.
                continue
            updated=db.execute(_wvr_text("""
              UPDATE waiting_vpn_controls
              SET state='disabled',disabled_at=NOW(),updated_at=NOW(),
                  restore_attempts=0,next_retry_at=NULL,last_restore_error=NULL
              WHERE id=:id AND subscription_id=:sid
                AND state='needs_review' AND disabled_at IS NULL
              RETURNING id
            """),{"id":int(row["id"]),"sid":int(sid)}).first()
            if updated:
                _wvr_journal_audit(db,sid,server,email,"vpn_waiting_disabled",
                                   "confirmed_by_readback_after_uncertain_response")
                db.commit()
                confirmed.append(server)
        except Exception as exc:
            db.rollback()
            print("WVR_CUT_READBACK_UNAVAILABLE",sid,server,type(exc).__name__,
                  str(exc)[:120])
    return confirmed

def _wvc_disable_one(sid,db):
    original=_WVR_ORIGINAL_DISABLE_ONE(sid,db)
    # Only an actual operator-triggered call reaches this wrapper.
    # The original routine has already written the journal marker.
    if original.get("ok") or not original.get("warnings"):
        return original
    verified=_wvr_promote_uncertain_disable(sid,db)
    if not verified:return original
    warnings=[w for w in original.get("warnings",[])
              if not any(w.startswith(s+":") for s in verified)]
    confirmed=sorted(set(original.get("confirmed",[]))|set(verified))
    return {**original,"ok":bool(confirmed) and not warnings,
            "confirmed":confirmed,"warnings":warnings,
            "message":("قطع X-UI با خواندن مجدد وضعیت تأیید شد"
                       if not warnings else "بخشی از قطع نیازمند بررسی است")}

def _wvr_backoff(attempts):
    return _WVR_BACKOFF[min(max(0,attempts-1),len(_WVR_BACKOFF)-1)]

def _wvr_mark_retry(db,row_id,sid,server,kind):
    # A failed/ambiguous XUI operation never causes a blind immediate retry.
    info=db.execute(_wvr_text("""
      SELECT restore_attempts FROM waiting_vpn_controls
      WHERE id=:id AND subscription_id=:sid AND state='activating'
    """),{"id":row_id,"sid":sid}).scalar()
    if info is None:
        db.rollback()
        return
    attempts=int(info)+1
    delay=_wvr_backoff(attempts)
    db.execute(_wvr_text("""
      UPDATE waiting_vpn_controls
      SET state='needs_review',restore_attempts=:attempts,
          next_retry_at=NOW()+(:delay * INTERVAL '1 second'),
          last_restore_error=:error,updated_at=NOW()
      WHERE id=:id AND subscription_id=:sid AND state='activating'
    """),{"id":row_id,"sid":sid,"attempts":attempts,"delay":delay,
          "error":str(kind)[:90]})
    db.commit()
    # Visible for admins in docker compose logs; no customer data or secrets.
    print("WVR_RETRY_SCHEDULED",sid,server,"attempt",attempts,
          "after_seconds",delay,"reason",str(kind)[:90])

def _wvr_finish(db,row_id,sid,server,email,result):
    updated=db.execute(_wvr_text("""
      UPDATE waiting_vpn_controls
      SET state='restored',activated_at=NOW(),updated_at=NOW(),
          next_retry_at=NULL,last_restore_error=NULL
      WHERE id=:id AND subscription_id=:sid AND state='activating'
      RETURNING id
    """),{"id":row_id,"sid":sid}).first()
    if not updated:raise RuntimeError("Lost restoration claim")
    _wvr_journal_audit(db,sid,server,email,"vpn_waiting_restored",result)
    db.commit()
    print("WVR_RESTORE_CONFIRMED",sid,server,result)

def _wvr_restore_one(db,record):
    row_id=int(record["id"]);sid=int(record["subscription_id"])
    server=str(record["server"]);email=str(record["email"])
    # A *new* actual financial payment since the waiting cut is essential.
    # The account must also be fully settled and unexpired.
    if not _wvc_ready(db,sid,False):return
    claim=db.execute(_wvr_text("""
      UPDATE waiting_vpn_controls
      SET state='activating',updated_at=NOW()
      WHERE id=:id AND subscription_id=:sid
        AND server=:server AND email=:email
        AND (
          state='disabled'
          OR (state='needs_review'
              AND (next_retry_at IS NULL OR next_retry_at<=NOW()))
          OR (state='activating'
              AND updated_at<NOW()-INTERVAL '240 seconds')
        )
        AND EXISTS(
          SELECT 1 FROM payments p
          WHERE p.subscription_id=:sid AND p.id>waiting_vpn_controls.payment_watermark
            AND p.amount_toman>0
        )
      RETURNING id
    """),{"id":row_id,"sid":sid,"server":server,"email":email}).first()
    if not claim:
        db.rollback();return
    db.commit()
    try:
        # Recheck AFTER exclusive journal claim; payment may have been undone.
        db.expire_all()
        if not _wvc_ready(db,sid,False):
            raise ValueError("FULL_PAYMENT_NO_LONGER_VALID")
        live=_ml_one(server,db)
        client=_wvc_match(live,server,sid)
        if client["email"].casefold()!=email.casefold():
            raise ValueError("XUI_IDENTITY_CHANGED")
        if client.get("client_enabled") is True:
            _wvr_finish(db,row_id,sid,server,email,"already_enabled_verified")
            return
        if client.get("client_enabled") is not False:
            raise ValueError("XUI_STATE_UNCONFIRMED")
        # Client-scoped CAS toggle; the root broker reads state back.
        try:
            answer=_ml_call("toggle",server,email=email,expected=False,target=True)
            if answer.get("client_enabled") is not True:
                raise RuntimeError("XUI_ENABLE_RESPONSE_UNCONFIRMED")
        except Exception as exc:
            # An HTTP/socket timeout may occur AFTER the panel has changed.
            # Read back exactly this approved client before labeling failure.
            try:
                check=_ml_one(server,db)
                fresh=_wvc_match(check,server,sid)
                if (fresh["email"].casefold()==email.casefold()
                    and fresh.get("client_enabled") is True):
                    _wvr_finish(db,row_id,sid,server,email,
                                "enabled_confirmed_after_broker_error")
                    return
            except Exception:
                pass
            raise RuntimeError("XUI_ENABLE_NOT_CONFIRMED:"+type(exc).__name__)
        _wvr_finish(db,row_id,sid,server,email,"auto_enabled_confirmed")
    except Exception as exc:
        db.rollback()
        # A payment reversal or mapping conflict never silently enables users.
        _wvr_mark_retry(db,row_id,sid,server,type(exc).__name__+":"+str(exc)[:55])

def _wvc_reconcile_once():
    """Scans only journal-owned post-payment clients.

    A pre-existing needs_review (ambiguous disable, failed restore, or worker
    restart) is no longer permanently abandoned. Backoff prevents a DPI/panel
    outage from generating unbounded requests. Other XUI disables are untouched.
    """
    generator=get_db()
    db=next(generator)
    try:
        candidates=db.execute(_wvr_text("""
          SELECT c.id,c.subscription_id,c.server,c.email
          FROM waiting_vpn_controls c
          WHERE (
            c.state='disabled'
            OR (c.state='needs_review'
                AND (c.next_retry_at IS NULL OR c.next_retry_at<=NOW()))
            OR (c.state='activating'
                AND c.updated_at<NOW()-INTERVAL '240 seconds')
          )
          AND EXISTS (
            SELECT 1 FROM payments p
            WHERE p.subscription_id=c.subscription_id
              AND p.id>c.payment_watermark AND p.amount_toman>0
          )
          ORDER BY c.updated_at,c.id LIMIT 8
        """)).mappings().all()
        for row in candidates:
            try:
                _wvr_restore_one(db,row)
            except Exception as exc:
                db.rollback()
                print("WVR_WORKER_ROW_ERROR",int(row["subscription_id"]),
                      type(exc).__name__,str(exc)[:125])
    finally:
        generator.close()
