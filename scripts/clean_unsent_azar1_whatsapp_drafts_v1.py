#!/usr/bin/env python3
"""HESAB_AZAR1_UNSENT_DRAFT_QUEUE_CLEAN_V1

One-time, narrowly scoped cancel of previously prepared OLD Azar 1 renewal
drafts that remain status='queued' in native_sms_v2_jobs.
No rows deleted, no messages sent, no payment/followup/customer changes.

Reject any matching claimed/opened draft as potentially already submitted.
Never touch sent, delivered, operator_opened, failed or uncertain evidence.
Never clear unrelated drafts or the operator-approved NEW exact text.

--check is read-only; --apply requires verified PostgreSQL pg_dump backup.
"""
import argparse
import ast
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path("/opt/vpn-control-center")
BACK=Path("/opt/hesab-backups")
COMPOSE=["docker","compose","-f","docker-compose.yml","-f","docker-compose.sms.yml"]

NEW=(
    "سلام، امروز اکانت شما تموم می‌شه.\n\n"
    "تا ساعت ۱۸ امروز برای پرداخت فرصت هست و بعد از این ساعت، اکانت شما قطع خواهد شد.\n\n"
    "امکان پرداخت تا ساعت ۱۲ ظهر روز ۲ آذر وجود داره و بعد از اون اکانت های پرداخت نشده حذف خواهد شد.\n\n"
    "اکانت شما به محض پرداخت مجدداً متصل خواهد شد.\n\n"
    "usersmanager.ir"
)
OLD_MESSAGES=(
    (
        "سلام امروز موعد تمدید اکانت شماست\n"
        "لطفا برای تمدید وارد پنل کاربری خودتون بشید و نسبت به پرداخت اقدام فرمایید\n\n"
        " ساعت 10 شب اکانت هایی که پرداخت نداشتن مسدود خواهند شد و تا فردا همچنان امکان پرداخت هست.فردا ساعت 12 ظهر اکانت های پرداخت نشده حذف خواهند شد.\n\n"
        "فعال یا غیرفعال شدن اکانت ها سیستمی بوده و امکان فعال سازی اکانت بدون واریز ممکن نیست\n\n"
        "usersmanager.ir"
    ),
    (
        "سلام، امروز اکانت شما تموم می‌شه.\n\n"
        "تا ساعت ۱۸ امروز برای پرداخت فرصت دارید و بعد از این ساعت، اکانت شما قطع خواهد شد.\n\n"
        "امکان پرداخت تا ساعت ۱۲ ظهر روز ۲ آذر وجود داره و بعد از اون اکانت شما حذف خواهد شد.\n\n"
        "اکانت شما به محض پرداخت مجدداً متصل خواهد شد.\n\n"
        "usersmanager.ir"
    ),
)

def stop(message):
    raise RuntimeError(message)

def run(cmd, input_data=None, timeout=120):
    proc=subprocess.run(cmd,cwd=ROOT,input=input_data,text=True,
                        stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        timeout=timeout)
    if proc.returncode:
        stop("POSTGRES_OPERATION_FAILED: "+(proc.stderr or "")[-320:])
    return proc.stdout.strip()

def psql(sql):
    return run(COMPOSE+["exec","-T","db","sh","-lc",
        'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -q -At -v ON_ERROR_STOP=1 '
        '-U "$POSTGRES_USER" -d "$POSTGRES_DB"'],sql)

def db_literal(message):
    # Hex avoids escaping/untrusted SQL interpolation and preserves Persian.
    return "convert_from(decode('"+message.encode("utf8").hex()+"','hex'),'UTF8')"

OLD="("+",".join(db_literal(v) for v in OLD_MESSAGES)+")"
NEW_SQL=db_literal(NEW)

