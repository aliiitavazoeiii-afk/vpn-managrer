"""Recover admin waiting state for SMS jobs 13-15, WITHOUT sending SMS.

The operator explicitly reports that recipients received these three reminders;
Android returned result=0, which is not a verified provider-delivery receipt.
Mark jobs 'operator_confirmed' (not 'delivered') so they cannot be retried and
restore only currently overdue/unpaid accounts listed in original sms_queue
audit events. No changes to subscriptions, expiries, debts, payments or fees.

Run in customer-portal container as: python - --apply < this_file
All DB updates are one transaction. Roll back entirely if metadata differs.
"""
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row

JOBS = (13, 14, 15)
EXPECTED_ERROR = "Android SMS send result=0"
MATCH_JOB = re.compile(r"\bjob=(\d+);")
MATCH_PHONE = re.compile(r"\bphone=(\d+);")
MATCH_ACCOUNTS = re.compile(r"\baccounts=([0-9,]+)(?:\s|$)")
MATCH_SID = re.compile(r"\bsid=(\d+)\b")

if sys.argv[1:] not in (["--apply"], ["--check"]):
    print("Usage: python - --check (read only) OR --apply (reconcile)")
    raise SystemExit(2)
APPLY = sys.argv[1:] == ["--apply"]

today = datetime.now(ZoneInfo("Asia/Tehran")).date()
try:
    with psycopg.connect(os.environ["DATABASE_DSN"], row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout='5s'")
            cur.execute(
                """
                SELECT id, phone, source, status, error, created_at
                FROM sms_jobs WHERE id=ANY(%s)
                ORDER BY id FOR UPDATE
                """, (list(JOBS),),
            )
            jobs = cur.fetchall()
            if [r["id"] for r in jobs] != list(JOBS):
                raise RuntimeError("One or more SMS job IDs are missing")
            for job in jobs:
                if not str(job["source"]).startswith("debt:"):
                    raise RuntimeError(f"Job {job['id']}: not a debt reminder")
                if job["status"] not in ("failed", "operator_confirmed"):
                    raise RuntimeError(f"Job {job['id']}: status changed to {job['status']}")
                if job["status"] == "failed" and job["error"] != EXPECTED_ERROR:
                    raise RuntimeError(f"Job {job['id']}: error changed, cannot safely confirm")

            cur.execute(
                """
                SELECT id, message, created_at FROM audit_events
                WHERE kind='sms_queue'
                ORDER BY id DESC
                """
            )
            queue_audits = {}
            for event in cur.fetchall():
                found = MATCH_JOB.search(str(event["message"] or ""))
                if not found:
                    continue
                job_id = int(found.group(1))
                if job_id in JOBS:
                    if job_id in queue_audits:
                        raise RuntimeError(f"Job {job_id}: multiple queue audit entries")
                    queue_audits[job_id] = event

            accounts_for_job = {}
            for job in jobs:
                event = queue_audits.get(job["id"])
                if event is None:
                    raise RuntimeError(f"Job {job['id']}: missing original queue audit")
                message = str(event["message"] or "")
                found_phone = MATCH_PHONE.search(message)
                found_accounts = MATCH_ACCOUNTS.search(message)
                if not found_phone or found_phone.group(1) != job["phone"]:
                    raise RuntimeError(f"Job {job['id']}: original phone mismatch")
                if not found_accounts:
                    raise RuntimeError(f"Job {job['id']}: missing original account IDs")
                account_ids = [int(x) for x in found_accounts.group(1).split(",")]
                if not account_ids or len(account_ids) != len(set(account_ids)):
                    raise RuntimeError(f"Job {job['id']}: invalid account list")
                accounts_for_job[job["id"]] = account_ids

            all_ids = sorted(set(sid for ids in accounts_for_job.values() for sid in ids))
            cur.execute(
                """
                SELECT id, phone, expiry_date, monthly_fee_toman, is_free
                FROM subscriptions
                WHERE id=ANY(%s)
                ORDER BY id FOR UPDATE
                """, (all_ids,),
            )
            accounts = {int(x["id"]): x for x in cur.fetchall()}
            if set(accounts) != set(all_ids):
                raise RuntimeError("A referenced account has been removed")

            # This is the same latest-event-wins rule used by the admin panels.
            cur.execute(
                """
                SELECT id, kind, message, created_at
                FROM audit_events
                WHERE kind IN ('followup_waiting','followup_clear','followup_cut')
                ORDER BY id DESC
                """
            )
            last_state = {}
            for ev in cur.fetchall():
                matched = MATCH_SID.search(str(ev["message"] or ""))
                if not matched:
                    continue
                sid = int(matched.group(1))
                if sid in all_ids and sid not in last_state:
                    last_state[sid] = ev

            # Do not undo a payment made after any particular SMS job.
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='public' AND table_name='payments'
                """
            )
            payment_cols = {x["column_name"] for x in cur.fetchall()}
            payment_timestamp = next(
                (c for c in ("paid_at", "created_at") if c in payment_cols),
                None,
            )
            if not payment_timestamp:
                raise RuntimeError("Cannot verify subsequent payments: time column missing")

            move_ids = set()
            examined = set()
            excluded = []
            for job in jobs:
                for sid in accounts_for_job[job["id"]]:
                    if sid in examined:
                        continue
                    examined.add(sid)
                    account = accounts[sid]
                    if account["phone"] != job["phone"]:
                        excluded.append((sid, "phone_changed"))
                        continue
                    if account["is_free"] or int(account["monthly_fee_toman"] or 0) <= 0:
                        excluded.append((sid, "free"))
                        continue
                    expiry = account["expiry_date"]
                    if not expiry or expiry > today:
                        excluded.append((sid, "future_or_missing_expiry"))
                        continue
                    latest = last_state.get(sid)
                    if latest and latest["kind"] == "followup_cut":
                        excluded.append((sid, "cut"))
                        continue
                    if latest and latest["kind"] == "followup_waiting":
                        excluded.append((sid, "already_waiting"))
                        continue
                    if latest and latest["kind"] == "followup_clear" and latest["created_at"] >= job["created_at"]:
                        excluded.append((sid, "cleared_after_sms"))
                        continue
                    cur.execute(
                        f"SELECT EXISTS(SELECT 1 FROM payments WHERE subscription_id=%s "
                        f"AND {payment_timestamp} >= %s) AS has_payment",
                        (sid, job["created_at"]),
                    )
                    if cur.fetchone()["has_payment"]:
                        excluded.append((sid, "payment_after_sms"))
                        continue
                    move_ids.add(sid)

            print(f"Target jobs: {','.join(str(x) for x in JOBS)}")
            print(f"Accounts mapped from original SMS audit events: {len(all_ids)}")
            print(f"Eligible overdue accounts to restore to waiting: {len(move_ids)}")
            if excluded:
                counts = {}
                for _, reason in excluded:
                    counts[reason] = counts.get(reason, 0) + 1
                print("Protected/skipped:", ", ".join(f"{k}={v}" for k,v in sorted(counts.items())))

            if not APPLY:
                conn.rollback()
                print("CHECK PASSED: database unchanged, ready to reconcile.")
                raise SystemExit(0)

            # No new sms_jobs are inserted and nothing is requeued.
            for job in jobs:
                if job["status"] == "operator_confirmed":
                    continue
                cur.execute(
                    """
                    UPDATE sms_jobs
                    SET status='operator_confirmed', updated_at=NOW()
                    WHERE id=%s AND status='failed' AND error=%s
                    """, (job["id"], EXPECTED_ERROR),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"Job {job['id']}: concurrent status change")
                cur.execute(
                    """
                    INSERT INTO audit_events(kind,message,created_at)
                    VALUES ('sms_operator_confirmed',%s,NOW())
                    """,
                    (
                        f"job={job['id']}; Android reported result=0; "
                        "operator explicitly confirmed recipient received reminder; "
                        "NO RESEND; gateway delivery not independently verified",
                    ),
                )

            for sid in sorted(move_ids):
                cur.execute(
                    """
                    INSERT INTO audit_events(kind,message,created_at)
                    VALUES ('followup_waiting',%s,NOW())
                    """,
                    (f"sid={sid}; recovered from jobs 13,14,15 by operator instruction; no new SMS sent",),
                )
        conn.commit()
    print("SUCCESS: RECONCILIATION COMPLETE — NO SMS QUEUED OR SENT")
    print("Jobs 13-15 are protected from retry; corresponding eligible accounts are in waiting.")
    print("No billing amounts, expiry dates, subscriptions or payments were changed.")
except Exception as exc:
    print(f"STOP: {type(exc).__name__}: {str(exc)[:240]}")
    print("No partial reconciliation was committed; all changes rolled back.")
    raise SystemExit(1)
