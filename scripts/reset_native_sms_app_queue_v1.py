#!/usr/bin/env python3
"""HESAB_NATIVE_SMS_APP_QUEUE_RESET_V1

Explicit one-time operator cleanup of the SERVER queue shown in Android V4 app.
- queued -> cancelled (unsent)
- claimed/opened -> uncertain (never presume unsent; requires manual review)
- operator_opened/sent/delivered/failed/cancelled/uncertain remain unchanged.
No row is deleted; no SMS is transmitted. No finance/followup/account changes.
Makes full PostgreSQL pg_dump before the write. Requires --apply.
"""
import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE=Path("/opt/vpn-control-center")
BACK=Path("/opt/hesab-backups")
COMPOSE=["docker","compose","-f","docker-compose.yml","-f","docker-compose.sms.yml"]
PSQL=['sh','-lc','PGPASSWORD="$POSTGRES_PASSWORD" psql -X -q -At -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"']
PGDUMP=['sh','-lc','PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc']

def command(service,args,input_data=None,timeout=100):
    p=subprocess.run(COMPOSE+["exec","-T",service]+args,cwd=BASE,text=True,
                     input=input_data,capture_output=True,timeout=timeout)
    if p.returncode:
        raise RuntimeError("DB read or commit failed; no further actions. "+
                           (p.stderr or "")[-300:])
    return p.stdout.strip()

def psql(sql):
    return command("db",PSQL,sql)

def backup():
    BACK.mkdir(parents=True,exist_ok=True)
    directory=BACK/("sms-app-queue-"+datetime.now().strftime("%Y%m%d-%H%M%S")+"-"+str(os.getpid()))
    directory.mkdir(mode=0o700)
    path=directory/"postgres-before-queue-clear.dump"
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"wb") as f:
        p=subprocess.run(COMPOSE+["exec","-T","db"]+PGDUMP,cwd=BASE,
                         stdout=f,stderr=subprocess.PIPE,timeout=210)
    if p.returncode or path.stat().st_size<1024:
        raise RuntimeError("PostgreSQL backup was incomplete; no queue changes.")
    with path.open("rb") as f:
        if f.read(5)!=b"PGDMP":
            raise RuntimeError("Unrecognized PostgreSQL dump header")
        f.seek(0)
        test=subprocess.run(COMPOSE+["exec","-T","db","pg_restore","-l"],
                            cwd=BASE,stdin=f,stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE,timeout=100)
    if test.returncode:raise RuntimeError("pg_restore could not list backup")
    print("DB_BACKUP:",path)
    return path

def main():
    if os.geteuid()!=0:raise RuntimeError("Must run as root on Hesab admin server")
    a=argparse.ArgumentParser()
    a.add_argument("--apply",action="store_true",help="explicitly cancel/flag current Android queue")
    opt=a.parse_args()
    if not (BASE/"docker-compose.sms.yml").is_file():
        raise RuntimeError("Hesab production compose not found")
    print("APP QUEUE RESET V1 — no deletion, only status updates",flush=True)
    current=psql("SELECT status,COUNT(*) FROM native_sms_v2_jobs GROUP BY status ORDER BY status;")
    print("BEFORE (state|count):\n"+(current or "(empty)"))
    # A single transaction with a minimal lock timeout, retaining full history.
    if not opt.apply:
        print("CHECK ONLY: to clear the Android V4 pending list, use --apply")
        return
    backup()
    sql="""
BEGIN;
SET LOCAL lock_timeout='5s';
WITH changed AS (
  UPDATE native_sms_v2_jobs
  SET status=CASE WHEN status='queued' THEN 'cancelled' ELSE 'uncertain' END,
      error=CASE WHEN status='queued'
                THEN 'Operator cleared unsent app queue; no SMS send'
                ELSE 'Operator cleared app queue; delivery unverified, review before retry' END,
      updated_at=NOW()
  WHERE status IN ('queued','claimed','opened')
  RETURNING status
), tally AS (
  SELECT COUNT(*) FILTER (WHERE status='cancelled') AS cancelled,
         COUNT(*) FILTER (WHERE status='uncertain') AS quarantined
  FROM changed
), audit AS (
  INSERT INTO audit_events(kind,message,created_at)
  SELECT 'sms_app_queue_clear',
         'Operator requested app queue reset; cancelled='||cancelled||
         '; uncertain='||quarantined||
         '; no SMS sent or deleted; payment and followup unchanged',
         NOW()
  FROM tally
  RETURNING id
)
SELECT 'APPLIED cancelled='||tally.cancelled||
       ' quarantined='||tally.quarantined||
       ' audit='||(SELECT COUNT(*) FROM audit)
FROM tally;
COMMIT;
"""
    result=psql(sql)
    print(result)
    final=psql("SELECT COUNT(*) FROM native_sms_v2_jobs WHERE status IN ('queued','claimed','opened');")
    print("PENDING_VISIBLE_APP_ROWS:",final)
    if final!="0":
        raise RuntimeError("New live drafts appeared during cleanup; inspect before repeating")
    print("SUCCESS: SERVER APP DRAFT QUEUE CLEARED")
    print("All previously sent/opened/uncertain history preserved; no finance, XUI or Shahan changes.")
    print("Android local pending acknowledgement may still need inspection if it existed.")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("QUEUE_RESET_STOP:",type(exc).__name__,str(exc)[:300],file=sys.stderr)
        sys.exit(1)