def backing_up():
    BACK.mkdir(parents=True,exist_ok=True)
    directory=BACK/("azar1-unsent-drafts-"+datetime.now(
        ZoneInfo("Asia/Tehran")).strftime("%Y%m%d-%H%M%S")+"-"+str(os.getpid()))
    directory.mkdir(mode=0o700)
    file=directory/"postgres-before-queue-clean.dump"
    with file.open("xb") as handle:
        os.chmod(file,0o600)
        result=subprocess.run(COMPOSE+["exec","-T","db","sh","-lc",
           'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" '
           '-d "$POSTGRES_DB" -Fc'],
           cwd=ROOT,stdout=handle,stderr=subprocess.PIPE,timeout=240)
    if result.returncode!=0 or file.stat().st_size<1024:
        stop("BACKUP_INCOMPLETE: NO_CHANGES")
    with file.open("rb") as handle:
        if handle.read(5)!=b"PGDMP":
            stop("INVALID_POSTGRES_BACKUP_HEADER")
    # Inspect archive inside the container, never run a restore.
    container_file="/tmp/hesab-azar1-clean-verify-"+str(os.getpid())+".dump"
    try:
        run(COMPOSE+["cp",str(file),"db:"+container_file],timeout=120)
        out=run(COMPOSE+["exec","-T","-u","0","db","pg_restore",
                         "--list",container_file],timeout=90)
        if "TABLE" not in out:stop("PG_RESTORE_LIST_VERIFICATION_FAILED")
    finally:
        subprocess.run(COMPOSE+["exec","-T","-u","0","db","rm","-f",container_file],
                       cwd=ROOT,capture_output=True,timeout=30)
    print("VERIFIED_DATABASE_BACKUP="+str(file),flush=True)

def verify_runtime():
    path=ROOT/"patches/sms_aban_default.py"
    if not path.is_file() or path.is_symlink():
        stop("MISSING_LIVE_CANONICAL_MESSAGE")
    doc=ast.parse(path.read_text(encoding="utf8"))
    found=[n for n in doc.body if isinstance(n,ast.Assign) and
           len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and
           n.targets[0].id=="_ABAN_SMS_PATTERN"]
    if len(found)!=1 or ast.literal_eval(found[0].value)!=NEW:
        stop("NEW_DEBT_MESSAGE_NOT_INSTALLED: run Azar1 text installer first")
    code=(
        "from app.main import _ABAN_SMS_PATTERN\n"
        "assert _ABAN_SMS_PATTERN=="+
        repr(NEW)+"\n"
        "print('RUNNING_MESSAGE_IS_EXACT=YES')\n"
    )
    output=run(COMPOSE+["exec","-T","app","python3","-c",code])
    print(output)

def status():
    sql=(
       "SELECT status,COUNT(*) FROM native_sms_v2_jobs "
       "WHERE message IN "+OLD+" AND status IN "
       "('queued','claimed','opened','operator_opened','sent','delivered',"
       "'failed','uncertain','cancelled') GROUP BY status ORDER BY status;"
    )
    print("PREVIOUS_APPROVED_TEXT_COUNTS_BY_STATUS")
    print(psql(sql) or "(none)",flush=True)
    sql2=(
      "SELECT "
      "COUNT(*) FILTER (WHERE status='queued' AND message IN "+OLD+"),"
      "COUNT(*) FILTER (WHERE status IN ('claimed','opened') AND message IN "+OLD+"),"
      "COUNT(*) FILTER (WHERE status='queued' AND message="+NEW_SQL+"),"
      "COUNT(*) FILTER (WHERE status IN ('queued','claimed','opened') AND "
      "message NOT IN "+OLD+" AND message<>"+NEW_SQL+") "
      "FROM native_sms_v2_jobs;"
    )
    row=psql(sql2)
    try:
        oldq,review,newq,other=(int(v) for v in row.split("|"))
    except Exception as exc:
        raise ValueError("invalid status report") from exc
    print("OLD_QUEUED="+str(oldq))
    print("OLD_CLAIMED_OR_OPENED_NEEDS_REVIEW="+str(review))
    print("NEW_TEXT_ALREADY_QUEUED="+str(newq))
    print("UNRELATED_VISIBLE_PENDING="+str(other))
    return oldq,review,newq,other

