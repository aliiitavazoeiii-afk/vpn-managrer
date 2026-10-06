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
