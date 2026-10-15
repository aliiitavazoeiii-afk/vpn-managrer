import hmac
import os
from datetime import datetime, timezone
from typing import Optional

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

DATABASE_DSN = os.environ["DATABASE_DSN"]
GATEWAY_TOKEN = os.environ.get("SMS_GATEWAY_TOKEN", "").strip()

if len(GATEWAY_TOKEN) < 24:
    raise RuntimeError("SMS_GATEWAY_TOKEN must be set to a strong secret")

app = FastAPI(title="Hesab SMS Gateway", docs_url=None, redoc_url=None)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sms_jobs (
    id BIGSERIAL PRIMARY KEY,
    phone VARCHAR(32) NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'queued',
    source VARCHAR(64) NOT NULL DEFAULT 'dashboard',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_at TIMESTAMPTZ,
    dispatching_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    device_id VARCHAR(128),
    sim_subscription_id INTEGER,
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_sms_jobs_queue ON sms_jobs(status, id);
CREATE INDEX IF NOT EXISTS idx_sms_jobs_phone ON sms_jobs(phone, created_at DESC);

CREATE TABLE IF NOT EXISTS sms_devices (
    device_id VARCHAR(128) PRIMARY KEY,
    device_name VARCHAR(160),
    app_version VARCHAR(64),
    android_version VARCHAR(64),
    sim_subscription_id INTEGER,
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def db_conn():
    return psycopg.connect(DATABASE_DSN, row_factory=dict_row)


def ensure_schema():
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()


@app.on_event("startup")
def _startup():
    ensure_schema()


def require_token(x_sms_gateway_token: str = Header(default="")):
    if not hmac.compare_digest(x_sms_gateway_token or "", GATEWAY_TOKEN):
        raise HTTPException(status_code=401, detail="invalid gateway token")


class Heartbeat(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
    device_name: str = Field(default="", max_length=160)
    app_version: str = Field(default="", max_length=64)
    android_version: str = Field(default="", max_length=64)
    sim_subscription_id: Optional[int] = None


class StatusUpdate(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
    status: str
    error: str = Field(default="", max_length=1000)
    sim_subscription_id: Optional[int] = None


@app.get("/health")
def health():
    return {"ok": True, "service": "Hesab SMS Gateway"}


@app.post("/v1/heartbeat")
def heartbeat(body: Heartbeat, x_sms_gateway_token: str = Header(default="")):
    require_token(x_sms_gateway_token)
    ensure_schema()
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sms_devices
                    (device_id, device_name, app_version, android_version, sim_subscription_id, last_seen)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (device_id) DO UPDATE SET
                    device_name = EXCLUDED.device_name,
                    app_version = EXCLUDED.app_version,
                    android_version = EXCLUDED.android_version,
                    sim_subscription_id = EXCLUDED.sim_subscription_id,
                    last_seen = NOW()
                """,
                (
                    body.device_id,
                    body.device_name,
                    body.app_version,
                    body.android_version,
                    body.sim_subscription_id,
                ),
            )
        conn.commit()
    return {"ok": True, "server_time": datetime.now(timezone.utc).isoformat()}


@app.get("/v1/jobs/next")
def next_job(device_id: str, x_sms_gateway_token: str = Header(default="")):
    require_token(x_sms_gateway_token)
    device_id = (device_id or "").strip()[:128]
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id required")

    ensure_schema()
    with db_conn() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE sms_jobs
                    SET status='queued', claimed_at=NULL, device_id=NULL, updated_at=NOW()
                    WHERE status='claimed'
                      AND claimed_at < NOW() - INTERVAL '3 minutes'
                    """
                )
                cur.execute(
                    """
                    WITH picked AS (
                        SELECT id
                        FROM sms_jobs
                        WHERE status='queued'
                        ORDER BY id
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE sms_jobs j
                    SET status='claimed',
                        claimed_at=NOW(),
                        updated_at=NOW(),
                        device_id=%s,
                        attempts=j.attempts + 1
                    FROM picked
                    WHERE j.id=picked.id
                    RETURNING j.id, j.phone, j.message, j.created_at, j.attempts
                    """,
                    (device_id,),
                )
                row = cur.fetchone()

    if not row:
        return Response(status_code=204)

    return {
        "id": row["id"],
        "phone": row["phone"],
        "message": row["message"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "attempts": row["attempts"],
    }


@app.post("/v1/jobs/{job_id}/status")
def update_status(
    job_id: int,
    body: StatusUpdate,
    x_sms_gateway_token: str = Header(default=""),
):
    require_token(x_sms_gateway_token)
    allowed = {"dispatching", "sent", "delivered", "failed"}
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail="invalid status")

    ensure_schema()
    with db_conn() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, status, device_id FROM sms_jobs WHERE id=%s FOR UPDATE",
                    (job_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="job not found")
                if row["device_id"] and row["device_id"] != body.device_id:
                    raise HTTPException(status_code=409, detail="job belongs to another device")

                current = row["status"]
                if current == "delivered":
                    return {"ok": True, "status": "delivered"}
                if current == "failed" and body.status != "failed":
                    raise HTTPException(status_code=409, detail="failed job must be retried from dashboard")

                fields = ["status=%s", "updated_at=NOW()", "device_id=%s"]
                values = [body.status, body.device_id]

                if body.sim_subscription_id is not None:
                    fields.append("sim_subscription_id=%s")
                    values.append(body.sim_subscription_id)

                if body.status == "dispatching":
                    fields.append("dispatching_at=COALESCE(dispatching_at, NOW())")
                elif body.status == "sent":
                    fields.append("sent_at=COALESCE(sent_at, NOW())")
                    fields.append("error=NULL")
                elif body.status == "delivered":
                    fields.append("sent_at=COALESCE(sent_at, NOW())")
                    fields.append("delivered_at=COALESCE(delivered_at, NOW())")
                    fields.append("error=NULL")
                elif body.status == "failed":
                    fields.append("failed_at=NOW()")
                    fields.append("error=%s")
                    values.append(body.error or "SMS send failed")

                values.append(job_id)
                cur.execute(
                    f"UPDATE sms_jobs SET {', '.join(fields)} WHERE id=%s RETURNING status",
                    tuple(values),
                )
                new_row = cur.fetchone()

    return {"ok": True, "status": new_row["status"]}


# NATIVE_SMS_V2_SEPARATE_QUEUE
# This API deliberately never consumes or retries old sms_jobs.
# One outstanding attempt across the dedicated queue; failed/uncertain hold
# the entire queue until an operator investigates.
from pydantic import BaseModel as _NModel, Field as _NField
from fastapi import Body as _NBody

NATIVE_DDL = """
CREATE TABLE IF NOT EXISTS native_sms_v2_jobs (
 id BIGSERIAL PRIMARY KEY,
 phone VARCHAR(11) NOT NULL, message TEXT NOT NULL,
 source VARCHAR(12) NOT NULL,
 cycle_key VARCHAR(32),
 account_ids INTEGER[] NOT NULL DEFAULT '{}',
 status VARCHAR(24) NOT NULL DEFAULT 'queued',
 device_id VARCHAR(128),
 parts INTEGER,
 result_code INTEGER,
 error TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 claimed_at TIMESTAMPTZ,
 started_at TIMESTAMPTZ,
 sent_at TIMESTAMPTZ,
 delivered_at TIMESTAMPTZ,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS native_sms_one_debt_cycle_v2
 ON native_sms_v2_jobs (phone,cycle_key) WHERE source='debt';
CREATE INDEX IF NOT EXISTS native_sms_v2_queue_idx ON native_sms_v2_jobs(status,id);
"""

class NativeStatus(_NModel):
    device_id: str = _NField(min_length=1,max_length=128)
    status: str
    parts: int = _NField(default=0,ge=0,le=30)
    result_code: int = 0
    error: str = _NField(default="", max_length=300)


def _native_setup(cursor):
    cursor.execute(NATIVE_DDL)


def _native_require(token):
    require_token(token)


@app.get("/v2/health")
def native_health(x_sms_gateway_token: str = Header(default="")):
    _native_require(x_sms_gateway_token)
    return {"ok": True, "engine": "native_sms_v2_separate_queue"}


@app.get("/v2/jobs/next")
def native_next(device_id: str, test_phone: str = "", x_sms_gateway_token: str = Header(default="")):
    _native_require(x_sms_gateway_token)
    device_id = (device_id or "").strip()
    if not 1 <= len(device_id) <= 128:
        raise HTTPException(status_code=400, detail="device_id")
    # Release is intentionally test-only: filter on the server BEFORE claiming.
    # Older clients without test_phone are rejected rather than consuming jobs.
    import re
    if not re.fullmatch(r"09[0-9]{9}", test_phone or ""):
        raise HTTPException(status_code=400, detail="valid test_phone required")
    with db_conn() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                _native_setup(cur)
                # Do not reclaim a timed-out claim or an attempted SMS. A
                # callback could arrive late and duplicate SMS is unacceptable.
                cur.execute("""
                  WITH next AS (
                    SELECT id FROM native_sms_v2_jobs
                    WHERE status='queued' AND phone=%s AND source='manual'
                      AND NOT EXISTS (
                        SELECT 1 FROM native_sms_v2_jobs
                        WHERE status IN ('claimed','attempting','failed','uncertain')
                      )
                      AND NOT EXISTS (
                        SELECT 1 FROM native_sms_v2_jobs
                        WHERE sent_at > NOW() - INTERVAL '90 seconds'
                      )
                    ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1
                  )
                  UPDATE native_sms_v2_jobs j SET status='claimed',
                   claimed_at=NOW(), device_id=%s,updated_at=NOW()
                  FROM next WHERE j.id=next.id
                  RETURNING j.id,j.phone,j.message
                """, (test_phone, device_id))
                row=cur.fetchone()
    return dict(row) if row else Response(status_code=204)


@app.post("/v2/jobs/{job_id}/start")
def native_start(job_id: int, body: NativeStatus,
                 x_sms_gateway_token: str=Header(default="")):
    _native_require(x_sms_gateway_token)
    if body.status != "attempting":
        raise HTTPException(400, "invalid start status")
    with db_conn() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                _native_setup(cur)
                cur.execute("""
                   UPDATE native_sms_v2_jobs
                   SET status='attempting',started_at=NOW(),updated_at=NOW(),
                       parts=%s
                   WHERE id=%s AND status='claimed' AND device_id=%s
                   RETURNING id
                """,(body.parts,job_id,body.device_id))
                row=cur.fetchone()
    if not row:
        raise HTTPException(409,"start rejected; no retry")
    return {"ok":True}


@app.post("/v2/jobs/{job_id}/report")
def native_report(job_id: int, body: NativeStatus,
                  x_sms_gateway_token: str=Header(default="")):
    _native_require(x_sms_gateway_token)
    if body.status not in ("sent","delivered","failed","uncertain"):
        raise HTTPException(400,"invalid result status")
    with db_conn() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                _native_setup(cur)
                cur.execute("""
                  SELECT id,phone,source,account_ids,status,device_id
                  FROM native_sms_v2_jobs WHERE id=%s FOR UPDATE
                """,(job_id,))
                row=cur.fetchone()
                if not row or row["device_id"] != body.device_id:
                    raise HTTPException(409,"unknown job or device")
                current=row["status"]
                if current == body.status:
                    return {"ok":True,"status":current,"duplicate":True}
                allowed = (current=="attempting" and
                           body.status in ("sent","failed","uncertain")) or (
                           current=="sent" and body.status=="delivered")
                if not allowed:
                    raise HTTPException(409,"transition not permitted; no retry")
                cur.execute("""
                  UPDATE native_sms_v2_jobs
                  SET status=%s,updated_at=NOW(),result_code=%s,error=%s,
                      sent_at=CASE WHEN %s IN ('sent','delivered')
                           THEN COALESCE(sent_at,NOW()) ELSE sent_at END,
                      delivered_at=CASE WHEN %s='delivered'
                           THEN NOW() ELSE delivered_at END
                  WHERE id=%s
                """,(body.status,body.result_code,body.error,
                     body.status,body.status,job_id))
                moved=0
                if body.status=="sent" and row["source"]=="debt":
                    # Only accounts pinned when the operator pressed Send;
                    # additionally guard against concurrent payment/archive.
                    for sid in row["account_ids"]:
                        cur.execute("""
                          SELECT id,phone,is_free,expiry_date
                          FROM subscriptions WHERE id=%s FOR UPDATE
                        """,(int(sid),))
                        sub=cur.fetchone()
                        if not sub or sub["phone"]!=row["phone"] or sub["is_free"]:
                            continue
                        cur.execute("""
                          SELECT kind FROM audit_events
                          WHERE kind IN ('followup_waiting','followup_cut','followup_clear')
                            AND message LIKE %s
                          ORDER BY id DESC LIMIT 1
                        """,(f"sid={int(sid)};%",))
                        ev=cur.fetchone()
                        if ev and ev["kind"] in ("followup_waiting","followup_cut"):
                            continue
                        # expiry at send time is rechecked; do not move accounts
                        # already extended by payment while this SMS was sending.
                        from datetime import date as _date
                        if sub["expiry_date"] is None or sub["expiry_date"] > _date.today():
                            continue
                        cur.execute("""
                          INSERT INTO audit_events(kind,message,created_at)
                          VALUES ('followup_waiting',%s,NOW())
                        """,(f"sid={int(sid)}; native SMS v2 sent; job={job_id}; "
                             "not a delivery receipt",))
                        moved+=1
                cur.execute("""
                  INSERT INTO audit_events(kind,message,created_at)
                  VALUES ('native_sms_v2_status',%s,NOW())
                """,(f"job={job_id}; status={body.status}; code={body.result_code}; "
                     f"moved={moved}",))
    return {"ok":True,"status":body.status,"moved":moved,
            "delivery_confirmed":body.status=="delivered"}


# GOOGLE_MESSAGES_MANUAL_HANDOFF_V1
# Uses only native_sms_v2_jobs, never the legacy sms_jobs or modem APIs.
# Claim is for showing a compose draft, NOT evidence of carrier submission.
@app.get("/v3/drafts/next")
def next_manual_draft(device_id: str, x_sms_gateway_token: str = Header(default="")):
    require_token(x_sms_gateway_token)
    if not (device_id and 1 <= len(device_id) <= 128):
        raise HTTPException(400, "device_id required")
    with db_conn() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                _native_setup(cur)
                cur.execute("""
                WITH picked AS (
                  SELECT id FROM native_sms_v2_jobs
                  WHERE status='queued'
                  ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1
                )
                UPDATE native_sms_v2_jobs j
                   SET status='claimed',device_id=%s,claimed_at=NOW(),updated_at=NOW()
                  FROM picked WHERE j.id=picked.id
                RETURNING j.id,j.phone,j.message
                """,(device_id,))
                row=cur.fetchone()
    return dict(row) if row else Response(status_code=204)


class ManualDraftResult(_NModel):
    device_id: str = _NField(min_length=1,max_length=128)


@app.post("/v3/drafts/{job_id}/opened")
def manual_draft_opened(job_id: int, body: ManualDraftResult,
                        x_sms_gateway_token: str = Header(default="")):
    require_token(x_sms_gateway_token)
    with db_conn() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                _native_setup(cur)
                cur.execute("""
                UPDATE native_sms_v2_jobs
                SET status='opened',updated_at=NOW()
                WHERE id=%s AND device_id=%s AND status='claimed'
                RETURNING id
                """,(job_id,body.device_id))
                matched=cur.fetchone()
    if not matched:
        raise HTTPException(409,"draft already opened or not owned by device")
    return {"ok":True,"status":"opened","sent":False,"delivered":False}


# GOOGLE_MESSAGES_SENT_FOLDER_V1
# The companion Android app reports only a verified matching entry in
# Telephony.Sms.Sent; opening the compose intent never calls this endpoint.
# The sent folder is not a recipient delivery receipt.
@app.post("/v3/drafts/{job_id}/verified-sent")
def manual_draft_verified_sent(job_id: int, body: ManualDraftResult,
                               x_sms_gateway_token: str = Header(default="")):
    require_token(x_sms_gateway_token)
    if job_id<=0:
        raise HTTPException(400,"invalid job")
    with db_conn() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                _native_setup(cur)
                cur.execute("""
                  SELECT id,phone,source,account_ids,status,device_id
                  FROM native_sms_v2_jobs WHERE id=%s FOR UPDATE
                """,(job_id,))
                row=cur.fetchone()
                if not row or row["device_id"]!=body.device_id:
                    raise HTTPException(409,"unknown job/device")
                if row["status"]=="sent":
                    return {"ok":True,"status":"sent","duplicate":True,"moved":0}
                if row["status"] not in ("claimed","opened"):
                    raise HTTPException(409,"not an open manual draft")
                cur.execute("""
                  UPDATE native_sms_v2_jobs
                  SET status='sent',sent_at=COALESCE(sent_at,NOW()),
                      updated_at=NOW(),error=NULL
                  WHERE id=%s
                """,(job_id,))
                moved=0
                if row["source"]=="debt":
                    # Never transition accounts that were paid, archived, or
                    # already advanced while the compose window was open.
                    from datetime import date as _date
                    for sid in row["account_ids"]:
                        cur.execute("""
                          SELECT id,phone,is_free,expiry_date
                          FROM subscriptions WHERE id=%s FOR UPDATE
                        """,(int(sid),))
                        sub=cur.fetchone()
                        if (not sub or sub["phone"]!=row["phone"] or
                            sub["is_free"] or sub["expiry_date"] is None or
                            sub["expiry_date"] > _date.today()):
                            continue
                        cur.execute("""
                          SELECT kind FROM audit_events
                          WHERE kind IN ('followup_waiting','followup_cut','followup_clear')
                            AND message LIKE %s
                          ORDER BY id DESC LIMIT 1
                        """,(f"sid={int(sid)};%",))
                        latest=cur.fetchone()
                        if latest and latest["kind"] in ("followup_waiting","followup_cut"):
                            continue
                        cur.execute("""
                          INSERT INTO audit_events(kind,message,created_at)
                          VALUES ('followup_waiting',%s,NOW())
                        """,(f"sid={int(sid)}; verified Google Messages sent-folder; "
                             f"job={job_id}; recipient delivery not confirmed",))
                        moved+=1
                cur.execute("""
                  INSERT INTO audit_events(kind,message,created_at)
                  VALUES ('sms_manual_sent_verified',%s,NOW())
                """,(f"job={job_id}; sent-folder confirmed; moved={moved}; "
                     "no receipt of delivery",))
    return {"ok":True,"status":"sent","moved":moved,
            "delivery_confirmed":False}


@app.post("/v3/drafts/{job_id}/cancel")
def manual_draft_cancel(job_id: int, body: ManualDraftResult,
                        x_sms_gateway_token: str = Header(default="")):
    require_token(x_sms_gateway_token)
    with db_conn() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                _native_setup(cur)
                cur.execute("""
                UPDATE native_sms_v2_jobs
                SET status='cancelled',updated_at=NOW()
                WHERE id=%s AND device_id=%s AND status IN ('claimed','opened')
                RETURNING id
                """,(job_id,body.device_id))
                matched=cur.fetchone()
    if not matched:
        raise HTTPException(409,"cannot cancel this draft")
    return {"ok":True,"status":"cancelled","sent":False}


# GOOGLE_MESSAGES_BATCH_OPEN_V4
# GET retrieves pending drafts without claiming them. Only explicit tap
# (not opening the app, syncing, or fetching the queue) changes followup.
# "operator_opened" means prepared in SMS composer, NOT sent/delivered.
from fastapi import Query as _batch_query

@app.get("/v4/drafts/pending")
def batch_pending_drafts(
    device_id: str,
    limit: int = _batch_query(default=200, ge=1, le=500),
    x_sms_gateway_token: str = Header(default=""),
):
    require_token(x_sms_gateway_token)
    if not 1 <= len(device_id or "") <= 128:
        raise HTTPException(status_code=400, detail="invalid device_id")
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, phone, message, source
                FROM native_sms_v2_jobs
                WHERE status='queued'
                   OR (status IN ('claimed','opened') AND device_id=%s)
                ORDER BY id ASC
                LIMIT %s
            """, (device_id, limit))
            rows=cur.fetchall()
            cur.execute("""
                SELECT COUNT(*) AS n FROM native_sms_v2_jobs
                WHERE status='queued'
                   OR (status IN ('claimed','opened') AND device_id=%s)
            """, (device_id,))
            total=int(cur.fetchone()["n"])
    return {
        "ok":True,"total":total,
        "drafts":[{"id":int(r["id"]),"phone":r["phone"],
                   "message":r["message"],"source":r["source"]} for r in rows]
    }


@app.post("/v4/drafts/{job_id}/operator-open")
def batch_operator_open(job_id: int, body: ManualDraftResult,
                        x_sms_gateway_token: str = Header(default="")):
    require_token(x_sms_gateway_token)
    if job_id<=0:
        raise HTTPException(status_code=400, detail="invalid job_id")
    with db_conn() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id,phone,source,account_ids,status,device_id
                    FROM native_sms_v2_jobs WHERE id=%s FOR UPDATE
                """,(job_id,))
                r=cur.fetchone()
                if not r:
                    raise HTTPException(status_code=404,detail="draft not found")
                # Idempotency of an operator click; no repeat audit or waiting.
                if r["status"]=="operator_opened" and r["device_id"]==body.device_id:
                    return {"ok":True,"status":"operator_opened","moved":0,"duplicate":True,
                            "sent_confirmed":False}
                allowed=r["status"]=="queued" or (
                    r["status"] in ("claimed","opened") and r["device_id"]==body.device_id
                )
                if not allowed:
                    raise HTTPException(status_code=409,detail="draft not available for device")
                cur.execute("""
                    UPDATE native_sms_v2_jobs
                       SET status='operator_opened', device_id=%s,
                           updated_at=NOW(), claimed_at=COALESCE(claimed_at,NOW())
                     WHERE id=%s
                """,(body.device_id,job_id))
                moved=0
                if r["source"]=="debt":
                    from datetime import date as _batch_date
                    # Apply only to subscriptions linked to this exact queued
                    # debt request, with the same guards as existing followup.
                    for sid in r["account_ids"]:
                        sid=int(sid)
                        cur.execute("""
                            SELECT id,phone,is_free,expiry_date
                            FROM subscriptions WHERE id=%s FOR UPDATE
                        """,(sid,))
                        sub=cur.fetchone()
                        if (not sub or sub["phone"]!=r["phone"] or
                            sub["is_free"] or sub["expiry_date"] is None or
                            sub["expiry_date"] > _batch_date.today()):
                            continue
                        cur.execute("""
                            SELECT kind FROM audit_events
                            WHERE kind IN ('followup_waiting','followup_cut','followup_clear')
                              AND message LIKE %s
                            ORDER BY id DESC LIMIT 1
                        """,(f"sid={sid};%",))
                        prev=cur.fetchone()
                        if prev and prev["kind"] in ("followup_waiting","followup_cut"):
                            continue
                        cur.execute("""
                            INSERT INTO audit_events(kind,message,created_at)
                            VALUES ('followup_waiting',%s,NOW())
                        """,(f"sid={sid}; Google Messages opened by operator; "
                             f"job={job_id}; SMS send not verified",))
                        moved+=1
                cur.execute("""
                    INSERT INTO audit_events(kind,message,created_at)
                    VALUES ('sms_manual_operator_open',%s,NOW())
                """,(f"job={job_id}; source={r['source']}; moved={moved}; "
                     "Google Messages composer opened; no proof of sending",))
    return {"ok":True,"status":"operator_opened","moved":moved,
            "sent_confirmed":False,"duplicate":False}