def main():
    if os.geteuid()!=0 or not (ROOT/"docker-compose.sms.yml").is_file():
        stop("ROOT_ON_HESAB_MANAGEMENT_HOST_REQUIRED")
    a=argparse.ArgumentParser()
    modes=a.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check",action="store_true")
    modes.add_argument("--apply",action="store_true")
    opts=a.parse_args()
    now=datetime.now(ZoneInfo("Asia/Tehran"))
    if now.date().isoformat()!="2026-11-22":
        stop("AZAR1_RENEWAL_TEXT_NOT_VALID_ON_THIS_TEHRAN_DATE")
    if len(OLD_MESSAGES)!=2 or NEW in OLD_MESSAGES:
        stop("UNEXPECTED_TARGET_MESSAGES")
    verify_runtime()
    oldq,review,newq,other=status()
    if opts.check:
        print("DRY_RUN=COMPLETE NO_RECORDS_CHANGED")
        print("WILL_CANCEL_ONLY_OLD_QUEUED="+str(oldq))
        if review:
            print("WARNING=CLAIMED_OR_OPENED_ROWS_REQUIRE_MANUAL_DELIVERY_REVIEW")
        return
    if review:
        stop("OLD_DRAFT_CLAIMED_OR_OPENED: manually verify actual delivery before resetting; NO_CHANGES")
    if newq:
        stop("NEW_APPROVED_DRAFT_ALREADY_QUEUED: inspect before requeue; NO_CHANGES")
    if other:
        stop("UNRELATED_PENDING_DRAFTS_EXIST: refusing to claim app fully clean; NO_CHANGES")
    if oldq==0:
        print("NO_OLD_PENDING_DRAFTS=YES")
        return
    backing_up()
    statement=(
      "BEGIN;\n"
      "SET LOCAL lock_timeout='5s';\n"
      "DO $cleanup$ BEGIN\n"
      "IF EXISTS (SELECT 1 FROM native_sms_v2_jobs WHERE status IN "
      "('claimed','opened') AND message IN "+OLD+") THEN\n"
      "RAISE EXCEPTION 'CLAIMED_OR_OPENED_ROW_CHANGED';\nEND IF;\n"
      "IF EXISTS (SELECT 1 FROM native_sms_v2_jobs WHERE status='queued' AND "
      "message="+NEW_SQL+") THEN\n"
      "RAISE EXCEPTION 'NEW_APPROVED_DRAFT_ALREADY_QUEUED';\nEND IF;\n"
      "END $cleanup$;\n"
      "WITH old_drafts AS (\n"
      "UPDATE native_sms_v2_jobs SET status='cancelled', "
      "error='Old Azar1 renewal draft cancelled by operator; not sent by app',"
      "updated_at=NOW()\n"
      "WHERE status='queued' AND message IN "+OLD+"\n"
      "RETURNING id),\n"
      "logged AS (INSERT INTO audit_events(kind,message,created_at)\n"
      "SELECT 'azar1_unsent_draft_cancel',"
      "'Operator explicitly cancelled old unsent Azar1 drafts; count='||"
      "(SELECT COUNT(*) FROM old_drafts)||"
      "'; no WhatsApp send; no customer/followup/payment edits',NOW() "
      "RETURNING id)\n"
      "SELECT 'CANCELLED_OLD_UNSENT='||(SELECT COUNT(*) FROM old_drafts),"
      "(SELECT COUNT(*) FROM logged);\nCOMMIT;"
    )
    print(psql(statement),flush=True)
    after=status()
    if after[0]!=0:
        stop("RACE: NEW OLD DRAFTS QUEUED DURING CLEANUP; inspect before proceeding")
    print("SUCCESS=OLD_UNSENT_AZAR1_DRAFTS_CANCELLED")
    print("SEND_OR_FINANCE_OR_FOLLOWUP_ACTION=NO")
    print("WHATSAPP_PENDING_LIST_CLEARS_ON_REFRESH")

if __name__=="__main__":
    try:
        main()
    except Exception as e:
        print("AZAR1_QUEUE_CLEAN_STOP",type(e).__name__,str(e)[:280],file=sys.stderr)
        sys.exit(1)
