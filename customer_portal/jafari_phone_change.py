# JAFARI_PHONE_CHANGE_V1
# Appended to customer_portal/v2.py by the guarded installer.
# No SMS or OTP. Only current subscriber owner 09357001107 can reassign
# their OWN account. Future billing follows subscriptions.phone as before.
from fastapi import Form as _jp_Form
from fastapi.responses import RedirectResponse as _jp_Redirect
import re as _jp_re

_JP_OWNER = "09357001107"


@app.post("/jafari/change-phone/{sid}")
def _jp_change_phone(
    sid: int, request: Request,
    csrf: str = _jp_Form(...),
    new_phone: str = _jp_Form(...),
):
    owner = _v2_session_phone(request)
    if owner != _JP_OWNER or not verify_csrf(_JP_OWNER, csrf):
        return _jp_Redirect("/", status_code=303)

    # Strict canonical Iranian mobile, different from the original owner.
    new_phone = normalize_phone(new_phone)
    if not _jp_re.fullmatch(r"09\d{9}", new_phone or "") or new_phone == _JP_OWNER:
        return _jp_Redirect("/?jafari_phone=invalid", status_code=303)

    with db_conn() as conn:
        with conn.cursor() as cur:
            # Lock ONLY the requested subscription; no bulk updates.
            cur.execute(
                "SELECT id, phone, display_name FROM subscriptions WHERE id=%s FOR UPDATE",
                (sid,),
            )
            item = cur.fetchone()
            if not item or item["phone"] != _JP_OWNER:
                return _jp_Redirect("/?jafari_phone=not_owned", status_code=303)

            # Disallow archived/disabled accounts; match the current visible list.
            if sid not in {int(a["id"]) for a in active_subscriptions(conn, _JP_OWNER)}:
                return _jp_Redirect("/?jafari_phone=not_owned", status_code=303)

            # Never join a different customer's account group accidentally.
            cur.execute(
                "SELECT 1 FROM subscriptions WHERE phone=%s AND id<>%s LIMIT 1",
                (new_phone, sid),
            )
            if cur.fetchone():
                return _jp_Redirect("/?jafari_phone=already_used", status_code=303)

            # Unresolved payment requests use the old phone as payer identity.
            # Fail closed rather than risk a paid callback applying after transfer.
            cur.execute(
                """
                SELECT 1 FROM ayria_payment_requests
                WHERE phone=%s AND
                  (status IN ('creating','created','pending','processing','waiting','verifying')
                   OR (status='paid' AND COALESCE(sync_status,'')<>'applied'))
                LIMIT 1
                """,
                (_JP_OWNER,),
            )
            if cur.fetchone():
                return _jp_Redirect("/?jafari_phone=pending_payment", status_code=303)

            cur.execute(
                "UPDATE subscriptions SET phone=%s WHERE id=%s AND phone=%s",
                (new_phone, sid, _JP_OWNER),
            )
            if cur.rowcount != 1:
                raise RuntimeError("Jafari phone change concurrency conflict")
            cur.execute(
                """
                INSERT INTO audit_events(kind,message,created_at)
                VALUES ('customer_account_phone_change', %s, NOW())
                """,
                (
                    f"sid={sid}; old_phone={_JP_OWNER}; new_phone={new_phone}; "
                    "authorized by source phone portal session; no OTP; "
                    "expiry, debt, payments and billing unchanged"
                ,),
            )
        conn.commit()
    return _jp_Redirect("/?jafari_phone=changed", status_code=303)
